"""Polymarket prediction desk (PAPER MONEY ONLY).

The macro team forecasts where a Polymarket market's YES price will be in a few hours. If its forecast differs
from the crowd price by more than a margin it takes a paper position (buy YES or buy NO) and is scored when the
position closes. Nothing here places a real bet: real Polymarket trading needs a crypto wallet, and Polymarket
restricts several regions (check the rules for where you live before ever doing that).
Forecast = crowd price + a nudge from (a) the recent move of the mapped asset and (b) Claude's world-events bias.
"""
import math

from strategies import mean, rets, std


class PolyBook:
    def __init__(self, cfg, brain, bankroll=1000.0, stake=0.02, edge=0.03, hold_hours=4, max_open=6, spread=0.01):
        self.cfg, self.b = cfg, brain
        self.bankroll0 = self.cash = bankroll
        self.stake, self.edge, self.hold, self.max_open, self.spread = stake, edge, hold_hours, max_open, spread
        self.open, self.closed = {}, []
        self.hits = self.n = 0
        self.by_mkt = {}                       # market id -> [bets, pnl]: markets we keep losing on get benched
        self.benched = ""

    def _fair(self, m, macro, market):
        """Our estimate of YES probability, or None if we have no view."""
        sh = []
        for s in m["symbols"]:
            syms = market.symbols if s == "ALL" else [s]
            for x in syms:
                c = [k["c"] for k in market.candles[x][-60:]]
                if len(c) < 20:
                    continue
                r = rets(c)
                sd = std(r)
                if sd:
                    sh.append((c[-1] / c[-8] - 1) / (sd * math.sqrt(7)))
        if not sh:
            return None
        z = mean(sh)
        fair = m["p"] + m["sign"] * 0.08 * math.tanh(z)
        b = (macro.world.get("bias") or {}).get(m["symbols"][0]) if m["symbols"] and m["symbols"][0] != "ALL" else None
        if b:
            fair += m["sign"] * 0.04 * b["direction"] * b["confidence"]
        return max(0.02, min(0.98, fair))

    def step(self, cycle, market, macro):
        if macro is None or getattr(self.cfg, "t0", 0) and False:
            return
        hz = self.cfg.cycles_per_hour * self.hold
        for mid, t in list(self.open.items()):                       # close old positions
            m = macro.markets.get(mid)
            if m is None or cycle - t["cycle"] >= hz:
                p = m["p"] if m else t["entry_p"]
                px = p if t["side"] == "YES" else 1 - p
                exit_px = max(0.01, px - self.spread / 2)
                pnl = t["shares"] * (exit_px - t["price"])
                self.cash += t["stake"] + pnl
                self.n += 1
                self.hits += pnl > 0
                r = self.by_mkt.setdefault(mid, [0, 0.0])
                r[0] += 1
                r[1] += pnl
                t.update(exit=exit_px, pnl=pnl, closed=cycle)
                self.closed = (self.closed + [t])[-40:]
                del self.open[mid]
        if self.n >= 30 and self.hits / self.n < 0.45:
            self.benched = f"benched: only {self.hits}/{self.n} winning bets, no edge shown"
        elif self.cash + sum(t['stake'] for t in self.open.values()) < self.bankroll0 * 0.85:
            self.benched = "benched: paper bankroll is down 15%"
        else:
            self.benched = ""
        if self.benched or len(self.open) >= self.max_open:
            return
        for mid, m in sorted(macro.markets.items(), key=lambda kv: -kv[1]["vol"]):
            r = self.by_mkt.get(mid)
            if r and r[0] >= 6 and r[1] < 0:
                continue
            if mid in self.open or not m["sign"] or len(self.open) >= self.max_open or m["vol"] < 1000:
                continue
            fair = self._fair(m, macro, market)
            if fair is None or abs(fair - m["p"]) < self.edge:
                continue
            side = "YES" if fair > m["p"] else "NO"
            px = (m["p"] if side == "YES" else 1 - m["p"]) + self.spread / 2
            stake = min(self.cash, self.bankroll0 * self.stake)
            if stake < 1 or px >= 0.97:
                continue
            self.cash -= stake
            self.open[mid] = {"id": mid, "q": m["question"][:80], "side": side, "price": px, "entry_p": m["p"], "fair": round(fair, 3),
                              "stake": stake, "shares": stake / px, "cycle": cycle}
        return

    def state(self, macro):
        eq = self.cash
        for mid, t in self.open.items():
            m = macro.markets.get(mid) if macro else None
            p = m["p"] if m else t["entry_p"]
            eq += t["shares"] * (p if t["side"] == "YES" else 1 - p)
        return {"paper_only": True, "bankroll_start": self.bankroll0, "equity": round(eq, 2), "pnl": round(eq - self.bankroll0, 2),
                "closed": self.n, "hit_rate": round(self.hits / self.n, 3) if self.n else None,
                "open": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in t.items()} for t in self.open.values()],
                "recent": [{"q": t["q"], "side": t["side"], "pnl": round(t["pnl"], 2)} for t in self.closed[-8:]],
                "synthetic": bool(macro and macro.synthetic), "status": self.benched or "betting"}
