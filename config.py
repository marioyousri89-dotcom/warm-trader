from dataclasses import dataclass


@dataclass
class Config:
    symbols: tuple = ("BTC", "ETH", "SOL")
    start_equity: float = 10_000.0
    seed: int = 7
    t0: int = 0                      # cycle where the graded run starts (set by the engine; moves after the academy)
    db_path: str = "brain.db"
    keep_brain: bool = False        # keep agent stats + lessons from a previous run

    horizon: int = 3                # candles a signal is judged over
    warmup: int = 260               # candles of history before agents start

    # decision layer (the Improver agents / Claude may tune these within TUNABLE bounds)
    agg_threshold: float = 0.22
    min_agents: int = 4
    llm_weight: float = 0.35

    # risk manager (hard limits, agents cannot override)
    risk_per_trade: float = 0.01
    max_positions: int = 8              # across all desks
    max_positions_per_desk: int = 2
    max_exposure: float = 1.0           # total gross position size <= 1x equity (no leverage)
    max_symbol_exposure: float = 0.35
    max_trade_exposure: float = 0.15    # one trade can't exceed 15% of equity (scaled by the desk's capital share)
    max_heat: float = 0.04              # money at risk (to the stops) across ALL open trades <= 4% of equity
    desk_min_share: float = 0.03
    desk_max_share: float = 0.25
    desk_loss_limit: float = 0.01       # a desk losing > 1% of total equity in 24h is paused
    desk_pause_hours: int = 2
    cycles_per_hour: int = 4            # simulated candle = 15 min; live mode uses 1-hour candles (1)
    daily_loss_limit: float = 0.03
    max_drawdown: float = 0.12       # kill switch
    cycles_per_day: int = 96
    fee: float = 0.0010                # OKX taker fee (the platform chosen for live trading)
    slippage: float = 0.0002
    stop_atr: float = 1.5
    target_atr: float = 2.0
    time_stop: int = 4              # signals are judged over ~3 candles, so don't hold much longer

    quant_every: int = 10
    improve_every: int = 10
    llm_every: int = 1               # ask Claude the chief-strategist question every N cycles
    model: str = "claude-sonnet-5-5"
    use_llm: bool = True


# Things the AI improvers are allowed to change, with hard bounds.
TUNABLE = {
    "agg_threshold": (0.10, 0.60),
    "min_agents": (2, 10),
    "llm_weight": (0.0, 0.70),
    "risk_per_trade": (0.0025, 0.02),
}
