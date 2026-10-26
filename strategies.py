"""Indicators, the strategy 'lenses' scouts/predictors use, and the quant test metrics.

Every lens has the same shape:  fn(candles, params) -> (direction, confidence)
direction is +1 (long), -1 (short) or 0 (no view). Candles are dicts with o,h,l,c,v.
"""
import math


# ---------------- tiny indicator toolkit ----------------
def cl(c):
    return [x["c"] for x in c]


def mean(a):
    return sum(a) / len(a) if a else 0.0


def std(a):
    if len(a) < 2:
        return 0.0
    m = mean(a)
    return math.sqrt(sum((x - m) ** 2 for x in a) / (len(a) - 1))


def rets(a):
    return [a[i] / a[i - 1] - 1 for i in range(1, len(a))]


def sign(x):
    return 1 if x > 0 else (-1 if x < 0 else 0)


def atr(c, n=14):
    seg = c[-(n + 1):]
    trs = [max(seg[i]["h"] - seg[i]["l"], abs(seg[i]["h"] - seg[i - 1]["c"]), abs(seg[i]["l"] - seg[i - 1]["c"]))
           for i in range(1, len(seg))]
    return mean(trs)


try:
    import numpy as _np
except Exception:
    _np = None


def ema(a, n):
    k = 2 / (n + 1)
    e = a[0]
    for x in a[1:]:
        e = x * k + e * (1 - k)
    return e


def rsi(a, n=14):
    seg = a[-(n + 1):]
    g = l = 0.0
    for i in range(1, len(seg)):
        d = seg[i] - seg[i - 1]
        if d > 0:
            g += d
        else:
            l -= d
    return 50.0 if g + l == 0 else 100 * g / (g + l)


# ---------------- scout lenses ----------------
def s_breakout(c, p):
    n = p["n"]
    if len(c) < n + 16:
        return 0, 0.0
    hi = max(x["h"] for x in c[-n - 1:-1])
    lo = min(x["l"] for x in c[-n - 1:-1])
    px, a = c[-1]["c"], atr(c) or 1e-9
    if px > hi:
        return 1, min(1.0, 0.5 + (px - hi) / a * 0.5)
    if px < lo:
        return -1, min(1.0, 0.5 + (lo - px) / a * 0.5)
    return 0, 0.0


def s_momentum(c, p):
    n = p["n"]
    if len(c) < n + 52:
        return 0, 0.0
    a = cl(c[-(n + 51):])
    roc = a[-1] / a[-1 - n] - 1
    sig = std(rets(a[-51:])) * math.sqrt(n)
    z = roc / sig if sig else 0
    return (sign(z), min(1.0, abs(z) / 2.5)) if abs(z) >= 0.8 else (0, 0.0)


def s_meanrev(c, p):
    n = p["n"]
    if len(c) < n + 2:
        return 0, 0.0
    a = cl(c[-n:])
    sd = std(a)
    if not sd:
        return 0, 0.0
    z = (a[-1] - mean(a)) / sd
    if abs(z) < p["z"]:
        return 0, 0.0
    return -sign(z), min(1.0, 0.4 + (abs(z) - p["z"]) / 1.5)


def s_volspike(c, p):
    n = p["n"]
    if len(c) < n + 2:
        return 0, 0.0
    avg = mean([x["v"] for x in c[-n - 1:-1]])
    ratio = c[-1]["v"] / avg if avg else 0
    if ratio < p["m"]:
        return 0, 0.0
    return sign(c[-1]["c"] - c[-1]["o"]), min(1.0, 0.4 + 0.2 * (ratio - p["m"]))


def s_rsi(c, p):
    if len(c) < p["n"] + 2:
        return 0, 0.0
    r = rsi(cl(c), p["n"])
    if r < p["lo"]:
        return 1, min(1.0, 0.4 + (p["lo"] - r) / 15)
    if r > p["hi"]:
        return -1, min(1.0, 0.4 + (r - p["hi"]) / 15)
    return 0, 0.0


def s_macross(c, p):
    if len(c) < p["slow"] * 3 + 2:
        return 0, 0.0
    a = cl(c[-p["slow"] * 3:])
    f, s_ = ema(a, p["fast"]), ema(a, p["slow"])
    g = abs(f - s_) / (atr(c) or 1e-9)
    conf = min(1.0, g / 2)
    return (sign(f - s_), conf) if conf > 0.25 else (0, 0.0)


