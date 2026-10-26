"""POLYMARKET DESK v2 (PAPER MONEY ONLY - Polymarket is blocked in Australia; this never places a real bet).

Scans the top ~150 Polymarket markets every 2 minutes, compares them with Kalshi and Manifold (from the market pipe),
and runs NINE strategy teams. Each team has its own paper bankroll share, is scored on its own results, earns more
capital when it wins and is benched when it keeps losing:

  1 momentum      odds moving fast in the last hour -> follow
  2 reversion     odds spiked too far too fast -> fade part of it
  3 longshot      very unlikely outcomes are usually over-priced (favourite-longshot bias) -> buy NO
  4 favourite     near-certain outcomes close to their end date -> buy YES (small, steady)
  5 cross_venue   same question priced differently on Kalshi/Manifold -> move toward the other venues
  6 news          a burst of headlines about the question + odds moving -> follow
  7 volume        a jump in trading volume with a price move -> follow the money
  8 crypto_link   crypto-price questions -> follow our live crypto momentum
  9 carry         steady favourites (60-85%) with days left and low noise -> buy YES
"""
import json
import math
import re
import threading
import time
import urllib.request
from collections import deque

STRATS = ["momentum", "reversion", "longshot", "favourite", "cross_venue", "news", "volume", "crypto_link", "carry"]
STOP = set("will the a an of in on by to be is at for and or with than more less before after end 2025 2026 2027 "
           "does do yes no".split())
CRYPTO = {"bitcoin": "BTC", "btc": "BTC", "ethereum": "ETH", "eth": "ETH", "solana": "SOL", "xrp": "XRP",
          "dogecoin": "DOGE", "bnb": "BNB"}


def words(q):
    return {w for w in re.findall(r"[a-z0-9]+", q.lower()) if w not in STOP and len(w) > 2}


