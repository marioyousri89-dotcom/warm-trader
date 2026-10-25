"""THE COUNCIL + THE GATE (the 'Jev' pattern from the brief):

  give it the context  ->  five roles each answer one narrow question  ->  one confidence number
  ->  the GATE:  strong (>= gate)          : goes ahead automatically (paper fill)
                 medium (>= floor, < gate) : HAND-OFF to the owner, who makes the final call in the app
                 weak   (< floor)          : rejected ("no edge")
  ->  ordinary code (the risk manager + portfolio) does the action.

The five seats (named after the jobs in the brief, all computed from our own data, no outside AI needed):
  SOURCES   - do enough independent exchanges agree on the price, and is there a story behind the move? (pipe)
  SENTIMENT - do headlines and the crowd (fear & greed, funding) lean the same way?                      (pipe)
  CHARTS    - does the chart regime support this side?                                                    (analysts)
  THESIS    - how strong is the case FOR versus the strongest case AGAINST (bull vs bear)?                (all votes)
  RISK      - the six hard rules. Any failure is a veto, no matter how good the rest looks.               (risk manager)
"""
import time
from collections import deque


class Council:
    def __init__(self, engine, gate=0.85, floor=0.55, wait_cycles=2):
        self.e = engine
        self.gate, self.floor, self.wait = gate, floor, wait_cycles
        self.human_review = True              # owner can switch off: then medium cases auto-approve (paper only)
        self.queue = {}                       # id -> pending hand-off
        self.answers = deque()                # owner YES/NO waiting to be applied on the engine thread
        self.log = deque(maxlen=60)
        self.n = {"auto": 0, "handoff": 0, "owner_yes": 0, "owner_no": 0, "expired": 0, "weak": 0, "veto": 0}
        self.seq = 0
        self.max_queue = 3                    # a human can't review hundreds: only the strongest few wait for you
        self.scores = []                      # scores seen in the academy, used to calibrate the gate
        self.calibration = None

    def calibrate(self, scores):
        """'Calibrate on yours': top ~20% of training ideas pass automatically, the next ~45% come to the owner."""
        s = sorted(x for x in scores if x is not None)
        if len(s) < 50:
            return
        q = lambda p: s[min(len(s) - 1, int(p * len(s)))]
        self.gate = round(min(0.90, max(0.60, q(0.80))), 3)
        self.floor = round(min(self.gate - 0.05, max(0.40, q(0.35))), 3)
        self.calibration = {"ideas": len(s), "gate": self.gate, "floor": self.floor}

    # ---------------------------------------------------------------- the five seats
    def review(self, sym, side, conf, ctx):
        e = self.e
        pipe = e.pipe if (e.pipe and e.live) else None   # real-world data only makes sense on real prices
        seats = {}
        c = pipe.consensus(sym) if pipe else None
        if c:
            agree = min(1.0, c["sources"] / 6) * (1.0 if c["spread"] < 0.004 else 0.4)
            nm = pipe.news_mood(sym, hours=6)
            seats["sources"] = (round(0.6 * agree + 0.4 * min(1.0, nm["n"] / 5), 2),
                                f"{c['sources']} exchanges, spread {c['spread']:.2%}, {nm['n']} stories")
            lean, why = 0.0, []
            if nm["scored"] >= 2:
                lean += nm["mood"]
                why.append(f"news {nm['mood']:+.2f}")
            if c["funding"] is not None:
                lean -= max(-1, min(1, c["funding"] / 0.0005)) * 0.5      # crowded longs = lean against longs
                why.append(f"funding {c['funding']:+.4%}")
            seats["sentiment"] = (round(max(0.0, min(1.0, 0.5 + 0.5 * lean * side)), 2), ", ".join(why) or "no strong lean")
        else:
            seats["sources"] = (0.5, "no live pipe data for this market (neutral)")
            seats["sentiment"] = (0.5, "no live pipe data (neutral)")
        reg = e.swarm.regimes.get(sym, {}).get("label", "?")
        ch = 1.0 if (reg == "up" and side > 0) or (reg == "down" and side < 0) else 0.0 if reg in ("up", "down") else 0.5
        seats["charts"] = (ch, f"regime {reg}")
        pro = con = 0.0
        for s in ctx.by.get(sym, []):
            w = e.swarm.agents.get(s["agent"], {}).get("weight", 1.0) * s["confidence"]
            if s["direction"] == side:
                pro += w
            elif s["direction"] == -side:
                con += w
        th = pro / (pro + con) if pro + con else 0.5
        seats["thesis"] = (round(th, 2), f"case for {pro:.1f} vs against {con:.1f}")
        score = 0.2 * seats["sources"][0] + 0.2 * seats["sentiment"][0] + 0.25 * seats["charts"][0] + 0.35 * seats["thesis"][0]
        score = 0.7 * score + 0.3 * min(1.0, conf)               # the desk's own conviction counts too
        return round(score, 3), seats

    # ---------------------------------------------------------------- the gate
    def decide(self, desk, it, ctx, risk_ok, risk_why):
        """Returns 'go', 'handoff' or 'no', plus a reason. Called only for proposals the desks made."""
        sym, side = it["sym"], it["side"]
        score, seats = self.review(sym, side, it["conf"], ctx)
        seats["risk"] = (1.0 if risk_ok else 0.0, "all six rules pass" if risk_ok else risk_why)
        entry = {"cycle": ctx.cycle, "desk": desk, "symbol": sym, "side": side, "score": score,
                 "seats": {k: {"v": v, "why": w} for k, (v, w) in seats.items()}}
        if not risk_ok:
            self.n["veto"] += 1
            entry["verdict"] = "VETO (risk)"
            self.log.appendleft(entry)
            return "no", risk_why
        if self.e.phase != "live":
            self.scores.append(score)
        live_owner = self.e.phase == "live" and self.human_review
        if score >= self.gate or (score >= self.floor and not live_owner):
            self.n["auto"] += 1
            entry["verdict"] = "AUTO" if score >= self.gate else "AUTO (review off)"
            self.log.appendleft(entry)
            return "go", f"council {score:.2f}"
        if score >= self.floor:
            if any(q["symbol"] == sym and q["desk"] == desk for q in self.queue.values()):
                return "no", "already waiting for owner"
            if len(self.queue) >= self.max_queue:
                weakest = min(self.queue.values(), key=lambda q: q["score"])
                if weakest["score"] >= score:
                    self.n["weak"] += 1
                    entry["verdict"] = "DROPPED (your queue is full of stronger ideas)"
                    self.log.appendleft(entry)
                    return "no", "council: queue full"
                self.queue.pop(weakest["id"])
                self.n["expired"] += 1
            self.seq += 1
            qid = f"H{self.seq}"
            self.queue[qid] = {**entry, "id": qid, "intent": it, "expires": ctx.cycle + self.wait, "t": time.time()}
            self.n["handoff"] += 1
            entry["verdict"] = "HAND-OFF to owner"
            self.log.appendleft(entry)
            return "handoff", f"council {score:.2f}: waiting for your YES"
        self.n["weak"] += 1
        entry["verdict"] = "REJECT (weak case)"
        self.log.appendleft(entry)
        return "no", f"council: weak case {score:.2f} < {self.floor}"

    # ---------------------------------------------------------------- owner answers (from the app)
    def answer(self, qid, yes):
        if qid not in self.queue:
            return "That proposal already expired or was answered."
        self.answers.append((qid, bool(yes)))
        return "Got it: " + ("approving" if yes else "rejecting") + f" {qid} on the next candle."

    def set_review(self, on):
        self.human_review = bool(on)
        return "Human review is ON: medium-confidence trades wait for your YES." if on else \
            "Human review is OFF: medium-confidence trades go ahead automatically (paper only)."

    def pending(self, ctx_cycle):
        """Pop expired items; return owner-approved intents to execute now."""
        go = []
        while self.answers:
            qid, yes = self.answers.popleft()
            q = self.queue.pop(qid, None)
            if not q:
                continue
            if yes:
                self.n["owner_yes"] += 1
                go.append(q)
            else:
                self.n["owner_no"] += 1
            self.log.appendleft({**{k: q[k] for k in ("cycle", "desk", "symbol", "side", "score", "seats")},
                                 "verdict": "OWNER YES" if yes else "OWNER NO"})
        for qid in [k for k, q in self.queue.items() if q["expires"] < ctx_cycle]:
            q = self.queue.pop(qid)
            self.n["expired"] += 1
            self.log.appendleft({**{k: q[k] for k in ("cycle", "desk", "symbol", "side", "score", "seats")},
                                 "verdict": "EXPIRED (no answer, not chased)"})
        return go

    def state(self):
        return {"gate": self.gate, "floor": self.floor, "calibration": self.calibration, "human_review": self.human_review, "counts": self.n,
                "queue": [{k: q[k] for k in ("id", "cycle", "desk", "symbol", "side", "score", "seats", "expires")}
                          for q in self.queue.values()],
                "log": list(self.log)[:30]}
