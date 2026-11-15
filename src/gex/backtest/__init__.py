"""
Historical Options Replay & Backtesting Engine for the GEX Options Trading System.
Provides deterministic simulation of dealer gamma setups, execution slippage,
Stops 1-5 evaluation, and quantitative risk/expectancy analytics.
"""

from src.gex.core.models import (
    BacktestConfig,
    BacktestDailySnapshot,
    BacktestResult,
    BacktestTrade,
)
from src.gex.backtest.engine import (
    BacktestEngine,
    HistoricalReplayHarness,
    calculate_backtest_metrics,
    calculate_simulated_entry_fill,
    calculate_simulated_exit_fill,
    simulate_backtest,
)

__all__ = [
    "BacktestConfig",
    "BacktestDailySnapshot",
    "BacktestResult",
    "BacktestTrade",
    "BacktestEngine",
    "HistoricalReplayHarness",
    "calculate_backtest_metrics",
    "calculate_simulated_entry_fill",
    "calculate_simulated_exit_fill",
    "simulate_backtest",
]