class PolyDesk:
    def __init__(self, engine, bankroll=1000.0, start=True):
        self.e = engine
        self.bankroll0 = self.cash = bankroll
        self.mk = {}                       # id -> {q, p, vol, end, hist deque[(t,p)], vhist deque[(t,vol)], w}
        self.open = {}                     # key -> position
        self.closed = deque(maxlen=200)
        self.stats = {s: {"n": 0, "w": 0, "pnl": 0.0, "open": 0, "benched": False} for s in STRATS}
        self.err = ""
        self.last_fetch = 0.0
        self.lock = threading.Lock()
        self.synthetic = False
        if start:
            threading.Thread(target=self._loop, daemon=True).start()

    # ---------------------------------------------------------------- data
    def _loop(self):
        while True:
            try:
                self._fetch()
            except Exception as ex:
                self.err = f"{type(ex).__name__}: {str(ex)[:80]}"
            time.sleep(120)

    def _fetch(self):
        url = "https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=150&order=volume24hr&ascending=false"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 SwarmTrader"})
        with urllib.request.urlopen(req, timeout=20) as r:
            rows = json.loads(r.read())
        now = time.time()
        with self.lock:
            for r in rows:
                try:
                    outs, prices = json.loads(r["outcomes"]), json.loads(r["outcomePrices"])
                    p = float(prices[outs.index("Yes")] if "Yes" in outs else prices[0])
                except Exception:
                    continue
                mid = str(r.get("id"))
                m = self.mk.setdefault(mid, {"id": mid, "q": str(r.get("question", ""))[:140], "hist": deque(maxlen=400),
                                             "vhist": deque(maxlen=400)})
                end = r.get("endDate") or r.get("end_date_iso")
                try:
                    m["end"] = time.mktime(time.strptime(end[:19], "%Y-%m-%dT%H:%M:%S")) if end else None
                except Exception:
                    m["end"] = None
                m["p"], m["vol"] = p, float(r.get("volume24hr") or 0)
                m["w"] = words(m["q"])
                m["hist"].append((now, p))
                m["vhist"].append((now, m["vol"]))
        self.last_fetch = now

    @staticmethod
    def _ago(h, secs, now):
        v = None
        for t, x in h:
            if t <= now - secs:
                v = x
            else:
                break
        return v

    # ---------------------------------------------------------------- the nine teams
    def _ideas(self, now):
        e, ideas = self.e, []
        pipe = e.pipe
        others = [f for f in pipe._live() if f["cat"] == "prediction" and f["provider"] in ("kalshi", "manifold")] if pipe else []
        for f in others:
            f.setdefault("_w", words(f["label"]))
        heads = []
        if pipe:
            with pipe.lock:
                heads = [(h["t"], words(h["title"])) for h in pipe.headlines[:1500] if now - h["t"] < 7200]
        for m in list(self.mk.values()):
            p, h = m.get("p"), m["hist"]
            if p is None or p <= 0.01 or p >= 0.99 or m["vol"] < 2000:
                continue
            p1 = self._ago(h, 3600, now)
            d1 = None if p1 is None else p - p1
            days = (m["end"] - now) / 86400 if m.get("end") else None
            if d1 is not None and 0.03 <= abs(d1) < 0.08:
                ideas.append(("momentum", m, "YES" if d1 > 0 else "NO", f"odds {d1:+.2f} in 1h"))
            if d1 is not None and abs(d1) >= 0.10:
                ideas.append(("reversion", m, "NO" if d1 > 0 else "YES", f"spike {d1:+.2f} in 1h, fading"))
            if p < 0.07 and m["vol"] > 20000:
                ideas.append(("longshot", m, "NO", f"long shot priced {p:.0%}"))
            if p > 0.88 and days is not None and 0 < days < 3:
                ideas.append(("favourite", m, "YES", f"{p:.0%} favourite, {days:.1f} days left"))
            if 0.6 <= p <= 0.85 and days is not None and 3 <= days <= 30 and len(h) >= 10:
                seg = [x for t, x in h if now - t < 6 * 3600]
                if seg and max(seg) - min(seg) < 0.03:
                    ideas.append(("carry", m, "YES", f"steady {p:.0%}, {days:.0f} days left"))
            if others and m["w"]:
                best = None
                for f in others:
                    if not f["_w"] or f["value"] is None:
                        continue
                    j = len(m["w"] & f["_w"]) / len(m["w"] | f["_w"])
                    if j >= 0.5 and (best is None or j > best[0]):
                        best = (j, f)
                if best and abs(best[1]["value"] - p) >= 0.07:
                    o = best[1]
                    ideas.append(("cross_venue", m, "YES" if o["value"] > p else "NO",
                                  f"{o['provider']} says {o['value']:.0%} vs Polymarket {p:.0%}"))
            if heads and m["w"] and d1 is not None and abs(d1) >= 0.02:
                hits = sum(1 for _, w in heads if len(m["w"] & w) >= 2)
                if hits >= 3:
                    ideas.append(("news", m, "YES" if d1 > 0 else "NO", f"{hits} headlines in 2h, odds {d1:+.2f}"))
            v1 = self._ago(m["vhist"], 3600, now)
            if v1 and m["vol"] > v1 * 1.3 and d1 is not None and abs(d1) >= 0.02:
                ideas.append(("volume", m, "YES" if d1 > 0 else "NO", f"volume +{m['vol'] / v1 - 1:.0%} in 1h"))
            sym = next((CRYPTO[w] for w in m["w"] if w in CRYPTO), None)
            if sym and sym in e.market.symbols and re.search(r"above|reach|hit|over|higher|exceed", m["q"], re.I):
                c = e.market.candles[sym]
                if len(c) > 8:
                    mv = c[-1]["c"] / c[-7]["c"] - 1
                    if abs(mv) > 0.015:
                        ideas.append(("crypto_link", m, "YES" if mv > 0 else "NO", f"{sym} {mv:+.1%} over 6h"))
        return ideas

    def _weight(self, s):
        st = self.stats[s]
        if st["n"] < 8:
            return 1.0
        wr = st["w"] / st["n"]
        return max(0.3, min(2.0, 1.0 + (wr - 0.5) * 3 + (0.5 if st["pnl"] > 0 else -0.3)))

    # ---------------------------------------------------------------- called every minute (fast lane) and every candle
    def tick(self):
        now = time.time()
        with self.lock:
            for k, t in list(self.open.items()):                  # mark, close after 6h or near resolution
                m = self.mk.get(t["mid"])
                p = m["p"] if m else t["entry_p"]
                val = p if t["side"] == "YES" else 1 - p
                if now - t["t"] >= 6 * 3600 or val >= 0.99 or val <= 0.01:
                    exit_px = max(0.0, val - 0.005)
                    pnl = t["shares"] * (exit_px - t["price"])
                    self.cash += t["stake"] + pnl
                    st = self.stats[t["strat"]]
                    st["n"] += 1
                    st["w"] += pnl > 0
                    st["pnl"] += pnl
                    st["open"] -= 1
                    t.update(exit=exit_px, pnl=pnl)
                    self.closed.appendleft(t)
                    del self.open[k]
            for s, st in self.stats.items():
                st["benched"] = st["n"] >= 15 and st["pnl"] < 0 and st["w"] / st["n"] < 0.45
            if self.e.phase != "live" or not self.mk:
                return
            for s, m, side, why in self._ideas(now):
                st = self.stats[s]
                k = f"{s}:{m['id']}"
                if st["benched"] or k in self.open or st["open"] >= 8 or len(self.open) >= 60:
                    continue
                if any(t["mid"] == m["id"] for t in self.open.values()):   # one position per market across teams
                    continue
                px = (m["p"] if side == "YES" else 1 - m["p"]) + 0.005
                if px >= 0.97 or px <= 0.02:
                    continue
                stake = min(self.cash, self.bankroll0 * 0.015 * self._weight(s))
                if stake < 1:
                    continue
                self.cash -= stake
                st["open"] += 1
                self.open[k] = {"strat": s, "mid": m["id"], "q": m["q"][:90], "side": side, "price": px, "entry_p": m["p"],
                                "fair": None, "why": why, "stake": stake, "shares": stake / px, "t": now}

    def step(self, cycle, market, macro):
        self.tick()

    def state(self, macro=None):
        with self.lock:
            eq = self.cash
            for t in self.open.values():
                m = self.mk.get(t["mid"])
                p = m["p"] if m else t["entry_p"]
                eq += t["shares"] * (p if t["side"] == "YES" else 1 - p)
            n = sum(s["n"] for s in self.stats.values())
            w = sum(s["w"] for s in self.stats.values())
            return {"paper_only": True, "bankroll_start": self.bankroll0, "equity": round(eq, 2), "pnl": round(eq - self.bankroll0, 2),
                    "closed": n, "hit_rate": round(w / n, 3) if n else None, "markets": len(self.mk),
                    "last_fetch": self.last_fetch, "error": self.err, "synthetic": False,
                    "open": [{"q": t["q"], "side": t["side"], "price": round(t["price"], 3), "fair": round(t["entry_p"], 3),
                              "strat": t["strat"], "why": t["why"]} for t in sorted(self.open.values(), key=lambda t: -t["t"])],
                    "recent": [{"q": t["q"], "side": t["side"], "strat": t["strat"], "pnl": round(t["pnl"], 2)} for t in list(self.closed)[:15]],
                    "strategies": [{"team": s, "bets": st["n"], "win": round(st["w"] / st["n"], 3) if st["n"] else None,
                                    "pnl": round(st["pnl"], 2), "open": st["open"], "weight": round(self._weight(s), 2),
                                    "status": "benched" if st["benched"] else "betting"} for s, st in self.stats.items()],
                    "status": "betting"}
