"""
Unit tests for Defined-Risk Vertical Spread Architecture & Payoff Engine.
Verifies Milestone 6.1 implementation.
"""

import json
import os
import tempfile
import unittest

from src.gex.core.models import VerticalSpread
from src.gex.screening.spreads import (
    calculate_spread_payoff,
    select_vertical_spread,
)
from src.gex.presentation.formatters import (
    format_vertical_spread_summary,
)


class TestSpreadPayoffCalculations(unittest.TestCase):
    """Tests for calculate_spread_payoff mathematical formulas."""

    def test_basic_payoff(self):
        # Long 100 strike at $4.00, Short 110 strike at $1.50
        # No slippage (mid-only)
        res = calculate_spread_payoff(
            long_strike=100.0,
            short_strike=110.0,
            long_mark=4.0,
            short_mark=1.5,
            long_ask=4.0,
            long_bid=4.0,
            short_ask=1.5,
            short_bid=1.5,
            slippage_factor=0.0,
        )
        self.assertEqual(res["width"], 10.0)
        self.assertAlmostEqual(res["net_debit"], 2.50, places=2)
        self.assertAlmostEqual(res["max_loss"], 250.0, places=2)
        self.assertAlmostEqual(res["max_profit"], 750.0, places=2)
        self.assertAlmostEqual(res["breakeven"], 102.50, places=2)
        self.assertAlmostEqual(res["risk_reward_ratio"], 3.0, places=2)
        # Naked long call would cost $400. Spread costs $250 -> 37.5% savings
        self.assertAlmostEqual(res["capital_savings_pct"], 37.5, places=1)

    def test_payoff_with_slippage(self):
        # Long: Bid 3.90, Ask 4.10, Mark 4.00 (Spread = 0.20)
        # Short: Bid 1.40, Ask 1.60, Mark 1.50 (Spread = 0.20)
        # Total spread = 0.40. Slippage = 0.40 * 0.35 * 0.5 = 0.07
        # Net debit = 2.50 + 0.07 = 2.57
        res = calculate_spread_payoff(
            long_strike=100.0,
            short_strike=110.0,
            long_mark=4.0,
            short_mark=1.5,
            long_ask=4.10,
            long_bid=3.90,
            short_ask=1.60,
            short_bid=1.40,
            slippage_factor=0.35,
        )
        self.assertAlmostEqual(res["net_debit"], 2.57, places=2)
        self.assertAlmostEqual(res["natural_debit"], 2.70, places=2)  # 4.10 - 1.40
        self.assertAlmostEqual(res["max_profit"], 743.0, places=2)

    def test_invalid_strike_ordering(self):
        # Short strike <= Long strike raises ValueError
        with self.assertRaises(ValueError):
            calculate_spread_payoff(
                long_strike=110.0,
                short_strike=100.0,
                long_mark=1.5,
                short_mark=4.0,
            )
        with self.assertRaises(ValueError):
            calculate_spread_payoff(
                long_strike=100.0,
                short_strike=100.0,
                long_mark=3.0,
                short_mark=3.0,
            )


