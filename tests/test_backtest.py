"""
Unit tests for the Historical Options Replay & Backtesting Engine (Roadmap Phase 5.1, #193).
Covers virtual portfolio state machine, dated snapshot replay harness, simulated fill models,
Stops 1-5 exit evaluation, quantitative risk metrics (Sharpe, Sortino, Max Drawdown),
and CLI routing.
"""

import json
import os
import shutil
import tempfile
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from src.gex.backtest import (
    BacktestEngine,
    HistoricalReplayHarness,
    calculate_backtest_metrics,
    calculate_simulated_entry_fill,
    calculate_simulated_exit_fill,
    simulate_backtest,
)
from src.gex.core.models import (
    BacktestConfig,
    BacktestDailySnapshot,
    BacktestResult,
    BacktestTrade,
)
from src.gex.presentation.formatters import (
    format_backtest_regime_breakdown,
    format_backtest_summary,
    format_backtest_trade_log,
)
import src.gex_engine as gex_engine


class TestBacktestModels(unittest.TestCase):
    """Tests strongly typed dataclasses for backtesting configuration and results."""

    def test_backtest_config_defaults_and_serialization(self):
        config = BacktestConfig(start_date="2026-11-01", end_date="2026-11-15")
        self.assertEqual(config.initial_capital, 100000.0)
        self.assertEqual(config.position_size_pct, 0.05)
        self.assertEqual(config.max_active_positions, 5)
        self.assertEqual(config.slippage_penalty_pct, 0.35)
        self.assertEqual(config.target_delta, 0.45)
        self.assertEqual(config.min_dte, 30)
        self.assertEqual(config.max_dte, 45)
        self.assertEqual(config.target_mode, "T1")

        data = config.to_dict()
        self.assertEqual(data["start_date"], "2026-11-01")
        self.assertEqual(data["initial_capital"], 100000.0)

    def test_backtest_trade_lifecycle_and_dict(self):
        trade = BacktestTrade(
            trade_id="BT-AAPL-0001",
            symbol="AAPL",
            option_id="opt_123",
            strike=150.0,
            expiration_date="2026-12-18",
            entry_date="2026-11-04",
            exit_date="2026-11-08",
            entry_price=4.20,
            exit_price=5.80,
            contracts=2,
            cost_basis=840.0,
            realized_pnl=320.0,
            realized_pnl_pct=38.10,
            holding_days=4,
            exit_reason="PROFIT_TARGET_T1",
            regime_at_entry="ALL TRACKS OK",
            status="CLOSED",
        )
        data = trade.to_dict()
        self.assertEqual(data["trade_id"], "BT-AAPL-0001")
        self.assertEqual(data["realized_pnl"], 320.0)
        self.assertEqual(data["exit_reason"], "PROFIT_TARGET_T1")
        self.assertEqual(data["status"], "CLOSED")

    def test_backtest_daily_snapshot(self):
        snap = BacktestDailySnapshot(
            date="2026-11-04",
            cash=95000.0,
            portfolio_equity=101200.0,
            unrealized_pnl=1200.0,
            open_positions_count=2,
            regime_status="ALL TRACKS OK",
        )
        data = snap.to_dict()
        self.assertEqual(data["date"], "2026-11-04")
        self.assertEqual(data["portfolio_equity"], 101200.0)


class TestSimulatedFills(unittest.TestCase):
    """Tests execution realism and 35% bid-ask spread penalty modeling."""

    def test_entry_fill_with_spread(self):
        quote = {
            "bid_price": "4.00",
            "ask_price": "4.50",
            "adjusted_mark_price": "4.25",
        }
        # spread = 0.50, penalty = 0.35 * 0.50 = 0.175 -> entry = 4.25 + 0.175 = 4.425 -> 4.42 (banker's rounding)
        fill = calculate_simulated_entry_fill(quote, slippage_penalty_pct=0.35)
        self.assertAlmostEqual(fill, 4.42, places=2)

    def test_exit_fill_with_spread(self):
        quote = {
            "bid_price": "5.00",
            "ask_price": "5.40",
            "adjusted_mark_price": "5.20",
        }
        # spread = 0.40, penalty = 0.35 * 0.40 = 0.14 -> exit = 5.20 - 0.14 = 5.06
        fill = calculate_simulated_exit_fill(quote, slippage_penalty_pct=0.35)
        self.assertAlmostEqual(fill, 5.06, places=2)

    def test_fill_zero_spread_fallback(self):
        quote = {"bid_price": "3.00", "ask_price": "3.00", "mark_price": "3.00"}
        entry_fill = calculate_simulated_entry_fill(quote)
        exit_fill = calculate_simulated_exit_fill(quote)
        self.assertEqual(entry_fill, 3.00)
        self.assertEqual(exit_fill, 3.00)

    def test_fill_minimum_clamping(self):
        quote = {"bid_price": "0.00", "ask_price": "0.01", "mark_price": "0.00"}
        exit_fill = calculate_simulated_exit_fill(quote)
        self.assertGreaterEqual(exit_fill, 0.01)


