"""Run the swarm:   python main.py            (endless, dashboard at http://localhost:8765)
                   python main.py --cycles 500 --interval 0     (fast test run)
Paper trading only. Set ANTHROPIC_API_KEY to let Claude run the chief strategist + improver."""
import argparse
import os
import time

from config import Config
from dashboard import serve
from engine import Engine
from macro import make_macro


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=0, help="stop after N trading cycles (0 = run forever)")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between cycles")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 in the cloud (requires DASHBOARD_TOKEN)")
    ap.add_argument("--no-dashboard", action="store_true")
    ap.add_argument("--no-llm", action="store_true", help="run without Claude (pure quant fallback)")
    ap.add_argument("--live", action="store_true", help="real Binance prices (data only, still paper trading)")
    ap.add_argument("--keep", action="store_true", help="keep agent stats + lessons from the previous run")
    ap.add_argument("--academy", action="store_true", help="send the agents to school first: training round + graded exam")
    ap.add_argument("--train", type=int, default=400)
    ap.add_argument("--exam", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--db", default="brain.db")
    args = ap.parse_args()

    cfg = Config(seed=args.seed, db_path=args.db, keep_brain=args.keep, use_llm=not args.no_llm)
    eng = Engine(cfg, live=args.live)
    print(f"[start] {sum(len(s) for _, _, s in __import__('agents').GROUPS)} agents | "
          f"mode: {eng.market_note} | "
          f"Claude: {'ON (' + cfg.model + ')' if eng.llm.on else 'OFF (set ANTHROPIC_API_KEY to enable)'} | PAPER TRADING ONLY")
    if not args.no_dashboard:
        token = os.environ.get("DASHBOARD_TOKEN")
        if args.host not in ("127.0.0.1", "localhost") and not token:
            raise SystemExit("Refusing to expose the dashboard publicly without a password. "
                             "Set the DASHBOARD_TOKEN environment variable to a long random string.")
        serve(eng, args.port, args.host, token)
        print(f"[dashboard] http://{args.host}:{args.port}" + ("/?token=<DASHBOARD_TOKEN>" if token else ""))
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if url:   # free Render plans sleep without inbound traffic: ping our own public address so the swarm keeps trading
        import threading, urllib.request
        def _keep():
            while True:
                time.sleep(540)
                try:
                    urllib.request.urlopen(url.rstrip('/') + '/healthz', timeout=30).read(1)
                except Exception:
                    pass
        threading.Thread(target=_keep, daemon=True).start()
    if os.environ.get("MARKET_PIPE", "1") != "0":
        from pipe import MarketPipe
        eng.pipe = MarketPipe()
        print(f"[pipe] market pipe started: {len(eng.pipe.providers)} providers, {len(eng.pipe.declared)} feeds requested")

        def _pipe_log():
            while True:
                time.sleep(120)
                s = eng.pipe.summary()
                bad = [p["name"] + " (" + p["err"][:50] + ")" for p in eng.pipe.providers.values() if p["ok"] is False]
                print(f"[pipe] live feeds {s['live']} / {s['declared']} | providers ok {s['providers_ok']}/{s['providers']} | {s['by_cat']}")
                if bad:
                    print("[pipe] failing: " + "; ".join(bad[:25]))
        import threading as _th
        _th.Thread(target=_pipe_log, daemon=True).start()
    eng.macro = make_macro(eng.live, cfg.symbols, cfg.cycles_per_hour, args.seed)
    eng.macro.llm = eng.llm
    print(f"[warmup] building {cfg.warmup} candles of history ...")
    eng.warm()
    if args.academy:
        def prog(phase, i, tot, eq):
            print(f"[academy:{phase}] {i}/{tot} equity {eq:.2f}")
        rep = eng.academy(args.train, args.exam, prog)
        print("[graduation]", rep["summary"])
    eng.mirror = os.environ.get('MIRROR_TO_BROKERS') == '1'   # demo-account mirroring is opt-in
    n = 0
    try:
        while args.cycles == 0 or n < args.cycles:
            eng.step()
            n += 1
            if n % 25 == 0:
                s = eng.state()
                t = s["totals"]
                print(f"[cycle {s['cycle']}] equity {s['equity']:.2f} ({s['pnl']:+.2f}) dd {s['drawdown']:.1%} "
                      f"open {len(s['open_trades'])} trades {t['trades']} win {t['win_rate']} "
                      f"claude calls {s['llm']['calls']}{' HALTED' if s['halted'] else ''}")
            if args.interval:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[stopped]")
    s = eng.state()
    print(f"[final] cycles {n} | equity {s['equity']:.2f} ({s['pnl']:+.2f}) | closed trades {s['totals']['trades']} "
          f"| win rate {s['totals']['win_rate']} | max-drawdown guard {'TRIPPED' if s['halted'] else 'ok'}")


if __name__ == "__main__":
    main()
