"""Broker mirrors. DEMO / SIMULATED ACCOUNTS ONLY.

When a trade has passed the risk manager and been opened in the practice book, a mirror order can be sent to a
broker's demo account so you can compare practice results with real broker fills. Orders go through a background
queue so a slow broker never stalls the swarm. Real-money endpoints are deliberately NOT implemented here.

  eToro    public API, demo endpoint (keys: ETORO_API_KEY, ETORO_USER_KEY; create a DEMO user key in eToro Settings).
  moomoo   OpenD gateway + `pip install moomoo-api`, simulated trading environment (MOOMOO_HOST/PORT, MOOMOO_SIM_ACCT).
  Mitrade  no public trading API found: signals can only come in/out by webhook or by hand. Stub only.
Status of each adapter is shown in the app. Anything marked UNVERIFIED was written from docs and never run
against the live service from the build sandbox (no outbound network there): test with tiny amounts first.
"""
import json
import os
import queue
import threading
import urllib.request
import uuid

ETORO = "https://public-api.etoro.com"


class Broker:
    name = "base"
    verified = False

    def __init__(self):
        self.last = "idle"
        self.sent = self.failed = 0

    def ready(self):
        return False

    def open(self, symbol, side, notional, stop, target):
        raise NotImplementedError

    def close(self, symbol, ref):
        raise NotImplementedError

    def info(self):
        return {"name": self.name, "ready": self.ready(), "env": "demo", "verified": self.verified,
                "sent": self.sent, "failed": self.failed, "last": self.last}


class EtoroDemo(Broker):
    name = "etoro"

    def __init__(self):
        super().__init__()
        self.key, self.ukey = os.environ.get("ETORO_API_KEY"), os.environ.get("ETORO_USER_KEY")
        self.ids = {}

    def ready(self):
        return bool(self.key and self.ukey)

    def _call(self, method, path, body=None):
        req = urllib.request.Request(ETORO + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                     headers={"x-api-key": self.key, "x-user-key": self.ukey, "x-request-id": str(uuid.uuid4()),
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}

    def _iid(self, sym):
        if sym not in self.ids:
            res = self._call("GET", f"/api/v1/market-data/search?internalSymbolFull={sym}")
            hit = [i for i in res.get("items", []) if str(i.get("internalSymbolFull", "")).upper() == sym]
            if not hit:
                raise RuntimeError(f"eToro has no instrument {sym}")
            self.ids[sym] = int(hit[0]["instrumentId"])
        return self.ids[sym]

    def open(self, symbol, side, notional, stop, target):
        body = {"action": "open", "transaction": "buy" if side > 0 else "sellShort", "instrumentId": self._iid(symbol),
                "orderType": "mkt", "leverage": 1, "amount": round(notional, 2), "orderCurrency": "usd",
                "stopLossRate": round(stop, 6), "takeProfitRate": round(target, 6), "stopLossType": "fixed"}
        res = self._call("POST", "/api/v2/trading/execution/demo/orders", body)     # 200 = accepted, not necessarily filled
        return str(res.get("orderId"))

    def close(self, symbol, ref):
        # Our practice trade ended. The mirrored position has its own stop/target on eToro; closing by hand/API needs the
        # positionId (from GET /api/v2/trading/info/demo/orders:lookup) and the demo close endpoint, which we could not
        # confirm from the docs. UNVERIFIED -> left to the broker-side stop/target. Never leaves an unprotected position.
        return "left to broker-side stop/target"


class MoomooSim(Broker):
    name = "moomoo"

    def __init__(self):
        super().__init__()
        self.host, self.port = os.environ.get("MOOMOO_HOST", "127.0.0.1"), int(os.environ.get("MOOMOO_PORT", "11111"))
        self.ctx = None

    def ready(self):
        try:
            import moomoo  # noqa: F401
        except Exception:
            return False
        return bool(os.environ.get("MOOMOO_ENABLE"))

    def _ctx(self):
        import moomoo as m
        if self.ctx is None:
            self.ctx = m.OpenUSTradeContext(host=self.host, port=self.port)
        return m, self.ctx

    def open(self, symbol, side, notional, stop, target):
        m, ctx = self._ctx()
        code = f"US.{symbol}"
        ok, q = m.OpenQuoteContext(host=self.host, port=self.port).get_market_snapshot([code])
        if ok != m.RET_OK:
            raise RuntimeError(str(q))
        px = float(q["last_price"][0])
        qty = max(1, int(notional / px))
        ret, d = ctx.place_order(price=px, qty=qty, code=code, trd_side=m.TrdSide.BUY if side > 0 else m.TrdSide.SELL,
                                 trd_env=m.TrdEnv.SIMULATE)            # SIMULATE ONLY
        if ret != m.RET_OK:
            raise RuntimeError(str(d))
        return str(d["order_id"][0])

    def close(self, symbol, ref):
        return "not implemented"


class MitradeStub(Broker):
    name = "mitrade"

    def info(self):
        d = super().info()
        d["last"] = "no public trading API found: use webhook alerts or manual"
        return d


class Executor:
    def __init__(self, brokers):
        self.brokers = [b for b in brokers if b.ready()]
        self.all = brokers
        self.max_notional = float(os.environ.get("BROKER_MAX_NOTIONAL", "500"))
        self.q = queue.Queue(maxsize=100)
        self.refs = {}
        if self.brokers:
            threading.Thread(target=self._run, daemon=True).start()

    def on_open(self, t):
        for b in self.brokers:
            try:
                self.q.put_nowait(("open", b, t["id"], t["symbol"], t["side"],
                                   min(t["size"] * t["entry"], self.max_notional), t["stop"], t["target"]))
            except queue.Full:
                b.failed += 1
                b.last = "queue full"

    def on_close(self, t):
        for b in self.brokers:
            try:
                self.q.put_nowait(("close", b, t["id"], t["symbol"], 0, 0, 0, 0))
            except queue.Full:
                pass

    def _run(self):
        while True:
            kind, b, tid, sym, side, notional, stop, target = self.q.get()
            try:
                if kind == "open":
                    self.refs[(b.name, tid)] = b.open(sym, side, notional, stop, target)
                    b.sent += 1
                    b.last = f"opened {sym} {'long' if side > 0 else 'short'} ${notional:.0f} (demo)"
                else:
                    b.last = str(b.close(sym, self.refs.get((b.name, tid))))
            except Exception as e:
                b.failed += 1
                b.last = f"{kind} failed: {str(e)[:100]}"

    def info(self):
        return [b.info() for b in self.all]


def make_executor():
    return Executor([EtoroDemo(), MitradeStub(), MoomooSim()])
