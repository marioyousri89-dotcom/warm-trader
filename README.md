# Swarm Trader: 80 AI agents, one shared brain

A self-operating multi-agent trading system. **It paper-trades only: there is no real-money order code in it.**

## The idea

```
                      ┌─────────────── SHARED BRAIN (brain.py / SQLite) ───────────────┐
                      │ blackboard of signals · agent roster + trust weights · trades   │
                      │ lessons · equity · copy-trader records                          │
                      └───────────────▲───────────────────────────────▲────────────────┘
   15 Scouts ── new ideas             │ every agent reads/writes      │
   15 Market analysts ── regimes ─────┤ ONLY through the brain        │
   15 Quants ── is the edge real? ────┤                               │
   12 Copy agents ── skill vs luck ───┤                               │
   13 Predictors ── forecast ─────────┘                               │
   10 Improvers ── audit everyone, change the system ─────────────────┘

   votes (weighted by each agent's track record)
     → Claude, Chief Strategist (judgement, can veto)
     → Risk manager (hard limits, nobody can override)
     → Paper executor
     → results flow back into the brain → agents are re-scored → loop forever
```

* **Scouts** (15): breakout, momentum, mean-reversion, volume-spike, RSI, MA-cross lenses with different parameters.
* **Market analysts** (15): vote on the regime (up / down / range / volatile), plus breadth and cross-asset correlation.
* **Quants** (15): backtest every strategy with no look-ahead and judge it with 15 different tests (hit rate, t-stat, Sharpe, profit factor, drawdown, stability, cost-adjusted, ...). A strategy that fails the tests loses its voting power.
* **Copy agents** (12): rank the traders being watched with statistics that separate skill from luck (Wilson bound, t-stat, recent form, consensus) and mirror the good ones with a realistic one-candle lag. One agent fades the consistently bad traders.
* **Predictors** (13): linear regression, AR(1), pattern-matching (kNN), order-flow, trend strength, ensemble, z-score reversion.
* **Improvers** (10): retire agents that are significantly worse than a coin flip, clone and mutate the best, tune thresholds and risk **within hard bounds**, spot duplicate agents, check whether copy-trading is skill or luck, review fees, write lessons. One of them is **Claude**, which reads the scoreboard and proposes changes.

Every agent's trust is its measured accuracy: signals are scored after 3 candles, and weights move slowly (overlapping signals are not independent samples).

## Run it

```bash
python main.py                       # endless run, dashboard at http://localhost:8765
python main.py --cycles 500 --interval 0 --no-dashboard    # fast test run
```
Python 3.9+. The swarm itself needs no packages.

### Let Claude run it (chief strategist + improver)
```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
python main.py
```
Each cycle where a candidate is strong enough, Claude reviews the vote and can confirm, weaken, flip or veto it. Every 10 cycles Claude reviews the scoreboard and may suggest setting changes, which are clamped to safe bounds (`TUNABLE` in `config.py`). Without a key the system falls back to pure quant voting. **Cost control:** raise `--interval`, or `llm_every` in `config.py`.

### Options
`--live` real Binance prices (data only, still paper; **untested in the build sandbox**, which had no outbound network) · `--keep` keep agent stats and lessons between runs · `--seed` · `--no-llm`

## Run it in the cloud

The loop must run **continuously**, so use an always-on VM or container (not scale-to-zero services such as Cloud Run or Lambda).

```bash
docker build -t swarm-trader .
docker run -d --restart unless-stopped -p 8765:8765 -v swarm-data:/data \
  -e ANTHROPIC_API_KEY=sk-ant-... -e DASHBOARD_TOKEN=$(openssl rand -hex 24) swarm-trader
# open  http://YOUR_SERVER:8765/?token=YOUR_TOKEN
```

* **Any VPS** (Hetzner, DigitalOcean, AWS Lightsail/EC2, ...): install Docker, run the commands above. Put it behind HTTPS (Caddy or nginx) if you open it to the internet.
* **Fly.io / Railway / Render**: deploy the Dockerfile as an always-on service, set `ANTHROPIC_API_KEY` and `DASHBOARD_TOKEN` as secrets, attach a persistent volume mounted at `/data`, and expose the `PORT` it gives you.
* The server **refuses to bind publicly without `DASHBOARD_TOKEN`**. Keep keys in secrets/env vars, never in files.