# ---------------- predictor lenses ----------------
def p_linreg(c, p):
    n = p["n"]
    if len(c) < n + 2:
        return 0, 0.0
    y = cl(c[-n:])
    xm, ym = (n - 1) / 2, mean(y)
    sxx = sum((i - xm) ** 2 for i in range(n))
    slope = sum((i - xm) * (y[i] - ym) for i in range(n)) / sxx
    resid = [y[i] - (ym + slope * (i - xm)) for i in range(n)]
    se = math.sqrt(sum(r * r for r in resid) / max(1, n - 2) / sxx) or 1e-12
    t = slope / se
    return (sign(slope), min(1.0, abs(t) / 6)) if abs(t) >= 2 else (0, 0.0)


def p_ar1(c, p):
    n = p["n"]
    if len(c) < n + 3:
        return 0, 0.0
    r = rets(cl(c[-(n + 1):]))
    x, y = r[:-1], r[1:]
    vx = std(x) ** 2
    if not vx:
        return 0, 0.0
    mx, my = mean(x), mean(y)
    phi = sum((a - mx) * (b - my) for a, b in zip(x, y)) / (len(x) - 1) / vx
    pred = phi * r[-1]
    if abs(phi) < 0.08 or abs(pred) < 0.3 * std(r):
        return 0, 0.0
    return sign(pred), min(1.0, abs(phi) * 3)


def p_knn(c, p):
    k, m = p["k"], p["m"]
    a = cl(c[-320:])
    r = rets(a)
    if len(r) < 80:
        return 0, 0.0
    if _np is not None:                          # vectorised nearest-neighbour search (~30x faster)
        R = _np.asarray(r)
        idx = _np.arange(m, len(r) - 3)
        win = _np.lib.stride_tricks.sliding_window_view(R, m)[idx - m]
        d = ((win - R[-m:]) ** 2).sum(axis=1)
        fut = (1 + R[idx]) * (1 + R[idx + 1]) * (1 + R[idx + 2]) - 1
        order = _np.argsort(d, kind="stable")[:k]
        best = [float(x) for x in fut[order]]
    else:
        cur = r[-m:]
        cand = []
        for i in range(m, len(r) - 3):
            dd = sum((x - y) ** 2 for x, y in zip(r[i - m:i], cur))
            cand.append((dd, (1 + r[i]) * (1 + r[i + 1]) * (1 + r[i + 2]) - 1))
        cand.sort(key=lambda t: t[0])
        best = [f for _, f in cand[:k]]
    avg = mean(best)
    agree = sum(1 for f in best if sign(f) == sign(avg)) / len(best)
    if agree < 0.7 or not sign(avg):
        return 0, 0.0
    return sign(avg), min(1.0, agree - 0.3 + min(0.3, abs(avg) / (std(r) * 3 or 1)))


def p_flow(c, p):
    seg = c[-p["n"]:]
    if len(seg) < p["n"]:
        return 0, 0.0
    tv = sum(x["v"] for x in seg)
    imb = sum(sign(x["c"] - x["o"]) * x["v"] for x in seg) / tv if tv else 0
    return (sign(imb), min(1.0, abs(imb))) if abs(imb) >= 0.3 else (0, 0.0)


def p_trendstr(c, p):
    if len(c) < 80:
        return 0, 0.0
    a = cl(c[-80:])
    ds = (ema(a, p["fast"]) - ema(a, p["slow"])) / (atr(c) or 1e-9)
    return (sign(ds), min(1.0, abs(ds) / 3)) if abs(ds) >= 0.5 else (0, 0.0)


def p_ensemble(c, p):
    if len(c) < 70:
        return 0, 0.0
    a = cl(c[-70:])
    votes = [sign(mean(a[-5:]) - mean(a[-20:])), sign(mean(a[-10:]) - mean(a[-30:])),
             sign(mean(a[-20:]) - mean(a[-60:])), sign(a[-1] - mean(a[-50:])), sign(a[-1] - a[-11])]
    tot = sum(votes)
    return (sign(tot), abs(tot) / 5) if abs(tot) >= 4 else (0, 0.0)


