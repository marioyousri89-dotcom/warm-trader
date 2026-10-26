"""Pipe expansion: hundreds more sources, news first.

- ~110 Google News searches (each pulls headlines from many different publishers; every publisher is counted)
- ~55 direct news / central-bank / regulator RSS feeds, ~9 Reddit communities
- ~35 more exchanges worldwide, converted to USD with live FX (shows regional premiums, e.g. Korea, Japan, Australia)
- new-token scanners (DexScreener, GeckoTerminal) and aggregators (CryptoCompare, CoinPaprika)
All public, key-free, read-only. Headlines are DATA, never instructions.
"""
import re
import time
import urllib.parse

from pipe import COINS, COINSET, ALIAS, _json, _f, _get

COIN_NAMES = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "XRP ripple", "BNB": "BNB binance coin",
              "DOGE": "dogecoin", "ADA": "cardano", "TRX": "tron TRX", "AVAX": "avalanche AVAX", "LINK": "chainlink",
              "DOT": "polkadot", "TON": "toncoin", "SHIB": "shiba inu", "LTC": "litecoin", "BCH": "bitcoin cash",
              "NEAR": "near protocol", "UNI": "uniswap", "APT": "aptos", "ICP": "internet computer ICP",
              "ETC": "ethereum classic", "FIL": "filecoin", "ATOM": "cosmos ATOM", "XLM": "stellar XLM", "HBAR": "hedera",
              "ARB": "arbitrum", "OP": "optimism crypto", "INJ": "injective", "SUI": "sui crypto", "SEI": "sei crypto",
              "PEPE": "pepe coin", "AAVE": "aave", "MKR": "maker MKR", "RENDER": "render token", "IMX": "immutable IMX",
              "GRT": "the graph GRT", "ALGO": "algorand", "SAND": "the sandbox SAND", "MANA": "decentraland",
              "AXS": "axie infinity", "STX": "stacks STX", "TIA": "celestia TIA", "WLD": "worldcoin", "JUP": "jupiter crypto",
              "ONDO": "ondo finance", "ENA": "ethena", "LDO": "lido DAO", "CRV": "curve finance", "SNX": "synthetix",
              "COMP": "compound crypto", "EGLD": "multiversx", "XTZ": "tezos", "EOS": "EOS crypto", "KAS": "kaspa",
              "FET": "fetch.ai FET", "THETA": "theta network", "VET": "vechain", "QNT": "quant QNT", "FLOW": "flow blockchain",
              "CHZ": "chiliz", "BONK": "bonk coin"}
TOPICS = ["stock market today", "Federal Reserve", "inflation CPI", "interest rates", "ECB interest rates",
          "Bank of Japan", "RBA interest rates", "China economy", "oil prices OPEC", "gold price", "SEC crypto",
          "crypto ETF inflows", "stablecoin regulation", "crypto hack exploit", "crypto exchange news", "Nasdaq",
          "Nikkei", "ASX 200", "Hang Seng", "FTSE 100", "DAX", "earnings season", "recession", "tariffs trade war",
          "dollar index", "treasury yields", "bitcoin mining", "ethereum upgrade", "memecoin", "DeFi",
          "Middle East oil markets", "Russia Ukraine markets", "jobs report payrolls", "PMI manufacturing",
          "bond market", "Japanese yen", "Chinese yuan", "crypto liquidations", "bitcoin ETF", "crypto regulation Australia",
          "Saudi Arabia economy", "India stock market", "Korea stock market", "Europe stocks", "Wall Street",
          # analysis companies, research desks, rating agencies
          "Goldman Sachs forecast", "JPMorgan strategist outlook", "Morgan Stanley outlook", "Bank of America research",
          "Citi strategist", "UBS outlook", "Barclays analysts", "Deutsche Bank research", "BlackRock outlook",
          "Morningstar analysis", "Moody's rating", "S&P Global Ratings", "Fitch Ratings", "analyst price target",
          "analyst upgrade downgrade", "Standard Chartered bitcoin forecast", "Bernstein crypto", "Glassnode on-chain",
          "CryptoQuant data", "Kaiko research", "Messari report", "CoinShares fund flows", "Galaxy Digital research",
          "Fundstrat Tom Lee", "VanEck crypto", "ARK Invest", "Bloomberg Intelligence",
          # economy and official data
          "US CPI report", "US PPI producer prices", "US GDP report", "jobless claims", "retail sales report",
          "consumer confidence", "ISM services", "FOMC minutes", "Fed chair speech", "ECB Lagarde",
          "Bank of England rates", "RBA Bullock", "Australia CPI", "Australia jobs data", "China PMI", "Japan inflation",
          "eurozone inflation", "UK inflation", "OPEC+ output", "IMF World Economic Outlook", "World Bank forecast"]
