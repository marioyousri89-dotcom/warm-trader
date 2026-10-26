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
START = {"BTC": 60000.0, "ETH": 3000.0, "SOL": 150.0, "XRP": 2.0, "BNB": 600.0, "DOGE": 0.15, "ADA": 0.6, "LINK": 15.0, "PAXG": 2600.0, "SPYX": 600.0, "QQQX": 520.0, "NVDAX": 180.0, "TSLAX": 300.0}
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
    """Real prices, one candle per cycle (1-hour candles by default: 1- and 15-minute moves were smaller than fees). Data only.
    Tries several public exchanges, because some block cloud servers (Binance answers HTTP 418 to Render)."""
    kind = "live"
    PAIRS = {"okx": "{s}-USDT", "bybit": "{s}USDT", "coinbase": "{s}-USD", "kraken": "{s}USD", "binance": "{s}USDT"}

    def __init__(self, symbols, keep=1200, pair_suffix="USDT", bar=60):
        self.symbols = list(symbols)
        self.bar = bar                                   # minutes per candle
        self.keep = keep
        self.candles = {s: [] for s in self.symbols}
        self._last = {}
        self._last_open_time = {s: 0 for s in self.symbols}
        self.src = {}
        self.errors = {}
        ok = []
        for s in self.symbols:
            try:
                rows = self._klines(s, 1000)[:-1]
            except Exception as e:
                print(f"[live] {s}: no exchange has it ({str(e)[:60]}), skipping this market")
                continue
            if len(rows) < 300:
                print(f"[live] {s}: only {len(rows)} candles of history, skipping this market")
                continue
            for k in rows:
                self._add(s, k)
            self._last[s] = self.candles[s][-1]["c"]
            ok.append(s)
        if not ok:
            raise RuntimeError("no market had live prices")
        n = min(len(self.candles[s]) for s in ok)          # line every market up on the same hours
        for s in ok:
            self.candles[s] = self.candles[s][-n:]
        self.symbols = ok
        self.candles = {s: self.candles[s] for s in ok}
        self.history = {s: list(v) for s, v in self.candles.items()}   # real history the academy replays
        self.cycle = min(len(v) for v in self.candles.values())        # live cycles continue after the history
        self.source = ", ".join(sorted(set(self.src.values())))
        self.on_wait = None          # engine's FAST LANE, called every ~60 s between candles
        self._last_wait = 0.0

    def _okxbar(self):
        return {60: "1H", 120: "2H", 240: "4H"}.get(self.bar, f"{self.bar}m")

    def _binbar(self):
        return {60: "1h", 120: "2h", 240: "4h"}.get(self.bar, f"{self.bar}m")

    @staticmethod
    def _get(url):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 SwarmTrader"})
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read())

    # each returns ascending [[open_ms, o, h, l, c, v], ...]; the last row may still be forming
    def _okx(self, s, limit):
        inst = f"{s}-USDT"
        rows = self._get(f"https://www.okx.com/api/v5/market/candles?instId={inst}&bar={self._okxbar()}&limit=300")["data"]
        while len(rows) < limit:
            more = self._get(f"https://www.okx.com/api/v5/market/history-candles?instId={inst}&bar={self._okxbar()}&limit=100&after={rows[-1][0]}")["data"]
            if not more:
                break
            rows += more
        return [[int(r[0]), r[1], r[2], r[3], r[4], r[5]] for r in rows[:limit]][::-1]

    def _bybit(self, s, limit):
        rows = self._get(f"https://api.bybit.com/v5/market/kline?category=spot&symbol={s}USDT&interval={self.bar}&limit={min(limit, 1000)}")["result"]["list"]
        return [[int(r[0]), r[1], r[2], r[3], r[4], r[5]] for r in rows][::-1]

    def _coinbase(self, s, limit):
        out, end = [], None
        while len(out) < limit:
            g = self.bar * 60
            q = "" if end is None else "&end=" + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(end)) + \
                "&start=" + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(end - 299 * g))
            rows = self._get(f"https://api.exchange.coinbase.com/products/{s}-USD/candles?granularity={g}{q}")
            if not rows:
                break
            out += rows
            end = rows[-1][0] - g
            if limit <= 300:
                break
        out = sorted({r[0]: r for r in out}.values())[-limit:]
        return [[int(r[0]) * 1000, r[3], r[2], r[1], r[4], r[5]] for r in out]

    def _kraken(self, s, limit):
        d = self._get(f"https://api.kraken.com/0/public/OHLC?pair={'XBT' if s == 'BTC' else s}USD&interval={self.bar}")["result"]
        rows = next(v for k, v in d.items() if k != "last")
        return [[int(r[0]) * 1000, r[1], r[2], r[3], r[4], r[6]] for r in rows][-limit:]

    def _binance(self, s, limit):
        for host in ("https://data-api.binance.vision", "https://api.binance.com"):
            try:
                return self._get(f"{host}/api/v3/klines?symbol={s}USDT&interval={self._binbar()}&limit={limit}")
            except Exception as e:
                err = e
        raise err

    def _klines(self, s, limit):
        order = ["okx", "bybit", "coinbase", "kraken", "binance"]
        if s in self.src:                       # stick with the exchange that worked, fall back if it stops
            order.remove(self.src[s])
            order.insert(0, self.src[s])
        err = None
        for name in order:
            try:
                rows = getattr(self, "_" + name)(s, limit)
                if len(rows) >= min(limit, 3):
                    if self.src.get(s) != name:
                        print(f"[live] {s} prices from {name}")
                    self.src[s] = name
                    return rows
            except Exception as e:
                err = e
                self.errors[name] = f"{type(e).__name__}: {str(e)[:80]}"
        raise err or RuntimeError("no exchange returned candles")

    def _add(self, s, k):
        if int(k[0]) <= self._last_open_time[s]:
            return False
        self._last_open_time[s] = int(k[0])
        self.candles[s].append({"o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5]), "t": int(k[0]) / 1000.0})
        del self.candles[s][:-self.keep]
        return True

    def step(self):
        """Blocks until a new closed candle exists. Network hiccups are retried, never fatal."""
        while True:
            fresh = 0
            for s in self.symbols:
                try:
                    ks = self._klines(s, 3)
                except Exception as e:
                    print(f"[live] {s}: all exchanges failed ({str(e)[:80]}), retrying")
                    continue
                if self._add(s, ks[-2]):          # ks[-1] is the still-forming candle
                    fresh += 1
            if fresh:
                break
            for _ in range(30):                   # new-candle check every 30 s; FAST LANE reacts within ~1 s of news/prices
                ev = getattr(self, "event", None)
                hot = ev is not None and ev.is_set()
                if self.on_wait and time.time() - self._last_wait >= 1:      # EVERY SECOND
                    if hot:
                        ev.clear()
                    self._last_wait = time.time()
                    try:
                        self.on_wait(hot)
                    except Exception as e:
                        print("[fast lane] error:", str(e)[:120])
                time.sleep(1)
        for s in self.symbols:
            self._last[s] = self.candles[s][-1]["c"]
        self.cycle += 1

    def last(self, s):
        return self._last[s]
