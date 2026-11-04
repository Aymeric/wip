#!/usr/bin/env python3
"""
Tests for Roadmap 5.3 — Automated Portfolio Beta-Weighted Macro Hedging Engine.
Verifies beta-weighting calculations, regime-linked hedge triggers, SPY/QQQ
Bear Put Debit Spread structuring, sizing guardrails, micro-account rules,
and CLI command integration.
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
from src.gex.risk.hedge import (  # noqa: E402
    BETA_SECTOR_MAP,
    BETA_TICKER_OVERRIDES,
    HedgePlan,
    PositionDeltaExposure,
    calculate_portfolio_beta_delta,
    derive_macro_hedge_plan,
    get_ticker_or_sector_beta,
)

ENGINE = "src.gex_engine"


class TestBetaWeightingFactors(unittest.TestCase):
    def test_ticker_overrides(self):
        self.assertEqual(get_ticker_or_sector_beta("NVDA"), 1.75)
        self.assertEqual(get_ticker_or_sector_beta("TSLA"), 2.00)
        self.assertEqual(get_ticker_or_sector_beta("AAPL"), 1.10)
        self.assertEqual(get_ticker_or_sector_beta("SPY"), 1.00)

    def test_sector_tag_fallbacks(self):
        self.assertEqual(get_ticker_or_sector_beta("UNKNOWN", "Technology / Semiconductors"), 1.25)
        self.assertEqual(get_ticker_or_sector_beta("UNKNOWN", "Healthcare Biotech"), 0.70)
        self.assertEqual(get_ticker_or_sector_beta("UNKNOWN", "Financials & Banks"), 1.05)
        self.assertEqual(get_ticker_or_sector_beta("UNKNOWN", "Utilities"), 0.35)
        self.assertEqual(get_ticker_or_sector_beta("UNKNOWN", "Consumer Defensive Staples"), 0.55)
        self.assertEqual(get_ticker_or_sector_beta("UNKNOWN", "Unknown Random Sector"), 1.00)


class TestPortfolioDeltaExposure(unittest.TestCase):
    def setUp(self):
        self.options = {
            "opt_1": {
                "Underlier": "NVDA",
                "Contracts": 1.0,
                "Type": "call",
                "Delta": 0.50,
                "Current Spot": 140.0,
                "Beta Sector Tag": "Technology/Beta",
            },
            "opt_2": {
                "Underlier": "PFE",
                "Contracts": 2.0,
                "Type": "call",
                "Delta": 0.40,
                "Current Spot": 30.0,
                "Beta Sector Tag": "Healthcare",
            },
        }
        self.stocks = {
            "AAPL": {
                "Shares": 50.0,
                "Average Buy Price": 200.0,
                "Current Price": 220.0,
                "Beta Sector Tag": "Technology/Beta",
            }
        }

    def test_calculate_portfolio_beta_delta(self):
        spy_price = 500.0
        (
            positions,
            tot_delta_shares,
            tot_dollar_delta,
            tot_bw_dollar_delta,
            spy_equiv_shares,
            tech_pct,
        ) = calculate_portfolio_beta_delta(
            self.options,
            self.stocks,
            spy_price=spy_price,
        )

        self.assertEqual(len(positions), 3)

        # NVDA option: 0.50 * 100 * 1 = 50 delta shares.
        # Dollar delta: 50 * 140 = $7,000.
        # Beta: 1.75 -> BW dollar delta: $7,000 * 1.75 = $12,250.
        nvda_pos = next(p for p in positions if p.symbol == "NVDA")
        self.assertAlmostEqual(nvda_pos.delta_shares, 50.0)
        self.assertAlmostEqual(nvda_pos.dollar_delta_exposure, 7000.0)
        self.assertAlmostEqual(nvda_pos.beta, 1.75)
        self.assertAlmostEqual(nvda_pos.beta_weighted_dollar_exposure, 12250.0)

        # PFE option: 0.40 * 100 * 2 = 80 delta shares.
        # Dollar delta: 80 * 30 = $2,400.
        # Beta: 0.70 -> BW dollar delta: $2,400 * 0.70 = $1,680.
        pfe_pos = next(p for p in positions if p.symbol == "PFE")
        self.assertAlmostEqual(pfe_pos.delta_shares, 80.0)
        self.assertAlmostEqual(pfe_pos.dollar_delta_exposure, 2400.0)
        self.assertAlmostEqual(pfe_pos.beta, 0.70)
        self.assertAlmostEqual(pfe_pos.beta_weighted_dollar_exposure, 1680.0)

        # AAPL stock: 50 shares * 1.0 delta = 50 delta shares.
        # Dollar delta: 50 * 220 = $11,000.
        # Beta: 1.10 -> BW dollar delta: $11,000 * 1.10 = $12,100.
        aapl_pos = next(p for p in positions if p.symbol == "AAPL")
        self.assertAlmostEqual(aapl_pos.delta_shares, 50.0)
        self.assertAlmostEqual(aapl_pos.dollar_delta_exposure, 11000.0)
        self.assertAlmostEqual(aapl_pos.beta, 1.10)
        self.assertAlmostEqual(aapl_pos.beta_weighted_dollar_exposure, 12100.0)

        # Totals
        expected_total_bw = 12250.0 + 1680.0 + 12100.0  # 26030.0
        self.assertAlmostEqual(tot_bw_dollar_delta, expected_total_bw)
        self.assertAlmostEqual(spy_equiv_shares, expected_total_bw / spy_price)

        # Tech percentage: (NVDA + AAPL) / Total = (12250 + 12100) / 26030 = 93.5%
        self.assertGreater(tech_pct, 90.0)


class TestMacroRegimeHedgeTriggers(unittest.TestCase):
    def setUp(self):
        self.options = {
            "opt_1": {
                "Underlier": "SPY",
                "Contracts": 2.0,
                "Type": "call",
                "Delta": 0.50,
                "Current Spot": 500.0,
                "Beta Sector Tag": "Equity",
            }
        }
        self.stocks = {}

    def test_all_tracks_ok_no_hedge_needed(self):
        regime = {"system_authorization": "ALL TRACKS OK", "gates_passed": 3}
        plan = derive_macro_hedge_plan(
            account="ACC123",
            net_liq=50000.0,
            cash_buying_power=20000.0,
            regime=regime,
            options_positions=self.options,
            stocks_positions=self.stocks,
            spy_price=500.0,
            qqq_price=450.0,
        )
        self.assertFalse(plan.hedge_required)
        self.assertEqual(plan.hedge_status, "NO_HEDGE_NEEDED")
        self.assertEqual(plan.target_coverage_pct, 0.0)
        self.assertEqual(plan.target_contracts, 0)

    def test_defensive_regime_50_pct_coverage(self):
        regime = {"system_authorization": "TRACK 1 OK", "gates_passed": 2}
        plan = derive_macro_hedge_plan(
            account="ACC123",
            net_liq=50000.0,
            cash_buying_power=20000.0,
            regime=regime,
            options_positions=self.options,
            stocks_positions=self.stocks,
            spy_price=500.0,
            qqq_price=450.0,
        )
        self.assertTrue(plan.hedge_required)
        self.assertEqual(plan.hedge_status, "DEFENSIVE_HEDGE")
        self.assertEqual(plan.target_coverage_pct, 0.50)
        # SPY equiv delta is 100 shares. 50% coverage = 50 shares.
        # Spread delta = 20 shares/contract. 50 / 20 = 2.5 -> rounds to 3 (or 2 depending on round).
        self.assertIn(plan.target_contracts, (2, 3))
        self.assertGreater(plan.total_estimated_cost, 0.0)

    def test_blocked_regime_100_pct_coverage(self):
        regime = {"system_authorization": "BLOCKED", "gates_passed": 1}
        plan = derive_macro_hedge_plan(
            account="ACC123",
            net_liq=100000.0,  # 3% budget = $3,000, comfortably fits 5 contracts ($2,100)
            cash_buying_power=40000.0,
            regime=regime,
            options_positions=self.options,
            stocks_positions=self.stocks,
            spy_price=500.0,
            qqq_price=450.0,
        )
        self.assertTrue(plan.hedge_required)
        self.assertEqual(plan.hedge_status, "FULL_MACRO_HEDGE")
        self.assertEqual(plan.target_coverage_pct, 1.00)
        # 100 shares / 20 shares per spread = 5 contracts
        self.assertEqual(plan.target_contracts, 5)

    def test_standard_account_3_pct_budget_cap(self):
        regime = {"system_authorization": "BLOCKED", "gates_passed": 0}
        plan = derive_macro_hedge_plan(
            account="ACC123",
            net_liq=50000.0,  # 3% budget = $1,500. 5 contracts cost $2,100 -> capped to 3 contracts ($1,260)
            cash_buying_power=20000.0,
            regime=regime,
            options_positions=self.options,
            stocks_positions=self.stocks,
            spy_price=500.0,
            qqq_price=450.0,
        )
        self.assertEqual(plan.target_contracts, 3)
        self.assertTrue(any("capped at 3.0%" in n for n in plan.notes))


class TestInstrumentSelectionAndSpreadStructuring(unittest.TestCase):
    def test_qqq_selected_for_tech_heavy_portfolio(self):
        options = {
            "opt_1": {
                "Underlier": "NVDA",
                "Contracts": 2.0,
                "Type": "call",
                "Delta": 0.50,
                "Current Spot": 140.0,
                "Beta Sector Tag": "Technology/Beta",
            }
        }
        regime = {"system_authorization": "BLOCKED", "gates_passed": 0}
        plan = derive_macro_hedge_plan(
            account="ACC123",
            net_liq=50000.0,
            cash_buying_power=20000.0,
            regime=regime,
            options_positions=options,
            stocks_positions={},
            spy_price=500.0,
            qqq_price=450.0,
            instrument_choice="AUTO",
        )
        self.assertEqual(plan.recommended_instrument, "QQQ")
        self.assertGreaterEqual(plan.tech_exposure_pct, 50.0)

    def test_spy_selected_for_broad_portfolio(self):
        options = {
            "opt_1": {
                "Underlier": "XLE",
                "Contracts": 5.0,
                "Type": "call",
                "Delta": 0.50,
                "Current Spot": 90.0,
                "Beta Sector Tag": "Energy",
            }
        }
        regime = {"system_authorization": "BLOCKED", "gates_passed": 0}
        plan = derive_macro_hedge_plan(
            account="ACC123",
            net_liq=50000.0,
            cash_buying_power=20000.0,
            regime=regime,
            options_positions=options,
            stocks_positions={},
            spy_price=500.0,
            qqq_price=450.0,
            instrument_choice="AUTO",
        )
        self.assertEqual(plan.recommended_instrument, "SPY")
        self.assertLess(plan.tech_exposure_pct, 50.0)

    def test_spread_strikes_and_defined_risk(self):
        options = {
            "opt_1": {
                "Underlier": "SPY",
                "Contracts": 1.0,
                "Type": "call",
                "Delta": 0.50,
                "Current Spot": 500.0,
                "Beta Sector Tag": "Equity",
            }
        }
        regime = {"system_authorization": "BLOCKED", "gates_passed": 0}
        plan = derive_macro_hedge_plan(
            account="ACC123",
            net_liq=50000.0,
            cash_buying_power=20000.0,
            regime=regime,
            options_positions=options,
            stocks_positions={},
            spy_price=500.0,
            qqq_price=450.0,
            instrument_choice="SPY",
        )
        # SPY at $500: Long Put ~ 0.98 * 500 = $490.00
        # Short Put ~ 0.95 * 500 = $475.00
        self.assertEqual(plan.long_put_strike, 490.0)
        self.assertEqual(plan.short_put_strike, 475.0)
        self.assertEqual(plan.spread_width, 15.0)
        self.assertGreater(plan.estimated_spread_debit, 0.0)
        self.assertGreater(plan.max_protection_pnl, 0.0)
        self.assertLess(plan.total_estimated_cost, plan.net_liq * 0.03)


class TestMicroAccountSizingRules(unittest.TestCase):
    def test_micro_account_1_contract_cap(self):
        options = {
            "opt_1": {
                "Underlier": "SPY",
                "Contracts": 5.0,
                "Type": "call",
                "Delta": 0.50,
                "Current Spot": 500.0,
                "Beta Sector Tag": "Equity",
            }
        }
        regime = {"system_authorization": "BLOCKED", "gates_passed": 0}
        plan = derive_macro_hedge_plan(
            account="970049961",
            net_liq=8500.0,  # Micro account (< $10,000)
            cash_buying_power=2000.0,
            regime=regime,
            options_positions=options,
            stocks_positions={},
            spy_price=500.0,
            qqq_price=450.0,
        )
        self.assertTrue(plan.is_micro_account)
        # Raw contracts would be 12-13, but micro accounts are capped at 1 contract
        self.assertEqual(plan.target_contracts, 1)
        self.assertTrue(any("Micro-Account" in n for n in plan.notes))

    def test_micro_account_cash_constrained(self):
        options = {
            "opt_1": {
                "Underlier": "SPY",
                "Contracts": 1.0,
                "Type": "call",
                "Delta": 0.50,
                "Current Spot": 500.0,
                "Beta Sector Tag": "Equity",
            }
        }
        regime = {"system_authorization": "BLOCKED", "gates_passed": 0}
        plan = derive_macro_hedge_plan(
            account="970049961",
            net_liq=8500.0,
            cash_buying_power=50.0,  # Insufficient cash for spread (~$420)
            regime=regime,
            options_positions=options,
            stocks_positions={},
            spy_price=500.0,
            qqq_price=450.0,
        )
        self.assertEqual(plan.target_contracts, 0)
        self.assertTrue(any("insufficient" in n.lower() for n in plan.notes))


class TestHedgePlanCLI(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.positions_file = os.path.join(self.test_dir, "active_positions_TEST.json")
        data = {
            "options_positions": {
                "opt_aapl": {
                    "Underlier": "AAPL",
                    "Contracts": 1.0,
                    "Type": "call",
                    "Delta": 0.50,
                    "Strike": 220.0,
                    "Expiration": "2026-11-20",
                    "Current Spot": 225.0,
                    "Purchase Premium": 5.0,
                    "Mark Price": 6.5,
                    "Beta Sector Tag": "Technology/Beta",
                }
            },
            "stocks_positions": {},
        }
        with open(self.positions_file, "w") as f:
            json.dump(data, f)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch(f"{ENGINE}.account_positions_file")
    @patch(f"{ENGINE}.get_regime_status")
    def test_cmd_hedge_plan_tabular(self, mock_regime, mock_file):
        mock_file.return_value = self.positions_file
        mock_regime.return_value = {
            "system_authorization": "TRACK 1 OK",
            "gates_passed": 2,
            "etf_details": {"SPY": {"Price": 500.0}, "QQQ": {"Price": 450.0}},
        }

        args = SimpleNamespace(
            account="TEST",
            net_liq=50000.0,
            target_coverage=1.0,
            instrument="AUTO",
            json=False,
        )

        with patch("sys.stdout", new=StringIO()) as fake_out:
            gex_engine.cmd_hedge_plan(args)
            output = fake_out.getvalue()

        self.assertIn("Portfolio Beta-Weighted Macro Hedge Plan", output)
        self.assertIn("AAPL", output)
        self.assertIn("QQQ Bear Put Debit Spread", output)
        self.assertIn("Rule H-1", output)

    @patch(f"{ENGINE}.account_positions_file")
    @patch(f"{ENGINE}.get_regime_status")
    def test_cmd_hedge_plan_json(self, mock_regime, mock_file):
        mock_file.return_value = self.positions_file
        mock_regime.return_value = {
            "system_authorization": "BLOCKED",
            "gates_passed": 1,
            "etf_details": {"SPY": {"Price": 500.0}, "QQQ": {"Price": 450.0}},
        }

        args = SimpleNamespace(
            account="TEST",
            net_liq=50000.0,
            target_coverage=None,
            instrument="AUTO",
            json=True,
        )

        with patch("sys.stdout", new=StringIO()) as fake_out:
            gex_engine.cmd_hedge_plan(args)
            output = fake_out.getvalue()

        parsed = json.loads(output)
        self.assertEqual(parsed["account"], "TEST")
        self.assertEqual(parsed["regime_status"], "BLOCKED")
        self.assertEqual(parsed["hedge_status"], "FULL_MACRO_HEDGE")
        self.assertEqual(parsed["recommended_structure"], "BEAR_PUT_SPREAD")
        self.assertIn("long_put_strike", parsed)
        self.assertIn("short_put_strike", parsed)
        self.assertGreater(len(parsed["positions"]), 0)


if __name__ == "__main__":
    unittest.main()
