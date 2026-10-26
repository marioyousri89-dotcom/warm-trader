"""CASH ACCOUNT: real money on OKX (spot), running alongside the paper training account.

The paper account is for TRAINING. When a trade opens on paper and every gate below is green, the cash account places
a small real order on the owner's own OKX account. Nothing here can withdraw money: the owner creates an OKX API key
with TRADE permission only (never "Withdraw") and puts it in Render -> Environment. Claude never sees or handles keys.

Environment (all set by the owner in Render):
  OKX_API_KEY, OKX_API_SECRET, OKX_API_PASSPHRASE   the owner's own key (TRADE permission only)
  OKX_DEMO=1                                         use OKX's demo-trading money first (recommended); 0 = real money
  CASH_TRADING=1                                     master switch (default off)
  CASH_PER_TRADE_USD=20   CASH_MAX_OPEN=3   CASH_DAILY_LOSS_USD=30   CASH_TOTAL_LOSS_USD=100

Gates (all must pass before any order): master switch on, keys present, owner pressed ARM in the app, academy exam
passed, paper account profitable over its last 30+ closed trades, cash daily/total loss limits not hit, kill switch not
tripped, the trade is LONG (OKX spot cannot short) on a coin with an OKX USDT market.
UNVERIFIED against the live OKX service from the build machine (no network there): start with OKX_DEMO=1.
"""
import base64
import hashlib
import hmac
import json
import os
import queue
import threading
import time
import urllib.request
from datetime import datetime, timezone

BASE = "https://www.okx.com"


