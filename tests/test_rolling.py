#!/usr/bin/env python3
"""
Tests for Roadmap 5.2 — Dynamic Delta Rolling & Profit Optimization Engine.
Verifies roll trigger evaluation, profit ratchets, target contract selection,
net credit calculations, portfolio roll aggregation, and CLI commands.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import src.gex_engine as gex_engine  # noqa: E402
from src.gex.risk.rolling import (  # noqa: E402
    RollRecommendation,
    calculate_profit_ratchet,
    estimate_target_contract_pricing,
    evaluate_position_roll,
    evaluate_portfolio_rolls,
)

ENGINE = "src.gex_engine"


class TestProfitRatchet(unittest.TestCase):
    def test_tier2_ratchet_at_100_pct(self):
        floor, desc = calculate_profit_ratchet(125.0)
        self.assertEqual(floor, 50.0)
        self.assertIn("Tier 2", desc)

    def test_tier1_ratchet_at_50_pct(self):
        floor, desc = calculate_profit_ratchet(65.0)
        self.assertEqual(floor, 25.0)
        self.assertIn("Tier 1", desc)

    def test_trailing_volatility_floor_from_peak(self):
        # 40% gain giveback from 40% peak -> floor is 32% (80% of peak)
        floor, desc = calculate_profit_ratchet(25.0, max_profit_pct=40.0)
        self.assertEqual(floor, 32.0)
        self.assertIn("Trailing Volatility Stop", desc)

    def test_no_ratchet_on_small_gain(self):
        floor, desc = calculate_profit_ratchet(15.0)
        self.assertIsNone(floor)
        self.assertIn("No Ratchet", desc)


class TestTargetContractEstimation(unittest.TestCase):
    def test_estimate_target_contract_pricing(self):
        spot = 200.0
        target_strike, target_mark = estimate_target_contract_pricing(
            spot=spot,
            current_strike=185.0,
            current_iv=0.30,
            target_delta=0.45,
            target_dte=35,
        )
        self.assertGreaterEqual(target_strike, spot)
        self.assertGreater(target_mark, 0.0)
        self.assertLess(target_mark, spot * 0.10)


class TestPositionRollEvaluation(unittest.TestCase):
    def test_delta_expansion_trigger(self):
        # Position with high delta (0.78)
        pos = {
            "Option ID": "opt_aapl_1",
            "Underlier": "AAPL",
            "Strike": 210.0,
            "Expiration": "2026-11-20",
            "Purchase Premium": 10.0,
            "Mark Price": 22.0,
            "Delta": 0.78,
            "Quantity": 1.0,
        }
        rec = evaluate_position_roll(
            position_data=pos,
            spot=230.0,
            threshold_delta=0.70,
            threshold_gain=150.0,  # set higher so profit trigger doesn't shadow
            today_override="2026-10-20",
        )
        self.assertTrue(rec.eligible)
        self.assertEqual(rec.action, "ROLL_RECOMMENDED")
        self.assertTrue(any("DELTA_EXPANSION" in t for t in rec.triggers))
        self.assertGreater(rec.estimated_net_credit, 0.0)
        self.assertGreater(rec.capital_extracted, 0.0)
        self.assertGreater(rec.capital_at_risk_reduction_pct, 0.0)

    def test_profit_acceleration_trigger(self):
        # Position with +110% profit
        pos = {
            "Option ID": "opt_nvda_1",
            "Underlier": "NVDA",
            "Strike": 120.0,
            "Expiration": "2026-12-18",
            "Purchase Premium": 4.0,
            "Mark Price": 8.50,
            "Delta": 0.55,
            "Quantity": 2.0,
        }
        rec = evaluate_position_roll(
            position_data=pos,
            spot=130.0,
            threshold_delta=0.75,
            threshold_gain=50.0,
            today_override="2026-10-20",
        )
        self.assertTrue(rec.eligible)
        self.assertEqual(rec.action, "ROLL_RECOMMENDED")
        self.assertTrue(any("PROFIT_ACCELERATION" in t for t in rec.triggers))
        # Ratchet floor should be locked at +50% because ROI >= 100%
        self.assertEqual(rec.ratchet_stop_floor_pct, 50.0)
        # 2 contracts -> capital extracted should be scaled by 2
        expected_extracted = round((8.50 - rec.target_mark) * 100.0 * 2.0, 2)
        self.assertAlmostEqual(rec.capital_extracted, expected_extracted, places=2)

    def test_theta_exhaustion_approach_trigger(self):
        # Position with DTE 18 (<= 21) and positive gain
        pos = {
            "Option ID": "opt_msft_1",
            "Underlier": "MSFT",
            "Strike": 420.0,
            "Expiration": "2026-11-05",
            "Purchase Premium": 5.0,
            "Mark Price": 6.0,
            "Delta": 0.50,
        }
        rec = evaluate_position_roll(
            position_data=pos,
            spot=425.0,
            threshold_delta=0.70,
            threshold_gain=50.0,
            today_override="2026-10-20",  # 16 DTE
        )
        self.assertTrue(rec.eligible)
        self.assertTrue(any("THETA_PRESERVATION" in t for t in rec.triggers))

    def test_healthy_position_no_roll_needed(self):
        pos = {
            "Option ID": "opt_healthy",
            "Underlier": "AMZN",
            "Strike": 190.0,
            "Expiration": "2026-12-05",
            "Purchase Premium": 5.0,
            "Mark Price": 5.80,
            "Delta": 0.45,
        }
        rec = evaluate_position_roll(
            position_data=pos,
            spot=192.0,
            threshold_delta=0.70,
            threshold_gain=50.0,
            today_override="2026-10-20",  # 46 DTE
        )
        self.assertFalse(rec.eligible)
        self.assertEqual(rec.action, "HOLD_CURRENT")
        self.assertEqual(len(rec.triggers), 0)


class TestPortfolioRolls(unittest.TestCase):
    def test_evaluate_portfolio_rolls_aggregation(self):
        active_options = {
            "opt_1": {
                "Underlier": "AAPL",
                "Strike": 200.0,
                "Expiration": "2026-11-20",
                "Purchase Premium": 8.0,
                "Mark Price": 18.0,  # +125% profit
                "Delta": 0.82,
                "Quantity": 1.0,
            },
            "opt_2": {
                "Underlier": "MSFT",
                "Strike": 400.0,
                "Expiration": "2026-12-18",
                "Purchase Premium": 10.0,
                "Mark Price": 11.0,  # +10% profit, delta 0.45
                "Delta": 0.45,
                "Quantity": 1.0,
            },
        }
        spots = {"AAPL": 225.0, "MSFT": 405.0}

        summary = evaluate_portfolio_rolls(
            active_options=active_options,
            spots=spots,
            threshold_delta=0.70,
            threshold_gain=50.0,
            today_override="2026-10-20",
        )
        self.assertEqual(summary["total_positions"], 2)
        self.assertEqual(summary["eligible_roll_count"], 1)
        self.assertGreater(summary["total_extractable_capital"], 0.0)
        self.assertEqual(len(summary["recommendations"]), 2)


class TestEvaluateRollsCli(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.pos_file = os.path.join(self.temp_dir, "active_positions_TEST.json")
        gex_engine.save_json(self.pos_file, {
            "options_positions": {
                "opt_deep_itm": {
                    "Underlier": "TSLA",
                    "Strike": 220.0,
                    "Expiration": "2026-11-20",
                    "Purchase Premium": 10.0,
                    "Mark Price": 25.0,
                    "Delta": 0.80,
                    "Quantity": 1.0,
                }
            }
        })

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_cli_evaluate_rolls_tabular(self):
        args = SimpleNamespace(
            account="TEST",
            threshold_delta=0.70,
            threshold_gain=50.0,
            json=False,
        )
        with patch(f"{ENGINE}.account_positions_file", return_value=self.pos_file), \
             patch(f"{ENGINE}.find_latest_underlier_spot", return_value=250.0), \
             patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            gex_engine.cmd_evaluate_rolls(args)
            output = mock_stdout.getvalue()
            self.assertIn("Dynamic Delta Rolling & Profit Ratchet Audit", output)
            self.assertIn("TSLA", output)
            self.assertIn("ROLL NOW", output)
            self.assertIn("Extractable Cash Capital", output)

    def test_cli_evaluate_rolls_json(self):
        args = SimpleNamespace(
            account="TEST",
            threshold_delta=0.70,
            threshold_gain=50.0,
            json=True,
        )
        with patch(f"{ENGINE}.account_positions_file", return_value=self.pos_file), \
             patch(f"{ENGINE}.find_latest_underlier_spot", return_value=250.0), \
             patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            gex_engine.cmd_evaluate_rolls(args)
            data = json.loads(mock_stdout.getvalue())
            self.assertEqual(data["total_positions"], 1)
            self.assertEqual(data["eligible_roll_count"], 1)
            self.assertGreater(data["total_extractable_capital"], 0.0)
            self.assertEqual(data["recommendations"][0]["underlier"], "TSLA")
            self.assertTrue(data["recommendations"][0]["eligible"])


if __name__ == "__main__":
    unittest.main()
