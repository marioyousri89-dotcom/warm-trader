"""The 80 agents. Six groups, one shared brain.

  15 scouts      find new trade ideas with different lenses
  15 analysts    read the market regime (trend / range / volatile)
  15 quants      backtest every strategy and vote on whether its edge is real
  12 copy        pick which traders deserve to be copied (skill vs luck) and mirror them
  13 predictors  forecast the next few candles with different methods
  10 improvers   audit all of the above and change the system (see improvers.py)
"""
import math
import random

from strategies import (FUNCS, TAGS, QUANT_SPECS, atr, backtest, cl, mean, metric_pass, rets, sign, std)

H = 3

SCOUT_SPECS = [
    ("breakout", {"n": 20}), ("breakout", {"n": 40}), ("breakout", {"n": 10}),
    ("momentum", {"n": 10}), ("momentum", {"n": 20}), ("momentum", {"n": 40}),
    ("meanrev", {"n": 20, "z": 2.0}), ("meanrev", {"n": 30, "z": 1.8}), ("meanrev", {"n": 15, "z": 2.2}),
    ("volspike", {"n": 20, "m": 2.0}), ("volspike", {"n": 30, "m": 2.5}),
    ("rsi", {"n": 14, "lo": 25, "hi": 75}), ("rsi", {"n": 9, "lo": 20, "hi": 80}),
    ("macross", {"fast": 8, "slow": 21}), ("macross", {"fast": 12, "slow": 48}),
    ("london_break", {}), ("asia_fade", {"n": 20, "z": 1.8}), ("ny_cont", {"m": 2.0}),
    ("bollinger", {"n": 20, "k": 2.0}), ("macd", {"fast": 12, "slow": 26, "sig": 9}),
]
PREDICTOR_SPECS = [
    ("linreg", {"n": 15}), ("linreg", {"n": 30}), ("linreg", {"n": 60}),
    ("ar1", {"n": 100}), ("ar1", {"n": 200}),
    ("knn", {"k": 7, "m": 4}), ("knn", {"k": 10, "m": 6}),
    ("flow", {"n": 10}), ("flow", {"n": 20}),
    ("trendstr", {"fast": 8, "slow": 24}), ("trendstr", {"fast": 12, "slow": 36}),
    ("ensemble", {}), ("zrev", {"n": 20}),
]
ANALYST_SPECS = [
    ("trend_er", {"n": 20}), ("trend_er", {"n": 50}), ("trend_er", {"n": 100}),
    ("vol_ratio", {"n": 10}), ("vol_ratio", {"n": 20}), ("vol_ratio", {"n": 40}),
    ("range_bb", {"n": 20}), ("range_bb", {"n": 40}),
    ("drawdown", {"n": 100}), ("volume", {"n": 50}), ("skew", {"n": 100}),
    ("breadth", {"n": 10}), ("breadth", {"n": 30}), ("corr", {"n": 30}), ("corr", {"n": 60}),
]
QUANT_ROSTER = [(m, {"w": w}) for m, w in QUANT_SPECS]
COPY_SPECS = [
    ("wilson", {"k": 1, "min_n": 8}), ("wilson", {"k": 2, "min_n": 8}), ("wilson", {"k": 3, "min_n": 12}),
    ("tstat", {"k": 1, "min_n": 8}), ("tstat", {"k": 2, "min_n": 10}), ("tstat", {"k": 3, "min_n": 12}),
    ("recent", {"k": 2, "min_n": 8}), ("recent", {"k": 3, "min_n": 8}),
    ("consensus", {"k": 5, "need": 2, "min_n": 8}), ("consensus", {"k": 8, "need": 3, "min_n": 8}),
    ("fade", {"k": 2, "min_n": 8}), ("sharpe", {"k": 2, "min_n": 10}),
]
# The macro team: what is going on AROUND the market (Polymarket odds, stock markets, world events).
MACRO_SPECS = [
    ("poly_momentum", {"hours": 4}), ("poly_momentum", {"hours": 12}), ("poly_momentum", {"hours": 24}),
    ("poly_level", {}), ("poly_divergence", {"hours": 12}),
    ("equity_riskon", {"hours": 4}), ("equity_riskon", {"hours": 24}),
    ("claude_world", {}),
]

IMPROVER_LENSES = ["accuracy_auditor", "cloner", "threshold_tuner", "risk_auditor", "copy_auditor",
                   "regime_analyst", "overtrading_auditor", "claude_reflector", "diversity_auditor",
                   "system_reviewer", "capital_allocator", "dev_postmortem", "dev_engineer", "session_analyst"]