class CashAccount:
    def __init__(self, engine):
        self.e = engine
        env = os.environ.get
        self.key, self.secret, self.passphrase = env("OKX_API_KEY"), env("OKX_API_SECRET"), env("OKX_API_PASSPHRASE")
        self.demo = env("OKX_DEMO", "1") != "0"
        self.master = env("CASH_TRADING", "0") == "1"
        self.per_trade = float(env("CASH_PER_TRADE_USD", "20"))
        self.max_open = int(env("CASH_MAX_OPEN", "3"))
        self.day_loss_cap = float(env("CASH_DAILY_LOSS_USD", "30"))
        self.total_loss_cap = float(env("CASH_TOTAL_LOSS_USD", "100"))
        self.armed = False
        self.pos = {}                 # paper trade id -> {sym, qty, cost, opened}
        self.closed = []              # [{sym, cost, proceeds, pnl, t}]
        self.log = []
        self.balance = None
        self.q = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()

    # ---------------------------------------------------------------- OKX signed REST (v5)
    def _req(self, method, path, body=None):
        ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        data = json.dumps(body) if body is not None else ""
        sign = base64.b64encode(hmac.new(self.secret.encode(), (ts + method + path + data).encode(), hashlib.sha256).digest()).decode()
        h = {"OK-ACCESS-KEY": self.key, "OK-ACCESS-SIGN": sign, "OK-ACCESS-TIMESTAMP": ts,
             "OK-ACCESS-PASSPHRASE": self.passphrase, "Content-Type": "application/json"}
        if self.demo:
            h["x-simulated-trading"] = "1"
        req = urllib.request.Request(BASE + path, data=data.encode() if data else None, method=method, headers=h)
        with urllib.request.urlopen(req, timeout=15) as r:
            out = json.loads(r.read())
        if str(out.get("code")) != "0":
            raise RuntimeError(f"OKX {out.get('code')}: {str(out.get('msg') or out.get('data'))[:120]}")
        return out["data"]

    def refresh_balance(self):
        if not self.keys():
            return None
        try:
            d = self._req("GET", "/api/v5/account/balance?ccy=USDT")
            det = (d[0].get("details") or [{}])[0] if d else {}
            self.balance = float(det.get("availBal") or det.get("cashBal") or 0)
        except Exception as ex:
            self._note(f"balance check failed: {ex}")
        return self.balance

    # ---------------------------------------------------------------- gates
    def keys(self):
        return bool(self.key and self.secret and self.passphrase)

    def pnl_today(self):
        day = time.time() - time.time() % 86400
        return sum(c["pnl"] for c in self.closed if c["t"] >= day)

    def gates(self):
        e = self.e
        g = e.b.kv_get("graduation")
        rows = e.b.q("SELECT pnl FROM trades WHERE status='closed' ORDER BY id DESC LIMIT 60")
        paper_pnl = sum(r["pnl"] for r in rows)
        checks = [
            ("live trading phase (academy finished)", e.phase == "live"),
            ("master switch CASH_TRADING=1 in Render", self.master),
            ("OKX API key in Render (trade-only)", self.keys()),
            ("owner pressed ARM in the app", self.armed),
            ("academy exam passed", bool(g and g.get("passed"))),
            (f"paper profitable over last {len(rows)} trades (needs 30+)", len(rows) >= 30 and paper_pnl > 0),
            (f"cash loss today under ${self.day_loss_cap:.0f}", -self.pnl_today() < self.day_loss_cap),
            (f"cash total loss under ${self.total_loss_cap:.0f}", -sum(c["pnl"] for c in self.closed) < self.total_loss_cap),
            ("kill switch not tripped", not e.port.halted),
        ]
        return checks, all(ok for _, ok in checks)

    def arm(self, on):
        checks, _ = self.gates()
        if on:
            missing = [n for n, ok in checks if not ok and "ARM" not in n]
            self.armed = True
            return "Cash account ARMED. " + ("It will only trade when these turn green: " + "; ".join(missing) if missing
                                             else f"All gates green: real {'DEMO ' if self.demo else ''}orders up to ${self.per_trade:.0f} each.")
        self.armed = False
        self.flatten("owner disarmed")
        return "Cash account DISARMED; open cash positions are being sold."

    # ---------------------------------------------------------------- mirror paper trades (called by the portfolio)
    def on_open(self, t):
        _, ok = self.gates()
        if not ok or t["side"] <= 0 or len(self.pos) >= self.max_open:
            return
        self.q.put(("buy", t))

    def on_close(self, t):
        key = t.get("id") or (t["desk"], t["symbol"], t["open_cycle"])
        if key in self.pos:
            self.q.put(("sell", t))

    def flatten(self, why):
        for k, p in list(self.pos.items()):
            self.q.put(("sell", {"id": k, "symbol": p["sym"], "why": why}))

    def _worker(self):
        while True:
            act, t = self.q.get()
            try:
                if act == "buy":
                    self._buy(t)
                else:
                    self._sell(t)
            except Exception as ex:
                self._note(f"{act} {t.get('symbol')} failed: {str(ex)[:120]}")

    def _buy(self, t):
        sym = t["symbol"]
        key = t.get("id") or (t["desk"], sym, t["open_cycle"])
        usd = self.per_trade
        if self.balance is not None and self.balance < usd:
            return self._note(f"skip {sym}: USDT balance {self.balance:.2f} < ${usd:.0f}")
        d = self._req("POST", "/api/v5/trade/order", {"instId": f"{sym}-USDT", "tdMode": "cash", "side": "buy",
                                                       "ordType": "market", "sz": f"{usd:.2f}", "tgtCcy": "quote_ccy"})
        oid = d[0]["ordId"]
        time.sleep(1.0)
        f = self._req("GET", f"/api/v5/trade/order?instId={sym}-USDT&ordId={oid}")[0]
        filled, fee = float(f.get("accFillSz") or 0), float(f.get("fee") or 0)     # OKX reports fees as negative numbers
        qty = filled + (fee if f.get("feeCcy") == sym else 0)
        cost = filled * float(f.get("avgPx") or 0) - (fee if f.get("feeCcy") == "USDT" else 0)
        qty = self._lot(sym, qty)
        if qty <= 0:
            return self._note(f"buy {sym}: order {oid} not filled")
        self.pos[key] = {"sym": sym, "qty": qty, "cost": cost, "opened": time.time(), "order": oid}
        self._note(f"BOUGHT {qty:.6g} {sym} for ${cost:.2f} ({'demo' if self.demo else 'REAL'}) — copying paper trade from {t.get('desk')}")
        self.refresh_balance()

    def _sell(self, t):
        key = t.get("id") or (t.get("desk"), t["symbol"], t.get("open_cycle"))
        p = self.pos.pop(key, None)
        if not p:
            return
        d = self._req("POST", "/api/v5/trade/order", {"instId": f"{p['sym']}-USDT", "tdMode": "cash", "side": "sell",
                                                       "ordType": "market", "sz": f"{p['qty']:.8g}"})
        oid = d[0]["ordId"]
        time.sleep(1.0)
        f = self._req("GET", f"/api/v5/trade/order?instId={p['sym']}-USDT&ordId={oid}")[0]
        proceeds = float(f.get("accFillSz") or 0) * float(f.get("avgPx") or 0) + (float(f.get("fee") or 0) if f.get("feeCcy") == "USDT" else 0)
        pnl = proceeds - p["cost"]
        self.closed.append({"sym": p["sym"], "cost": round(p["cost"], 2), "proceeds": round(proceeds, 2), "pnl": round(pnl, 2), "t": time.time()})
        self._note(f"SOLD {p['sym']}: ${proceeds:.2f} back, P/L {pnl:+.2f} ({'demo' if self.demo else 'REAL'})")
        self.refresh_balance()

    def _lot(self, sym, qty):
        """Round a quantity down to the exchange's lot size so the sell order is accepted."""
        lots = getattr(self, "_lots", {})
        self._lots = lots
        if sym not in lots:
            try:
                req = urllib.request.Request(f"{BASE}/api/v5/public/instruments?instType=SPOT&instId={sym}-USDT",
                                             headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    lots[sym] = float(json.loads(r.read())["data"][0]["lotSz"])
            except Exception:
                lots[sym] = 0.0
        step = lots[sym]
        return (int(qty / step) * step) if step else qty

    def _note(self, text):
        self.log = ([{"t": time.time(), "text": text}] + self.log)[:60]

    def state(self):
        checks, ok = self.gates()
        return {"mode": "OKX DEMO money" if self.demo else "OKX REAL money", "armed": self.armed, "live": ok,
                "gates": [{"check": n, "ok": bool(v)} for n, v in checks], "per_trade": self.per_trade,
                "max_open": self.max_open, "balance": self.balance,
                "open": [{"symbol": p["sym"], "qty": p["qty"], "cost": round(p["cost"], 2)} for p in self.pos.values()],
                "closed": self.closed[-20:][::-1], "pnl": round(sum(c["pnl"] for c in self.closed), 2),
                "pnl_today": round(self.pnl_today(), 2), "log": self.log[:25]}
