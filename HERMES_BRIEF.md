# Brief for Hermes: Swarm Trader

**What it is:** a self-operating, multi-agent paper-trading system. It runs 24/7 in the cloud on Render
(https://swarm-trader.onrender.com, dashboard needs `?token=DASHBOARD_TOKEN` from Render → Environment).
Code: this repo. Render redeploys automatically on every push to `main`. Nothing runs on the owner's laptop.

**Rules you must keep**
- PAPER MONEY ONLY. No real orders, no wallets, no API keys with withdrawal or trading rights.
- Polymarket is blocked in Australia: paper bets only.
- Never weaken the risk manager (`decision.py: Risk`), the kill switch (12% drawdown) or the daily loss limit (3%).
- Fees are set to OKX's real taker fee (0.10%) in `config.py`; don't lower them to make results look better.

**How it works (data in → trades out)**
1. `pipe.py` + `pipe_more.py` + `ws_prices.py`: market pipe, 6 parallel pipelines (prices, futures, news,
   economy/analysts, world, signals), ~340 platforms and hundreds of news publishers, streaming prices from OKX/Bybit.
2. `agents.py`: teams of agents (60 analysts, scouts, quants, predictors, macro, pipe agents, smart-money copy team).
3. `council.py`: five seats (sources, sentiment, charts, thesis, risk) score each idea; a calibrated gate decides.
4. `decision.py`: the risk manager (six hard rules) approves every trade; `desks.py`: 11 trading desks.
5. `engine.py`: hourly candles + a FAST LANE every second (live stops/targets, News Desk reacting to news).
6. `polydesk.py`: Polymarket desk with 9 betting teams on the top ~150 markets (paper).
7. `livetraders.py`: real smart-money/crowd sources the copy team learns from.
8. `selfdev.py`: self-improvement every minute (news graded at 15 min, bad price sources dropped, team pulse),
   every 15 min for the first 12 live hours, then every hour (improvers, gate re-calibration, publisher trust).
9. Academy: on every start it trains on ~25 days of real history and sits an exam on unseen data.
10. `dashboard.py`: 21-page phone dashboard (BLUEPRINT page = live health check of every part).

**Status:** running live on paper. It has not yet passed its exam on real prices, so it must not trade real money.
**Owner actions only:** add `ANTHROPIC_API_KEY` in Render to turn on Claude features; upgrade Render to Starter for 5× CPU.