class TestQuantitativeMetrics(unittest.TestCase):
    """Tests mathematical calculation of Sharpe, Sortino, Max Drawdown, and Profit Factor."""

    def test_metrics_calculation_deterministic(self):
        config = BacktestConfig(initial_capital=100000.0)
        trades = [
            BacktestTrade(
                trade_id="BT-1", symbol="NVDA", option_id="opt1", strike=120.0,
                expiration_date="2026-12-18", entry_date="2026-11-04", exit_date="2026-11-06",
                entry_price=3.0, exit_price=4.5, contracts=2, cost_basis=600.0,
                realized_pnl=300.0, realized_pnl_pct=50.0, holding_days=2,
                exit_reason="PROFIT_TARGET_T1", regime_at_entry="ALL TRACKS OK",
            ),
            BacktestTrade(
                trade_id="BT-2", symbol="AMD", option_id="opt2", strike=140.0,
                expiration_date="2026-12-18", entry_date="2026-11-05", exit_date="2026-11-07",
                entry_price=2.0, exit_price=1.6, contracts=2, cost_basis=400.0,
                realized_pnl=-80.0, realized_pnl_pct=-20.0, holding_days=2,
                exit_reason="STOP1", regime_at_entry="TRACK 1 OK",
            ),
        ]
        snapshots = [
            BacktestDailySnapshot("2026-11-04", 99400.0, 100000.0, 0.0, 1, "ALL TRACKS OK"),
            BacktestDailySnapshot("2026-11-05", 99000.0, 100200.0, 200.0, 2, "ALL TRACKS OK"),
            BacktestDailySnapshot("2026-11-06", 99900.0, 100300.0, 300.0, 1, "TRACK 1 OK"),
            BacktestDailySnapshot("2026-11-07", 100220.0, 100220.0, 220.0, 0, "TRACK 1 OK"),
        ]

        result = calculate_backtest_metrics(
            config=config,
            start_date="2026-11-04",
            end_date="2026-11-07",
            simulation_days=4,
            initial_capital=100000.0,
            final_equity=100220.0,
            closed_trades=trades,
            daily_snapshots=snapshots,
        )

        self.assertEqual(result.total_trades, 2)
        self.assertEqual(result.winning_trades, 1)
        self.assertEqual(result.losing_trades, 1)
        self.assertEqual(result.win_rate, 50.0)
        self.assertEqual(result.total_realized_pnl, 220.0)
        self.assertAlmostEqual(result.total_return_pct, 0.22, places=2)
        # Profit factor: 300 / 80 = 3.75
        self.assertAlmostEqual(result.profit_factor, 3.75, places=2)
        # Max drawdown: (100300 - 100220) / 100300 = 80 / 100300 = 0.0797%
        self.assertAlmostEqual(result.max_drawdown_pct, 0.08, places=2)
        self.assertEqual(result.trades_by_exit_reason.get("PROFIT_TARGET_T1"), 1)
        self.assertEqual(result.trades_by_exit_reason.get("STOP1"), 1)
        self.assertEqual(result.trades_by_regime["ALL TRACKS OK"]["total_trades"], 1)
        self.assertEqual(result.trades_by_regime["TRACK 1 OK"]["total_trades"], 1)