def p_zrev(c, p):
    n = p["n"]
    if len(c) < n + 2:
        return 0, 0.0
    a = cl(c[-n:])
    sd = std(a)
    if not sd:
        return 0, 0.0
    z = (a[-1] - mean(a)) / sd
    return (-sign(z), min(1.0, abs(z) / 3)) if abs(z) >= 1.8 else (0, 0.0)


def _asia_range(c):
    """High/low of today's Asia session (00-07 UTC) from timestamped candles, or None."""
    t = c[-1].get("t")
    if t is None:
        return None
    day = t // 86400
    seg = [x for x in c if x.get("t", 0) // 86400 == day and (x["t"] % 86400) < 7 * 3600]
    return (max(x["h"] for x in seg), min(x["l"] for x in seg), len(seg)) if len(seg) >= 6 else None


def s_london_break(c, p):
    """London open: price leaves the Asia range -> follow it."""
    t = c[-1].get("t")
    if t is None or not (7 * 3600 <= t % 86400 < 12 * 3600):
        return 0, 0.0
    r = _asia_range(c)
    if not r:
        return 0, 0.0
    hi, lo, _ = r
    px, a = c[-1]["c"], atr(c) or 1e-9
    if px > hi:
        return 1, min(1.0, 0.5 + (px - hi) / a * 0.5)
    if px < lo:
        return -1, min(1.0, 0.5 + (lo - px) / a * 0.5)
    return 0, 0.0


def s_asia_fade(c, p):
    """Asia is usually quiet: fade stretched moves back toward the session mean."""
    t = c[-1].get("t")
    if t is None or (t % 86400) >= 7 * 3600 or len(c) < p["n"] + 2:
        return 0, 0.0
    cs = cl(c)[-p["n"]:]
    sd = std(cs) or 1e-9
    z = (cs[-1] - mean(cs)) / sd
    if abs(z) > p["z"]:
        return (-1 if z > 0 else 1), min(1.0, 0.4 + (abs(z) - p["z"]) * 0.3)
    return 0, 0.0


def s_ny_cont(c, p):
    """US session: continue the direction London established since its open."""
    t = c[-1].get("t")
    if t is None or not (13 * 3600 <= t % 86400 < 20 * 3600):
        return 0, 0.0
    day = t // 86400
    seg = [x for x in c if x.get("t", 0) // 86400 == day and 7 * 3600 <= x["t"] % 86400 < 13 * 3600]
    if len(seg) < 8:
        return 0, 0.0
    move = (seg[-1]["c"] - seg[0]["o"]) / (atr(c) or 1e-9)
    if abs(move) > p["m"]:
        return (1 if move > 0 else -1), min(1.0, 0.4 + (abs(move) - p["m"]) * 0.1)
    return 0, 0.0


def s_bollinger(c, p):
    """Bollinger bands: a close outside the band is stretched -> revert (squeeze breakouts are covered by 'breakout')."""
    n = p["n"]
    if len(c) < n + 2:
        return 0, 0.0
    cs = cl(c)[-n:]
    mid, sd = mean(cs), std(cs) or 1e-9
    up, dn = mid + p["k"] * sd, mid - p["k"] * sd
    if cs[-1] > up:
        return -1, min(1.0, 0.5 + (cs[-1] - up) / sd * 0.3)
    if cs[-1] < dn:
        return 1, min(1.0, 0.5 + (dn - cs[-1]) / sd * 0.3)
    return 0, 0.0


def s_macd(c, p):
    """MACD histogram crosses zero: momentum has turned."""
    cs = cl(c)
    if len(cs) < p["slow"] * 3:
        return 0, 0.0
    kf, ks = 2 / (p["fast"] + 1), 2 / (p["slow"] + 1)       # one pass over the prices (was: re-run per candle)
    ef = es = cs[0]
    macd_all = [0.0]
    for x in cs[1:]:
        ef = x * kf + ef * (1 - kf)
        es = x * ks + es * (1 - ks)
        macd_all.append(ef - es)

    def hist(n):                                 # identical maths to before, on the first n prices
        macd = macd_all[n - p["sig"] - 2:n]
        return macd[-1] - ema(macd, p["sig"])
    h1, h0 = hist(len(cs)), hist(len(cs) - 1)
    a = atr(c) or 1e-9
    if h0 <= 0 < h1:
        return 1, min(1.0, 0.5 + abs(h1) / a * 2)
    if h0 >= 0 > h1:
        return -1, min(1.0, 0.5 + abs(h1) / a * 2)
    return 0, 0.0


FUNCS = {
    "breakout": s_breakout, "momentum": s_momentum, "meanrev": s_meanrev, "volspike": s_volspike,
    "rsi": s_rsi, "macross": s_macross,
    "linreg": p_linreg, "ar1": p_ar1, "knn": p_knn, "flow": p_flow, "trendstr": p_trendstr,
    "ensemble": p_ensemble, "zrev": p_zrev,
    "london_break": s_london_break, "asia_fade": s_asia_fade, "ny_cont": s_ny_cont, "bollinger": s_bollinger, "macd": s_macd,
}
# 'trend' lenses do better in trending regimes, 'revert' lenses in ranges
TAGS = {
    "breakout": "trend", "momentum": "trend", "meanrev": "revert", "volspike": "trend", "rsi": "revert",
    "macross": "trend", "linreg": "trend", "ar1": "trend", "knn": "neutral", "flow": "trend",
    "trendstr": "trend", "ensemble": "trend", "zrev": "revert",
    "london_break": "trend", "asia_fade": "revert", "ny_cont": "trend", "bollinger": "revert", "macd": "trend",
}


# ---------------- backtest + quant metrics ----------------
def backtest(fn, params, candles, window=160, stride=2, h=3):
    """Replay a lens over recent history. Returns [(age, gross_return_of_signal)] with no look-ahead:
    the signal at time t only sees candles[:t+1] and is judged on the next h candles."""
    out = []
    n = len(candles)
    start = max(60, n - window - h)
    for t in range(start, n - h, stride):
        d, conf = fn(candles[:t + 1], params)
        if d:
            out.append((n - 1 - t, d * (candles[t + h]["c"] / candles[t]["c"] - 1)))
    return out


COST = 0.0014   # round-trip fees + slippage


def _w(series, w):
    return [p for age, p in series if age < w]


def metric_pass(metric, w, series, all_series):
    xs = _w(series, w)
    if len(xs) < 5:
        return False
    m, sd = mean(xs), std(xs)
    if metric == "hit":
        return sum(1 for x in xs if x > 0) / len(xs) > 0.53
    if metric == "tstat":
        return sd > 0 and m / (sd / math.sqrt(len(xs))) > 1.0
    if metric == "sharpe":
        return sd > 0 and m / sd > 0.12
    if metric == "pf":
        gains = sum(x for x in xs if x > 0)
        loss = -sum(x for x in xs if x < 0)
        return loss > 0 and gains / loss > 1.15
    if metric == "dd":
        eq = peak = dd = 0.0
        for x in xs:
            eq += x
            peak = max(peak, eq)
            dd = max(dd, peak - eq)
        return m > 0 and dd < 12 * (mean([abs(x) for x in xs]) or 1)
    if metric == "stable":
        half = len(xs) // 2
        return half >= 3 and mean(xs[:half]) > 0 and mean(xs[half:]) > 0
    if metric == "cost":
        return m - COST > 0
    if metric == "recent":
        recent = [p for age, p in sorted(series, key=lambda t: t[0])][:20]
        return len(recent) >= 5 and mean(recent) > 0
    if metric == "tail":
        return m > 0 and min(xs) > -5 * (mean([abs(x) for x in xs]) or 1)
    if metric == "xsym":
        pos = sum(1 for s in all_series if len(_w(s, w)) >= 3 and mean(_w(s, w)) > 0)
        return pos >= 2
    return False


QUANT_SPECS = [("hit", 60), ("hit", 120), ("tstat", 60), ("tstat", 120), ("sharpe", 90), ("pf", 90),
               ("dd", 90), ("stable", 120), ("cost", 90), ("recent", 120), ("tail", 90), ("xsym", 120),
               ("tstat", 40), ("hit", 40), ("cost", 120)]
