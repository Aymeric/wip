"""
Unit tests for Milestone 5.11: Pre-Earnings Vega Run-Up Harvester (GitHub issue #197).
Tests analytical Black-Scholes Vega, PreEarningsCandidate domain models,
window gating (15-25 DTE), Rule 7 mandatory exit enforcement (T-14),
IV Rank filtering (<= 40%), and CLI formatting / execution.
"""

import argparse
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.gex.core.models import PreEarningsCandidate
from src.gex.presentation.formatters import format_pre_earnings_table
from src.gex.quant.greeks import calculate_black_scholes_vega
from src.gex.screening.vega_scanner import (
    calculate_pre_earnings_vega_setup,
    scan_pre_earnings_candidates,
)
from src.gex.cli.screening import cmd_pre_earnings_candidates
import gex_engine


class TestBlackScholesVega(unittest.TestCase):
    """Validates analytical Black-Scholes Vega calculations and boundary conditions."""

    def test_vega_at_the_money(self):
        """Verify Vega calculation for standard ATM equity options."""
        # Spot = 100, Strike = 100, DTE = 30, IV = 0.30
        vega = calculate_black_scholes_vega(spot=100.0, strike=100.0, dte_days=30.0, iv=0.30)
        self.assertGreater(vega, 11.0)
        self.assertLess(vega, 12.0)

    def test_vega_highest_atm(self):
        """Verify Vega peaks ATM and decays as strikes move ITM or OTM."""
        vega_atm = calculate_black_scholes_vega(spot=100.0, strike=100.0, dte_days=30.0, iv=0.30)
        vega_otm = calculate_black_scholes_vega(spot=100.0, strike=120.0, dte_days=30.0, iv=0.30)
        vega_itm = calculate_black_scholes_vega(spot=100.0, strike=80.0, dte_days=30.0, iv=0.30)

        self.assertGreater(vega_atm, vega_otm)
        self.assertGreater(vega_atm, vega_itm)

    def test_vega_scaling_with_time(self):
        """Verify Vega increases proportionally with sqrt(T)."""
        vega_30 = calculate_black_scholes_vega(spot=100.0, strike=100.0, dte_days=30.0, iv=0.30)
        vega_60 = calculate_black_scholes_vega(spot=100.0, strike=100.0, dte_days=60.0, iv=0.30)
        self.assertGreater(vega_60, vega_30)

    def test_vega_edge_cases_non_negative(self):
        """Verify Vega handles non-positive inputs gracefully without throwing."""
        self.assertEqual(calculate_black_scholes_vega(spot=0.0, strike=100.0, dte_days=30.0, iv=0.30), 0.0)
        self.assertEqual(calculate_black_scholes_vega(spot=100.0, strike=0.0, dte_days=30.0, iv=0.30), 0.0)
        self.assertEqual(calculate_black_scholes_vega(spot=100.0, strike=100.0, dte_days=30.0, iv=0.0), 0.0)
        self.assertEqual(calculate_black_scholes_vega(spot=-10.0, strike=100.0, dte_days=30.0, iv=0.30), 0.0)
        self.assertEqual(calculate_black_scholes_vega(spot=100.0, strike=100.0, dte_days=-5.0, iv=0.30), 0.0)


class TestPreEarningsCandidateModel(unittest.TestCase):
    """Validates the PreEarningsCandidate domain dataclass and serialization."""

    def test_model_to_dict(self):
        candidate = PreEarningsCandidate(
            symbol="AAPL",
            spot=230.50,
            earnings_date="2026-12-10",
            days_to_earnings=22,
            mandatory_exit_date="2026-11-26",
            current_iv=0.285,
            iv_rank=24.5,
            iv_percentile=30.0,
            historical_high_iv=0.55,
            projected_iv_target=0.4175,
            projected_iv_expansion=0.1325,
            option_strike=230.0,
            option_expiration="2026-12-18",
            option_dte=30,
            option_vega=26.43,
            option_ask=7.20,
            projected_vega_pnl=350.20,
            projected_return_pct=48.64,
        )
        d = candidate.to_dict()
        self.assertEqual(d["symbol"], "AAPL")
        self.assertEqual(d["spot"], 230.50)
        self.assertEqual(d["days_to_earnings"], 22)
        self.assertEqual(d["mandatory_exit_date"], "2026-11-26")
        self.assertEqual(d["iv_rank"], 24.5)
        self.assertEqual(d["setup_grade"], "CONFIRMED")


