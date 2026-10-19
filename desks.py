"""The Trading Desk. These agents ACT on what the research teams found.

Each desk agent has its own style, its own slice of capital and its own book of positions. Desks are judged
on PROFIT PER HOUR: every hour the capital_allocator improver moves money toward the desks earning the most
per hour (shrunk for small samples) and a desk that loses too much is paused. The risk manager and the
total-risk (heat) cap sit in front of every desk, so 'maximise profit per hour' never means 'take any risk'.

Some desks trade the research teams' vote, some COPY: one copies the statistically proven external trader,
one copies the consensus of the copy agents, one copies whichever internal desk is earning the most.
"""
import math
from collections import deque

from strategies import TAGS, atr, sign

COPY_STYLES = ("copy_trader", "copy_desk", "copyc", "fade")


class DeskManager:
    def __init__(self, eng):
        self.e = eng
        self.log = deque(maxlen=60)
        self.req = self.yes = self.no = 0          # decision-desk counters: proposals, approved, rejected
        self.reasons = {}                           # rejection reason -> count
        self.paused_until = {}
        self.alloc = {}
        self.last_hour_equity = eng.cfg.start_equity
        self.last_rebalance = -10 ** 9

    # ------------------------------------------------------------------ helpers
    def desks(self):
        return self.e.swarm.active("desk")

    def style(self, name):
        a = self.e.swarm.agents.get(name)
        return a["params"].get("style") if a else None

    def share(self, name):
        if not self.alloc:
            self.alloc = self.e.b.kv_get("alloc", {}) or {}
        ds = self.desks()
        if name not in self.alloc:
            self.alloc[name] = 1.0 / max(1, len(ds))
        return self.alloc[name]

    def stats(self, cycle):
        """Per desk: trades, wins, P/L and PROFIT PER HOUR over the last 24 hours, plus all-time P/L."""
        cfg, b = self.e.cfg, self.e.b
        since = cycle - cfg.cycles_per_day
        hours = max(1.0, min(cfg.cycles_per_day, cycle - cfg.t0) / cfg.cycles_per_hour)
        out = {a["name"]: {"n": 0, "wins": 0, "pnl": 0.0, "fees": 0.0, "pph": 0.0, "all_pnl": 0.0, "all_n": 0}
               for a in self.e.swarm.agents.values() if a["grp"] == "desk"}
        for r in b.q("SELECT desk,COUNT(*) n,COALESCE(SUM(pnl>0),0) w,COALESCE(SUM(pnl),0) p,COALESCE(SUM(fees),0) f "
                     "FROM trades WHERE status='closed' AND close_cycle>? GROUP BY desk", (since,)):
            if r["desk"] in out:
                out[r["desk"]].update(n=r["n"], wins=r["w"], pnl=r["p"], fees=r["f"], pph=r["p"] / hours)
        for r in b.q("SELECT desk,COUNT(*) n,COALESCE(SUM(pnl),0) p FROM trades WHERE status='closed' GROUP BY desk"):
            if r["desk"] in out:
                out[r["desk"]].update(all_n=r["n"], all_pnl=r["p"])
        return out

    # ------------------------------------------------------------------ what each desk wants to do
    def _scored(self, ctx, kinds=None, filt=None):
        sw, out = self.e.swarm, []
        for sym in ctx.market.symbols:
            sigs = [s for s in ctx.by[sym] if kinds is None or s["kind"] in kinds]
            out.append(self.e.agg.score(sym, sigs, sw, sw.regimes[sym], filt))
        return out

    def intents(self, a, ctx):
        p, st, cfg = a["params"], a["params"]["style"], self.e.cfg
        hold, stop, tgt = p.get("hold", cfg.time_stop), p.get("stop", cfg.stop_atr), p.get("target", cfg.target_atr)

        def mk(sym, side, conf, why, h=None, sources=None):
            return {"sym": sym, "side": side, "conf": conf, "reason": why, "hold": h or hold,
                    "stop": stop, "target": tgt, "sources": sources or []}

        out = []
        if st == "copy_trader":      # mirror the external traders whose skill is statistically undeniable
            ts = ctx.tstats
            best = [t for t, s in ts.items() if s["n"] >= 30 and s["mean"] > 0 and
                    (s["wr"] - 0.5) / math.sqrt(0.25 / s["n"]) > 2.5]
            best = sorted(best, key=lambda t: -ts[t]["wilson"])[:2]
            for pos in ctx.visible:
                if pos["trader"] in best:
                    out.append(mk(pos["symbol"], pos["side"], 0.6, f"copying {pos['trader']} (skill z>2.5)",
                                  max(1, pos["close_cycle"] - ctx.cycle), [pos["trader"]]))
        elif st == "copy_desk":      # mirror whichever other desk is earning the most per hour
            st_ = self.stats(ctx.cycle)
            cand = [(n, s["pph"]) for n, s in st_.items()
                    if n != a["name"] and s["n"] >= 5 and s["pnl"] > 0 and self.style(n) != "copy_desk"]
            if cand:
                src = max(cand, key=lambda x: x[1])[0]
                for t in self.e.port.open.values():
                    if t["desk"] == src and t["open_cycle"] == ctx.cycle - 1:
                        out.append(mk(t["symbol"], t["side"], 0.5, f"copying desk {src}",
                                      max(1, t["max_hold"] - 1), [src]))
        else:
            kinds, filt, need_regime = {
                "consensus": (None, None, None), "scalper": (None, None, None), "sprinter": (None, None, None),
                "trend": (None, lambda ag: TAGS.get(ag["lens"], "neutral") in ("trend", "neutral"), "trend"),
                "range": (None, lambda ag: TAGS.get(ag["lens"], "neutral") in ("revert", "neutral"), "range"),
                "predict": ({"predict"}, None, None),
                "copyc": ({"copy"}, None, None),
                "fade": ({"copy"}, lambda ag: ag["lens"] == "fade", None),
                "macro": ({"macro"}, None, None),
                "platform": ({"platform"}, None, None),
            }[st]
            need = p.get("need") or max(2, cfg.min_agents + p.get("need_d", 0))
            thr = cfg.agg_threshold * p.get("thr", 1.0)
            for cd in self._scored(ctx, kinds, filt):
                reg = cd["regime"]
                if (need_regime == "trend" and reg not in ("up", "down")) or (need_regime == "range" and reg != "range"):
                    continue
                score = ctx.adjust(cd["symbol"], cd["score"], veto_only=st in COPY_STYLES + ("macro", "platform"))
                d = sign(score)
                if not d or abs(score) < thr or d != cd["dir"] or cd["agree"] < need:
                    continue
                if need_regime == "trend" and d != (1 if reg == "up" else -1):
                    continue
                out.append(mk(cd["symbol"], d, abs(score),
                              f"{st}: score {score:+.2f}, {cd['agree']}/{cd['n']} agents agree, regime {reg}",
                              sources=[t[0] for t in cd["top"][:5]]))
        out = [o for o in out if not ctx.vetoed(o["sym"], o["side"])]
        return sorted(out, key=lambda o: -o["conf"])[:2]

    # ------------------------------------------------------------------ act
    def run(self, ctx):
        e, n_act = self.e, max(1, len(self.desks()))
        corr_high = e.swarm.global_flags["corr"] > 0.7
        for a in self.desks():
            name = a["name"]
            if self.paused_until.get(name, 0) > ctx.cycle:
                continue
            opened = 0
            for it in self.intents(a, ctx):
                if opened >= 2:
                    break
                sym, side, m = it["sym"], it["side"], ctx.market
                px, at = m.last(sym), atr(m.candles[sym])
                reg = e.swarm.regimes[sym]
                mult = min(1.5, max(0.4, self.share(name) * n_act)) * e.session_mult.get(e.port.session, 1.0)
                size, why, risk = e.risk.approve(name, sym, px, at, it["stop"], it["conf"], reg["vol_high"], corr_high,
                                                 e.port, ctx.eq, ctx.prices, mult)
                if size > 0:
                    e.port.open_trade(name, sym, side, size, px, px - side * it["stop"] * at,
                                      px + side * it["target"] * at, ctx.cycle, reg["label"], it["sources"],
                                      side * it["conf"], it["reason"], it["hold"], risk)
                    opened += 1
                    why = "OPENED"
                self.req += 1
                if why == "OPENED":
                    self.yes += 1
                else:
                    self.no += 1
                    self.reasons[why] = self.reasons.get(why, 0) + 1
                if why not in ("already in position", "desk position limit"):
                    self.log.append({"cycle": ctx.cycle, "desk": name, "symbol": sym, "side": side, "result": why,
                                     "reason": it["reason"][:90]})

    # ------------------------------------------------------------------ every simulated/real hour
    def hourly(self, cycle):
        e, cfg, b = self.e, self.e.cfg, self.e.b
        eq = e.port.last_equity
        hour = (cycle - cfg.t0) // cfg.cycles_per_hour
        st = self.stats(cycle)
        best = max(st.items(), key=lambda kv: kv[1]["pph"])[0] if st else None
        n = b.q("SELECT COUNT(*) n FROM trades WHERE status='closed' AND close_cycle>?", (cycle - cfg.cycles_per_hour,))[0]["n"]
        b.x("INSERT OR REPLACE INTO hours(hour,cycle,pnl,equity,trades,best_desk) VALUES(?,?,?,?,?,?)",
            (hour, cycle, eq - self.last_hour_equity, eq, n, best))
        self.last_hour_equity = eq
        if e.swarm.frozen:                  # exam: record the hour, change nothing
            return
        for a in self.desks():              # cooling-off for a desk that is bleeding
            s, name = st.get(a["name"]), a["name"]
            if s and self.paused_until.get(name, 0) <= cycle and s["pnl"] < -cfg.desk_loss_limit * eq:
                self.paused_until[name] = cycle + cfg.desk_pause_hours * cfg.cycles_per_hour
                b.add_lesson(cycle, "risk_manager", f"Paused desk {name} for {cfg.desk_pause_hours}h: lost "
                                                    f"{s['pnl']:+.0f} in 24h (limit {cfg.desk_loss_limit:.0%} of equity).")
        e.improvers.run_one("capital_allocator", cycle)

    def rebalance(self, cycle):
        """Move capital toward the desks earning the most profit per hour. Shrunk for small samples,
        smoothed so one lucky hour doesn't swing it, and bounded per desk."""
        cfg, b = self.e.cfg, self.e.b
        ds = [a["name"] for a in self.desks()]
        if len(ds) < 2 or cycle - self.last_rebalance < cfg.cycles_per_hour:
            return
        self.last_rebalance = cycle
        st = self.stats(cycle)
        scale = max(1.0, self.e.port.last_equity * 0.001)       # 0.1% of equity per hour = one 'unit'
        raw = {d: math.exp(max(-3.0, min(3.0, st[d]["pph"] * st[d]["n"] / (st[d]["n"] + 10) / scale))) for d in ds}
        tot = sum(raw.values())
        old = {d: self.share(d) for d in ds}
        new = {d: 0.6 * old[d] + 0.4 * raw[d] / tot for d in ds}
        for _ in range(8):                                       # clamp to [min,max] and renormalise
            new = {d: min(cfg.desk_max_share, max(cfg.desk_min_share, v)) for d, v in new.items()}
            s = sum(new.values())
            new = {d: v / s for d, v in new.items()}
        self.alloc = new
        b.kv_set("alloc", new)
        moves = sorted(((new[d] - old[d], d) for d in ds))
        if abs(moves[-1][0]) >= 0.02:
            up, dn = moves[-1], moves[0]
            b.add_lesson(cycle, "capital_allocator",
                         f"Capital moved toward {up[1]} ({up[0]:+.1%}) and away from {dn[1]} ({dn[0]:+.1%}) "
                         f"based on profit per hour over the last 24h.")

    # ------------------------------------------------------------------ for the dashboard / Claude
    def board(self, cycle, prices):
        st = self.stats(cycle)
        port = self.e.port
        rows = []
        for a in self.desks():
            n, s = a["name"], st.get(a["name"], {})
            rows.append({"desk": n, "style": a["params"].get("style"), "share": round(self.share(n), 3),
                         "open": port.desk_count(n), "n": s.get("n", 0),
                         "win": round(s["wins"] / s["n"], 3) if s.get("n") else None,
                         "pph": round(s.get("pph", 0.0), 2), "pnl24": round(s.get("pnl", 0.0), 2),
                         "all_pnl": round(s.get("all_pnl", 0.0) + port.desk_unrealized(n, prices), 2),
                         "paused": self.paused_until.get(n, 0) > cycle})
        return sorted(rows, key=lambda r: -r["pph"])