class TestVerticalSpreadSelection(unittest.TestCase):
    """Tests for select_vertical_spread pairing and candidate selection."""

    def setUp(self):
        # Build standard mock options dataset
        # Spot = 100.0, Target GEX Call Wall = 110.0
        # Expiration: 35 days out
        self.exp_date = "2026-11-20"
        self.today = "2026-10-16"  # 35 DTE

        self.mock_instruments = [
            {"id": "call_95", "type": "call", "strike_price": 95.0, "expiration_date": self.exp_date, "chain_symbol": "TEST"},
            {"id": "call_100", "type": "call", "strike_price": 100.0, "expiration_date": self.exp_date, "chain_symbol": "TEST"},
            {"id": "call_105", "type": "call", "strike_price": 105.0, "expiration_date": self.exp_date, "chain_symbol": "TEST"},
            {"id": "call_110", "type": "call", "strike_price": 110.0, "expiration_date": self.exp_date, "chain_symbol": "TEST"},
            {"id": "call_115", "type": "call", "strike_price": 115.0, "expiration_date": self.exp_date, "chain_symbol": "TEST"},
            # Short-dated expiration (< 14 DTE, should be excluded)
            {"id": "call_short", "type": "call", "strike_price": 100.0, "expiration_date": "2026-10-20", "chain_symbol": "TEST"},
        ]

        self.mock_quotes = [
            {"quote": {"instrument_id": "call_95", "bid_price": 6.80, "ask_price": 7.00, "mark_price": 6.90, "open_interest": 1000, "delta": 0.65}},
            {"quote": {"instrument_id": "call_100", "bid_price": 3.90, "ask_price": 4.10, "mark_price": 4.00, "open_interest": 2500, "delta": 0.48}},
            {"quote": {"instrument_id": "call_105", "bid_price": 1.90, "ask_price": 2.10, "mark_price": 2.00, "open_interest": 1800, "delta": 0.30}},
            {"quote": {"instrument_id": "call_110", "bid_price": 0.85, "ask_price": 0.95, "mark_price": 0.90, "open_interest": 3200, "delta": 0.18}},
            {"quote": {"instrument_id": "call_115", "bid_price": 0.35, "ask_price": 0.45, "mark_price": 0.40, "open_interest": 800, "delta": 0.08}},
            {"quote": {"instrument_id": "call_short", "bid_price": 1.00, "ask_price": 1.10, "mark_price": 1.05, "open_interest": 100, "delta": 0.50}},
        ]

    def test_select_best_spread_pegged_to_call_wall(self):
        best_spread, all_spreads = select_vertical_spread(
            inst_data=self.mock_instruments,
            quotes_data=self.mock_quotes,
            spot=100.0,
            gex_target=110.0,
            today_override=self.today,
        )

        self.assertIsNotNone(best_spread)
        # Long leg should be ATM strike 100.0 (delta 0.48)
        self.assertEqual(best_spread.long_strike, 100.0)
        # Short leg should be pegged to +GEX strike 110.0
        self.assertEqual(best_spread.short_strike, 110.0)
        self.assertEqual(best_spread.width, 10.0)
        self.assertGreater(best_spread.max_profit, best_spread.max_loss)
        self.assertGreater(best_spread.capital_savings_pct, 20.0)
        self.assertTrue(best_spread.spread_ok)
        self.assertTrue(best_spread.oi_ok)
        self.assertFalse(best_spread.earnings_blocked)

    def test_earnings_blackout_flag(self):
        # Earnings occur before expiration date (e.g. 2026-11-10 <= 2026-11-20)
        best_spread, _ = select_vertical_spread(
            inst_data=self.mock_instruments,
            quotes_data=self.mock_quotes,
            spot=100.0,
            gex_target=110.0,
            earnings_date="2026-11-10",
            today_override=self.today,
        )
        self.assertIsNotNone(best_spread)
        self.assertTrue(best_spread.earnings_blocked)

    def test_empty_or_illiquid_inputs(self):
        best_spread, all_spreads = select_vertical_spread(
            inst_data=[],
            quotes_data=[],
            spot=100.0,
        )
        self.assertIsNone(best_spread)
        self.assertEqual(len(all_spreads), 0)