class TestCalculatePreEarningsVegaSetup(unittest.TestCase):
    """Validates screening logic, window gating, and Rule 7 mandatory exit enforcement."""

    def setUp(self):
        self.session_date = "2026-11-18"
        self.historical_ivs = [0.25, 0.28, 0.30, 0.35, 0.40, 0.45, 0.50] * 3  # 21 observations

    def test_valid_setup_passes_filters(self):
        """Underlier with 20 days to earnings and low IV Rank (25%) passes."""
        # Current IV = 0.28, range 0.25 to 0.50 -> IV Rank ~ 12%
        res = calculate_pre_earnings_vega_setup(
            symbol="AMD",
            spot=140.0,
            earnings_date="2026-12-08",  # exactly 20 days from 2026-11-18
            session_date=self.session_date,
            current_iv=0.28,
            historical_ivs=self.historical_ivs,
            min_days=15,
            max_days=25,
            max_iv_rank=40.0,
        )
        self.assertIsNotNone(res)
        self.assertEqual(res.symbol, "AMD")
        self.assertEqual(res.days_to_earnings, 20)
        # Mandatory Exit Date must be exactly 14 calendar days before earnings (2026-12-08 - 14d = 2026-11-24)
        self.assertEqual(res.mandatory_exit_date, "2026-11-24")
        self.assertLessEqual(res.iv_rank, 40.0)
        self.assertGreater(res.option_vega, 0.0)
        self.assertGreater(res.projected_vega_pnl, 0.0)

    def test_rule7_rejection_inside_blackout_window(self):
        """Underlier with 10 days to earnings is rejected (violates Rule 7 14-day boundary)."""
        res = calculate_pre_earnings_vega_setup(
            symbol="NVDA",
            spot=125.0,
            earnings_date="2026-11-28",  # 10 days from 2026-11-18 (< 15)
            session_date=self.session_date,
            current_iv=0.30,
            historical_ivs=self.historical_ivs,
        )
        self.assertIsNone(res)

    def test_premature_earnings_rejected(self):
        """Underlier with 35 days to earnings is rejected (too early for vega expansion ramp)."""
        res = calculate_pre_earnings_vega_setup(
            symbol="MSFT",
            spot=415.0,
            earnings_date="2026-12-23",  # 35 days from 2026-11-18 (> 25)
            session_date=self.session_date,
            current_iv=0.25,
            historical_ivs=self.historical_ivs,
        )
        self.assertIsNone(res)

    def test_high_iv_rank_rejected(self):
        """Underlier with IV Rank > 40% is rejected (event premium already priced in)."""
        # Current IV = 0.48 (near historical high of 0.50) -> IV Rank ~ 92%
        res = calculate_pre_earnings_vega_setup(
            symbol="META",
            spot=560.0,
            earnings_date="2026-12-08",  # 20 days
            session_date=self.session_date,
            current_iv=0.48,
            historical_ivs=self.historical_ivs,
            max_iv_rank=40.0,
        )
        self.assertIsNone(res)


class TestScanPreEarningsCandidates(unittest.TestCase):
    """Validates the candidate universe scanner and sorting."""

    @patch("src.gex_engine.discover_earnings_date")
    @patch("src.gex_engine.find_latest_underlier_spot")
    @patch("src.gex_engine.find_latest_historical_closes")
    def test_scan_multiple_symbols(self, mock_closes, mock_spot, mock_earnings):
        mock_spot.side_effect = lambda sym: {"AAPL": 225.0, "TSLA": 210.0, "GOOGL": 175.0}.get(sym)
        mock_earnings.side_effect = lambda sym, **k: {
            "AAPL": "2026-12-09",  # 21 days from 2026-11-18 -> eligible
            "TSLA": "2026-11-25",  # 7 days -> ineligible (inside 14-day blackout)
            "GOOGL": "2027-01-15", # 58 days -> ineligible (too far)
        }.get(sym)
        mock_closes.return_value = None

        candidates = scan_pre_earnings_candidates(
            symbols=["AAPL", "TSLA", "GOOGL"],
            session_date="2026-11-18",
            min_days=15,
            max_days=25,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].symbol, "AAPL")
        self.assertEqual(candidates[0].days_to_earnings, 21)
        self.assertEqual(candidates[0].mandatory_exit_date, "2026-11-25")


class TestPreEarningsPresentationAndCli(unittest.TestCase):
    """Validates terminal table formatting and CLI execution."""

    def test_format_pre_earnings_table(self):
        candidate = PreEarningsCandidate(
            symbol="AMZN",
            spot=190.0,
            earnings_date="2026-12-06",
            days_to_earnings=18,
            mandatory_exit_date="2026-11-22",
            current_iv=0.32,
            iv_rank=28.0,
            iv_percentile=32.0,
            historical_high_iv=0.58,
            projected_iv_target=0.45,
            projected_iv_expansion=0.13,
            option_strike=190.0,
            option_expiration="2026-12-18",
            option_dte=30,
            option_vega=21.5,
            option_ask=7.60,
            projected_vega_pnl=279.50,
            projected_return_pct=36.78,
        )

        table_output = format_pre_earnings_table([candidate])
        self.assertIn("Pre-Earnings Vega Run-Up Harvester Candidates", table_output)
        self.assertIn("AMZN", table_output)
        self.assertIn("$190.00", table_output)
        self.assertIn("2026-11-22", table_output)
        self.assertIn("+36.8%", table_output)

    def test_format_empty_candidates_table(self):
        table_output = format_pre_earnings_table([])
        self.assertIn("No underliers currently match", table_output)

    @patch("src.gex.screening.vega_scanner.scan_pre_earnings_candidates")
    def test_cmd_pre_earnings_candidates_json_output(self, mock_scan):
        mock_cand = PreEarningsCandidate(
            symbol="AAPL",
            spot=230.0,
            earnings_date="2026-12-10",
            days_to_earnings=22,
            mandatory_exit_date="2026-11-26",
            current_iv=0.28,
            iv_rank=20.0,
            iv_percentile=25.0,
            historical_high_iv=0.50,
            projected_iv_target=0.39,
            projected_iv_expansion=0.11,
            option_strike=230.0,
            option_expiration="2026-12-18",
            option_dte=30,
            option_vega=26.0,
            option_ask=7.0,
            projected_vega_pnl=286.0,
            projected_return_pct=40.86,
        )
        mock_scan.return_value = [mock_cand]

        args = argparse.Namespace(
            symbols=["AAPL"],
            session_date="2026-11-18",
            min_days=15,
            max_days=25,
            max_iv_rank=40.0,
            strict_iv_rank=False,
            json=True,
        )

        payload = cmd_pre_earnings_candidates(args)
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["symbol"], "AAPL")
        self.assertEqual(payload[0]["mandatory_exit_date"], "2026-11-26")


if __name__ == "__main__":
    unittest.main()