class TestReplayHarnessAndStateSimulation(unittest.TestCase):
    """Tests discovery, ingestion, and simulation lifecycle across simulated dated folders."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

        # Day 1: 20261104 - AAPL setup qualified and entered
        day1 = os.path.join(self.test_dir, "20261104")
        os.makedirs(day1)

        # Mock ETF quotes (Regime: ALL TRACKS OK)
        etf_quotes = {
            "results": [
                {"symbol": "SPY", "last_trade_price": "505.00", "previous_close": "500.00"},  # +1.0% -> Basket PASS
                {"symbol": "QQQ", "last_trade_price": "430.00", "previous_close": "428.00"},
                {"symbol": "IWM", "last_trade_price": "205.00", "previous_close": "200.00"},
                {"symbol": "DIA", "last_trade_price": "390.00", "previous_close": "388.00"},
            ]
        }
        with open(os.path.join(day1, "etf_quotes.json"), "w") as f:
            json.dump(etf_quotes, f)

        # Underlier quotes
        underlier_quotes = {
            "results": [{"symbol": "AAPL", "last_trade_price": "150.00"}]
        }
        with open(os.path.join(day1, "aapl_underlier_quotes.json"), "w") as f:
            json.dump(underlier_quotes, f)

        # Options Instruments & Quotes for AAPL
        inst_data = {
            "instruments": [
                {
                    "id": "aapl_c_155",
                    "strike_price": "155.00",
                    "type": "call",
                    "expiration_date": "2026-12-18",
                },
                {
                    "id": "aapl_c_160",
                    "strike_price": "160.00",
                    "type": "call",
                    "expiration_date": "2026-12-18",
                },
                {
                    "id": "aapl_p_140",
                    "strike_price": "140.00",
                    "type": "put",
                    "expiration_date": "2026-12-18",
                },
            ]
        }
        with open(os.path.join(day1, "aapl_option_instruments.json"), "w") as f:
            json.dump(inst_data, f)

        quotes_data = {
            "results": [
                {
                    "instrument_id": "aapl_c_155",
                    "strike_price": "155.00",
                    "type": "call",
                    "expiration_date": "2026-12-18",
                    "bid_price": "3.80",
                    "ask_price": "4.20",
                    "adjusted_mark_price": "4.00",
                    "open_interest": 5000,
                    "delta": "0.45",
                    "gamma": "0.03",
                    "implied_volatility": "0.32",
                },
                {
                    "instrument_id": "aapl_c_160",
                    "strike_price": "160.00",
                    "type": "call",
                    "expiration_date": "2026-12-18",
                    "bid_price": "2.10",
                    "ask_price": "2.30",
                    "adjusted_mark_price": "2.20",
                    "open_interest": 8000,
                    "delta": "0.30",
                    "gamma": "0.02",
                    "implied_volatility": "0.30",
                },
                {
                    "instrument_id": "aapl_p_140",
                    "strike_price": "140.00",
                    "type": "put",
                    "expiration_date": "2026-12-18",
                    "bid_price": "1.50",
                    "ask_price": "1.70",
                    "adjusted_mark_price": "1.60",
                    "open_interest": 10000,
                    "delta": "-0.20",
                    "gamma": "0.02",
                    "implied_volatility": "0.35",
                },
            ]
        }
        with open(os.path.join(day1, "aapl_option_quotes.json"), "w") as f:
            json.dump(quotes_data, f)

        # Candidates scan
        with open(os.path.join(day1, "scan_gex_momentum_raw.json"), "w") as f:
            json.dump({"results": [{"symbol": "AAPL"}]}, f)

        # Day 2: 20261105 - AAPL spot rises to 162.00 (hits +GEX call wall -> T1 Target triggered)
        day2 = os.path.join(self.test_dir, "20261105")
        os.makedirs(day2)

        with open(os.path.join(day2, "etf_quotes.json"), "w") as f:
            json.dump(etf_quotes, f)

        with open(os.path.join(day2, "aapl_underlier_quotes.json"), "w") as f:
            json.dump({"results": [{"symbol": "AAPL", "last_trade_price": "162.00"}]}, f)

        with open(os.path.join(day2, "aapl_option_instruments.json"), "w") as f:
            json.dump(inst_data, f)

        quotes_data_day2 = {
            "results": [
                {
                    "instrument_id": "aapl_c_155",
                    "strike_price": "155.00",
                    "type": "call",
                    "expiration_date": "2026-12-18",
                    "bid_price": "7.80",
                    "ask_price": "8.20",
                    "adjusted_mark_price": "8.00",
                    "open_interest": 5000,
                    "delta": "0.75",
                    "gamma": "0.02",
                    "implied_volatility": "0.34",
                }
            ]
        }
        with open(os.path.join(day2, "aapl_option_quotes.json"), "w") as f:
            json.dump(quotes_data_day2, f)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_dated_directory_discovery(self):
        harness = HistoricalReplayHarness(downloads_dir=self.test_dir)
        dated = harness.discover_dated_directories()
        self.assertEqual(len(dated), 2)
        self.assertEqual(dated[0][0], "2026-11-04")
        self.assertEqual(dated[1][0], "2026-11-05")

        # Test date filtering
        filtered = harness.discover_dated_directories(start_date="2026-11-05")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0][0], "2026-11-05")

    def test_end_to_end_backtest_simulation(self):
        config = BacktestConfig(
            start_date="2026-11-04",
            end_date="2026-11-05",
            initial_capital=50000.0,
            position_size_pct=0.10,
        )
        result = simulate_backtest(config=config, downloads_dir=self.test_dir)

        self.assertEqual(result.simulation_days, 2)
        self.assertEqual(result.total_trades, 1)
        self.assertEqual(result.winning_trades, 1)
        self.assertEqual(result.losing_trades, 0)
        self.assertEqual(result.win_rate, 100.0)
        self.assertGreater(result.total_realized_pnl, 0.0)
        self.assertGreater(result.final_equity, 50000.0)
        self.assertEqual(result.trades[0].symbol, "AAPL")
        self.assertTrue(result.trades[0].exit_reason.startswith("PROFIT_TARGET"))


class TestPresentationFormatters(unittest.TestCase):
    """Tests ASCII and tabular reporting formatters for backtesting."""

    def test_formatters_render(self):
        config = BacktestConfig(initial_capital=100000.0)
        trade = BacktestTrade(
            trade_id="BT-AAPL-0001", symbol="AAPL", option_id="opt_1", strike=150.0,
            expiration_date="2026-12-18", entry_date="2026-11-04", exit_date="2026-11-05",
            entry_price=4.0, exit_price=6.0, contracts=2, cost_basis=800.0,
            realized_pnl=400.0, realized_pnl_pct=50.0, holding_days=1,
            exit_reason="PROFIT_TARGET_T1", regime_at_entry="ALL TRACKS OK",
        )
        result = BacktestResult(
            config=config,
            start_date="2026-11-04",
            end_date="2026-11-05",
            simulation_days=2,
            initial_capital=100000.0,
            final_equity=100400.0,
            total_realized_pnl=400.0,
            total_return_pct=0.40,
            total_trades=1,
            winning_trades=1,
            losing_trades=0,
            win_rate=100.0,
            profit_factor=999.99,
            max_drawdown_pct=0.0,
            sharpe_ratio=2.15,
            sortino_ratio=3.40,
            avg_holding_days=1.0,
            trades_by_regime={"ALL TRACKS OK": {"total_trades": 1, "winning_trades": 1, "win_rate": 100.0, "realized_pnl": 400.0}},
            trades_by_exit_reason={"PROFIT_TARGET_T1": 1},
            daily_snapshots=[],
            trades=[trade],
        )

        summary = format_backtest_summary(result)
        self.assertIn("GEX SYSTEMATIC HISTORICAL BACKTEST PERFORMANCE SUMMARY", summary)
        self.assertIn("100.0%", summary)

        breakdown = format_backtest_regime_breakdown(result)
        self.assertIn("ALL TRACKS OK", breakdown)

        log = format_backtest_trade_log(result)
        self.assertIn("BT-AAPL-0001", log)
        self.assertIn("AAPL", log)


class TestCLIAndRootReexports(unittest.TestCase):
    """Tests CLI subparser routing, JSON flag output, and backward-compatible root re-exports."""

    def test_root_reexports(self):
        self.assertTrue(hasattr(gex_engine, "BacktestConfig"))
        self.assertTrue(hasattr(gex_engine, "BacktestTrade"))
        self.assertTrue(hasattr(gex_engine, "BacktestResult"))
        self.assertTrue(hasattr(gex_engine, "BacktestEngine"))
        self.assertTrue(hasattr(gex_engine, "HistoricalReplayHarness"))
        self.assertTrue(hasattr(gex_engine, "simulate_backtest"))
        self.assertTrue(hasattr(gex_engine, "calculate_backtest_metrics"))
        self.assertTrue(hasattr(gex_engine, "calculate_simulated_entry_fill"))
        self.assertTrue(hasattr(gex_engine, "calculate_simulated_exit_fill"))

    def test_cmd_backtest_cli_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = MagicMock()
            args.start = "2026-11-04"
            args.end = "2026-11-05"
            args.capital = 100000.0
            args.max_positions = 5
            args.position_size_pct = 0.05
            args.target_delta = 0.45
            args.min_dte = 30
            args.max_dte = 45
            args.target_mode = "T1"
            args.downloads_dir = tmpdir
            args.json = True

            with patch("builtins.print") as mock_print:
                gex_engine.cmd_backtest(args)
                self.assertTrue(mock_print.called)
                printed_str = mock_print.call_args[0][0]
                parsed = json.loads(printed_str)
                self.assertIn("config", parsed)
                self.assertIn("simulation_days", parsed)


if __name__ == "__main__":
    unittest.main()
