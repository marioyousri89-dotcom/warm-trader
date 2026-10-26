"""Streaming prices (websockets): OKX + Bybit push every trade-price change to us, instead of us asking every 30-60 s.
Each tick lands in the shared pipe as 'okx-live:<SYM>' / 'bybit-live:<SYM>' within milliseconds. The fast lane uses
these first (they are fresher than anything polled)."""
import json
import threading
import time


def start(pipe, symbols):
    try:
        import websocket                    # pip package: websocket-client
    except Exception as e:
        print("[ws] websocket-client not installed, streaming off:", e)
        return
    pipe.ws_stats = {"okx": {"ticks": 0, "last": 0.0, "up": False}, "bybit": {"ticks": 0, "last": 0.0, "up": False}}

    def tick(src, sym, px):
        try:
            v = float(px)
        except Exception:
            return
        if v > 0:
            pipe._put(f"{src}-live:{sym}", "crypto", f"{src}-live", f"{sym} streaming on {src}", v, None, {"stream": True})
            st = pipe.ws_stats[src]
            st["ticks"] += 1
            st["last"] = time.time()

    def run(name, url, sub, ping, parse):
        while True:
            ws = None
            try:
                ws = websocket.create_connection(url, timeout=30)
                ws.send(json.dumps(sub))
                pipe.ws_stats[name]["up"] = True
                last_ping = time.time()
                while True:
                    if time.time() - last_ping > 20:
                        ws.send(ping)
                        last_ping = time.time()
                    try:
                        msg = ws.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    if not msg or msg == "pong":
                        continue
                    for sym, px in parse(json.loads(msg)):
                        tick(name, sym, px)
            except Exception as e:
                pipe.ws_stats[name]["up"] = False
                pipe.ws_stats[name]["err"] = str(e)[:80]
                time.sleep(5)
            finally:
                try:
                    ws and ws.close()
                except Exception:
                    pass

    def okx_parse(d):
        for x in d.get("data") or []:
            yield x.get("instId", "").split("-")[0], x.get("last")

    def bybit_parse(d):
        x = d.get("data")
        if isinstance(x, dict) and str(d.get("topic", "")).startswith("tickers."):
            yield d["topic"][8:].replace("USDT", ""), x.get("lastPrice")

    okx_sub = {"op": "subscribe", "args": [{"channel": "tickers", "instId": f"{s}-USDT"} for s in symbols]}
    by_sub = {"op": "subscribe", "args": [f"tickers.{s}USDT" for s in symbols]}
    threading.Thread(target=run, args=("okx", "wss://ws.okx.com:8443/ws/v5/public", okx_sub, "ping", okx_parse), daemon=True).start()
    threading.Thread(target=run, args=("bybit", "wss://stream.bybit.com/v5/public/spot", by_sub, json.dumps({"op": "ping"}),
                                       bybit_parse), daemon=True).start()
    print(f"[ws] streaming prices for {', '.join(symbols)} from OKX + Bybit")