REGIONS = [("en-US", "US", "US:en"), ("en-AU", "AU", "AU:en"), ("en-GB", "GB", "GB:en"), ("en-IN", "IN", "IN:en"),
           ("en-SG", "SG", "SG:en")]

RSS = [
    ("blockworks", "https://blockworks.co/feed"), ("bitcoin.com", "https://news.bitcoin.com/feed/"),
    ("coingape", "https://coingape.com/feed/"), ("cryptopolitan", "https://www.cryptopolitan.com/feed/"),
    ("zycrypto", "https://zycrypto.com/feed/"), ("coinpedia", "https://coinpedia.org/feed/"),
    ("crypto.news", "https://crypto.news/feed/"), ("watcher.guru", "https://watcher.guru/news/feed"),
    ("protos", "https://protos.com/feed/"), ("dlnews", "https://www.dlnews.com/arc/outboundfeeds/rss/"),
    ("coinrepublic", "https://www.thecoinrepublic.com/feed/"), ("ct-bitcoin", "https://cointelegraph.com/rss/tag/bitcoin"),
    ("ct-ethereum", "https://cointelegraph.com/rss/tag/ethereum"), ("ct-altcoin", "https://cointelegraph.com/rss/tag/altcoin"),
    ("ct-regulation", "https://cointelegraph.com/rss/tag/regulation"),
    ("ct-markets", "https://cointelegraph.com/rss/category/market-analysis"),
    ("bloomberg-markets", "https://feeds.bloomberg.com/markets/news.rss"),
    ("bloomberg-economics", "https://feeds.bloomberg.com/economics/news.rss"),
    ("cnbc-top", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"),
    ("cnbc-world", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362"),
    ("cnbc-asia", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19832390"),
    ("cnbc-europe", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19794221"),
    ("mw-realtime", "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines"),
    ("mw-bulletins", "https://feeds.content.dowjones.io/public/rss/mw_bulletins"),
    ("investing-stocks", "https://www.investing.com/rss/news_25.rss"),
    ("investing-economy", "https://www.investing.com/rss/news_14.rss"),
    ("investing-forex", "https://www.investing.com/rss/news_1.rss"),
    ("investing-commodities", "https://www.investing.com/rss/news_11.rss"),
    ("investing-crypto", "https://www.investing.com/rss/news_301.rss"),
    ("abc-au-top", "https://www.abc.net.au/news/feed/51120/rss.xml"), ("smh-business", "https://www.smh.com.au/rss/business.xml"),
    ("scmp-business", "https://www.scmp.com/rss/92/feed"),
    ("et-markets", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("aljazeera", "https://www.aljazeera.com/xml/rss/all.xml"), ("dw-business", "https://rss.dw.com/rdf/rss-en-bus"),
    ("france24-business", "https://www.france24.com/en/business/rss"), ("nikkei-asia", "https://asia.nikkei.com/rss/feed/nar"),
    ("cnn-money", "http://rss.cnn.com/rss/money_latest.rss"),
    ("business-insider", "https://feeds.businessinsider.com/custom/all"),
    ("guardian-markets", "https://www.theguardian.com/business/stock-markets/rss"),
    ("guardian-economics", "https://www.theguardian.com/business/economics/rss"),
    ("nyt-economy", "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml"),
    ("bbc-asia", "https://feeds.bbci.co.uk/news/world/asia/rss.xml"),
    ("sec", "https://www.sec.gov/news/pressreleases.rss"), ("cftc", "https://www.cftc.gov/RSS/RSSGP/rssgp.xml"),
    ("bank-of-england", "https://www.bankofengland.co.uk/rss/news"), ("imf", "https://www.imf.org/en/News/rss?language=eng"),
    ("boj", "https://www.boj.or.jp/en/rss/whatsnew.xml"), ("kraken-blog", "https://blog.kraken.com/feed"),
    ("ethereum-blog", "https://blog.ethereum.org/feed.xml"), ("decrypt-markets", "https://decrypt.co/feed?category=markets"),
    ("theblock-latest", "https://www.theblock.co/rss.xml?category=latest"),
    ("benzinga", "https://www.benzinga.com/feed"), ("fxempire", "https://www.fxempire.com/api/v1/en/articles/rss/news"),
    ("financial-post", "https://financialpost.com/feed"),
    # analysis companies / research
    ("motley-fool", "https://www.fool.com/a/feeds/foolwatch?format=rss2&id=foolwatch&apikey=foolwatch-feed"),
    ("kiplinger", "https://www.kiplinger.com/feeds/all"), ("coinshares", "https://blog.coinshares.com/feed"),
    ("glassnode", "https://insights.glassnode.com/rss/"), ("cryptoquant", "https://cryptoquant.com/insights/feed"),
    ("seekingalpha-news", "https://seekingalpha.com/feed.xml"), ("zerohedge", "https://feeds.feedburner.com/zerohedge/feed"),
    ("calculatedrisk", "https://www.calculatedriskblog.com/feeds/posts/default"),
    ("wolfstreet", "https://wolfstreet.com/feed/"), ("mish", "https://mishtalk.com/feed"),
    ("economist-markets", "https://www.economist.com/finance-and-economics/rss.xml"),
    # economy / official data
    ("bls", "https://www.bls.gov/feed/bls_latest.rss"), ("bea", "https://apps.bea.gov/rss/rss.xml"),
    ("fed-speeches", "https://www.federalreserve.gov/feeds/speeches.xml"),
    ("fed-monetary", "https://www.federalreserve.gov/feeds/press_monetary.xml"),
    ("ecb-blog", "https://www.ecb.europa.eu/rss/blog.html"), ("tradingeconomics", "https://tradingeconomics.com/rss/news.aspx"),
    ("abs-australia", "https://www.abs.gov.au/rss.xml"), ("statcan", "https://www150.statcan.gc.ca/n1/dai-quo/rss/dai-quo-eng.xml"),
    ("ons-uk", "https://www.ons.gov.uk/releasecalendar/rss"),
]
REDDIT = ["CryptoCurrency", "Bitcoin", "ethereum", "solana", "CryptoMarkets", "wallstreetbets", "stocks", "investing",
          "Economics"]


def _b(sym):
    s = str(sym).upper()
    return ALIAS.get(s, s)


# ------------------------------------------------------------ exchanges: rows of (base, quote, price, chg24, quote_vol)
def x_upbit():
    mk = [m["market"] for m in _json("https://api.upbit.com/v1/market/all") if m["market"].startswith("KRW-")
          and _b(m["market"][4:]) in COINSET]
    rows = _json("https://api.upbit.com/v1/ticker?markets=" + ",".join(mk))
    return [(_b(r["market"][4:]), "KRW", _f(r["trade_price"]), _f(r.get("signed_change_rate")), _f(r.get("acc_trade_price_24h")))
            for r in rows]


def x_bithumb():
    d = _json("https://api.bithumb.com/public/ticker/ALL_KRW")["data"]
    return [(_b(k), "KRW", _f(v.get("closing_price")), (_f(v.get("fluctate_rate_24H")) or 0) / 100, _f(v.get("acc_trade_value_24H")))
            for k, v in d.items() if isinstance(v, dict)]


def x_coinone():
    d = _json("https://api.coinone.co.kr/public/v2/ticker_new/KRW?additional_data=false")
    return [(_b(r["target_currency"]), "KRW", _f(r.get("last")),
             (_f(r["last"]) / _f(r["first"]) - 1) if _f(r.get("first")) else None, _f(r.get("quote_volume")))
            for r in d.get("tickers", [])]


def x_korbit():
    d = _json("https://api.korbit.co.kr/v1/ticker/detailed/all")
    return [(_b(k.split("_")[0]), "KRW", _f(v.get("last")), (_f(v.get("changePercent")) or 0) / 100, None)
            for k, v in d.items() if k.endswith("_krw")]


def x_bitbank():
    d = _json("https://public.bitbank.cc/tickers")["data"]
    return [(_b(r["pair"].split("_")[0]), r["pair"].split("_")[1].upper(), _f(r.get("last")),
             (_f(r["last"]) / _f(r["open"]) - 1) if _f(r.get("open")) else None, None) for r in d]


def x_bitflyer():
    out = []
    for pc in ("BTC_JPY", "ETH_JPY", "XRP_JPY"):
        r = _json(f"https://api.bitflyer.com/v1/ticker?product_code={pc}")
        out.append((pc.split("_")[0], "JPY", _f(r.get("ltp")), None, None))
    return out


def x_coincheck():
    out = []
    for p in ("btc_jpy", "eth_jpy", "xrp_jpy"):
        r = _json(f"https://coincheck.com/api/ticker?pair={p}")
        out.append((p.split("_")[0].upper(), "JPY", _f(r.get("last")), None, None))
    return out


def x_btcmarkets():
    ids = "&".join(f"marketId={c}-AUD" for c in ("BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LINK", "LTC", "BCH", "DOT", "AVAX", "UNI"))
    d = _json(f"https://api.btcmarkets.net/v3/markets/tickers?{ids}")
    return [(_b(r["marketId"].split("-")[0]), "AUD", _f(r.get("lastPrice")), (_f(r.get("pricePct24h")) or 0) / 100,
             _f(r.get("volumeQte24h"))) for r in d]


def x_coinspot():
    d = _json("https://www.coinspot.com.au/pubapi/v2/latest")["prices"]
    return [(_b(k), "AUD", _f(v.get("last")), None, None) for k, v in d.items() if isinstance(v, dict)]


def x_indreserve():
    out = []
    for c, code in (("BTC", "xbt"), ("ETH", "eth"), ("SOL", "sol"), ("XRP", "xrp")):
        r = _json(f"https://api.independentreserve.com/Public/GetMarketSummary?primaryCurrencyCode={code}&secondaryCurrencyCode=aud")
        out.append((c, "AUD", _f(r.get("LastPrice")), None, None))
    return out


def x_coinjar():
    out = []
    for c in ("BTC", "ETH", "SOL", "XRP"):
        r = _json(f"https://data.exchange.coinjar.com/products/{c}AUD/ticker")
        out.append((c, "AUD", _f(r.get("last")), None, None))
    return out


def x_luno():
    out = []
    for r in _json("https://api.luno.com/api/1/tickers")["tickers"]:
        p = r["pair"]
        for q in ("ZAR", "EUR", "GBP", "NGN", "MYR", "IDR", "USDC", "USDT"):
            if p.endswith(q):
                out.append((_b(p[:-len(q)]), q, _f(r.get("last_trade")), None, None))
    return out


def x_valr():
    out = []
    for r in _json("https://api.valr.com/v1/public/marketsummary"):
        p = r["currencyPair"]
        for q in ("ZAR", "USDT", "USDC"):
            if p.endswith(q):
                out.append((_b(p[:-len(q)]), q, _f(r.get("lastTradedPrice")), (_f(r.get("changeFromPrevious")) or 0) / 100,
                            _f(r.get("quoteVolume"))))
    return out


def x_bitso():
    return [(_b(r["book"].split("_")[0]), r["book"].split("_")[1].upper(), _f(r.get("last")), _f(r.get("change_24")), None)
            for r in _json("https://api.bitso.com/v3/ticker/")["payload"]]


def x_mercado():
    syms = ",".join(f"{c}-BRL" for c in ("BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LINK", "LTC", "BCH", "DOT", "AVAX", "UNI"))
    return [(_b(r["pair"].split("-")[0]), "BRL", _f(r.get("last")),
             (_f(r["last"]) / _f(r["open"]) - 1) if _f(r.get("open")) else None, None)
            for r in _json(f"https://api.mercadobitcoin.net/api/v4/tickers?symbols={syms}")]


def x_btcturk():
    out = []
    for r in _json("https://api.btcturk.com/api/v2/ticker")["data"]:
        q = r.get("denominator") or r.get("denominatorSymbol")
        out.append((_b(r.get("numeratorSymbol") or r.get("numerator")), str(q).upper(), _f(r.get("last")),
                    (_f(r.get("dailyPercent")) or 0) / 100, None))
    return out


def x_paribu():
    return [(_b(k.split("_")[0]), "TRY", _f(v.get("last")), (_f(v.get("percentChange")) or 0) / 100, None)
            for k, v in _json("https://www.paribu.com/ticker").items() if k.endswith("_TL")]


def x_indodax():
    return [(_b(k.split("_")[0]), k.split("_")[1].upper(), _f(v.get("last")), None, None)
            for k, v in _json("https://indodax.com/api/tickers")["tickers"].items()]


def x_bitkub():
    return [(_b(k.split("_")[1]), "THB", _f(v.get("last")), (_f(v.get("percentChange")) or 0) / 100, _f(v.get("quoteVolume")))
            for k, v in _json("https://api.bitkub.com/api/market/ticker").items() if k.startswith("THB_")]


def x_coindcx():
    out = []
    for r in _json("https://api.coindcx.com/exchange/ticker"):
        m = r["market"]
        for q in ("INR", "USDT"):
            if m.endswith(q):
                out.append((_b(m[:-len(q)]), q, _f(r.get("last_price")), (_f(r.get("change_24_hour")) or 0) / 100, None))
    return out


def x_wazirx():
    out = []
    for r in _json("https://api.wazirx.com/sapi/v1/tickers/24hr"):
        s = r["symbol"].upper()
        for q in ("INR", "USDT"):
            if s.endswith(q):
                out.append((_b(s[:-len(q)]), q, _f(r.get("lastPrice")),
                            (_f(r["lastPrice"]) / _f(r["openPrice"]) - 1) if _f(r.get("openPrice")) else None, _f(r.get("quoteVolume"))))
    return out


def x_bitvavo():
    return [(_b(r["market"].split("-")[0]), r["market"].split("-")[1], _f(r.get("last")),
             (_f(r["last"]) / _f(r["open"]) - 1) if _f(r.get("open")) and _f(r.get("last")) else None, _f(r.get("volumeQuote")))
            for r in _json("https://api.bitvavo.com/v2/ticker/24h")]


def x_bitpanda():
    return [(_b(r["instrument_code"].split("_")[0]), r["instrument_code"].split("_")[1], _f(r.get("last_price")),
             (_f(r.get("price_change_percentage")) or 0) / 100, None)
            for r in _json("https://api.exchange.bitpanda.com/public/v1/market-ticker")]


def x_whitebit():
    return [(_b(k.split("_")[0]), k.split("_")[1], _f(v.get("last_price")), (_f(v.get("change")) or 0) / 100, _f(v.get("quote_volume")))
            for k, v in _json("https://whitebit.com/api/v4/public/ticker").items() if "_" in k]


def x_poloniex():
    return [(_b(r["symbol"].split("_")[0]), r["symbol"].split("_")[1], _f(r.get("close")),
             (_f(r["close"]) / _f(r["open"]) - 1) if _f(r.get("open")) else None, _f(r.get("amount")))
            for r in _json("https://api.poloniex.com/markets/ticker24h")]


def x_bitmart():
    return [(_b(r[0].split("_")[0]), r[0].split("_")[1], _f(r[1]), (_f(r[1]) / _f(r[4]) - 1) if _f(r[4]) else None, _f(r[3]))
            for r in _json("https://api-cloud.bitmart.com/spot/quotation/v3/tickers")["data"] if "_" in r[0]]


def x_coinex():
    return [(_b(r["market"][:-4]), "USDT", _f(r.get("last")), (_f(r["last"]) / _f(r["open"]) - 1) if _f(r.get("open")) else None,
             _f(r.get("value"))) for r in _json("https://api.coinex.com/v2/spot/ticker")["data"] if r["market"].endswith("USDT")]


def x_xt():
    return [(_b(r["s"].split("_")[0]), r["s"].split("_")[1].upper(), _f(r.get("c")), _f(r.get("cr")), _f(r.get("q")))
            for r in _json("https://sapi.xt.com/v4/public/ticker")["result"] if "_" in r["s"]]


def x_lbank():
    return [(_b(r["symbol"].split("_")[0]), r["symbol"].split("_")[1].upper(), _f(r["ticker"].get("latest")),
             (_f(r["ticker"].get("change")) or 0) / 100, _f(r["ticker"].get("turnover")))
            for r in _json("https://api.lbkex.com/v2/ticker/24hr.do?symbol=all")["data"] if "_" in r["symbol"]]


def x_bingx():
    out = []
    for r in _json(f"https://open-api.bingx.com/openApi/spot/v1/ticker/24hr?timestamp={int(time.time() * 1000)}")["data"]:
        b, q = r["symbol"].split("-") if "-" in r["symbol"] else (r["symbol"], "")
        out.append((_b(b), q, _f(r.get("lastPrice")), (_f(r["lastPrice"]) / _f(r["openPrice"]) - 1) if _f(r.get("openPrice")) else None,
                    _f(r.get("quoteVolume"))))
    return out


def x_ascendex():
    return [(_b(r["symbol"].split("/")[0]), r["symbol"].split("/")[1], _f(r.get("close")),
             (_f(r["close"]) / _f(r["open"]) - 1) if _f(r.get("open")) else None, None)
            for r in _json("https://ascendex.com/api/pro/v1/spot/ticker")["data"] if "/" in r["symbol"]]


def x_hitbtc():
    out = []
    for k, v in _json("https://api.hitbtc.com/api/3/public/ticker").items():
        for q in ("USDT", "USD"):
            if k.endswith(q):
                out.append((_b(k[:-len(q)]), q, _f(v.get("last")),
                            (_f(v["last"]) / _f(v["open"]) - 1) if _f(v.get("open")) and _f(v.get("last")) else None,
                            _f(v.get("volume_quote"))))
                break
    return out


def x_probit():
    return [(_b(r["market_id"].split("-")[0]), r["market_id"].split("-")[1], _f(r.get("last")),
             (_f(r["last"]) / (_f(r["last"]) - _f(r["change"])) - 1) if _f(r.get("change")) and _f(r.get("last")) and _f(r["last"]) != _f(r["change"]) else None,
             _f(r.get("quote_volume"))) for r in _json("https://api.probit.com/api/exchange/v1/ticker")["data"]]


def x_bitrue():
    out = []
    for r in _json("https://openapi.bitrue.com/api/v1/ticker/24hr"):
        s = r["symbol"].upper()
        if s.endswith("USDT"):
            out.append((_b(s[:-4]), "USDT", _f(r.get("lastPrice")),
                        (_f(r["lastPrice"]) / _f(r["openPrice"]) - 1) if _f(r.get("openPrice")) else None, _f(r.get("quoteVolume"))))
    return out


def x_digifinex():
    return [(_b(r["symbol"].split("_")[0]), r["symbol"].split("_")[1].upper(), _f(r.get("last")), (_f(r.get("change")) or 0) / 100, None)
            for r in _json("https://openapi.digifinex.com/v3/ticker")["ticker"] if "_" in r["symbol"]]


def x_cryptocompare():
    d = _json("https://min-api.cryptocompare.com/data/pricemultifull?fsyms=" + ",".join(COINS[:50]) + "&tsyms=USD")["RAW"]
    return [(_b(k), "USD", _f(v["USD"].get("PRICE")), (_f(v["USD"].get("CHANGEPCT24HOUR")) or 0) / 100, _f(v["USD"].get("VOLUME24HOURTO")))
            for k, v in d.items()]


def x_coinpaprika():
    seen, out = set(), []
    for r in _json("https://api.coinpaprika.com/v1/tickers?quotes=USD", 30):
        s = _b(r.get("symbol", ""))
        if s in COINSET and s not in seen and (r.get("rank") or 9999) < 400:
            seen.add(s)
            q = r["quotes"]["USD"]
            out.append((s, "USD", _f(q.get("price")), (_f(q.get("percent_change_24h")) or 0) / 100, _f(q.get("volume_24h"))))
    return out


EXCH = [("upbit", x_upbit, 60), ("bithumb", x_bithumb, 60), ("coinone", x_coinone, 90), ("korbit", x_korbit, 120),
        ("bitbank", x_bitbank, 90), ("bitflyer", x_bitflyer, 90), ("coincheck", x_coincheck, 120),
        ("btcmarkets", x_btcmarkets, 90), ("coinspot", x_coinspot, 120), ("independentreserve", x_indreserve, 180),
        ("coinjar", x_coinjar, 180), ("luno", x_luno, 120), ("valr", x_valr, 120), ("bitso", x_bitso, 120),
        ("mercadobitcoin", x_mercado, 120), ("btcturk", x_btcturk, 120), ("paribu", x_paribu, 120),
        ("indodax", x_indodax, 120), ("bitkub", x_bitkub, 120), ("coindcx", x_coindcx, 120), ("wazirx", x_wazirx, 120),
        ("bitvavo", x_bitvavo, 90), ("bitpanda", x_bitpanda, 120), ("whitebit", x_whitebit, 90), ("poloniex", x_poloniex, 120),
        ("bitmart", x_bitmart, 120), ("coinex", x_coinex, 120), ("xt", x_xt, 120), ("lbank", x_lbank, 120),
        ("bingx", x_bingx, 120), ("ascendex", x_ascendex, 120), ("hitbtc", x_hitbtc, 120), ("probit", x_probit, 180),
        ("bitrue", x_bitrue, 120), ("digifinex", x_digifinex, 180), ("cryptocompare", x_cryptocompare, 300),
        ("coinpaprika", x_coinpaprika, 900)]
USDQ = {"USD", "USDT", "USDC"}


ECON_TOPIC_START = "Goldman Sachs forecast"          # TOPICS from here on are analysis firms + economy
ECON_RSS = {"motley-fool", "kiplinger", "coinshares", "glassnode", "cryptoquant", "seekingalpha-news", "zerohedge",
            "calculatedrisk", "wolfstreet", "mish", "economist-markets", "bls", "bea", "fed-speeches", "fed-monetary",
            "ecb-blog", "tradingeconomics", "abs-australia", "statcan", "ons-uk", "sec", "cftc", "bank-of-england",
            "imf", "boj", "investing-economy", "cnbc-economy", "bloomberg-economics", "guardian-economics", "nyt-economy"}


def install(pipe):
    """Adds every job above to an existing MarketPipe."""
    k = TOPICS.index(ECON_TOPIC_START) if ECON_TOPIC_START in TOPICS else len(TOPICS)
    pipe.econ_jobs = {f"gnews:{t}" for t in TOPICS[k:]} | {"news:" + s for s in ECON_RSS} | \
        {"news:fed", "news:ecb", "news:economist-finance"}
    pipe.publishers = set()            # every distinct news publisher ever seen (Google News names each one)

    def fx(ccy):
        if ccy in USDQ:
            return 1.0
        f = pipe.feeds.get("fx:" + ccy) or pipe.feeds.get("ecbfx:" + ccy)
        return f["value"] if f else None

    def price_job(name, fn):
        def run():
            best = {}
            for base, quote, px, chg, vol in fn():
                if base not in COINSET or not px or px <= 0:
                    continue
                quote = str(quote).upper().replace("TL", "TRY")
                rate = fx(quote)
                if not rate:
                    continue
                usd = px / rate
                rank = 0 if quote in USDQ else 1
                if base not in best or rank < best[base][0]:
                    best[base] = (rank, usd, chg, quote, px)
            for c, (_, usd, chg, q, local) in best.items():
                pipe._put(f"{name}:{c}", "crypto", name, f"{c} on {name} ({q})", usd, chg, {"quote": q, "local": local})
            return len(best)
        return run

    for name, fn, every in EXCH:
        pipe._job(name, "crypto", every, price_job(name, fn))
        pipe.declared |= {f"{name}:{c}" for c in COINS[:20]}

    def gnews(label, q, hl, gl, ceid):
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q + " when:1d", "hl": hl, "gl": gl, "ceid": ceid})

        def run():
            import xml.etree.ElementTree as ET
            root = ET.fromstring(_get(url, 15))
            titles = []
            for it in list(root.iter("item"))[:40]:
                t = (it.findtext("title") or "").strip()
                pub = (it.findtext("source") or "").strip()
                if pub:
                    pipe.publishers.add(pub)
                    t = re.sub(r"\s+-\s+" + re.escape(pub) + r"\s*$", "", t)
                if t:
                    titles.append((t[:180], pub or "google-news"))
            pipe.add_headlines(titles, "gnews:" + label)
            return len(titles)
        return run

    n = 0
    for c in COINS:
        q = f'"{c}" OR {COIN_NAMES.get(c, c)} crypto'
        pipe._job(f"gnews:{c}", "news", 420, gnews(c, q, "en-US", "US", "US:en"))
        n += 1
    for i, t in enumerate(TOPICS):
        hl, gl, ceid = REGIONS[i % len(REGIONS)]
        pipe._job(f"gnews:{t}", "news", 420, gnews(t, t, hl, gl, ceid))
    for name, url in RSS:
        pipe._job("news:" + name, "news", 150, lambda s=name, u=url: pipe._news(s, u))
    for sub in REDDIT:
        pipe._job("reddit:" + sub, "social", 1800, lambda s=sub: pipe._news("r/" + s, f"https://www.reddit.com/r/{s}/hot/.rss?limit=25"))
    pipe.declared |= {f"gnews:{c}" for c in COINS} | {f"gnews:{t}" for t in TOPICS} | {"news:" + s for s, _ in RSS} | \
        {"reddit:" + s for s in REDDIT}

    def dexscreener():
        rows = _json("https://api.dexscreener.com/token-profiles/latest/v1")
        for i, r in enumerate(rows[:30]):
            pipe._put(f"newtoken:{i}", "newtokens", "dexscreener", f"new token on {r.get('chainId')}: "
                      f"{str(r.get('description') or r.get('tokenAddress'))[:80]}", 1, None, {"url": r.get("url")})
        return len(rows)

    def geckoterminal():
        d = _json("https://api.geckoterminal.com/api/v2/networks/trending_pools")["data"]
        for i, r in enumerate(d[:20]):
            a = r["attributes"]
            pipe._put(f"trending:{i}", "newtokens", "geckoterminal", f"trending pool {a.get('name')}",
                      _f(a.get("base_token_price_usd")), (_f((a.get("price_change_percentage") or {}).get("h24")) or 0) / 100)
        return len(d)
    pipe._job("dexscreener", "newtokens", 300, dexscreener)
    pipe._job("geckoterminal", "newtokens", 300, geckoterminal)
    pipe.declared |= {f"newtoken:{i}" for i in range(30)} | {f"trending:{i}" for i in range(20)}
