"""SMART-MONEY 'TRADERS' for the copy team on real prices.

In the simulator the copy team watches 12 simulated traders. On real prices those don't exist, so the copy team sat
idle (and 4 desks that depend on it never traded). Here each REAL crowd / smart-money source becomes a 'trader' that
takes a position every hour. The copy team then does what it always does: measures each one's skill on real
outcomes (Wilson / t-stat) and copies only those that prove themselves.

Sources (public, key-free; any that fail are skipped):
  okx_top_accounts   OKX top traders, long/short ACCOUNT ratio           follow
  okx_top_positions  OKX top traders, long/short POSITION ratio          follow
  okx_all_accounts   OKX all accounts long/short ratio (the crowd)       follow (copy team decides if it's skill or a fade)
  okx_takers         OKX taker buy vs sell volume                        follow
  bybit_crowd        Bybit account buy/sell ratio                        follow
  funding_fade       average funding across perps (pipe)                 fade the crowded side
  usd_premium        USD-venue vs USDT-venue premium (pipe)              follow
  korea_premium      Upbit/Bithumb price vs world price (pipe)           fade a hot Korean premium
  news_crowd         publisher-weighted headline mood (pipe)             follow
  fear_greed         crypto fear & greed (pipe)                          fade extremes
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

H = 3   # hold for 3 candles, like the simulated traders


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 SwarmTrader"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


class LiveTraders:
    NAMES = ["okx_top_accounts", "okx_top_positions", "okx_all_accounts", "okx_takers", "bybit_crowd",
             "funding_fade", "usd_premium", "korea_premium", "news_crowd", "fear_greed"]

    def __init__(self, engine):
        self.e = engine
        self.traders = [(n, None) for n in self.NAMES]          # same shape as SimTraders (name, hidden skill)
        self.last = {}                                           # name -> {symbol: side} last views, for the UI
        self.errors = {}

    # ---------------------------------------------------------------- one source = one 'trader'
    def _okx_ratio(self, kind, sym):
        if kind == "okx_all_accounts":
            d = _get(f"https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy={sym}&period=1H")["data"]
            r = float(d[0][1])
        elif kind == "okx_takers":
            d = _get(f"https://www.okx.com/api/v5/rubik/stat/taker-volume?ccy={sym}&instType=CONTRACTS&period=1H")["data"]
            sell, buy = float(d[0][1]), float(d[0][2])
            r = buy / sell if sell else 1.0
        else:
            ep = "long-short-account-ratio-contract-top-trader" if kind == "okx_top_accounts" else \
                "long-short-position-ratio-contract-top-trader"
            d = _get(f"https://www.okx.com/api/v5/rubik/stat/contracts/{ep}?instId={sym}-USDT-SWAP&period=1H")["data"]
            r = float(d[0][1])
        return 1 if r > 1.08 else -1 if r < 0.92 else 0

    def _bybit(self, sym):
        d = _get(f"https://api.bybit.com/v5/market/account-ratio?category=linear&symbol={sym}USDT&period=1h&limit=1")
        x = d["result"]["list"][0]
        b, s = float(x["buyRatio"]), float(x["sellRatio"])
        return 1 if b > s * 1.08 else -1 if s > b * 1.08 else 0

    def _pipe_view(self, kind, sym):
        p = self.e.pipe
        if not p:
            return 0
        feeds = p._live()
        c = p.consensus(sym, feeds)
        if kind == "funding_fade":
            f = c and c.get("funding")
            return 0 if f is None else (-1 if f > 0.0001 else 1 if f < -0.00005 else 0)
        if kind == "usd_premium":
            u = c and c.get("usd_premium")
            return 0 if u is None else (1 if u > 0.0006 else -1 if u < -0.0006 else 0)
        if kind == "korea_premium":
            kr = [f["value"] for f in feeds if f["id"] in (f"upbit:{sym}", f"bithumb:{sym}")]
            if not kr or not c:
                return 0
            prem = sum(kr) / len(kr) / c["price"] - 1
            return -1 if prem > 0.02 else 1 if prem < -0.005 else 0
        if kind == "news_crowd":
            nm = p.news_mood(sym, hours=3)
            return 0 if nm["scored"] < 2 else (1 if nm["mood"] > 0.15 else -1 if nm["mood"] < -0.15 else 0)
        if kind == "fear_greed":
            f = next((x["value"] for x in feeds if x["id"] == "feargreed:index"), None)
            return 0 if f is None else (1 if f < 30 else -1 if f > 70 else 0)
        return 0

    def _view(self, name, sym):
        try:
            if name.startswith("okx_"):
                return self._okx_ratio(name, sym)
            if name == "bybit_crowd":
                return self._bybit(sym)
            return self._pipe_view(name, sym)
        except Exception as ex:
            self.errors[name] = f"{type(ex).__name__}: {str(ex)[:60]}"
            return 0

    # ---------------------------------------------------------------- same interface as SimTraders.step
    def step(self, cycle):
        e = self.e
        if e.phase != "live":                 # history replay: today's crowd data says nothing about old candles
            return
        m, b = e.market, e.b
        for p in b.q("SELECT * FROM trader_pos WHERE status='open' AND close_cycle<=?", (cycle,)):
            px = m.last(p["symbol"])
            b.x("UPDATE trader_pos SET exit=?,pnl=?,status='closed' WHERE id=?", (px, p["side"] * (px / p["entry"] - 1), p["id"]))
        jobs = [(n, s) for n in self.NAMES for s in m.symbols]
        with ThreadPoolExecutor(max_workers=8) as ex:
            views = dict(zip(jobs, ex.map(lambda j: self._view(*j), jobs)))
        for (n, s), side in views.items():
            self.last.setdefault(n, {})[s] = side
            if not side:
                continue
            has = b.q("SELECT COUNT(*) n FROM trader_pos WHERE trader=? AND symbol=? AND status='open'", (n, s))[0]["n"]
            if not has:
                b.x("INSERT INTO trader_pos(trader,symbol,side,entry,open_cycle,close_cycle,status) VALUES(?,?,?,?,?,?,'open')",
                    (n, s, side, m.last(s), cycle, cycle + H))

    def state(self):
        return {"views": self.last, "errors": self.errors}