# The trading desk: these are the agents that ACT. Each has its own style and its own slice of capital,
# and is judged on profit per hour. hold = candles, stop/target = multiples of ATR.
DESK_SPECS = [
    ("consensus", {"style": "consensus"}),
    ("scalper", {"style": "scalper", "thr": 0.65, "need_d": -2, "hold": 2, "stop": 1.0, "target": 1.0}),
    ("trend", {"style": "trend", "thr": 0.8, "need_d": -1, "hold": 6, "stop": 1.5, "target": 3.0}),
    ("range", {"style": "range", "thr": 0.8, "need_d": -1, "hold": 4, "stop": 1.5, "target": 2.0}),
    ("predict", {"style": "predict", "thr": 0.9, "need_d": -1, "hold": 4, "stop": 1.5, "target": 2.0}),
    ("copytrader", {"style": "copy_trader", "hold": 3, "stop": 1.5, "target": 2.0}),
    ("copyconsensus", {"style": "copyc", "thr": 0.8, "need": 2, "hold": 3, "stop": 1.5, "target": 2.0}),
    ("copydesk", {"style": "copy_desk", "hold": 3, "stop": 1.5, "target": 2.0}),
    ("fader", {"style": "fade", "thr": 0.5, "need": 1, "hold": 3, "stop": 1.5, "target": 2.0}),
    ("sprinter", {"style": "sprinter", "thr": 0.75, "need_d": -1, "hold": 4, "stop": 1.0, "target": 1.5}),
]

GROUPS = [("scout", "S", SCOUT_SPECS), ("analyst", "A", ANALYST_SPECS), ("quant", "Q", QUANT_ROSTER),
          ("copy", "C", COPY_SPECS), ("predictor", "P", PREDICTOR_SPECS), ("macro", "M", MACRO_SPECS),
          ("platform", "X", []), ("pipe", "Y", []), ("desk", "T", DESK_SPECS),
          ("improver", "I", [(l, {}) for l in IMPROVER_LENSES])]
KIND = {"scout": "scout", "predictor": "predict", "copy": "copy"}


def pname(prefix, i, lens, params):
    ps = "".join(f"{k}{v}" for k, v in params.items() if k not in ("lo", "hi"))
    return f"{prefix}{i:02d}.{lens}" + (f".{ps}" if ps else "")