class TestVerticalSpreadFormatting(unittest.TestCase):
    """Tests for format_vertical_spread_summary."""

    def test_formatting_output(self):
        spread = VerticalSpread(
            symbol="NVDA",
            expiration_date="2026-11-20",
            dte=35,
            long_strike=120.0,
            short_strike=130.0,
            long_option_id="opt_120",
            short_option_id="opt_130",
            long_mark=5.0,
            short_mark=1.8,
            long_ask=5.10,
            long_bid=4.90,
            short_ask=1.90,
            short_bid=1.70,
            net_debit=3.27,
            max_profit=673.0,
            max_loss=327.0,
            breakeven=123.27,
            risk_reward_ratio=2.06,
            capital_savings_pct=34.6,
            long_delta=0.48,
            short_delta=0.22,
            net_delta=0.26,
            long_oi=1500,
            short_oi=2800,
            earnings_blocked=False,
            spread_ok=True,
            oi_ok=True,
        )

        res = format_vertical_spread_summary(spread)
        self.assertIn("NVDA", res)
        self.assertIn("Bull Call Debit Spread", res)
        self.assertIn("Strike $120.00", res)
        self.assertIn("Strike $130.00", res)
        self.assertIn("Net Debit", res)
        self.assertIn("Max Profit", res)
        self.assertIn("34.6%", res)
        self.assertIn("LIQUIDITY: PASS", res)


class TestVerticalSpreadModel(unittest.TestCase):
    """Tests for VerticalSpread dataclass methods."""

    def test_to_dict(self):
        spread = VerticalSpread(
            symbol="AAPL",
            expiration_date="2026-12-18",
            dte=42,
            long_strike=220.0,
            short_strike=235.0,
            long_option_id="opt_220",
            short_option_id="opt_235",
            long_mark=6.0,
            short_mark=2.0,
            long_ask=6.10,
            long_bid=5.90,
            short_ask=2.10,
            short_bid=1.90,
            net_debit=4.10,
            max_profit=1090.0,
            max_loss=410.0,
            breakeven=224.10,
            risk_reward_ratio=2.66,
            capital_savings_pct=31.7,
            long_delta=0.45,
            short_delta=0.20,
            net_delta=0.25,
        )
        d = spread.to_dict()
        self.assertEqual(d["symbol"], "AAPL")
        self.assertEqual(d["width"], 15.0)
        self.assertEqual(d["net_debit"], 4.10)
        self.assertEqual(d["max_profit"], 1090.0)


class TestSelectSpreadsCLI(unittest.TestCase):
    """Tests for select-spreads CLI execution."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.inst_file = os.path.join(self.tmp_dir, "inst.json")
        self.quote_file = os.path.join(self.tmp_dir, "quotes.json")

        inst_data = [
            {"id": "call_100", "type": "call", "strike_price": 100.0, "expiration_date": "2026-12-18", "chain_symbol": "XYZ"},
            {"id": "call_110", "type": "call", "strike_price": 110.0, "expiration_date": "2026-12-18", "chain_symbol": "XYZ"},
        ]
        quotes_data = [
            {"quote": {"instrument_id": "call_100", "bid_price": 3.90, "ask_price": 4.10, "mark_price": 4.00, "open_interest": 1000, "delta": 0.50}},
            {"quote": {"instrument_id": "call_110", "bid_price": 1.40, "ask_price": 1.60, "mark_price": 1.50, "open_interest": 1500, "delta": 0.25}},
        ]
        with open(self.inst_file, "w") as f:
            json.dump(inst_data, f)
        with open(self.quote_file, "w") as f:
            json.dump(quotes_data, f)

    def tearDown(self):
        import shutil
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)

    def test_cli_select_spreads(self):
        import io
        from unittest.mock import patch
        from src.gex_engine import cmd_select_spreads

        class Args:
            symbol = "XYZ"
            spot = 100.0
            gex = 110.0
            inst_file = self.inst_file
            quote_file = self.quote_file
            earnings_date = None
            target_delta = 0.45
            min_dte = 20
            max_dte = 50
            json = True

        out = io.StringIO()
        with patch("sys.stdout", out):
            cmd_select_spreads(Args())

        output_str = out.getvalue()
        payload = json.loads(output_str)
        self.assertEqual(payload["symbol"], "XYZ")
        self.assertEqual(payload["best_spread"]["long_strike"], 100.0)
        self.assertEqual(payload["best_spread"]["short_strike"], 110.0)
        self.assertGreater(payload["best_spread"]["capital_savings_pct"], 30.0)


if __name__ == "__main__":
    unittest.main()
