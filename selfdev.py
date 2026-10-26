"""SELF-DEVELOPMENT, every live hour. The system teaches itself in four ways:

1. NEWS SKILL: every headline about a coin we trade is remembered with its tone (upbeat/downbeat) and the price at
   that moment. One hour later we check: did the price move the way the headline leaned? Each publisher builds a
   track record, and the news mood used by the agents is weighted by that record (proven publishers count more,
   publishers that keep being wrong count less). Nobody is trusted on reputation.
2. IMPROVERS every hour (instead of every 10): agents re-weighted, losers retired, winners cloned, thresholds tuned
   within hard limits.
3. COUNCIL GATE re-calibrated every hour on the most recent ideas.
4. A written development report each hour: what changed and why, so the owner can follow the learning.
"""
import math
import re
import time
from collections import deque

from pipe import NAMES


def wilson_lb(w, n, z=1.28):
    if n == 0:
        return 0.5
    p = w / n
    return (p + z * z / (2 * n) - z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / (1 + z * z / n)


class SelfDev:
    def __init__(self, engine):
        self.e = engine
        saved = engine.b.kv_get("news_skill") if engine.cfg.keep_brain else None
        self.stats = dict(saved or {})            # publisher -> [right, graded]
        self.pending = deque(maxlen=20000)        # headlines waiting to be graded
        self.last_t = time.time()
        self.reports = deque(engine.b.kv_get("selfdev_reports") or [], maxlen=72)
        self.pat = {}

    def _mentions(self, title, sym):
        if sym not in self.pat:
            alt = NAMES.get(sym, "")
            self.pat[sym] = re.compile(r"\b(" + sym.lower() + ("|" + alt if alt else "") + r")\b", re.I)
        return bool(self.pat[sym].search(title))

    def weight(self, pub):
        w, n = self.stats.get(pub, (0, 0))
        if n < 6:
            return 1.0
        return max(0.25, min(2.5, 1.0 + 4.0 * (wilson_lb(w, n) - 0.45)))   # proven > 1, poor < 1

    # ---------------------------------------------------------------- news skill
    def _news_skill(self, market):
        pipe = self.e.pipe
        if not pipe:
            return 0, 0
        now, graded = time.time(), 0
        keep = deque(maxlen=self.pending.maxlen)
        for it in self.pending:
            if now - it["t"] < 3600:
                keep.append(it)
                continue
            px = market.last(it["sym"])
            move = px / it["px"] - 1
            if abs(move) >= 0.002:                       # ignore noise: only judge real moves
                s = self.stats.setdefault(it["pub"], [0, 0])
                s[0] += 1 if (move > 0) == (it["dir"] > 0) else 0
                s[1] += 1
                graded += 1
        self.pending = keep
        new = 0
        with pipe.lock:
            heads = [h for h in pipe.headlines[:800] if h["t"] > self.last_t]
        for h in heads:
            if not h["s"]:
                continue
            for sym in market.symbols:
                if self._mentions(h["title"], sym):
                    self.pending.append({"t": h["t"], "pub": h["src"], "sym": sym, "dir": 1 if h["s"] > 0 else -1,
                                         "px": market.last(sym)})
                    new += 1
        self.last_t = now
        return new, graded

    # ---------------------------------------------------------------- the hourly round
    def hourly(self, cycle):
        e, m = self.e, self.e.market
        before = {k: getattr(e.cfg, k) for k in ("agg_threshold", "min_agents", "llm_weight", "risk_per_trade")}
        n_lessons = len(e.b.lessons(200))
        new, graded = self._news_skill(m)
        if e.pipe:
            e.pipe.pub_weight = self.weight
        cal = None
        c = e.council
        if len(c.scores) >= 80:
            c.calibrate(list(c.scores)[-600:])
            cal = (c.gate, c.floor)
        after = {k: getattr(e.cfg, k) for k in before}
        changed = [f"{k} {before[k]} -> {after[k]}" for k in before if before[k] != after[k]]
        fresh_lessons = [l["text"][:140] for l in e.b.lessons(200)[:max(0, len(e.b.lessons(200)) - n_lessons)]]
        rated = sorted(((p, s[0], s[1], self.weight(p)) for p, s in self.stats.items() if s[1] >= 6), key=lambda x: -x[3])
        grp = {}
        for a in e.swarm.agents.values():
            if a["active"] and a["n"] >= 10:
                grp.setdefault(a["grp"], []).append(a["acc"])
        rep = {"cycle": cycle, "t": time.time(),
               "equity": round(e.port.last_equity, 2),
               "hour_pnl": (e.b.q("SELECT pnl FROM hours ORDER BY hour DESC LIMIT 1") or [{"pnl": 0}])[0]["pnl"],
               "news_tracked": new, "news_graded": graded, "publishers_rated": len(rated),
               "best_publishers": [(p, w, n) for p, w, n, _ in rated[:3]],
               "worst_publishers": [(p, w, n) for p, w, n, _ in rated[-3:]] if len(rated) > 3 else [],
               "settings_changed": changed, "lessons": fresh_lessons[:6], "gate": cal,
               "team_hit": {g: round(sum(v) / len(v), 3) for g, v in grp.items()},
               "active_agents": sum(1 for a in e.swarm.agents.values() if a["active"])}
        self.reports.appendleft(rep)
        e.b.kv_set("selfdev_reports", list(self.reports))
        e.b.kv_set("news_skill", self.stats)
        return rep

    def state(self):
        rated = sorted(((p, s[0], s[1], round(self.weight(p), 2)) for p, s in self.stats.items() if s[1] >= 6),
                       key=lambda x: -x[3])
        return {"reports": list(self.reports)[:24], "publishers_rated": len(rated), "pending": len(self.pending),
                "top": rated[:12], "bottom": rated[-12:][::-1] if len(rated) > 12 else []}