def wilson_lb(w, n):
    if n == 0:
        return 0.0
    p, z = w / n, 1.645
    return (p + z * z / (2 * n) - z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / (1 + z * z / n)


def mutate(params, rng):
    out = {}
    for k, v in params.items():
        if k in ("lo", "hi"):
            out[k] = max(10, min(90, v + rng.randint(-3, 3)))
        elif isinstance(v, int):
            out[k] = max(2, int(round(v * rng.uniform(0.7, 1.4))))
        elif isinstance(v, float):
            out[k] = round(v * rng.uniform(0.8, 1.25), 2)
        else:
            out[k] = v
    if "fast" in out and "slow" in out and out["fast"] >= out["slow"]:
        out["slow"] = out["fast"] + 5
    return out


class Swarm:
    def __init__(self, cfg, brain):
        self.cfg, self.b = cfg, brain
        self.rng = random.Random(cfg.seed + 5)
        self.pass_frac = {}
        self.frozen = False          # exam mode: signals are still graded, but nobody's weight changes
        self.exam = {}               # agent -> [hits, n] collected while frozen
        self.regimes = {}
        self.global_flags = {"corr": 0.0, "breadth": 0.5}
        self.load()
        if not self.agents:
            self.seed_roster()

    # ---------------- roster ----------------
    def load(self):
        import json
        self.agents = {}
        for r in self.b.q("SELECT * FROM agents"):
            r["params"] = json.loads(r["params"])
            self.agents[r["name"]] = r

    def seed_roster(self):
        for grp, prefix, specs in GROUPS:
            for i, (lens, params) in enumerate(specs, 1):
                name = f"{prefix}{i:02d}.{lens}" if grp == "desk" else pname(prefix, i, lens, params)
                self.add_agent(grp, name, lens, params, 0, None)
            self.b.kv_set(f"target_{grp}", len(specs))
            self.b.kv_set(f"seq_{grp}", len(specs))

    def add_agent(self, grp, name, lens, params, born, parent):
        import json
        row = {"name": name, "grp": grp, "lens": lens, "params": params, "active": 1, "n": 0,
               "acc": 0.5, "weight": 1.0, "born": born, "parent": parent}
        self.agents[name] = row
        self.b.x("INSERT OR REPLACE INTO agents(name,grp,lens,params,active,n,acc,weight,born,parent)"
                 " VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (name, grp, lens, json.dumps(params), 1, 0, 0.5, 1.0, born, parent))
        return row

    def save(self, a):
        import json
        self.b.x("UPDATE agents SET params=?,active=?,n=?,acc=?,weight=? WHERE name=?",
                 (json.dumps(a["params"]), a["active"], a["n"], a["acc"], a["weight"], a["name"]))

    def active(self, grp):
        return [a for a in self.agents.values() if a["grp"] == grp and a["active"]]

    # ---------------- scouts + predictors ----------------
    def run_signal_agents(self, cycle, market):
        for grp in ("scout", "predictor"):
            for a in self.active(grp):
                fn = FUNCS[a["lens"]]
                for sym in market.symbols:
                    d, conf = fn(market.candles[sym], a["params"])
                    if d and conf > 0:
                        self.b.post(cycle, a["name"], grp, sym, KIND[grp], d, conf,
                                    {"lens": a["lens"], "tag": TAGS.get(a["lens"], "neutral")},
                                    market.last(sym), cycle + H)

    # ---------------- macro team: Polymarket odds, stock markets, world events ----------------
    def run_macro(self, cycle, market, macro):
        if macro is None:
            return
        hz = self.cfg.cycles_per_hour
        for a in self.active("macro"):
            lens, p = a["lens"], a["params"]
            for sym in market.symbols:
                d, conf = 0, 0.0
                if lens == "poly_momentum":
                    m, w = macro.mom(sym, p["hours"])
                    if w and abs(m) > 0.01:
                        d, conf = (1 if m > 0 else -1), min(1.0, abs(m) * 12)
                elif lens == "poly_level":
                    lv = macro.level(sym)
                    if abs(lv) > 0.08:
                        d, conf = (1 if lv > 0 else -1), min(1.0, abs(lv) * 4)
                elif lens == "poly_divergence":
                    # crowd odds moved one way while price moved the other: bet the price catches up
                    m, w = macro.mom(sym, p["hours"])
                    c = market.candles[sym]
                    k = min(len(c) - 1, p["hours"] * hz)
                    if w and k > 0 and abs(m) > 0.02:
                        pr = c[-1]["c"] / c[-1 - k]["c"] - 1
                        if pr * m < 0:
                            d, conf = (1 if m > 0 else -1), min(1.0, abs(m) * 10)
                elif lens == "equity_riskon":
                    z = macro.eq_z(p["hours"])
                    if z is not None and abs(z) > 0.8:
                        d, conf = (1 if z > 0 else -1), min(1.0, abs(z) / 3)
                elif lens == "claude_world":
                    b = (macro.world.get("bias") or {}).get(sym)
                    if b and b["direction"]:
                        d, conf = b["direction"], b["confidence"]
                if d and conf > 0:
                    self.b.post(cycle, a["name"], "macro", sym, "macro", d, conf,
                                {"lens": lens, "tag": "neutral"}, market.last(sym), cycle + hz)

    # ---------------- outside platforms (TradingView, TrendSpider, ... via webhook) ----------------
    def run_platform(self, cycle, market, items):
        """Each platform that ever sends an alert becomes its own agent, scored like every other agent."""
        for it in items:
            name = f"X.{it['source']}"
            if name not in self.agents:
                self.add_agent("platform", name, "webhook", {"source": it["source"]}, cycle, None)
            if not self.agents[name]["active"]:
                continue
            self.b.post(cycle, name, "platform", it["symbol"], "platform", it["side"], it["strength"],
                        {"note": it["note"]}, market.last(it["symbol"]), cycle + self.cfg.cycles_per_hour)

    # ---------------- market pipe agents (one per idea: news, funding, premium, fear&greed, world, breadth) ----------------
    def run_pipe(self, cycle, market, items):
        for src, sym, side, strength, note in items:
            name = f"Y.{src}"
            if name not in self.agents:
                self.add_agent("pipe", name, src, {"source": src}, cycle, None)
            if not self.agents[name]["active"] or sym not in market.symbols:
                continue
            self.b.post(cycle, name, "pipe", sym, "platform", side, strength, {"note": note},
                        market.last(sym), cycle + self.cfg.cycles_per_hour)

    # ---------------- market analysts ----------------
    def run_analysts(self, cycle, market):
        votes = {s: {"up": 0, "down": 0, "range": 0, "volatile": 0} for s in market.symbols}
        corrs, breadths = [], []
        for a in self.active("analyst"):
            lens, n = a["lens"], a["params"]["n"]
            if lens == "breadth":
                ups = sum(1 for s in market.symbols if len(market.candles[s]) > n and
                          market.candles[s][-1]["c"] > market.candles[s][-1 - n]["c"])
                breadths.append(ups / len(market.symbols))
                self.b.post(cycle, a["name"], "analyst", "ALL", "regime", 0, 0, {"breadth": breadths[-1]})
                continue
            if lens == "corr":
                corrs.append(self._avg_corr(market, n))
                self.b.post(cycle, a["name"], "analyst", "ALL", "regime", 0, 0, {"corr": corrs[-1]})
                continue
            for sym in market.symbols:
                c = market.candles[sym]
                v = self._analyst_vote(lens, n, c)
                if v:
                    votes[sym][v] += 1
                    self.b.post(cycle, a["name"], "analyst", sym, "regime", 0, 0, {"vote": v})
        self.regimes = {}
        for sym, v in votes.items():
            label = max(("up", "down", "range"), key=lambda k: (v[k], k == "range"))
            if label in ("up", "down") and v[label] <= v["range"]:
                label = "range"
            self.regimes[sym] = {"label": label, "vol_high": v["volatile"] >= 3, "votes": v}
        self.global_flags = {"corr": mean(corrs) if corrs else 0.0, "breadth": mean(breadths) if breadths else 0.5}

    @staticmethod
    def _analyst_vote(lens, n, c):
        if lens == "trend_er" and len(c) > n + 1:
            a = cl(c[-(n + 1):])
            path = sum(abs(a[i] - a[i - 1]) for i in range(1, len(a)))
            er = abs(a[-1] - a[0]) / path if path else 0
            return ("up" if a[-1] > a[0] else "down") if er > 0.3 else "range"
        if lens == "vol_ratio" and len(c) > n * 5 + 2:
            r = rets(cl(c[-(n * 5 + 1):]))
            lg = std(r)
            return "volatile" if lg and std(r[-n:]) > 1.6 * lg else None
        if lens == "range_bb" and len(c) > n + 15:
            seg = c[-n:]
            width = max(x["h"] for x in seg) - min(x["l"] for x in seg)
            return "range" if width / (atr(c) or 1e-9) < 1.6 * math.sqrt(n) else None
        if lens == "drawdown" and len(c) > n:
            hi = max(x["h"] for x in c[-n:])
            return "down" if c[-1]["c"] < hi * 0.92 else None
        if lens == "volume" and len(c) > n + 6:
            recent = mean([x["v"] for x in c[-5:]])
            base = mean([x["v"] for x in c[-n - 5:-5]])
            return "volatile" if base and recent > 2 * base else None
        if lens == "skew" and len(c) > n + 2:
            r = rets(cl(c[-(n + 1):]))
            sd = std(r)
            return "volatile" if sd and sum(1 for x in r if abs(x) > 2.5 * sd) / len(r) > 0.04 else None
        return None

    @staticmethod
    def _avg_corr(market, n):
        series = [rets(cl(market.candles[s][-(n + 1):])) for s in market.symbols if len(market.candles[s]) > n + 1]
        out = []
        for i in range(len(series)):
            for j in range(i + 1, len(series)):
                a, b = series[i], series[j]
                sa, sb = std(a), std(b)
                if sa and sb:
                    ma, mb = mean(a), mean(b)
                    out.append(sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (len(a) - 1) / (sa * sb))
        return mean(out) if out else 0.0

    # ---------------- quants ----------------
    def refresh_quants(self, cycle, market):
        quants = self.active("quant")
        strategies = self.active("scout") + self.active("predictor")
        if not quants:
            return
        passed = {q["name"]: 0 for q in quants}
        for a in strategies:
            fn = FUNCS[a["lens"]]
            series = {s: backtest(fn, a["params"], market.candles[s], h=H) for s in market.symbols}
            for sym in market.symbols:
                ok = 0
                for q in quants:
                    if metric_pass(q["lens"], q["params"]["w"], series[sym], list(series.values())):
                        ok += 1
                        passed[q["name"]] += 1
                self.pass_frac[(a["name"], sym)] = ok / len(quants)
        total = len(strategies) * len(market.symbols)
        for q in quants:
            self.b.post(cycle, q["name"], "quant", "ALL", "verdict", 0, 0,
                        {"metric": q["lens"], "window": q["params"]["w"], "passed": passed[q["name"]], "of": total})

    def vfactor(self, name, sym):
        f = self.pass_frac.get((name, sym))
        if f is None:
            return 0.5
        return max(0.0, min(1.4, 2 * (f - 0.3)))

    # ---------------- copy-trading agents ----------------
    def trader_stats(self, cycle):
        rows = self.b.q("SELECT trader,pnl FROM trader_pos WHERE status='closed' AND close_cycle>? ORDER BY close_cycle",
                        (cycle - 600,))
        by = {}
        for r in rows:
            by.setdefault(r["trader"], []).append(r["pnl"])
        out = {}
        for t, ps in by.items():
            n = len(ps)
            wins = sum(1 for p in ps if p > 0)
            m, sd = mean(ps), std(ps)
            out[t] = {"n": n, "wr": wins / n, "mean": m, "wilson": wilson_lb(wins, n),
                      "tstat": m / (sd / math.sqrt(n)) if sd else 0.0, "sharpe": m / sd if sd else 0.0,
                      "recent": mean([1.0 if p > 0 else 0.0 for p in ps[-6:]])}
        return out

    def run_copy(self, cycle, market):
        stats = self.trader_stats(cycle)
        visible = self.b.q("SELECT * FROM trader_pos WHERE status='open' AND open_cycle=?", (cycle - 1,))
        if not visible:
            return
        for a in self.active("copy"):
            p = a["params"]
            elig = {t: s for t, s in stats.items() if s["n"] >= p["min_n"]}
            lens, k = a["lens"], p["k"]
            if lens == "fade":
                pick = sorted((t for t, s in elig.items() if s["tstat"] < -1.2), key=lambda t: elig[t]["tstat"])[:k]
                conf_of = lambda s: min(1.0, -s["tstat"] / 3)
                flip = -1
            else:
                flip = 1
                key, ok, conf_of = {
                    "wilson": ("wilson", lambda s: s["wilson"] > 0.5 and s["mean"] > 0, lambda s: min(1.0, max(0.0, (s["wilson"] - 0.4) * 2))),
                    "tstat": ("tstat", lambda s: s["tstat"] > 1.0, lambda s: min(1.0, s["tstat"] / 3)),
                    "recent": ("recent", lambda s: s["recent"] >= 0.67 and s["mean"] > 0, lambda s: s["recent"]),
                    "sharpe": ("sharpe", lambda s: s["sharpe"] > 0.2, lambda s: min(1.0, s["sharpe"] / 0.6)),
                    "consensus": ("wilson", lambda s: s["wilson"] > 0.45 and s["mean"] > 0, lambda s: min(1.0, max(0.1, (s["wilson"] - 0.35) * 2))),
                }[lens]
                pick = sorted((t for t, s in elig.items() if ok(s)), key=lambda t: -elig[t][key])[:k]
            if not pick:
                continue
            net = {}
            cnt = {}
            for pos in visible:
                if pos["trader"] in pick:
                    net[pos["symbol"]] = net.get(pos["symbol"], 0.0) + flip * pos["side"] * conf_of(elig[pos["trader"]])
                    cnt.setdefault(pos["symbol"], []).append(flip * pos["side"])
            for sym, v in net.items():
                if lens == "consensus":
                    sides = cnt[sym]
                    if abs(sum(sides)) < p["need"]:
                        continue
                if sign(v):
                    self.b.post(cycle, a["name"], "copy", sym, "copy", sign(v), min(1.0, abs(v)),
                                {"traders": pick, "lens": lens}, market.last(sym), cycle + H - 1)

    # ---------------- learning: score every directional signal ----------------
    def resolve(self, cycle, market):
        rows = self.b.q("SELECT id,agent,symbol,direction,entry_price FROM signals "
                        "WHERE due<=? AND resolved=0 AND direction!=0", (cycle,))
        if not rows:
            return
        upd, touched = [], set()
        for r in rows:
            ret = market.last(r["symbol"]) / r["entry_price"] - 1
            hit = 1 if r["direction"] * ret > 0 else 0
            upd.append((hit, r["id"]))
            a = self.agents.get(r["agent"])
            if a and self.frozen:
                e = self.exam.setdefault(a["name"], [0, 0])
                e[0] += hit
                e[1] += 1
            elif a:
                n = a["n"]
                a["acc"] += max(1 / (n + 1), 0.02) * (hit - a["acc"])
                a["n"] = n + 1
                # trust grows slowly: signals overlap in time, so n calls are worth ~n/horizon independent samples
                a["weight"] = max(0.1, min(2.5, 1 + 6 * (a["acc"] - 0.5) * min(1.0, a["n"] / 80)))
                touched.add(a["name"])
        with self.b.lock:
            self.b.db.executemany("UPDATE signals SET resolved=1,hit=? WHERE id=?", upd)
            self.b.db.commit()
        for n in touched:
            self.save(self.agents[n])