## Files
`main.py` entry · `engine.py` the cycle loop and Claude chief · `agents.py` 80-agent roster · `improvers.py` the 10 improvers · `decision.py` aggregator, risk manager, paper portfolio · `strategies.py` indicators, lenses, backtest · `market.py` simulated market, simulated traders, optional live feed · `brain.py` shared database · `llm.py` Claude client · `dashboard.py` live page · `config.py` all settings

## Read this before trusting any number

* The built-in market is **simulated**, with artificial regimes and traders with hidden skill. Profit in the simulation proves the machinery works (agents get scored, weak ones retired, risk limits hold). **It says nothing about real-market profit.** Real edges are far smaller and disappear.
* Real copy-trading data is much harder: you see positions late, and the top trader of any group is often just the luckiest one. The skill-vs-luck statistics help, but do not remove that risk.
* Before any real money: run `--live` paper trading for weeks, compare against doing nothing, and only then consider a broker adapter behind `Portfolio.open_trade` / `close_trade`. The risk manager must stay in front of it, with money you can afford to lose. This is software, not financial advice.


---
# v2 additions

**Run it:** `python main.py --academy` (simulated market, trains then takes the exam) or add `--live` for real
Binance/Polymarket/Yahoo data (still PAPER). Cloud: build the Dockerfile on any always-on host (Fly.io, Railway,
Render, a VPS), set `DASHBOARD_TOKEN` and `ANTHROPIC_API_KEY`, open `https://your-app/?token=...` on your phone.

**What is new**
- 10 trading desks (consensus, scalper, trend, range, predict, copy-trader, copy-consensus, copy-desk, fader, sprinter).
  Capital is re-allocated every hour toward the desks earning the most per hour (min 3%, max 25% each); a desk that
  loses more than 1% of equity in 24h is benched for 2 hours.
- Macro team: Polymarket odds, S&P/Nasdaq/VIX, Claude as world-events analyst.
- Polymarket prediction desk (`polybook.py`): paper bets only; benches itself without a proven edge.
- Academy: training round, then an exam with everything frozen on unseen data, then a graduation report.
- Bull vs Bear debate inside the Chief Strategist; hard-coded risk veto that no agent can override.
- Development team: post-mortems every 40 cycles; Claude writes engineering proposals that WAIT FOR YOUR APPROVAL.
- App: pause / resume / flatten / clear-kill-switch buttons, chat, webhook `POST /api/signal?token=...`
  (TradingView / TrendSpider alerts become scored agents).
- Broker mirrors (`brokers.py`), DEMO ONLY, opt-in with `MIRROR_TO_BROKERS=1`: eToro demo (needs demo keys),
  moomoo simulated account (needs OpenD + `moomoo-api`), Mitrade (no public trading API found: webhook/manual only).
  These adapters were written from the docs and NOT run against the live services; test with tiny amounts.

**Honest limits.** Simulated results prove nothing about real markets. No system can promise 100% or "as much money
as possible": more aggressive settings mostly mean bigger losses. The risk manager and kill switch stay; you change
the limits yourself in `config.py`. Check the rules where you live before ever using real money or real Polymarket.

**Voice + General Manager (added last).** The "General Manager" card has a Speak button (browser speech recognition,
en-AU) and reads replies aloud. It needs Chrome or Safari, and https when you're not on localhost (any cloud host gives
you that). The manager knows the whole org chart, explains daily results (press "Daily briefing"; it also saves one
every simulated/real day), and discusses how to develop the system with you. By voice it can pause, resume or flatten
when you clearly order it; it cannot raise risk limits or clear the kill switch (use the button).

**Sessions + techniques.** Agents know the three sessions (Asia 00-07, London 07-13, New York 13-21 UTC, London/NY
overlap 13-16). New technique agents: London breakout of the Asia range, Asia fade, NY continuation, Bollinger, MACD
(plus RSI, moving-average cross, breakout, momentum, mean reversion, volume spike, regression, AR1, kNN already there).
The session_analyst improver measures P/L per session and sizes down sessions that lose (and up a little where it
earns, with statistics, never beyond x1.15). The exam report now lists how each technique scored on unseen data.
In the simulator the session volatility pattern is synthetic; only live data shows whether a session edge is real.
