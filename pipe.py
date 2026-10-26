"""The MARKET PIPE: one shared intake that every page and every team can read.

It polls ~70 public, key-free providers in the background and splits what they return into
individual FEEDS (one feed = one provider x one instrument / headline source / indicator), e.g.
"okx:BTC", "kraken:ETH", "bybit_perp:SOL", "news:coindesk", "world:^N225", "fx:JPY", "kalshi:<market>".

Honest counting: `declared` is every feed the pipe asks for; `live` is the feeds that actually
returned a value in the last 15 minutes. Both numbers are shown on the MARKET PIPE page.

All data is read-only. Text that comes in (headlines, market questions) is DATA, never instructions.
"""
import json
import re
import statistics
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) SwarmTrader-MarketPipe/1.0", "Accept": "*/*"}
LIVE_WINDOW = 900   # a feed counts as live if it reported within 15 minutes

COINS = ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "TRX", "AVAX", "LINK", "DOT", "TON", "SHIB", "LTC",
         "BCH", "NEAR", "UNI", "APT", "ICP", "ETC", "FIL", "ATOM", "XLM", "HBAR", "ARB", "OP", "INJ", "SUI",
         "SEI", "PEPE", "AAVE", "MKR", "RENDER", "IMX", "GRT", "ALGO", "SAND", "MANA", "AXS", "STX", "TIA",
         "WLD", "JUP", "ONDO", "ENA", "LDO", "CRV", "SNX", "COMP", "EGLD", "XTZ", "EOS", "KAS", "FET", "THETA",
         "VET", "QNT", "FLOW", "CHZ", "BONK", "PAXG", "SPYX", "QQQX", "NVDAX", "TSLAX"]
COINSET = set(COINS)
NAMES = {"BTC": "bitcoin", "ETH": "ethereum|ether", "SOL": "solana", "XRP": "xrp|ripple", "BNB": "bnb|binance coin",
         "DOGE": "dogecoin", "ADA": "cardano", "LINK": "chainlink", "PAXG": "gold|paxg|bullion", "SPYX": "S&P 500|S&P|Wall Street|stocks",
         "QQQX": "nasdaq|tech stocks", "NVDAX": "nvidia", "TSLAX": "tesla"}
ALIAS = {"XBT": "BTC", "XDG": "DOGE", "RNDR": "RENDER"}
USD_QUOTES = ("USDT", "USDC", "USD", "FDUSD")

WORLD = [  # (yahoo symbol, label, kind)
    ("^GSPC", "S&P 500", "index"), ("^DJI", "Dow Jones", "index"), ("^IXIC", "Nasdaq", "index"),
    ("^RUT", "Russell 2000", "index"), ("^VIX", "VIX fear index", "vol"), ("^GSPTSE", "Toronto TSX", "index"),
    ("^BVSP", "Brazil Bovespa", "index"), ("^MXX", "Mexico IPC", "index"), ("^FTSE", "London FTSE 100", "index"),
    ("^GDAXI", "Germany DAX", "index"), ("^FCHI", "France CAC 40", "index"), ("^STOXX50E", "Euro Stoxx 50", "index"),
    ("^IBEX", "Spain IBEX", "index"), ("FTSEMIB.MI", "Italy FTSE MIB", "index"), ("^AEX", "Amsterdam AEX", "index"),
    ("^SSMI", "Swiss SMI", "index"), ("^N225", "Tokyo Nikkei 225", "index"), ("^HSI", "Hong Kong Hang Seng", "index"),
    ("000001.SS", "Shanghai Composite", "index"), ("^KS11", "Korea KOSPI", "index"), ("^TWII", "Taiwan TAIEX", "index"),
    ("^BSESN", "India Sensex", "index"), ("^NSEI", "India Nifty 50", "index"), ("^AXJO", "ASX 200", "index"),
    ("^NZ50", "NZX 50", "index"), ("^STI", "Singapore STI", "index"), ("^JKSE", "Jakarta", "index"),
    ("^TASI.SR", "Saudi Tadawul", "index"), ("GC=F", "Gold", "commodity"), ("SI=F", "Silver", "commodity"),
    ("CL=F", "WTI oil", "commodity"), ("BZ=F", "Brent oil", "commodity"), ("NG=F", "Natural gas", "commodity"),
    ("HG=F", "Copper", "commodity"), ("ZW=F", "Wheat", "commodity"), ("ZC=F", "Corn", "commodity"),
    ("DX-Y.NYB", "US dollar index", "fx"), ("^TNX", "US 10y yield", "rates"), ("^IRX", "US 3m bill", "rates"),
    ("^TYX", "US 30y yield", "rates"), ("EURUSD=X", "EUR/USD", "fx"), ("JPY=X", "USD/JPY", "fx"),
    ("GBPUSD=X", "GBP/USD", "fx"), ("AUDUSD=X", "AUD/USD", "fx"), ("CNY=X", "USD/CNY", "fx"),
    ("AAPL", "Apple", "stock"), ("MSFT", "Microsoft", "stock"), ("NVDA", "Nvidia", "stock"), ("AMZN", "Amazon", "stock"),
    ("GOOGL", "Alphabet", "stock"), ("META", "Meta", "stock"), ("TSLA", "Tesla", "stock"), ("COIN", "Coinbase", "stock"),
    ("MSTR", "Strategy (MSTR)", "stock"), ("IBIT", "iShares Bitcoin ETF", "stock"), ("ETHA", "iShares Ether ETF", "stock"),
]
RISK_ON = ("^GSPC", "^IXIC", "^N225", "^GDAXI", "^HSI", "^AXJO", "^FTSE")

FX = ["EUR", "JPY", "GBP", "AUD", "CAD", "CHF", "CNY", "HKD", "NZD", "SEK", "KRW", "SGD", "NOK", "MXN", "INR",
      "RUB", "ZAR", "TRY", "BRL", "TWD", "DKK", "PLN", "THB", "IDR", "HUF", "CZK", "ILS", "CLP", "PHP", "AED",
      "COP", "SAR", "MYR", "RON", "ARS", "VND", "NGN", "EGP", "PKR", "KWD"]

NEWS = [
    ("coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"), ("cointelegraph", "https://cointelegraph.com/rss"),
    ("decrypt", "https://decrypt.co/feed"), ("theblock", "https://www.theblock.co/rss.xml"),
    ("bitcoinmagazine", "https://bitcoinmagazine.com/.rss/full/"), ("newsbtc", "https://www.newsbtc.com/feed/"),
    ("bitcoinist", "https://bitcoinist.com/feed/"), ("utoday", "https://u.today/rss"),
    ("beincrypto", "https://beincrypto.com/feed/"), ("cryptonews", "https://cryptonews.com/news/feed/"),
    ("dailyhodl", "https://dailyhodl.com/feed/"), ("coinjournal", "https://coinjournal.net/feed/"), ("ambcrypto", "https://ambcrypto.com/feed/"),
    ("cnbc-markets", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069"),
    ("cnbc-economy", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"),
    ("cnbc-finance", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"),
    ("marketwatch-top", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("marketwatch-pulse", "https://feeds.content.dowjones.io/public/rss/mw_marketpulse"),
    ("wsj-markets", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
    ("investing", "https://www.investing.com/rss/news.rss"),
    ("bbc-business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("bbc-world", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("guardian-business", "https://www.theguardian.com/business/rss"),
    ("nyt-business", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"),
    ("economist-finance", "https://www.economist.com/finance-and-economics/rss.xml"),
    ("seekingalpha", "https://seekingalpha.com/market_currents.xml"),
    ("fed", "https://www.federalreserve.gov/feeds/press_all.xml"), ("ecb", "https://www.ecb.europa.eu/rss/press.html"),
    ("abc-au-business", "https://www.abc.net.au/news/feed/51892/rss.xml"),
]

POS = set("surge surges soar soars rally rallies gain gains jump jumps rise rises record bull bullish beat beats upgrade "
          "approval approved inflow inflows breakout high highs climbs boost adoption partnership launch etf buy buys "
          "rebound recovers recovery strong optimism".split())
NEG = set("plunge plunges crash crashes slump slumps fall falls drop drops tumble tumbles sink sinks bear bearish miss "
          "misses downgrade hack hacked exploit lawsuit sue sues ban bans outflow outflows liquidation liquidations low "
          "lows fear fears selloff sell-off weak recession default fraud probe investigation warning collapse".split())


def _get(url, timeout=12):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _json(url, timeout=12):
    return json.loads(_get(url, timeout))


def _f(x):
    try:
        v = float(x)
        return v if v == v else None
    except Exception:
        return None


def base_of(sym):
    """'BTC-USDT', 'BTC_USDT', 'BTCUSDT', 'btcusdt', 'BTC/USD', 'XXBTZUSD' -> 'BTC' (or None)."""
    s = re.sub(r"[-_/:]", "", str(sym).upper())
    if s.endswith("ZUSD"):
        b = s[:-4]
        b = b[1:] if len(b) == 4 and b[0] == "X" else b
        b = ALIAS.get(b, b)
        return b if b in COINSET else None
    for q in USD_QUOTES:
        if s.endswith(q) and len(s) > len(q):
            b = s[:-len(q)]
            if len(b) == 4 and b[0] == "X" and b[1:] in ("XBT", "XDG", "ETH", "XRP", "LTC", "ETC", "XLM"):
                b = b[1:]
            b = ALIAS.get(b, b)
            return b if b in COINSET else None
    return None


def quote_rank(sym):
    s = re.sub(r"[-_/:]", "", str(sym).upper())
    for i, q in enumerate(("USDT", "USD", "USDC")):
        if s.endswith(q):
            return i
    return 9


# ------------------------------------------------------------------ price parsers -> [(coin, price, chg, quote_vol, pair)]
def p_okx(d):
    return [(r["instId"], _f(r["last"]), (_f(r["last"]) / _f(r["open24h"]) - 1) if _f(r.get("open24h")) else None,
             _f(r.get("volCcy24h"))) for r in d["data"]]


def p_kraken(d):
    out = []
    for k, r in d["result"].items():
        last, op = _f(r["c"][0]), _f(r.get("o"))
        out.append((k, last, (last / op - 1) if op else None, (_f(r["v"][1]) or 0) * (last or 0)))
    return out


def p_kucoin(d):
    return [(r["symbol"], _f(r.get("last")), _f(r.get("changeRate")), _f(r.get("volValue"))) for r in d["data"]["ticker"]]


def p_gate(d):
    return [(r["currency_pair"], _f(r.get("last")), (_f(r.get("change_percentage")) or 0) / 100, _f(r.get("quote_volume")))
            for r in d]


def p_bitget(d):
    return [(r["symbol"], _f(r.get("lastPr")), _f(r.get("change24h")), _f(r.get("usdtVolume") or r.get("quoteVolume")))
            for r in d["data"]]


def p_bin(d):   # binance / mexc share the format
    return [(r["symbol"], _f(r.get("lastPrice")),
             (_f(r["lastPrice"]) / _f(r["openPrice"]) - 1) if _f(r.get("openPrice")) else None, _f(r.get("quoteVolume")))
            for r in d]


def p_bybit(d):
    return [(r["symbol"], _f(r.get("lastPrice")),
             (_f(r["lastPrice"]) / _f(r["prevPrice24h"]) - 1) if _f(r.get("prevPrice24h")) else None, _f(r.get("turnover24h")))
            for r in d["result"]["list"]]


def p_htx(d):
    return [(r["symbol"], _f(r.get("close")), (_f(r["close"]) / _f(r["open"]) - 1) if _f(r.get("open")) else None,
             _f(r.get("vol"))) for r in d["data"]]


def p_cdc(d):
    return [(r["i"], _f(r.get("a")), _f(r.get("c")), _f(r.get("vv"))) for r in d["result"]["data"]]


def p_bitfinex(d):
    out = []
    for r in d:
        if isinstance(r, list) and len(r) > 8 and str(r[0]).startswith("t"):
            out.append((str(r[0])[1:], _f(r[7]), _f(r[6]), (_f(r[8]) or 0) * (_f(r[7]) or 0)))
    return out


def p_bitstamp(d):
    return [(r["pair"], _f(r.get("last")), (_f(r["last"]) / _f(r["open"]) - 1) if _f(r.get("open")) else None,
             (_f(r.get("volume")) or 0) * (_f(r.get("last")) or 0)) for r in d]


def p_gemini(d):
    return [(r["pair"], _f(r.get("price")), _f(r.get("percentChange24h")), None) for r in d]


def p_coinbase(d):
    out = []
    for cur, rate in d["data"]["rates"].items():
        r = _f(rate)
        if r and cur in COINSET:
            out.append((cur + "USD", 1 / r, None, None))
    return out


def p_coingecko(d):
    return [(r["symbol"].upper() + "USD", _f(r.get("current_price")), (_f(r.get("price_change_percentage_24h")) or 0) / 100,
             _f(r.get("total_volume"))) for r in d]


def p_coinlore(d):
    return [(r["symbol"].upper() + "USD", _f(r.get("price_usd")), (_f(r.get("percent_change_24h")) or 0) / 100,
             _f(r.get("volume24"))) for r in d["data"]]


PRICE = [  # (name, url, parser, poll seconds)
    ("okx", "https://www.okx.com/api/v5/market/tickers?instType=SPOT", p_okx, 30),
    ("bybit", "https://api.bybit.com/v5/market/tickers?category=spot", p_bybit, 30),
    ("coinbase", "https://api.coinbase.com/v2/exchange-rates?currency=USD", p_coinbase, 30),
    ("kraken", "https://api.kraken.com/0/public/Ticker", p_kraken, 45),
    ("kucoin", "https://api.kucoin.com/api/v1/market/allTickers", p_kucoin, 45),
    ("gate", "https://api.gateio.ws/api/v4/spot/tickers", p_gate, 60),
    ("bitget", "https://api.bitget.com/api/v2/spot/market/tickers", p_bitget, 45),
    ("mexc", "https://api.mexc.com/api/v3/ticker/24hr", p_bin, 60),
    ("htx", "https://api.huobi.pro/market/tickers", p_htx, 45),
    ("cryptocom", "https://api.crypto.com/exchange/v1/public/get-tickers", p_cdc, 45),
    ("bitfinex", "https://api-pub.bitfinex.com/v2/tickers?symbols=ALL", p_bitfinex, 60),
    ("bitstamp", "https://www.bitstamp.net/api/v2/ticker/", p_bitstamp, 60),
    ("gemini", "https://api.gemini.com/v1/pricefeed", p_gemini, 45),
    ("coingecko", "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250", p_coingecko, 900),
    ("coinlore", "https://api.coinlore.net/api/tickers/?start=0&limit=100", p_coinlore, 180),
]


# ------------------------------------------------------------------ derivatives -> [(pair, funding, open_interest_usd)]
def d_bybit(d):
    return [(r["symbol"], _f(r.get("fundingRate")), _f(r.get("openInterestValue"))) for r in d["result"]["list"]]


def d_bitget(d):
    return [(r["symbol"], _f(r.get("fundingRate")), (_f(r.get("holdingAmount")) or 0) * (_f(r.get("lastPr")) or 0))
            for r in d["data"]]


def d_gate(d):
    return [(r["contract"], _f(r.get("funding_rate")), None) for r in d]


def d_okx(d):
    return [(r["instId"].replace("-SWAP", ""), None, _f(r.get("oiUsd"))) for r in d["data"]]


DERIV = [
    ("bybit_perp", "https://api.bybit.com/v5/market/tickers?category=linear", d_bybit, 60),
    ("bitget_perp", "https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES", d_bitget, 60),
    ("gate_perp", "https://api.gateio.ws/api/v4/futures/usdt/tickers", d_gate, 90),
    ("okx_oi", "https://www.okx.com/api/v5/public/open-interest?instType=SWAP", d_okx, 90),
]


class MarketPipe:
    def __init__(self, start=True):
        self.lock = threading.Lock()
        self.event = threading.Event()      # set the moment new headlines or prices land: the engine reacts within ~1 s
        self.feeds = {}          # id -> {cat, provider, label, value, chg, extra, ts}
        self.providers = {}      # name -> {cat, ok, err, last, ms, n, every, due}
        self.headlines = []      # {t, src, title, s}
        self.declared = set()
        self.jobs = []
        for name, url, fn, every in PRICE:
            self._job(name, "crypto", every, lambda u=url, f=fn, n=name: self._price(n, u, f))
            self.declared |= {f"{name}:{c}" for c in COINS}
        for name, url, fn, every in DERIV:
            self._job(name, "derivatives", every, lambda u=url, f=fn, n=name: self._deriv(n, u, f))
            self.declared |= {f"{name}:{c}" for c in COINS}
        for i in range(0, len(WORLD), 20):
            chunk = WORLD[i:i + 20]
            self._job(f"yahoo-{i // 20 + 1}", "world", 120, lambda c=chunk: self._world(c))
        self.declared |= {f"world:{s}" for s, _, _ in WORLD}
        self._job("frankfurter", "fx", 600, self._fx_frankfurter)
        self._job("er-api", "fx", 900, self._fx_erapi)
        self.declared |= {f"fx:{c}" for c in FX} | {f"ecbfx:{c}" for c in FX[:30]}
        for src, url in NEWS:
            self._job("news:" + src, "news", 150, lambda s=src, u=url: self._news(s, u))
            self.declared.add("news:" + src)
        self._job("polymarket", "prediction", 300, self._polymarket)
        self._job("kalshi", "prediction", 300, self._kalshi)
        self._job("manifold", "prediction", 600, self._manifold)
        self.declared |= {f"polymarket:{i}" for i in range(40)} | {f"kalshi:{i}" for i in range(30)} | {f"manifold:{i}" for i in range(20)}
        self._job("feargreed", "sentiment", 900, self._fng)
        self._job("mempool", "onchain", 120, self._mempool)
        self._job("blockchain", "onchain", 600, self._blockchain)
        self._job("defillama", "defi", 900, self._llama)
        self._job("stablecoins", "defi", 900, self._stables)
        self._job("cg-global", "crypto", 1800, self._cg_global)
        self.declared |= {"feargreed:index", "mempool:fastest", "mempool:hour", "mempool:difficulty", "blockchain:hashrate",
                          "blockchain:tx24h", "stablecoins:total", "global:mcap", "global:btc_dominance"} | \
            {f"defillama:{i}" for i in range(20)}
        self.publishers = set()
        try:
            from pipe_more import install          # hundreds more sources: news first
            install(self)
        except Exception as e:
            print("[pipe] expansion failed to load:", e)
        self.started = time.time()
        if start:
            threading.Thread(target=self._loop, daemon=True).start()

    # ---------------------------------------------------------------- scheduler: SIX pipelines -> ONE shared pipe
    LANES = {"prices": 6, "futures": 2, "news": 5, "economy": 3, "world": 2, "signals": 2}   # parallel workers each
    LANE_OF_CAT = {"crypto": "prices", "derivatives": "futures", "news": "news", "social": "news",
                   "world": "world", "fx": "world", "onchain": "world", "defi": "world", "sentiment": "signals",
                   "prediction": "signals", "newtokens": "signals"}

    def _job(self, name, cat, every, fn, lane=None):
        lane = lane or ("economy" if name in getattr(self, "econ_jobs", ()) else self.LANE_OF_CAT.get(cat, "world"))
        self.providers[name] = {"name": name, "cat": cat, "lane": lane, "ok": None, "err": "", "last": 0.0, "ms": 0,
                                "n": 0, "every": every, "due": 0.0}
        self.jobs.append((name, fn))

    def _loop(self):
        """Each pipeline has its own scheduler and its own workers, so a slow news site can never hold up prices."""
        from collections import deque
        self.lane_log = {k: deque(maxlen=4000) for k in self.LANES}
        for lane, workers in self.LANES.items():
            jobs = [(n, f) for n, f in self.jobs if self.providers[n]["lane"] == lane]
            threading.Thread(target=self._lane_loop, args=(lane, jobs, workers), daemon=True).start()

    def _lane_loop(self, lane, jobs, workers):
        pool = ThreadPoolExecutor(max_workers=workers)
        running = set()
        step = max(0.15, 45.0 / max(1, len(jobs)))      # spread each lane's first round over ~45 s
        for k, (name, _) in enumerate(jobs):
            self.providers[name]["due"] = time.time() + k * step
        while True:
            now = time.time()
            for name, fn in jobs:
                p = self.providers[name]
                if name in running or now < p["due"]:
                    continue
                running.add(name)
                p["due"] = now + p["every"]
                pool.submit(self._run, name, fn, running)
            time.sleep(0.5)

    def _run(self, name, fn, running):
        p = self.providers[name]
        t0 = time.time()
        try:
            n = fn() or 0
            p.update(ok=True, err="", n=n)
            log = getattr(self, "lane_log", {}).get(p["lane"])
            if log is not None:
                log.append((time.time(), n))
        except Exception as e:
            p.update(ok=False, err=f"{type(e).__name__}: {str(e)[:90]}")
            if "429" in str(e) or "418" in str(e) or "403" in str(e):
                p["due"] = time.time() + max(p["every"] * 3, 300)      # back off politely
        finally:
            p["ms"] = int((time.time() - t0) * 1000)
            p["last"] = time.time()
            running.discard(name)

    def lanes(self):
        now, out = time.time(), []
        for lane, workers in self.LANES.items():
            ps = [p for p in self.providers.values() if p["lane"] == lane]
            log = [x for x in getattr(self, "lane_log", {}).get(lane, []) if now - x[0] < 60]
            out.append({"lane": lane, "workers": workers, "sources": len(ps), "ok": sum(1 for p in ps if p["ok"]),
                        "fail": sum(1 for p in ps if p["ok"] is False), "runs_min": len(log),
                        "items_min": sum(x[1] for x in log),
                        "last": max((p["last"] for p in ps if p["ok"]), default=0)})
        return out

    def _put(self, fid, cat, provider, label, value, chg=None, extra=None):
        if value is None:
            return
        with self.lock:
            self.feeds[fid] = {"id": fid, "cat": cat, "provider": provider, "label": label, "value": value,
                               "chg": chg, "extra": extra, "ts": time.time()}

    # ---------------------------------------------------------------- fetchers
    def _price(self, name, url, fn):
        rows = fn(_json(url, 15))
        best = {}
        for pair, px, chg, vol in rows:
            c = base_of(pair)
            if not c or not px or px <= 0:
                continue
            rk = quote_rank(pair)
            if c not in best or rk < best[c][0]:
                best[c] = (rk, pair, px, chg, vol)
        for c, (_, pair, px, chg, vol) in best.items():
            self._put(f"{name}:{c}", "crypto", name, f"{c} on {name} ({pair})", px, chg, {"vol": vol})
        pass
        return len(best)

    def _deriv(self, name, url, fn):
        n = 0
        for pair, fund, oi in fn(_json(url, 15)):
            c = base_of(pair)
            if not c:
                continue
            self._put(f"{name}:{c}", "derivatives", name, f"{c} perp on {name.split('_')[0]}",
                      fund if fund is not None else oi, None, {"funding": fund, "oi_usd": oi})
            n += 1
        return n

    def _world(self, chunk):
        syms = ",".join(s for s, _, _ in chunk)
        d = None
        for host in ("query1", "query2"):
            try:
                d = _json(f"https://{host}.finance.yahoo.com/v7/finance/spark?symbols={urllib.request.quote(syms)}"
                          "&range=1d&interval=15m", 15)
                break
            except Exception:
                if host == "query2":
                    raise
        lab = {s: (l, k) for s, l, k in chunk}
        n = 0
        for r in d["spark"]["result"]:
            try:
                meta = r["response"][0]["meta"]
                px, prev = _f(meta.get("regularMarketPrice")), _f(meta.get("chartPreviousClose") or meta.get("previousClose"))
            except Exception:
                continue
            s = r["symbol"]
            if px:
                l, k = lab.get(s, (s, "index"))
                self._put(f"world:{s}", "world", "yahoo", l, px, (px / prev - 1) if prev else None, {"kind": k, "symbol": s})
                n += 1
        return n

    def _fx_frankfurter(self):
        d = _json("https://api.frankfurter.app/latest?from=USD")
        n = 0
        for c, v in d.get("rates", {}).items():
            if c in FX[:30] or c in FX:
                self._put(f"ecbfx:{c}", "fx", "frankfurter (ECB)", f"USD/{c} (ECB)", _f(v))
                n += 1
        return n

    def _fx_erapi(self):
        d = _json("https://open.er-api.com/v6/latest/USD")
        n = 0
        for c in FX:
            v = _f(d.get("rates", {}).get(c))
            if v:
                self._put(f"fx:{c}", "fx", "er-api", f"USD/{c}", v)
                n += 1
        return n

    def _news(self, src, url):
        root = ET.fromstring(_get(url, 15))
        items = list(root.iter("item")) or [e for e in root.iter() if e.tag.endswith("entry")]
        fresh = []
        for it in items[:25]:
            t = (it.findtext("title") or it.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
            t = re.sub(r"<[^>]+>|\s+", " ", t).strip()[:180]
            if t:
                fresh.append(t)
        self.add_headlines([(t, src) for t in fresh], ("reddit:" + src[2:]) if src.startswith("r/") else "news:" + src)
        return len(fresh)

    def add_headlines(self, items, feed_id):
        """items: [(title, publisher)]. New titles go to the top of the shared news tape."""
        now = time.time()
        with self.lock:
            seen = self._seen if hasattr(self, "_seen") else set(h["title"] for h in self.headlines)
            self._seen = seen
            add = []
            for t, pub in items:
                k = t.lower()
                if k not in seen:
                    seen.add(k)
                    add.append({"t": now, "src": pub, "title": t, "s": self.tone(t), "via": feed_id})
            self.headlines = (add + self.headlines)[:2500]
            if add:
                self.event.set()
            if len(seen) > 20000:
                self._seen = set(h["title"].lower() for h in self.headlines)
        moods = [self.tone(t) for t, _ in items]
        cat = "social" if feed_id.startswith("reddit:") else "news"
        self._put(feed_id, cat, feed_id.split(":", 1)[0], f"{feed_id.split(':', 1)[1]} headlines", len(items),
                  statistics.mean(moods) if moods else 0.0, {"latest": items[0][0] if items else "", "new": len(add)})

    @staticmethod
    def tone(title):
        w = re.findall(r"[a-z\-]+", title.lower())
        p, n = sum(x in POS for x in w), sum(x in NEG for x in w)
        return 0.0 if p == n else (p - n) / (p + n)

    def _polymarket(self):
        rows = _json("https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=40&order=volume24hr&ascending=false")
        for i, r in enumerate(rows[:40]):
            try:
                outs, prices = json.loads(r["outcomes"]), json.loads(r["outcomePrices"])
                p = _f(prices[outs.index("Yes")] if "Yes" in outs else prices[0])
            except Exception:
                continue
            self._put(f"polymarket:{i}", "prediction", "polymarket", str(r.get("question", ""))[:140], p, None,
                      {"vol24": _f(r.get("volume24hr"))})
        return len(rows)

    def _kalshi(self):
        d = _json("https://api.elections.kalshi.com/trade-api/v2/markets?status=open&limit=200")
        ms = sorted(d.get("markets", []), key=lambda m: -(_f(m.get("volume_24h")) or 0))[:30]
        for i, m in enumerate(ms):
            p = _f(m.get("last_price"))
            self._put(f"kalshi:{i}", "prediction", "kalshi", str(m.get("title", ""))[:140],
                      p / 100 if p is not None else None, None, {"vol24": _f(m.get("volume_24h"))})
        return len(ms)

    def _manifold(self):
        rows = _json("https://api.manifold.markets/v0/search-markets?term=&sort=liquidity&filter=open&limit=20")
        for i, r in enumerate(rows[:20]):
            self._put(f"manifold:{i}", "prediction", "manifold", str(r.get("question", ""))[:140], _f(r.get("probability")))
        return len(rows)

    def _fng(self):
        d = _json("https://api.alternative.me/fng/?limit=1")["data"][0]
        self._put("feargreed:index", "sentiment", "alternative.me", f"Crypto fear & greed ({d.get('value_classification')})",
                  _f(d["value"]))
        return 1

    def _mempool(self):
        f = _json("https://mempool.space/api/v1/fees/recommended")
        self._put("mempool:fastest", "onchain", "mempool.space", "BTC fee, fastest (sat/vB)", _f(f.get("fastestFee")))
        self._put("mempool:hour", "onchain", "mempool.space", "BTC fee, 1 hour (sat/vB)", _f(f.get("hourFee")))
        d = _json("https://mempool.space/api/v1/difficulty-adjustment")
        self._put("mempool:difficulty", "onchain", "mempool.space", "Next difficulty change %", _f(d.get("difficultyChange")))
        return 3

    def _blockchain(self):
        d = _json("https://api.blockchain.info/stats")
        self._put("blockchain:hashrate", "onchain", "blockchain.com", "BTC hash rate (GH/s)", _f(d.get("hash_rate")))
        self._put("blockchain:tx24h", "onchain", "blockchain.com", "BTC transactions 24h", _f(d.get("n_tx")))
        return 2

    def _llama(self):
        rows = sorted(_json("https://api.llama.fi/v2/chains", 20), key=lambda r: -(_f(r.get("tvl")) or 0))[:20]
        for i, r in enumerate(rows):
            self._put(f"defillama:{i}", "defi", "defillama", f"{r.get('name')} TVL (USD)", _f(r.get("tvl")))
        return len(rows)

    def _stables(self):
        d = _json("https://stablecoins.llama.fi/stablecoins?includePrices=false", 20)
        tot = sum((_f((a.get("circulating") or {}).get("peggedUSD")) or 0) for a in d.get("peggedAssets", []))
        self._put("stablecoins:total", "defi", "defillama", "Stablecoin supply (USD)", tot)
        return 1

    def _cg_global(self):
        d = _json("https://api.coingecko.com/api/v3/global")["data"]
        self._put("global:mcap", "crypto", "coingecko", "Total crypto market cap (USD)", _f(d["total_market_cap"]["usd"]),
                  (_f(d.get("market_cap_change_percentage_24h_usd")) or 0) / 100)
        self._put("global:btc_dominance", "crypto", "coingecko", "BTC dominance %", _f(d["market_cap_percentage"]["btc"]))
        return 2

    # ---------------------------------------------------------------- reading the pipe
    def _live(self):
        now = time.time()
        with self.lock:
            return [f for f in self.feeds.values() if now - f["ts"] < LIVE_WINDOW]

    def consensus(self, coin, feeds=None):
        feeds = feeds if feeds is not None else self._live()
        px = [f for f in feeds if f["cat"] == "crypto" and f["id"].endswith(":" + coin) and not f["id"].startswith("global")]
        if not px:
            return None
        vals = [f["value"] for f in px]
        med = statistics.median(vals)
        good = [f for f in px if abs(f["value"] / med - 1) < 0.05]        # throw away broken / wrong-asset quotes
        vals = [f["value"] for f in good] or vals
        chg = [f["chg"] for f in good if f["chg"] is not None]
        usd = [f["value"] for f in good if f["provider"] in ("coinbase", "kraken", "bitstamp", "gemini")]
        usdt = [f["value"] for f in good if f["provider"] in ("okx", "bybit", "kucoin", "gate", "bitget", "mexc", "htx", "binance")]
        fund = [f["extra"]["funding"] for f in feeds if f["cat"] == "derivatives" and f["id"].endswith(":" + coin)
                and f["extra"] and f["extra"].get("funding") is not None]
        return {"coin": coin, "price": statistics.median(vals), "sources": len(vals),
                "spread": (max(vals) / min(vals) - 1) if len(vals) > 1 else 0.0,
                "chg24": statistics.median(chg) if chg else None,
                "usd_premium": (statistics.median(usd) / statistics.median(usdt) - 1) if usd and usdt else None,
                "funding": statistics.mean(fund) if fund else None}

    def news_mood(self, coin=None, hours=6):
        """Mood of recent headlines, weighted by each publisher's earned track record (see selfdev.py)."""
        now = time.time()
        with self.lock:
            hs = [h for h in self.headlines if now - h["t"] < hours * 3600]
        if coin:
            pat = re.compile(r"\b(" + coin.lower() + ("|" + NAMES[coin] if coin in NAMES else "") + r")\b", re.I)
            hs = [h for h in hs if pat.search(h["title"])]
        w = getattr(self, "pub_weight", None) or (lambda p: 1.0)
        sc = [(h["s"], w(h["src"])) for h in hs if h["s"]]
        tw = sum(x[1] for x in sc)
        return {"n": len(hs), "scored": len(sc), "mood": sum(a * b for a, b in sc) / tw if tw else 0.0}

    def world_mood(self, feeds=None):
        feeds = feeds if feeds is not None else self._live()
        w = {f["extra"]["symbol"]: f for f in feeds if f["cat"] == "world" and f["extra"]}
        risk = [w[s]["chg"] for s in RISK_ON if s in w and w[s]["chg"] is not None]
        vix = w.get("^VIX", {}).get("chg") if "^VIX" in w else None
        return {"n": len(risk), "risk": statistics.mean(risk) if risk else None, "vix": vix}

    def summary(self):
        """Small block that goes to EVERY page. Cached for 5 s so many phones don't slow the server."""
        c = getattr(self, "_sum_cache", None)
        if c and time.time() - c[0] < 5:
            return c[1]
        out = self._summary()
        self._sum_cache = (time.time(), out)
        return out

    def _summary(self):
        feeds = self._live()
        by = {}
        for f in feeds:
            by[f["cat"]] = by.get(f["cat"], 0) + 1
        provs = list(self.providers.values())
        fng = next((f for f in feeds if f["id"] == "feargreed:index"), None)
        top = [c for c in (self.consensus(k, feeds) for k in COINS[:8]) if c]
        ok = [p for p in provs if p["ok"]]
        with self.lock:
            latest = [{"t": h["t"], "src": h["src"], "title": h["title"][:120], "s": h["s"]} for h in self.headlines[:15]]
        last_fetch = max((p["last"] for p in provs if p["ok"]), default=0)
        return {"declared": len(self.declared), "live": len(feeds), "by_cat": by,
                "publishers": len(self.publishers), "latest": latest, "last_fetch": last_fetch,
                "lanes": self.lanes(), "stream": getattr(self, "ws_stats", None),
                "sources": len([p for p in ok if not p["name"].startswith("gnews:")]) + len(self.publishers),
                "news_per_hour": self.news_mood(hours=1)["n"],
                "providers_ok": sum(1 for p in provs if p["ok"]), "providers": len(provs),
                "providers_failing": sum(1 for p in provs if p["ok"] is False),
                "top": top, "fng": fng and {"value": fng["value"], "label": fng["label"]},
                "news": self.news_mood(), "world": self.world_mood(feeds),
                "warming_up": time.time() - self.started < 90}

    def full(self):
        """Everything, for the MARKET PIPE / WORLD / NEWS / STOCKS & CRYPTO pages."""
        feeds = self._live()
        now = time.time()
        with self.lock:
            heads = list(self.headlines[:200])
            allf = sorted(self.feeds.values(), key=lambda f: f["id"])
        coins = [c for c in (self.consensus(k, feeds) for k in COINS) if c]
        return {"summary": self.summary(), "coins": coins, "publishers": sorted(self.publishers)[:1500],
                "newtokens": [f for f in feeds if f["cat"] == "newtokens"],
                "world": sorted([f for f in feeds if f["cat"] == "world"], key=lambda f: f["extra"]["kind"]),
                "fx": sorted([f for f in feeds if f["cat"] == "fx"], key=lambda f: f["id"]),
                "prediction": [f for f in feeds if f["cat"] == "prediction"],
                "other": [f for f in feeds if f["cat"] in ("sentiment", "onchain", "defi") or f["id"].startswith("global:")],
                "headlines": heads,
                "providers": sorted(self.providers.values(), key=lambda p: (p["cat"], p["name"])),
                "feeds": [{"id": f["id"], "cat": f["cat"], "label": f["label"], "value": f["value"], "chg": f["chg"],
                           "age": int(now - f["ts"])} for f in allf]}

    # ---------------------------------------------------------------- what the pipe agents vote
    def signals(self, symbols):
        """Cached 5 s: the fast lane can ask every second without re-reading 2,500 headlines each time."""
        key = tuple(symbols)
        c = getattr(self, "_sig_cache", None)
        if c and c[0] == key and time.time() - c[1] < 5:
            return c[2]
        out = self._signals(symbols)
        self._sig_cache = (key, time.time(), out)
        return out

    def _signals(self, symbols):
        """Opinions for the pipe agents (one agent per idea). Each is scored by the brain like any other agent."""
        out = []
        feeds = self._live()
        wm = self.world_mood(feeds)
        fng = next((f["value"] for f in feeds if f["id"] == "feargreed:index"), None)
        coins = [c for c in (self.consensus(k, feeds) for k in COINS) if c and c["chg24"] is not None]
        breadth = sum(1 for c in coins if c["chg24"] > 0) / len(coins) if len(coins) >= 15 else None
        for s in symbols:
            c = self.consensus(s, feeds)
            nm = self.news_mood(s, hours=4)
            if nm["scored"] >= 3 and abs(nm["mood"]) >= 0.3:
                out.append(("pipe_news", s, 1 if nm["mood"] > 0 else -1, min(0.9, 0.4 + abs(nm["mood"]) / 2),
                            f"{nm['scored']} scored headlines, mood {nm['mood']:+.2f}"))
            hr, day = self.news_mood(s, hours=1), self.news_mood(s, hours=24)
            base = max(1.0, day["n"] / 24)
            if hr["n"] >= 5 and hr["n"] >= 3 * base and abs(hr["mood"]) >= 0.2:      # sudden burst of stories
                out.append(("pipe_buzz", s, 1 if hr["mood"] > 0 else -1, min(0.85, 0.5 + abs(hr["mood"]) / 2),
                            f"news burst: {hr['n']} stories in 1h vs {base:.1f}/h normal, mood {hr['mood']:+.2f}"))
            if c and c["funding"] is not None and (c["funding"] > 0.0003 or c["funding"] < -0.0001):
                out.append(("pipe_funding", s, -1 if c["funding"] > 0 else 1, 0.5, f"avg funding {c['funding']:+.5f} (crowded side fades)"))
            if c and c["usd_premium"] is not None and abs(c["usd_premium"]) > 0.0012:
                out.append(("pipe_premium", s, 1 if c["usd_premium"] > 0 else -1, 0.5, f"USD-venue premium {c['usd_premium']:+.3%}"))
            if c and c["sources"] >= 4 and c["spread"] > 0.004:
                pass   # wide cross-exchange spread = unreliable moment; no vote
            if fng is not None and (fng <= 20 or fng >= 80):
                out.append(("pipe_feargreed", s, 1 if fng <= 20 else -1, 0.4, f"fear & greed {fng:.0f} (contrarian)"))
            if wm["risk"] is not None and wm["n"] >= 3 and abs(wm["risk"]) > 0.006:
                v = 1 if wm["risk"] > 0 else -1
                if wm["vix"] is not None and wm["vix"] * v > 0.05:
                    v = 0                                   # stocks up but fear up too: mixed, stay out
                if v:
                    out.append(("pipe_world", s, v, 0.45, f"world indices {wm['risk']:+.2%}, VIX {wm['vix'] if wm['vix'] is None else round(wm['vix'] * 100, 1)}%"))
            if breadth is not None and (breadth >= 0.75 or breadth <= 0.25):
                out.append(("pipe_breadth", s, 1 if breadth >= 0.75 else -1, 0.45, f"{breadth:.0%} of {len(coins)} coins up 24h"))
        return out


class OfflinePipe(MarketPipe):
    """Used by tests: never touches the network."""

    def __init__(self):
        super().__init__(start=False)
