"""Market data.

SimMarket     a simulated multi-asset market with regimes (up / down / range / volatile).
SimTraders    12 simulated traders the copy-trading agents can watch. Some have a hidden
              edge, most are luck, two are bad. Agents never see the hidden skill.
LiveMarket    OPTIONAL real prices from Binance's public API (data only, still paper
              trading). Not tested in the build sandbox (no outbound network there).
"""
import json
import random
import time
import urllib.request

from sessions import SIM_VOL, session_at
from collections import deque

REG = {"up": (0.0015, 0.006), "down": (-0.0015, 0.006), "range": (0.0, 0.004), "volatile": (0.0, 0.015)}
START = {"BTC": 60000.0, "ETH": 3000.0, "SOL": 150.0}
H = 3


class SimMarket:
    kind = "sim"

    def __init__(self, symbols, seed=7, keep=600):
        self.rng = random.Random(seed)
        self.symbols = list(symbols)
        self.cycle = 0
        self.keep = keep
        self.candles = {s: [] for s in self.symbols}
        self.regime = {s: self.rng.choice(list(REG)) for s in self.symbols}
        self._gp = {s: START.get(s, 100.0) for s in self.symbols}
        self._anchor = dict(self._gp)
        self._prev = {s: 0.0 for s in self.symbols}
        self._last = dict(self._gp)
        self.queue = {s: deque() for s in self.symbols}
        for s in self.symbols:
            for _ in range(H):
                self.queue[s].append(self._gen(s))

    def _gen(self, s):
        rng = self.rng
        if rng.random() < 0.03:
            self.regime[s] = rng.choice(list(REG))
        mu, sig = REG[self.regime[s]]
        sig *= SIM_VOL[session_at(self.cycle * 900.0)]      # 15-min candles; London/NY overlap is the most volatile
        r = mu + sig * rng.gauss(0, 1)
        if self.regime[s] in ("up", "down"):
            r += 0.12 * self._prev[s]
        if self.regime[s] == "range":
            r += -0.15 * (self._gp[s] / self._anchor[s] - 1)
        r = max(-0.08, min(0.08, r))
        self._gp[s] *= 1 + r
        self._anchor[s] += 0.05 * (self._gp[s] - self._anchor[s])
        self._prev[s] = r
        return r

    def step(self):
        rng = self.rng
        for s in self.symbols:
            r = self.queue[s].popleft()
            self.queue[s].append(self._gen(s))
            o = self._last[s]
            c = o * (1 + r)
            sig = REG[self.regime[s]][1]
            h = max(o, c) * (1 + abs(rng.gauss(0, 1)) * sig * 0.4)
            l = min(o, c) * (1 - abs(rng.gauss(0, 1)) * sig * 0.4)
            v = 100 * (1 + abs(r) / sig * 1.5) * rng.lognormvariate(0, 0.3)
            self.candles[s].append({"o": o, "h": h, "l": l, "c": c, "v": v, "t": self.cycle * 900.0})
            if len(self.candles[s]) > self.keep:
                del self.candles[s][0]
            self._last[s] = c
        self.cycle += 1

    def last(self, s):
        return self._last[s]

    def future_ret(self, s, k=H):
        p = 1.0
        for r in list(self.queue[s])[:k]:
            p *= 1 + r
        return p - 1


class SimTraders:
    """Traders open a position that lasts H candles. Copy agents only SEE a position one
    candle after it opens (realistic lag), so they get only part of the move."""

    def __init__(self, brain, market, seed=11):
        self.rng = random.Random(seed)
        self.m, self.b = market, brain
        skills = [0.22, 0.15, 0.08] + [0.0] * 7 + [-0.10, -0.18]   # hidden from agents
        self.rng.shuffle(skills)
        self.traders = [(f"trader_{i + 1:02d}", sk) for i, sk in enumerate(skills)]

    def step(self, cycle):
        for name, sk in self.traders:
            for p in self.b.q("SELECT * FROM trader_pos WHERE trader=? AND status='open' AND close_cycle<=?",
                              (name, cycle)):
                px = self.m.last(p["symbol"])
                self.b.x("UPDATE trader_pos SET exit=?,pnl=?,status='closed' WHERE id=?",
                         (px, p["side"] * (px / p["entry"] - 1), p["id"]))
            has_open = self.b.q("SELECT COUNT(*) n FROM trader_pos WHERE trader=? AND status='open'", (name,))[0]["n"]
            if not has_open and self.rng.random() < 0.35:
                s = self.rng.choice(self.m.symbols)
                d = 1 if self.m.future_ret(s) > 0 else -1
                if self.rng.random() > 0.5 + sk:
                    d = -d
                self.b.x("INSERT INTO trader_pos(trader,symbol,side,entry,open_cycle,close_cycle,status)"
                         " VALUES(?,?,?,?,?,?, 'open')", (name, s, d, self.m.last(s), cycle, cycle + H))


class ReplayMarket:
    """Replays recorded candles one at a time (no look-ahead): used by the academy on real history."""
    kind = "replay"

    def __init__(self, symbols, hist, start, keep=600):
        self.symbols = list(symbols)
        self.hist, self.cycle, self.keep = hist, start, keep
        self.candles = {s: list(hist[s][:start]) for s in self.symbols}
        self._last = {s: self.candles[s][-1]["c"] for s in self.symbols}

    def step(self):
        for s in self.symbols:
            c = self.hist[s][self.cycle]
            self.candles[s].append(c)
            if len(self.candles[s]) > self.keep:
                del self.candles[s][0]
            self._last[s] = c["c"]
        self.cycle += 1

    def last(self, s):
        return self._last[s]


class LiveMarket:
    """Real prices, one candle per cycle (1-minute klines). Data only; no copy traders here."""
    kind = "live"

    def __init__(self, symbols, keep=1200, pair_suffix="USDT"):
        self.symbols = list(symbols)
        self.suffix = pair_suffix
        self.keep = keep
        self.candles = {s: [] for s in self.symbols}
        self._last = {}
        self._last_open_time = {s: 0 for s in self.symbols}
        for s in self.symbols:
            for k in self._klines(s, 1000)[:-1]:
                self._add(s, k)
            self._last[s] = self.candles[s][-1]["c"]
        self.history = {s: list(v) for s, v in self.candles.items()}   # real history the academy replays
        self.cycle = min(len(v) for v in self.candles.values())        # live cycles continue after the history

    def _klines(self, s, limit):
        path = f"/api/v3/klines?symbol={s}{self.suffix}&interval=1m&limit={limit}"
        err = None
        for host in ("https://data-api.binance.vision", "https://api.binance.com"):   # first one is the public market-data mirror (works from more regions)
            try:
                with urllib.request.urlopen(host + path, timeout=10) as r:
                    return json.loads(r.read())
            except Exception as e:
                err = e
        raise err

    def _add(self, s, k):
        if k[0] <= self._last_open_time[s]:
            return False
        self._last_open_time[s] = k[0]
        self.candles[s].append({"o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5]), "t": k[0] / 1000.0})
        del self.candles[s][:-self.keep]
        return True

    def step(self):
        """Blocks until a new closed 1-minute candle exists for every symbol."""
        while True:
            fresh = 0
            for s in self.symbols:
                ks = self._klines(s, 3)
                if self._add(s, ks[-2]):          # ks[-1] is the still-forming candle
                    fresh += 1
            if fresh:
                break
            time.sleep(3)
        for s in self.symbols:
            self._last[s] = self.candles[s][-1]["c"]
        self.cycle += 1

    def last(self, s):
        return self._last[s]
