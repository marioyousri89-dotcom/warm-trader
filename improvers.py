"""The 10 improver agents. They do not trade. They audit everyone else and change the system:
retire weak agents, clone and mutate strong ones, tune thresholds and risk (inside hard bounds),
write lessons into the shared brain, and (with an API key) let Claude reflect on the numbers."""
import json

from agents import GROUPS, mutate, pname
from strategies import mean

PREFIX = {g: p for g, p, _ in GROUPS}


class Improvers:
    def __init__(self, eng):
        self.e = eng
        self.review_no = 0

    def run(self, cycle):
        self.review_no += 1
        for a in self.e.swarm.active("improver"):
            if a["lens"] == "capital_allocator":      # runs hourly, called by the desk manager
                continue
            fn = getattr(self, a["lens"], None)
            if fn:
                fn(cycle)

    def run_one(self, lens, cycle):
        if any(a["lens"] == lens for a in self.e.swarm.active("improver")):
            getattr(self, lens)(cycle)

    # ---------- helpers ----------
    def _closed(self, n=40):
        """Recent closed trades, excluding the pure copy-mirror desks (their results don't depend on our settings)."""
        skip = {a["name"] for a in self.e.swarm.agents.values()
                if a["grp"] == "desk" and a["params"].get("style") in ("copy_trader", "copy_desk")}
        rows = self.e.b.q("SELECT * FROM trades WHERE status='closed' ORDER BY id DESC LIMIT ?", (n * 3,))
        return [t for t in rows if t["desk"] not in skip][:n]

    # ---------- 13. session analyst: does the system make money in Asia / London / New York, or only lose there? ----------
    def session_analyst(self, cycle):
        e = self.e
        if cycle % 20:
            return
        agg = {}
        for t in self._closed(300):
            s = e.port.sess_of.get(t["id"])
            if s:
                agg.setdefault(s, []).append(t["pnl"])
        out, notes = {}, []
        for s, v in agg.items():
            n = len(v)
            m, sd = mean(v), (sum((x - mean(v)) ** 2 for x in v) / max(1, n - 1)) ** 0.5
            t = m / (sd / n ** 0.5) if sd and n > 1 else 0.0
            target = 1.0
            if n >= 25 and t < -1.5:
                target = 0.6                                  # lose money here: trade smaller
            elif n >= 25 and t > 1.5:
                target = 1.15                                 # genuinely profitable here: a little more
            out[s] = round(0.6 * e.session_mult.get(s, 1.0) + 0.4 * target, 3)
            notes.append(f"{s} {n} trades avg {m:+.2f} (t={t:+.1f})")
        if out:
            e.session_mult.update(out)
            e.b.kv_set("session_mult", e.session_mult)
            e.b.kv_set("session_stats", {s: {"n": len(v), "avg": round(mean(v), 3)} for s, v in agg.items()})
            self._lesson(cycle, "session_analyst", "Sessions: " + "; ".join(notes) + f". Size multipliers: {e.session_mult}", always=False)

    # ---------- 12. development team: post-mortems, then written engineering proposals ----------
    def dev_postmortem(self, cycle):
        """Looks at every losing trade, finds WHERE the losses cluster, and records it. Pure statistics, no model needed."""
        if cycle % 40:
            return
        rows = self._closed(120)
        losers = [t for t in rows if t["pnl"] < 0]
        if len(rows) < 30 or not losers:
            return
        def top(key):
            agg = {}
            for t in rows:
                k = str(t.get(key))
                a = agg.setdefault(k, [0, 0.0, 0])
                a[0] += 1
                a[1] += t["pnl"]
                a[2] += t["pnl"] < 0
            worst = min(agg.items(), key=lambda kv: kv[1][1])
            return worst[0], worst[1]
        findings = []
        for key in ("desk", "regime", "symbol"):
            k, (n, pnl, lost) = top(key)
            if n >= 10 and pnl < 0:
                findings.append(f"worst {key}: {k} ({n} trades, {pnl:+.1f}, {lost} lost)")
        by_exit = {"stop": 0, "time": 0, "target": 0}
        for t in losers:
            ex = "stop" if "exit: stop" in t["reason"] else "time" if "exit: time" in t["reason"] else "target"
            by_exit[ex] += 1
        findings.append(f"{len(losers)}/{len(rows)} recent trades lost; exits of losers: {by_exit}")
        self.e.b.kv_set("dev_findings", {"cycle": cycle, "items": findings})
        self._lesson(cycle, "dev_postmortem", "Post-mortem: " + "; ".join(findings), always=False)

    def dev_engineer(self, cycle):
        """Claude turns the post-mortem into written proposals. NOTHING is applied automatically except the bounded
        settings the reflector already tunes: code/structure changes wait for the owner to approve."""
        e = self.e
        if not e.llm.on or cycle % 120:
            return
        f = e.b.kv_get("dev_findings")
        if not f:
            return
        system = ("You are the lead engineer of a paper-trading multi-agent system. You get a post-mortem of recent losses. "
                  "Propose at most 3 concrete, testable changes to the system (a rule, a filter, an agent to add or retire, "
                  "a data source). Be statistically sceptical: say what evidence would confirm each. Reply ONLY with JSON: "
                  '{"proposals": [{"title": "<=10 words", "change": "<=40 words", "test": "<=25 words"}]}')
        out = e.llm.ask_json(system, json.dumps({"post_mortem": f, "scorecard": e.b.kv_get("graduation")}), max_tokens=700)
        if not out:
            return
        old = e.b.kv_get("dev_proposals") or []
        new = [{"cycle": cycle, "status": "pending owner review", **{k: str(p.get(k, ""))[:300] for k in ("title", "change", "test")}}
               for p in (out.get("proposals") or [])[:3] if isinstance(p, dict)]
        e.b.kv_set("dev_proposals", (new + old)[:20])

    # ---------- 11. hourly: move capital to the desks earning the most per hour ----------
    def capital_allocator(self, cycle):
        self.e.desks.rebalance(cycle)

    def _lesson(self, cycle, author, text, always=True):
        if always or self.review_no % 5 == 0:
            self.e.b.add_lesson(cycle, author, text)

    # ---------- 1. retire agents that are worse than a coin flip ----------
    def accuracy_auditor(self, cycle):
        """Signals overlap in time (a breakout stays 'on' for several candles), so n calls are worth only
        about n/3 independent samples. Retire only when accuracy is significantly below 50% on that basis."""
        sw = self.e.swarm
        for grp in ("scout", "predictor", "copy"):
            for a in sorted(sw.active(grp), key=lambda x: x["acc"]):
                if len(sw.active(grp)) <= 8:
                    break
                if a["n"] < 45 or cycle - a["born"] < 60:
                    continue
                limit = 0.5 - 1.64 * 0.5 / (max(1.0, a["n"] / 3) ** 0.5)
                if a["acc"] < limit:
                    a["active"] = 0
                    sw.save(a)
                    self._lesson(cycle, "accuracy_auditor",
                                 f"Retired {a['name']}: {a['acc']:.0%} accuracy over {a['n']} signals, "
                                 f"significantly worse than a coin flip (cut-off {limit:.0%}).")

    # ---------- 2. replace retired agents with mutated clones of the best ----------
    def cloner(self, cycle):
        sw, b = self.e.swarm, self.e.b
        for grp in ("scout", "predictor", "copy"):
            target = b.kv_get(f"target_{grp}", 0)
            deficit = target - len(sw.active(grp))
            pool = [a for a in sw.active(grp) if a["n"] >= 20 and a["acc"] > 0.5] or \
                   [a for a in sw.active(grp) if a["n"] >= 20] or sw.active(grp)
            for _ in range(min(2, max(0, deficit))):
                if not pool:
                    break
                parent = max(pool, key=lambda x: x["acc"])
                seq = b.kv_get(f"seq_{grp}", target) + 1
                b.kv_set(f"seq_{grp}", seq)
                params = mutate(parent["params"], sw.rng)
                row = sw.add_agent(grp, pname(PREFIX[grp], seq, parent["lens"], params), parent["lens"], params,
                                   cycle, parent["name"])
                self._lesson(cycle, "cloner", f"Spawned {row['name']} as a mutation of {parent['name']} ({parent['acc']:.0%} accuracy).")

    # ---------- 3. decision threshold ----------
    def _fresh(self, key, n=40):
        """Closed trades that were opened AFTER this setting last changed (never judge a setting on old trades)."""
        since = self.e.tuned_at.get(key, 0)
        return [t for t in self._closed(n) if t["open_cycle"] > since]

    def threshold_tuner(self, cycle):
        cfg = self.e.cfg
        last = self._fresh("agg_threshold", 15)
        if len(last) >= 10:
            wr = sum(1 for t in last if t["pnl"] > 0) / len(last)
            total = sum(t["pnl"] for t in last)
            if wr < 0.40 and total < 0:
                self.e.apply_tunable("agg_threshold", cfg.agg_threshold + 0.02, "threshold_tuner",
                                     f"win rate {wr:.0%} and {total:+.0f} P/L over {len(last)} trades since the last change, getting pickier")
            elif wr > 0.60 and total > 0:
                self.e.apply_tunable("agg_threshold", cfg.agg_threshold - 0.01, "threshold_tuner",
                                     f"win rate {wr:.0%} and {total:+.0f} P/L, can afford more trades")
        recent = self.e.b.q("SELECT COUNT(*) n FROM trades WHERE open_cycle>?", (cycle - 80,))[0]["n"]
        if recent == 0:
            if cfg.agg_threshold > 0.15:
                self.e.apply_tunable("agg_threshold", cfg.agg_threshold - 0.01, "threshold_tuner",
                                     "no trades for 80 cycles, loosening slightly")
            if cfg.min_agents > 4:
                self.e.apply_tunable("min_agents", cfg.min_agents - 1, "threshold_tuner",
                                     "no trades for 80 cycles, requiring fewer agreeing agents")

    # ---------- 4. risk ----------
    def risk_auditor(self, cycle):
        cfg, port = self.e.cfg, self.e.port
        dd = port.drawdown(port.last_equity)
        base = self.e.base_risk
        if dd > 0.05:
            self.e.apply_tunable("risk_per_trade", cfg.risk_per_trade * 0.8, "risk_auditor",
                                 f"drawdown {dd:.1%}, cutting position risk")
        elif dd < 0.02 and cfg.risk_per_trade < base:
            self.e.apply_tunable("risk_per_trade", min(base, cfg.risk_per_trade * 1.1), "risk_auditor",
                                 "drawdown recovered, restoring risk")

    # ---------- 5. is copy-trading skill or luck? ----------
    def copy_auditor(self, cycle):
        stats = self.e.swarm.trader_stats(cycle)
        ranked = sorted(((t, s) for t, s in stats.items() if s["n"] >= 10), key=lambda x: -x[1]["wilson"])
        if ranked:
            t, s = ranked[0]
            z = (s["wr"] - 0.5) / (0.25 / s["n"]) ** 0.5
            # with ~12 traders watched, the best of them reaches z of about 1.6 by pure luck
            verdict = ("that is too strong to be luck, so copying is justified" if z > 3.5 else
                       "that is within what luck produces when you watch this many traders, so treat with suspicion")
            self._lesson(cycle, "copy_auditor",
                         f"Best copy target {t}: {s['wr']:.0%} wins over {s['n']} trades (z = {z:.1f}); {verdict}.",
                         always=False)

    # ---------- 6. which regime do we make money in? ----------
    def regime_analyst(self, cycle):
        by = {}
        for t in self._closed(80):
            by.setdefault(t["regime"] or "?", []).append(t["pnl"])
        parts = [f"{k}: {sum(1 for p in v if p > 0) / len(v):.0%} wins, {sum(v):+.0f} ({len(v)} trades)"
                 for k, v in by.items() if len(v) >= 4]
        if parts:
            self._lesson(cycle, "regime_analyst", "Results by regime, " + "; ".join(parts), always=False)

    # ---------- 7. are fees eating the edge? ----------
    def overtrading_auditor(self, cycle):
        last = self._fresh("min_agents", 30)
        if len(last) >= 15:
            fees = sum(t["fees"] for t in last)
            gross = sum(t["pnl"] + t["fees"] for t in last)
            if gross < fees and self.e.cfg.min_agents < 8:
                self.e.apply_tunable("min_agents", self.e.cfg.min_agents + 1, "overtrading_auditor",
                                     f"fees {fees:.0f} vs gross {gross:+.0f}; requiring more agents to agree")

    # ---------- 8. Claude reads the numbers and proposes changes ----------
    def claude_reflector(self, cycle):
        e = self.e
        if not e.llm.on:
            return
        sw = e.swarm
        groups = {}
        for g in ("scout", "predictor", "copy"):
            act = [a for a in sw.active(g) if a["n"] >= 10]
            groups[g] = {"active": len(sw.active(g)),
                         "avg_acc": round(mean([a["acc"] for a in act]), 3) if act else None,
                         "best": [(a["name"], round(a["acc"], 2), a["n"]) for a in sorted(act, key=lambda x: -x["acc"])[:3]],
                         "worst": [(a["name"], round(a["acc"], 2), a["n"]) for a in sorted(act, key=lambda x: x["acc"])[:3]]}
        trades = [{"sym": t["symbol"], "side": t["side"], "pnl": round(t["pnl"], 2), "regime": t["regime"],
                   "reason": t["reason"][:80]} for t in self._closed(20)]
        payload = {"cycle": cycle, "equity": round(e.port.last_equity, 2), "drawdown": round(e.port.drawdown(e.port.last_equity), 4),
                   "groups": groups, "recent_trades": trades,
                   "settings": {k: getattr(e.cfg, k) for k in ("agg_threshold", "min_agents", "llm_weight", "risk_per_trade")},
                   "allowed_bounds": {"agg_threshold": [0.10, 0.60], "min_agents": [2, 10], "llm_weight": [0.0, 0.70],
                                      "risk_per_trade": [0.0025, 0.02]},
                   "recent_lessons": [l["text"] for l in e.b.lessons(6)]}
        system = ("You are the Improvement Lead of a paper-trading multi-agent system. You get performance data and "
                  "must be statistically sceptical: small samples are noise, do not overreact. Reply ONLY with JSON: "
                  '{"lessons": [up to 3 short strings], "suggestions": [up to 2 objects {"key","value","reason"}]}. '
                  "Only use keys listed in allowed_bounds. Suggest nothing if the data does not justify a change.")
        out = e.llm.ask_json(system, json.dumps(payload), max_tokens=700)
        if not out:
            return
        for text in (out.get("lessons") or [])[:3]:
            if isinstance(text, str):
                e.b.add_lesson(cycle, "claude", text[:300])
        for s in (out.get("suggestions") or [])[:2]:
            try:
                if s.get("key") in ("agg_threshold", "min_agents", "llm_weight", "risk_per_trade"):
                    e.apply_tunable(s["key"], float(s["value"]), "claude", str(s.get("reason", ""))[:160])
            except Exception:
                continue

    # ---------- 9. find agents that just say the same thing ----------
    def diversity_auditor(self, cycle):
        rows = self.e.b.q("SELECT agent,cycle,symbol,direction FROM signals WHERE cycle>? AND kind IN ('scout','predict')",
                          (cycle - 60,))
        votes = {}
        for r in rows:
            votes.setdefault(r["agent"], {})[(r["cycle"], r["symbol"])] = r["direction"]
        names = [n for n, v in votes.items() if len(v) >= 30]
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = votes[names[i]], votes[names[j]]
                shared = set(a) & set(b)
                if len(shared) >= 30 and sum(1 for k in shared if a[k] == b[k]) / len(shared) > 0.98:
                    sw = self.e.swarm
                    x, y = sw.agents[names[i]], sw.agents[names[j]]
                    drop = x if (x["n"], x["acc"]) < (y["n"], y["acc"]) else y
                    if len(sw.active(drop["grp"])) > 8 and drop["active"]:
                        drop["active"] = 0
                        sw.save(drop)
                        self._lesson(cycle, "diversity_auditor",
                                     f"Retired {drop['name']}: duplicates {(y if drop is x else x)['name']} "
                                     f"({len(shared)} identical calls), adds no new information.")
                        return

    # ---------- 10. group-level scorecard ----------
    def system_reviewer(self, cycle):
        parts = []
        for g in ("scout", "predictor", "copy"):
            act = [a for a in self.e.swarm.active(g) if a["n"] >= 10]
            if act:
                parts.append(f"{g}s {mean([a['acc'] for a in act]):.1%} hit rate over {sum(a['n'] for a in act)} calls")
        if parts:
            self._lesson(cycle, "system_reviewer", "Scorecard, " + "; ".join(parts) + ". 50% is a coin flip.", always=False)
