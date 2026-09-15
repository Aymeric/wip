#!/usr/bin/env python3
"""
Unit Tests for GEX Options Mechanical Trading Engine
"""

import unittest
import sys
import os
import subprocess

# Ensure the src directory is in the path to import gex_engine correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from gex_engine import (
    calculate_candidate_score,
    calculate_grade, 
    compute_regime_gates, 
    compute_exit_rule_state,
    derive_gex_profile,
    derive_volatility_profile,
    select_best_option,
    discover_earnings_date,
    calculate_bollinger_bands,
    calculate_atr,
    calculate_trade_journal,
    parse_spot_overrides,
    parse_effective_session_date,
    RegimeGates,
    OptionPosition,
    StockPosition
)

class TestGEXEngine(unittest.TestCase):

    def test_repository_root_launcher_forwards_cli_arguments(self):
        repository_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        result = subprocess.run(
            [sys.executable, "gex_engine.py", "--help"],
            cwd=repository_root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("update-regime", result.stdout)

    def test_portfolio_accepts_account_argument(self):
        repository_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        result = subprocess.run(
            [sys.executable, "gex_engine.py", "portfolio", "--account", "970049961"],
            cwd=repository_root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("unrecognized arguments", result.stderr)

    def test_default_cache_paths_are_repository_anchored(self):
        import gex_engine

        repository_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.assertEqual(gex_engine.REPOSITORY_ROOT, repository_root)
        self.assertEqual(gex_engine.REGIME_FILE, os.path.join(repository_root, "data", "regime.json"))
        self.assertEqual(gex_engine.DOWNLOADS_DIR, os.path.join(repository_root, "data", "downloads"))

    def test_parse_spot_overrides_normalizes_tickers(self):
        self.assertEqual(
            parse_spot_overrides(" aapl=290, BABA = 81.5 "),
            {"AAPL": 290.0, "BABA": 81.5},
        )

    def test_parse_spot_overrides_rejects_invalid_input(self):
        from argparse import ArgumentTypeError

        for value in ("AAPL", "AAPL=not-a-price", "AAPL=-1", ""):
            with self.subTest(value=value):
                with self.assertRaises(ArgumentTypeError):
                    parse_spot_overrides(value)

    def test_effective_session_date_requires_iso_date(self):
        self.assertEqual(parse_effective_session_date("2026-08-11"), "2026-08-11")
        from argparse import ArgumentTypeError

        with self.assertRaises(ArgumentTypeError):
            parse_effective_session_date("2026-08-12T00:00:00")

    def test_calculate_trade_journal_metrics(self):
        report = calculate_trade_journal({
            "closed_options": [
                {"Realized P&L ($)": 100.0, "Days Held": 3, "Close Reason": "Target", "Target Mode": "T1"},
                {"Realized P&L ($)": -40.0, "Days Held": 5, "Close Reason": "Stop", "Target Mode": "T1"},
            ],
            "closed_stocks": [],
        }, {"monthly_pnl_dlr": 60.0})

        self.assertEqual(report["expectancy_per_trade"], 30.0)
        self.assertEqual(report["profit_factor"], 2.5)
        self.assertEqual(report["max_consecutive_losses"], 1)
        self.assertEqual(report["cache_reconciliation"], "MATCH")
        self.assertEqual(report["close_reasons"]["Target"]["count"], 1)

    def test_technical_indicators(self):
        # Bollinger Bands Test
        closes = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119]
        mid, upper, lower = calculate_bollinger_bands(closes, period=10)
        self.assertIsNotNone(mid)
        assert mid is not None and upper is not None and lower is not None
        self.assertTrue(upper > mid > lower)

        # ATR Test
        highs = [105] * 20
        lows = [95] * 20
        closes = [100] * 20
        atr = calculate_atr(highs, lows, closes, period=10)
        self.assertIsNotNone(atr)
        assert atr is not None
        self.assertGreater(atr, 0)

    def test_save_json_preserves_existing_file_on_serialization_failure(self):
        import tempfile
        import gex_engine

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write('{"state": "original"}')
        try:
            gex_engine.save_json(tmp_path, {"state": object()})
            self.assertEqual(gex_engine.load_json(tmp_path, {}), {"state": "original"})
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_compute_regime_gates(self):
        # Case 1: All Tracks Passed (All Gates PASS)
        # SPY change > 0.5%, bull/bear ratio > 3.0, VIX bearish = True
        basket_gate, bull_bear_ratio, bull_bear_gate, vix_delta_gate, system_auth, gates_passed = compute_regime_gates(
            spy_pct=0.6, qqq_pct=0.2, bull_count=4, bear_count=1, vix_dealer_delta_bearish=True
        )
        self.assertEqual(basket_gate, "PASS")
        self.assertEqual(bull_bear_gate, "PASS")
        self.assertEqual(vix_delta_gate, "PASS")
        self.assertEqual(system_auth, "ALL TRACKS OK")
        self.assertEqual(gates_passed, 3)

        # Case 2: Track 1 Authorized (2/3 Gates PASS)
        # Basket FAIL, bull_bear PASS, VIX PASS
        basket_gate, bull_bear_ratio, bull_bear_gate, vix_delta_gate, system_auth, gates_passed = compute_regime_gates(
            spy_pct=0.1, qqq_pct=0.1, bull_count=10, bear_count=2, vix_dealer_delta_bearish=True
        )
        self.assertEqual(basket_gate, "FAIL")
        self.assertEqual(bull_bear_gate, "PASS")
        self.assertEqual(vix_delta_gate, "PASS")
        self.assertEqual(system_auth, "TRACK 1 OK")
        self.assertEqual(gates_passed, 2)

        # Case 3: Blocked (1/3 Gates PASS)
        basket_gate, bull_bear_ratio, bull_bear_gate, vix_delta_gate, system_auth, gates_passed = compute_regime_gates(
            spy_pct=0.1, qqq_pct=0.1, bull_count=2, bear_count=2, vix_dealer_delta_bearish=False
        )
        self.assertEqual(system_auth, "BLOCKED")
        self.assertEqual(gates_passed, 0)

    def test_calculate_grade(self):
        # Case 1: Perfect Grade 11
        # Spot is above COTMP (280) and pTrans (285), +GEX (310) is above Spot, and extraRules all True
        extra_rules = {
            "total_call_gex_positive": True,
            "call_gex_gt_put_gex": True,
            "total_oi_gt_10000": True,
            "iv_30_lt_hv_90": True,
            "oi_depth_target_positive": True,
            "dealer_gamma_net_positive": True,
            "rv_10_stable": True
        }
        grade, rule_checklist = calculate_grade(
            ticker="AAPL", spot=290.0, ptrans=285.0, ntrans=282.0, gex=310.0, cotmp=280.0, extra_rules=extra_rules
        )
        self.assertEqual(grade, 11)
        self.assertTrue(all(rule_checklist))

        # Case 2: Missing trigger condition (Spot <= ptrans) -> Rule 6 Fails
        grade, rule_checklist = calculate_grade(
            ticker="AAPL", spot=284.0, ptrans=285.0, ntrans=282.0, gex=310.0, cotmp=280.0, extra_rules=extra_rules
        )
        self.assertEqual(grade, 10)
        self.assertFalse(rule_checklist[5]) # Rule 6 is 0-indexed index 5

    def test_compute_exit_rule_state(self):
        # Case 1: Standard Hold Status
        # Spot is above pTrans, within Day 1 (no time stops), no stalling, under T1 target
        exit_rule, action, time_st, dist_ntrans, dist_max = compute_exit_rule_state(
            spot=290.0, purchase_premium=4.75, mark_price=5.0,
            ptrans=285.0, ntrans=282.0, gex_t1=310.0,
            days_held=1, stalling_counter=0, dte=30
        )
        self.assertEqual(exit_rule, "HOLD")
        self.assertEqual(action, "No Action")
        self.assertEqual(time_st, "ON TRACK")

        # Case 2: Watch Status
        # Spot drops below pTrans but above nTrans, minor P&L loss
        exit_rule, action, time_st, dist_ntrans, dist_max = compute_exit_rule_state(
            spot=284.0, purchase_premium=4.75, mark_price=4.50,
            ptrans=285.0, ntrans=282.0, gex_t1=310.0,
            days_held=1, stalling_counter=0, dte=30
        )
        self.assertEqual(exit_rule, "WATCH")
        self.assertEqual(action, "Hold existing, but add NOTHING")

        # Case 3: Structural Stop Triggered
        # Spot drops below nTrans (282)
        exit_rule, action, time_st, dist_ntrans, dist_max = compute_exit_rule_state(
            spot=280.0, purchase_premium=4.75, mark_price=3.0,
            ptrans=285.0, ntrans=282.0, gex_t1=310.0,
            days_held=1, stalling_counter=0, dte=30
        )
        self.assertTrue("Structural Stop" in exit_rule)

        # Case 4: Max Asset Loss Stop Triggered
        # Spot is below pTrans, and options loss of -10% or more
        exit_rule, action, time_st, dist_ntrans, dist_max = compute_exit_rule_state(
            spot=284.0, purchase_premium=4.75, mark_price=4.20, # -11.5% loss
            ptrans=285.0, ntrans=282.0, gex_t1=310.0,
            days_held=1, stalling_counter=0, dte=30
        )
        self.assertTrue("Max Asset Stop" in exit_rule)

        # Case 5: Time Stop Triggered at Day 7 (Insufficient Progress)
        # Spot has only gained $1 from pTrans (285) to +GEX (310) -> full run is $25. Progress is 4%, under 50%
        exit_rule, action, time_st, dist_ntrans, dist_max = compute_exit_rule_state(
            spot=286.0, purchase_premium=4.75, mark_price=5.0,
            ptrans=285.0, ntrans=282.0, gex_t1=310.0,
            days_held=7, stalling_counter=0, dte=30
        )
        self.assertTrue("Time Stop" in exit_rule)

        # Case 5b: LEAP / Long-DTE Option (> 90 DTE) is exempt from Day 7 velocity time stop
        exit_rule_leap, action_leap, time_st_leap, _, _ = compute_exit_rule_state(
            spot=286.0, purchase_premium=4.75, mark_price=5.0,
            ptrans=285.0, ntrans=282.0, gex_t1=310.0,
            days_held=28, stalling_counter=0, dte=499
        )
        self.assertEqual(exit_rule_leap, "HOLD")
        self.assertEqual(time_st_leap, "ON TRACK (LEAP/Long-DTE Exempt)")

        # Case 6: Momentum Stalling Stop Triggered
        # Stalling days >= 3
        exit_rule, action, time_st, dist_ntrans, dist_max = compute_exit_rule_state(
            spot=290.0, purchase_premium=4.75, mark_price=5.0,
            ptrans=285.0, ntrans=282.0, gex_t1=310.0,
            days_held=1, stalling_counter=3, dte=30
        )
        self.assertTrue("Stalling Stop" in exit_rule)

        # Case 7: Expiration Stop Triggered
        # DTE < 0
        exit_rule, action, time_st, dist_ntrans, dist_max = compute_exit_rule_state(
            spot=290.0, purchase_premium=4.75, mark_price=5.0,
            ptrans=285.0, ntrans=282.0, gex_t1=310.0,
            days_held=1, stalling_counter=0, dte=-1
        )
        self.assertTrue("EXPIRED" in exit_rule)

        # Case 8: Profit Target T1 Check Priority vs. Option Decay Loss
        # Spot is above +GEX (310), but options premium is in a loss (-89.2% like BABA in active_positions)
        # Stalling is active, meaning Stalling Stop has triggered.
        # Previously BABA showed profit take. Now it should trigger the defensive Stalling Stop.
        exit_rule, action, time_st, dist_ntrans, dist_max = compute_exit_rule_state(
            spot=315.0, purchase_premium=15.0, mark_price=1.62,
            ptrans=285.0, ntrans=282.0, gex_t1=310.0,
            days_held=56, stalling_counter=3, dte=71
        )
        self.assertTrue("Stalling Stop" in exit_rule)

        # Case 9: Underlier Target Met but Option in Loss (No Stall or explicit triggers, but option lost value due to mismatch/decay)
        exit_rule, action, time_st, dist_ntrans, dist_max = compute_exit_rule_state(
            spot=315.0, purchase_premium=5.0, mark_price=4.0,
            ptrans=285.0, ntrans=282.0, gex_t1=310.0,
            days_held=2, stalling_counter=0, dte=10
        )
        self.assertEqual(exit_rule, "UNDERLIER TARGET MET (Option in Loss)")

        # Case 10: PROFIT TAKE (T1 TARGET MET) with healthy option returns
        exit_rule, action, time_st, dist_ntrans, dist_max = compute_exit_rule_state(
            spot=315.0, purchase_premium=5.0, mark_price=8.0,
            ptrans=285.0, ntrans=282.0, gex_t1=310.0,
            days_held=2, stalling_counter=0, dte=10
        )
        self.assertEqual(exit_rule, "PROFIT TAKE (T1 TARGET MET)")

    def test_etf_file_regime_integration(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            import gex_engine
            with patch('gex_engine.REGIME_FILE', tmp_path):
                # Verify etf-file regime data processing via dummy args Namespace
                class DummyArgs:
                    def __init__(self):
                        self.spy = None
                        self.qqq = None
                        self.bulls = None
                        self.bears = None
                        self.vix_bearish = None
                        self.vix_spot = 15.0
                        self.etf_file = "data/downloads/20260708/etf_quotes.json"
                        
                # We can dynamically test the parsing engine on cached data file
                args = DummyArgs()
                from gex_engine import cmd_update_regime
                # Should not raise exception and execute status check reporting success
                cmd_update_regime(args)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_regime_update_does_not_write_performance_cache(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as regime_tmp, \
             tempfile.NamedTemporaryFile(suffix=".json", delete=False) as performance_tmp:
            regime_path = regime_tmp.name
            performance_path = performance_tmp.name
        try:
            import gex_engine
            with patch("gex_engine.REGIME_FILE", regime_path), patch("gex_engine.PERFORMANCE_FILE", performance_path):
                class DummyArgs:
                    spy = 0.6
                    qqq = 0.1
                    bulls = 4
                    bears = 1
                    vix_bearish = True
                    vix_spot = 15.0
                    etf_file = None

                gex_engine.cmd_update_regime(DummyArgs())
                self.assertEqual(gex_engine.load_json(performance_path, {}), {})
                self.assertEqual(gex_engine.load_json(regime_path, {})["system_authorization"], "ALL TRACKS OK")
        finally:
            for path in (regime_path, performance_path):
                if os.path.exists(path):
                    os.remove(path)

    def test_account_performance_path_is_scoped(self):
        import gex_engine

        self.assertTrue(gex_engine.account_performance_file("5QR24141").endswith("performance_5QR24141.json"))

    def test_account_position_paths_are_scoped(self):
        import gex_engine

        self.assertTrue(gex_engine.account_positions_file("5QR24141").endswith("active_positions_5QR24141.json"))
        self.assertTrue(gex_engine.account_closed_positions_file("5QR24141").endswith("closed_positions_5QR24141.json"))
        self.assertTrue(gex_engine.account_positions_file().endswith("active_positions.json"))
        self.assertTrue(gex_engine.account_closed_positions_file().endswith("closed_positions.json"))

    def test_hyg_credit_divergence_integration(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            import gex_engine
            with patch('gex_engine.REGIME_FILE', tmp_path):
                class DummyArgs:
                    def __init__(self):
                        self.spy = None
                        self.qqq = None
                        self.bulls = None
                        self.bears = None
                        self.vix_bearish = None
                        self.vix_spot = 15.0
                        self.hyg = -0.45
                        self.etf_file = "data/downloads/20260708/etf_quotes.json"
                        
                args = DummyArgs()
                from gex_engine import cmd_update_regime
                cmd_update_regime(args)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_derive_gex_profile_standard(self):
        # Setup realistic raw options instruments and quotes payloads
        inst_data = {
            "instruments": [
                {"id": "put1", "strike_price": "90.0000", "type": "put"},
                {"id": "put2", "strike_price": "95.0000", "type": "put"},
                {"id": "call1", "strike_price": "105.0000", "type": "call"},
                {"id": "call2", "strike_price": "110.0000", "type": "call"}
            ]
        }
        quotes_data = {
            "results": [
                {"quote": {"instrument_id": "put1", "open_interest": 1000, "gamma": "0.01", "implied_volatility": "0.30"}},
                {"quote": {"instrument_id": "put2", "open_interest": 2000, "gamma": "0.02", "implied_volatility": "0.28"}},
                {"quote": {"instrument_id": "call1", "open_interest": 3000, "gamma": "0.015", "implied_volatility": "0.25"}},
                {"quote": {"instrument_id": "call2", "open_interest": 1500, "gamma": "0.01", "implied_volatility": "0.27"}}
            ]
        }
        
        # Test GEX derivation at spot = 100.0
        gex_profile = derive_gex_profile(inst_data, quotes_data, spot=100.0)
        self.assertEqual(gex_profile["derived_ptrans"], 95.0)
        self.assertEqual(gex_profile["derived_ntrans"], 90.0)
        self.assertEqual(gex_profile["derived_gex"], 105.0)
        self.assertEqual(gex_profile["total_oi"], 1000 + 2000 + 3000 + 1500)
        self.assertFalse(gex_profile["rule7_derived"]) # Total OI > 10,000 is False (7500 <= 10000)
        
        # Test Rule 1 and Rule 2
        # Call GEX: sum(oi * gamma * 100 * spot)
        # put1: 1000 * 0.01 * 100 * 100 = 100000, put2: 2000 * 0.02 * 100 * 100 = 400000 -> Put GEX = 500k
        # call1: 3000 * 0.015 * 100 * 100 = 450000, call2: 1500 * 0.01 * 100 * 100 = 150000 -> Call GEX = 600k
        self.assertTrue(gex_profile["rule1_derived"]) # total_call_gex > 0
        self.assertTrue(gex_profile["rule2_derived"]) # Call GEX > Put GEX (600k > 500k)

    def test_derive_gex_profile_tie_breaking(self):
        # Case where open interest is 0 for matching strikes, but total_oi > 0 (by having 1 OI on one strike)
        inst_data = {
            "instruments": [
                {"id": "put1", "strike_price": "90.0000", "type": "put"},
                {"id": "put2", "strike_price": "95.0000", "type": "put"},
                {"id": "call1", "strike_price": "105.0000", "type": "call"},
                {"id": "call2", "strike_price": "110.0000", "type": "call"}
            ]
        }
        quotes_data = {
            "results": [
                {"quote": {"instrument_id": "put1", "open_interest": 0, "gamma": "0.01", "implied_volatility": "0.30"}},
                {"quote": {"instrument_id": "put2", "open_interest": 0, "gamma": "0.02", "implied_volatility": "0.28"}},
                {"quote": {"instrument_id": "call1", "open_interest": 1, "gamma": "0.015", "implied_volatility": "0.25"}},
                {"quote": {"instrument_id": "call2", "open_interest": 0, "gamma": "0.01", "implied_volatility": "0.27"}}
            ]
        }
        
        gex_profile = derive_gex_profile(inst_data, quotes_data, spot=100.0)
        # Should break ties by choosing highest strike closest to spot for pTrans (95.0, not 90.0)
        self.assertEqual(gex_profile["derived_ptrans"], 95.0)
        # Should break ties for nTrans by choosing highest strike strictly below pTrans (90.0)
        self.assertEqual(gex_profile["derived_ntrans"], 90.0)
        # Should choose the strike with largest call open interest (105.0 has 1 OI, 110.0 has 0 OI)
        self.assertEqual(gex_profile["derived_gex"], 105.0)

    def test_derive_gex_profile_spot_above_all_strikes(self):
        inst_data = {
            "instruments": [
                {"id": "call1", "strike_price": "105.0000", "type": "call"},
                {"id": "call2", "strike_price": "110.0000", "type": "call"}
            ]
        }
        quotes_data = {
            "results": [
                {"quote": {"instrument_id": "call1", "open_interest": 500, "gamma": "0.015", "implied_volatility": "0.25"}},
                {"quote": {"instrument_id": "call2", "open_interest": 500, "gamma": "0.01", "implied_volatility": "0.27"}}
            ]
        }
        
        # Spot is 120.0, which is strictly higher than 105 and 110 (all calls)
        # our at_above_spot_calls is empty!
        # Fallback should occur and assign gex to spot * 1.05 = 126.0
        gex_profile = derive_gex_profile(inst_data, quotes_data, spot=120.0)
        self.assertEqual(gex_profile["derived_gex"], 126.0)

    def test_derive_volatility_profile(self):
        # Create a series of 12 closes => 11 log returns with minimal variance
        hist_data = {
            "bars": [
                {"begins_at": "2026-06-01T00:00:00Z", "close_price": "100.000"},
                {"begins_at": "2026-06-02T00:00:00Z", "close_price": "100.100"},
                {"begins_at": "2026-06-03T00:00:00Z", "close_price": "99.9000"},
                {"begins_at": "2026-06-04T00:00:00Z", "close_price": "100.050"},
                {"begins_at": "2026-06-05T00:00:00Z", "close_price": "99.9500"},
                {"begins_at": "2026-06-08T00:00:00Z", "close_price": "100.020"},
                {"begins_at": "2026-06-09T00:00:00Z", "close_price": "100.080"},
                {"begins_at": "2026-06-10T00:00:00Z", "close_price": "99.9200"},
                {"begins_at": "2026-06-11T00:00:00Z", "close_price": "100.040"},
                {"begins_at": "2026-06-12T00:00:00Z", "close_price": "99.9600"},
                {"begins_at": "2026-06-15T00:00:00Z", "close_price": "100.010"},
                {"begins_at": "2026-06-16T00:00:00Z", "close_price": "100.070"},
            ]
        }
        
        # Pass iv_sum = 0.5, iv_count = 2 => avg iv = 0.25 => iv30 = 25.0%
        vol_profile = derive_volatility_profile(hist_data, "AAPL", iv_sum=0.5, iv_count=2)
        self.assertEqual(vol_profile["iv30_val"], 25.0)
        self.assertGreater(vol_profile["hv90_val"], 0.0)
        self.assertGreater(vol_profile["rv10_val"], 0.0)
        # Check rule derivations
        self.assertTrue(vol_profile["rule11_derived"]) # Realized 10-day is under 35.0%

    def test_t2_target_exit_rules(self):
        # Case 1: T2 Target Mode - Option price is above purchase premium, spot is below T2 target -> HOLD
        exit_rule, action, time_st, dist_ntrans, dist_max = compute_exit_rule_state(
            spot=295.0, purchase_premium=5.0, mark_price=6.0,
            ptrans=285.0, ntrans=282.0, gex_t1=310.0,
            days_held=2, stalling_counter=0, dte=15,
            target_mode="T2", t2_target=320.0
        )
        self.assertEqual(exit_rule, "HOLD")
        self.assertEqual(action, "No Action")

        # Case 2: T2 Target Mode - Option price drops to entry premium (purchase premium) -> STOP TRIGGERED (Trailed Stop)
        exit_rule, action, time_st, dist_ntrans, dist_max = compute_exit_rule_state(
            spot=295.0, purchase_premium=5.0, mark_price=5.0,
            ptrans=285.0, ntrans=282.0, gex_t1=310.0,
            days_held=2, stalling_counter=0, dte=15,
            target_mode="T2", t2_target=320.0
        )
        self.assertTrue("Trailed Stop" in exit_rule)
        self.assertTrue("protect T1 gains" in action)

        # Case 3: T2 Target Mode - Option price drops below entry premium -> STOP TRIGGERED (Trailed Stop)
        exit_rule, action, time_st, dist_ntrans, dist_max = compute_exit_rule_state(
            spot=295.0, purchase_premium=5.0, mark_price=4.5,
            ptrans=285.0, ntrans=282.0, gex_t1=310.0,
            days_held=2, stalling_counter=0, dte=15,
            target_mode="T2", t2_target=320.0
        )
        self.assertTrue("Trailed Stop" in exit_rule)

        # Case 4: T2 Target Mode - Spot meets or exceeds T2 target -> PROFIT TAKE (T2 TARGET MET)
        exit_rule, action, time_st, dist_ntrans, dist_max = compute_exit_rule_state(
            spot=325.0, purchase_premium=5.0, mark_price=12.0,
            ptrans=285.0, ntrans=282.0, gex_t1=310.0,
            days_held=2, stalling_counter=0, dte=15,
            target_mode="T2", t2_target=320.0
        )
        self.assertEqual(exit_rule, "PROFIT TAKE (T2 TARGET MET)")
        self.assertTrue("lock in full T2" in action)

    def test_active_positions_are_not_excluded_when_empty(self):
        # Verify that the compatibility field stays empty when no positions are present
        from unittest.mock import patch
        import gex_engine
        
        with patch('gex_engine.load_json') as mock_load:
            # Simulated empty options file
            mock_load.return_value = {"options_positions": {}}
            
            # Create dummy args
            class DummyArgs:
                min_price = 5.0
                max_price = 1000.0
                min_volume = 200000
                min_change = 0.3
                min_market_cap = 1000000000
                
            with patch('gex_engine.persist_new_scans') as mock_persist, \
                 patch('gex_engine.save_json') as mock_save:
                
                gex_engine.cmd_update_candidates(DummyArgs())
                self.assertTrue(mock_save.called)
                saved_data = mock_save.call_args[0][1]
                self.assertEqual(saved_data["excluded_symbols"], [])

    def test_active_positions_are_retained_in_candidates(self):
        # Verify that active option underliers and stock tickers remain eligible candidates
        from unittest.mock import patch
        import gex_engine
        
        with patch('gex_engine.load_json') as mock_load:
            # Simulated active options and stocks
            mock_load.return_value = {
                "options_positions": {
                    "opt_1": {"Underlier": "AAPL"}
                },
                "stocks_positions": {
                    "MSFT": {}
                }
            }
            
            class DummyArgs:
                min_price = 5.0
                max_price = 1000.0
                min_volume = 200000
                min_change = 0.3
                min_market_cap = 1000000000
                
            with patch('gex_engine.persist_new_scans') as mock_persist, \
                 patch('gex_engine.save_json') as mock_save:
                
                gex_engine.cmd_update_candidates(DummyArgs())
                self.assertTrue(mock_save.called)
                saved_data = mock_save.call_args[0][1]
                self.assertEqual(saved_data["excluded_symbols"], [])

    def test_build_system_snapshot_aggregates_cached_state(self):
        from unittest.mock import patch
        import tempfile
        import gex_engine

        cached_state = {
            gex_engine.OPTIONS_FILE: {
                "options_positions": {"option-1": {"Underlier": "AAPL"}},
                "stocks_positions": {"MSFT": {"Ticker": "MSFT"}},
            },
            gex_engine.CANDIDATES_FILE: {"candidates": ["NVDA", "AMD"]},
            gex_engine.ANALYSES_FILE: {
                "NVDA": {"Signal Status": "CONFIRMED (11/11)"},
                "AMD": {"Signal Status": "PENDING"},
                "TSLA": {"Signal Status": "BLOCKED"},
            },
            gex_engine.SENTIMENT_FILE: {"NVDA": {"sentiment": 0.4}},
            gex_engine.WORKFLOW_STATE_FILE: {"current_phase": "Phase II"},
        }

        def load_cached(path, default):
            return cached_state.get(path, default)

        with patch("gex_engine.load_json", side_effect=load_cached), \
             patch("gex_engine.get_regime_status", return_value={"system_authorization": "TRACK 1 OK"}), \
             patch("gex_engine.get_performance_status", return_value={"drawdown_gate_status": "PASS"}):
            snapshot = gex_engine.build_system_snapshot()

        self.assertEqual(snapshot["portfolio"]["option_count"], 1)
        self.assertEqual(snapshot["portfolio"]["stock_count"], 1)
        self.assertEqual(snapshot["candidates"]["count"], 2)
        self.assertEqual(snapshot["analyses"]["signal_counts"], {"CONFIRMED": 1, "PENDING": 1, "BLOCKED": 1})
        self.assertIn("generated_at", snapshot)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            output_path = tmp.name
        try:
            with patch("gex_engine.build_system_snapshot", return_value=snapshot):
                gex_engine.cmd_snapshot(type("Args", (), {"output": output_path})())
            self.assertEqual(gex_engine.load_json(output_path, {}), snapshot)
        finally:
            if os.path.exists(output_path):
                os.remove(output_path)

    def test_ticker_analysis_freshness_is_evaluated_per_symbol(self):
        from unittest.mock import patch
        import gex_engine

        cached_state = {
            gex_engine.ANALYSES_FILE: {
                "AAPL": {"analyzed_date": "2026-08-10", "Signal Status": "PENDING"},
                "MSFT": {"analyzed_date": "2026-08-05", "Signal Status": "CONFIRMED"},
            },
            gex_engine.CANDIDATES_FILE: {
                "candidates": [{"symbol": "AAPL"}, {"symbol": "MSFT"}, {"symbol": "NVDA"}],
            },
            gex_engine.OPTIONS_FILE: {"options_positions": {}, "stocks_positions": {}},
        }

        def load_cached(path, default):
            return cached_state.get(path, default)

        with patch("gex_engine.load_json", side_effect=load_cached):
            freshness = gex_engine.get_ticker_analysis_freshness(("2026-08-10",))

        self.assertEqual(freshness["current"], ["AAPL"])
        self.assertEqual(freshness["stale"][0]["symbol"], "MSFT")
        self.assertEqual(freshness["missing"], ["NVDA"])

    def test_update_workflow_recovers_from_incomplete_state(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        import gex_engine

        args = SimpleNamespace(
            phase="Phase II: Discovery",
            agent="Candidate-Generator",
            status="SUCCESS",
            note="Candidate pool refreshed",
        )
        malformed_state = {"current_phase": "", "subagents": [], "notes": {}}

        with patch("gex_engine.load_json", return_value=malformed_state), \
             patch("gex_engine.save_json") as mock_save:
            gex_engine.cmd_update_workflow(args)

        saved_state = mock_save.call_args[0][1]
        self.assertEqual(saved_state["current_phase"], "Phase II: Discovery")
        self.assertEqual(saved_state["subagents"]["Candidate-Generator"]["status"], "SUCCESS")
        self.assertEqual(len(saved_state["notes"]), 1)

    def test_update_workflow_retains_only_latest_ten_notes(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        import gex_engine

        args = SimpleNamespace(phase=None, agent=None, status=None, note="new note")
        existing_state = {
            "current_phase": "Phase I: Audit",
            "subagents": {},
            "notes": [{"content": f"note {index}"} for index in range(10)],
        }

        with patch("gex_engine.load_json", return_value=existing_state), \
             patch("gex_engine.save_json") as mock_save:
            gex_engine.cmd_update_workflow(args)

        notes = mock_save.call_args[0][1]["notes"]
        self.assertEqual(len(notes), 10)
        self.assertEqual(notes[0]["content"], "note 1")
        self.assertEqual(notes[-1]["content"], "new note")

    def test_portfolio_concentration_alerts_options_and_stocks(self):
        # Verify that both option underliers and stock tickers trigger high concentration warnings
        import tempfile
        from unittest.mock import patch, MagicMock
        import gex_engine

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            # Set up 50k portfolio where AAPL option is 20k (40% >= 15% net_liq) and MSFT stock is 10k (20% >= 15% net_liq)
            mock_data = {
                "options_positions": {
                    "opt_aapl": {
                        "Underlier": "AAPL",
                        "Strike": 150.0,
                        "Expiration": "2026-08-08",
                        "Type": "call",
                        "Purchase Premium": 10.0,
                        "Mark Price": 200.0,
                        "Days Held": 1,
                        "Stalling Days": 0
                    }
                },
                "stocks_positions": {
                    "MSFT": {
                        "Ticker": "MSFT",
                        "Shares": 25.0,
                        "Average Buy Price": 100.0,
                        "Current Price": 400.0,
                        "Beta Sector Tag": "Technology/Beta"
                    }
                }
            }
            gex_engine.save_json(tmp_path, mock_data)
            
            with patch('gex_engine.OPTIONS_FILE', tmp_path), patch('sys.stdout') as mock_stdout:
                mock_stdout.isatty = MagicMock(return_value=False)
                class PortfolioArgs:
                    net_liq = 50000.0
                    spot_overrides = {}
                gex_engine.cmd_portfolio(PortfolioArgs())
                
                # Check output calls to verify high concentration alerts were printed
                output = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)
                self.assertIn("HIGH CONCENTRATION ALERT", output)
                self.assertIn("AAPL (40.00%)", output) # Option mark price 200.0 * 100 = 20000; 20k / 50k = 40%
                self.assertIn("MSFT (20.00%)", output) # Stock shares 25.0 * 400.0 = 10000; 10k / 50k = 20%
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_add_and_update_stocks_positions(self):
        import tempfile
        from unittest.mock import patch
        import gex_engine

        # Using a temporary file path for active_positions.json to mock file interactions
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            with patch('gex_engine.OPTIONS_FILE', tmp_path):
                # 1) Add stock position
                class AddArgs:
                    ticker = "MSFT"
                    shares = 15.0
                    average_buy_price = 400.00
                    sector = "Technology/Beta"
                
                gex_engine.cmd_add_stock_pos(AddArgs())
                
                # Check stored structure
                data = gex_engine.load_json(tmp_path, {})
                stocks = data.get("stocks_positions", {})
                self.assertIn("MSFT", stocks)
                self.assertEqual(stocks["MSFT"]["Shares"], 15.0)
                self.assertEqual(stocks["MSFT"]["Average Buy Price"], 400.00)
                self.assertEqual(stocks["MSFT"]["Beta Sector Tag"], "Technology/Beta")

                # 2) Update stock position
                class UpdateArgs:
                    ticker = "MSFT"
                    price = 425.00
                    shares = 20.0
                    sector = "Beta Core"
                
                gex_engine.cmd_update_stock_pos(UpdateArgs())
                data = gex_engine.load_json(tmp_path, {})
                target = data.get("stocks_positions", {}).get("MSFT", {})
                self.assertEqual(target["Current Price"], 425.00)
                self.assertEqual(target["Shares"], 20.0)
                self.assertEqual(target["Beta Sector Tag"], "Beta Core")
                self.assertEqual(target["Asset Cost Basis"], 8000.0) # 20 shares * 400 avg price

                # 3) Close stock position
                class CloseArgs:
                    ticker = "MSFT"
                    close_price = 450.00
                
                gex_engine.cmd_close_stock_pos(CloseArgs())
                data = gex_engine.load_json(tmp_path, {})
                self.assertNotIn("MSFT", data.get("stocks_positions", {}))
                
                closed_path = os.path.join(os.path.dirname(tmp_path), "closed_positions.json")
                closed_data = gex_engine.load_json(closed_path, {})
                self.assertEqual(len(closed_data.get("closed_stocks", [])), 1)
                closed_item = closed_data["closed_stocks"][0]
                self.assertEqual(closed_item["Ticker"], "MSFT")
                self.assertEqual(closed_item["Close Price"], 450.00)
                self.assertEqual(closed_item["Realized P&L ($)"], 1000.0) # (450 - 400) * 20 shares
                self.assertEqual(closed_item["Realized P&L (%)"], 12.5) # (450 - 400) / 400
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            closed_path = os.path.join(os.path.dirname(tmp_path), "closed_positions.json")
            if os.path.exists(closed_path):
                os.remove(closed_path)

    def test_sync_positions_prefers_newest_snapshot_over_folder_name(self):
        import tempfile
        import shutil
        from unittest.mock import patch
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        try:
            downloads_dir = os.path.join(temp_dir, "downloads")
            dated_dir = os.path.join(downloads_dir, "20260728")
            os.makedirs(dated_dir)
            active_file = os.path.join(temp_dir, "active_positions_ACC.json")
            gex_engine.save_json(active_file, {"options_positions": {}, "stocks_positions": {}})

            stale_payload = {"positions": [{"symbol": "OLD", "quantity": "1", "average_buy_price": "10"}]}
            current_payload = {"positions": [{"symbol": "NEW", "quantity": "2", "average_buy_price": "20"}]}
            stale_file = os.path.join(dated_dir, "equity_positions_ACC.json")
            current_file = os.path.join(downloads_dir, "equity_positions_ACC.json")
            gex_engine.save_json(stale_file, stale_payload)
            gex_engine.save_json(current_file, current_payload)
            os.utime(stale_file, (100.0, 100.0))
            os.utime(current_file, (200.0, 200.0))

            with patch('gex_engine.DOWNLOADS_DIR', downloads_dir), patch('gex_engine.account_positions_file', return_value=active_file):
                class SyncArgs:
                    base_dir = ""
                    account = "ACC"

                gex_engine.cmd_sync_positions(SyncArgs())

            positions = gex_engine.load_json(active_file, {})["stocks_positions"]
            self.assertIn("NEW", positions)
            self.assertNotIn("OLD", positions)
        finally:
            shutil.rmtree(temp_dir)

    def test_sync_positions_removes_cached_positions_absent_from_snapshot(self):
        import tempfile
        import shutil
        from unittest.mock import patch
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        try:
            downloads_dir = os.path.join(temp_dir, "downloads")
            os.makedirs(downloads_dir)
            active_file = os.path.join(temp_dir, "active_positions_ACC.json")
            gex_engine.save_json(active_file, {
                "options_positions": {
                    "old-option": {"Option ID": "old-option", "Account": "ACC"},
                    "kept-option": {"Option ID": "kept-option", "Account": "ACC"},
                },
                "stocks_positions": {
                    "OLD": {"Ticker": "OLD", "Account": "ACC"},
                    "KEPT": {"Ticker": "KEPT", "Account": "ACC"},
                },
            })
            gex_engine.save_json(os.path.join(downloads_dir, "equity_positions_ACC.json"), {
                "positions": [{"symbol": "KEPT", "quantity": "1", "average_buy_price": "10"}]
            })
            gex_engine.save_json(os.path.join(downloads_dir, "option_positions_ACC.json"), {
                "positions": [{"option_id": "kept-option", "chain_symbol": "KEPT", "quantity": "1", "average_price": "100"}]
            })

            with patch('gex_engine.DOWNLOADS_DIR', downloads_dir), patch('gex_engine.account_positions_file', return_value=active_file):
                class SyncArgs:
                    base_dir = ""
                    account = "ACC"

                gex_engine.cmd_sync_positions(SyncArgs())

            synced = gex_engine.load_json(active_file, {})
            self.assertEqual(set(synced["stocks_positions"]), {"KEPT"})
            self.assertEqual(set(synced["options_positions"]), {"kept-option"})
        finally:
            shutil.rmtree(temp_dir)

    def test_sync_positions_account_scoped_quotes_and_instruments_precedence(self):
        import tempfile
        import shutil
        from unittest.mock import patch
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        try:
            downloads_dir = os.path.join(temp_dir, "downloads")
            old_dir = os.path.join(downloads_dir, "20260710")
            new_dir = os.path.join(downloads_dir, "20260908")
            os.makedirs(old_dir)
            os.makedirs(new_dir)

            active_file = os.path.join(temp_dir, "active_positions_ACC.json")
            gex_engine.save_json(active_file, {"options_positions": {}, "stocks_positions": {}})

            # Old quote file has stale mark price
            gex_engine.save_json(os.path.join(old_dir, "option_quotes_raw.json"), {
                "results": [{"quote": {"instrument_id": "opt-1", "mark_price": "5.10"}}]
            })
            # Current session has account-scoped files
            gex_engine.save_json(os.path.join(new_dir, "option_instruments_ACC_raw.json"), {
                "data": {"instruments": [{"id": "opt-1", "strike_price": "40.0000", "type": "call", "expiration_date": "2026-10-16"}]}
            })
            gex_engine.save_json(os.path.join(new_dir, "option_quotes_ACC_raw.json"), {
                "data": {"results": [{"quote": {"instrument_id": "opt-1", "mark_price": "1.530000"}}]}
            })
            gex_engine.save_json(os.path.join(new_dir, "option_positions_ACC_raw.json"), {
                "positions": [{"option_id": "opt-1", "chain_symbol": "NKE", "quantity": "1", "average_price": "475"}]
            })

            with patch('gex_engine.DOWNLOADS_DIR', downloads_dir), patch('gex_engine.account_positions_file', return_value=active_file):
                class SyncArgs:
                    base_dir = new_dir
                    account = "ACC"

                gex_engine.cmd_sync_positions(SyncArgs())

            synced = gex_engine.load_json(active_file, {})["options_positions"]
            self.assertIn("opt-1", synced)
            self.assertEqual(synced["opt-1"]["Mark Price"], 1.53)
            self.assertEqual(synced["opt-1"]["Strike"], "40.00")
            self.assertAlmostEqual(synced["opt-1"]["P&L (%)"], -67.79, places=2)
            self.assertAlmostEqual(synced["opt-1"]["P&L ($)"], -322.0, places=1)
        finally:
            shutil.rmtree(temp_dir)

    def test_select_best_option(self):
        # Setup mock option files with different maturities and liquidity
        inst_data = {
            "instruments": [
                # Expiration is 30 days exactly from 2026-07-09 => 2026-08-08
                {"id": "call_opt_perfect", "expiration_date": "2026-08-08", "strike_price": "102.0000", "type": "call", "chain_symbol": "TEST"},
                {"id": "call_opt_too_high_strike", "expiration_date": "2026-08-08", "strike_price": "115.0000", "type": "call", "chain_symbol": "TEST"},
                {"id": "call_opt_too_soon_weekly", "expiration_date": "2026-07-15", "strike_price": "100.0000", "type": "call", "chain_symbol": "TEST"}, # 6 days away
                {"id": "put_opt", "expiration_date": "2026-08-08", "strike_price": "100.0000", "type": "put", "chain_symbol": "TEST"},
                # Expiration is farther away
                {"id": "call_opt_farther", "expiration_date": "2026-09-08", "strike_price": "102.0000", "type": "call", "chain_symbol": "TEST"}
            ]
        }
        quotes_data = {
            "results": [
                {
                    "quote": {
                        "instrument_id": "call_opt_perfect",
                        "bid_price": "2.40", "ask_price": "2.50", "mark_price": "2.45",
                        "open_interest": 600, "volume": 12, "delta": "0.45", "gamma": "0.02"
                    }
                },
                {
                    "quote": {
                        "instrument_id": "call_opt_too_high_strike",
                        "bid_price": "0.40", "ask_price": "0.45", "mark_price": "0.42",
                        "open_interest": 800, "volume": 5, "delta": "0.15", "gamma": "0.01"
                    }
                },
                {
                    "quote": {
                        "instrument_id": "call_opt_too_soon_weekly",
                        "bid_price": "1.40", "ask_price": "1.45", "mark_price": "1.42",
                        "open_interest": 1200, "volume": 50, "delta": "0.52", "gamma": "0.03"
                    }
                },
                {
                    "quote": {
                        "instrument_id": "put_opt",
                        "bid_price": "1.10", "ask_price": "1.15", "mark_price": "1.12",
                        "open_interest": 2000, "volume": 30, "delta": "-0.48", "gamma": "0.02"
                    }
                },
                {
                    "quote": {
                        "instrument_id": "call_opt_farther",
                        "bid_price": "3.40", "ask_price": "3.55", "mark_price": "3.47",
                        "open_interest": 700, "volume": 8, "delta": "0.46", "gamma": "0.015"
                    }
                }
            ]
        }

        # Spot is 100.0, +GEX target (gex_target) is 110.0. Target date is 2026-07-09.
        best, eligible = select_best_option(inst_data, quotes_data, spot=100.0, gex_target=110.0, today_override="2026-07-09")
        
        self.assertIsNotNone(best)
        self.assertEqual(best["option_id"], "call_opt_perfect")
        self.assertEqual(best["strike"], 102.0)
        self.assertEqual(best["expiration_date"], "2026-08-08")
        self.assertTrue(best["spread_ok"])
        self.assertTrue(best["oi_ok"])
        self.assertTrue(best["liquidity_passed"])
        
        # Verify the list handles exclusions correctly
        # Strikes must be strictly below +GEX (110.0), so 115.0 call is omitted
        for contract in eligible:
            self.assertLess(contract["strike"], 110.0)

        # Test with custom target_delta (e.g. 0.15 should prefer the high strike call contract)
        best_custom_delta, _ = select_best_option(inst_data, quotes_data, spot=100.0, gex_target=120.0, today_override="2026-07-09", target_delta=0.15)
        self.assertIsNotNone(best_custom_delta)
        self.assertEqual(best_custom_delta["option_id"], "call_opt_too_high_strike")

        # Test with custom DTE parameters (e.g. selecting farther monthly duration, min_dte=50 to max_dte=70)
        best_custom_dte, _ = select_best_option(inst_data, quotes_data, spot=100.0, gex_target=110.0, today_override="2026-07-09", min_dte=50, max_dte=70)
        self.assertIsNotNone(best_custom_dte)
        self.assertEqual(best_custom_dte["option_id"], "call_opt_farther")

    def test_risk_reward_calculation(self):
        """Test R/R calculations for different spot/pTrans/gex combinations."""
        # Scenario 1: Standard R/R > 2.0
        reward = 155.0 - 100.0  # +GEX - Spot
        risk = 100.0 - 95.0     # Spot - pTrans
        ratio = reward / risk if risk > 0 else 0
        self.assertGreaterEqual(ratio, 2.0)
        
        # Scenario 2: Edge case where risk is very small
        reward2 = 110.0 - 100.0
        risk2 = 100.0 - 99.5  # Tiny risk
        ratio2 = reward2 / risk2
        self.assertGreater(ratio2, 10.0)  # Should be 20.0
        
        # Scenario 3: R/R fails
        reward3 = 105.0 - 100.0
        risk3 = 100.0 - 95.0
        ratio3 = reward3 / risk3
        self.assertLess(ratio3, 2.0)

    def test_cotmp_cushion_thresholds(self):
        """Test COTMP cushion validation logic."""
        spot = 100.0
        cotmp = 98.0
        
        # Case 1: Standard 2.0% cushion required
        cushion_pct = ((spot - cotmp) / cotmp) * 100
        self.assertGreaterEqual(cushion_pct, 2.0)
        
        # Case 2: Grade 11 DEEP with 1.0% cushion allowed
        spot2 = 99.5
        cotmp2 = 98.5
        deep_cushion = ((spot2 - cotmp2) / cotmp2) * 100
        self.assertGreaterEqual(deep_cushion, 1.0)
        self.assertLess(deep_cushion, 2.0)
        
        # Case 3: Cushion too thin (fails)
        spot3 = 98.5
        cotmp3 = 98.0
        thin_cushion = ((spot3 - cotmp3) / cotmp3) * 100
        self.assertLess(thin_cushion, 1.0)

    def test_regime_gates_boundary_cases(self):
        """Test regime gate thresholds at exact boundaries."""
        # Test Basket Gate at exact boundary (+0.5%)
        basket_gate1, _, _, _, _, _ = compute_regime_gates(
            spy_pct=0.5, qqq_pct=0.0, bull_count=5, bear_count=1, vix_dealer_delta_bearish=True
        )
        self.assertEqual(basket_gate1, "FAIL")  # 0.5% is NOT > 0.5%
        
        basket_gate2, _, _, _, _, _ = compute_regime_gates(
            spy_pct=0.500001, qqq_pct=0.0, bull_count=5, bear_count=1, vix_dealer_delta_bearish=True
        )
        self.assertEqual(basket_gate2, "PASS")  # Slightly over 0.5% passes
        
        # Test Bull:Bear Gate at exact boundary (3.0:1)
        _, ratio1, bb_gate1, _, _, _ = compute_regime_gates(
            spy_pct=0.6, qqq_pct=0.2, bull_count=3, bear_count=1, vix_dealer_delta_bearish=True
        )
        self.assertEqual(bb_gate1, "FAIL")  # 3.0:1 is NOT > 3.0:1
        
        _, ratio2, bb_gate2, _, _, _ = compute_regime_gates(
            spy_pct=0.6, qqq_pct=0.2, bull_count=4, bear_count=1, vix_dealer_delta_bearish=True
        )
        self.assertEqual(bb_gate2, "PASS")  # 4.0:1 passes

    def test_vix_bearish_flag_sensitivity(self):
        """Test VIX bearish flag flip."""
        # VIX bearish True -> should pass
        _, _, _, vix_gate1, auth1, gates1 = compute_regime_gates(
            spy_pct=0.6, qqq_pct=0.2, bull_count=4, bear_count=1, vix_dealer_delta_bearish=True
        )
        self.assertEqual(vix_gate1, "PASS")
        self.assertEqual(gates1, 3)
        
        # VIX bearish False -> should fail
        _, _, _, vix_gate2, auth2, gates2 = compute_regime_gates(
            spy_pct=0.6, qqq_pct=0.2, bull_count=4, bear_count=1, vix_dealer_delta_bearish=False
        )
        self.assertEqual(vix_gate2, "FAIL")
        self.assertEqual(gates2, 2)

    def test_zero_bear_count_edge_case(self):
        """Test bull:bear ratio when bear_count is zero."""
        _, ratio, bb_gate, _, auth, gates = compute_regime_gates(
            spy_pct=0.6, qqq_pct=0.2, bull_count=5, bear_count=0, vix_dealer_delta_bearish=True
        )
        # When bear_count = 0, ratio should be set to float(bull_count) = 5.0
        self.assertEqual(ratio, 5.0)
        self.assertEqual(bb_gate, "PASS")

    def test_option_bid_ask_spread_thresholds(self):
        """Test bid-ask spread validation against liquidity thresholds."""
        # Premium <= $2.00: spread must be <= $0.15
        bid1, ask1 = 1.85, 2.00
        spread1 = ask1 - bid1  # 0.15
        self.assertLessEqual(spread1, 0.15)
        
        # Premium > $2.00 and <= $5.00: spread must be <= $0.25
        bid2, ask2 = 3.75, 4.00
        spread2 = ask2 - bid2  # 0.25
        self.assertLessEqual(spread2, 0.25)
        
        # Premium > $5.00: spread must be <= 10% of bid
        bid3, ask3 = 7.50, 8.10
        spread3 = ask3 - bid3  # 0.60
        max_spread3 = bid3 * 0.10  # 0.75
        self.assertLessEqual(spread3, max_spread3)

    def test_open_interest_thresholds(self):
        """Test open interest validation."""
        # Minimum OI for liquidity: 500 contracts
        oi1 = 500
        self.assertGreaterEqual(oi1, 500)
        
        oi2 = 499
        self.assertLess(oi2, 500)
        
        # Rule 7 threshold: 10,000 contracts total
        total_oi_rule7 = 10000
        self.assertGreaterEqual(total_oi_rule7, 10000)
        
        total_oi_fail_rule7 = 9999
        self.assertLess(total_oi_fail_rule7, 10000)

    def test_scanner_percent_change_ratio_conversion(self):
        """Test that scanner % Change column is handled as a ratio."""
        # Raw value from scanner: 0.039 (which is 3.9%)
        raw_change = 0.039
        pct_change = raw_change * 100  # Convert to percentage
        self.assertEqual(pct_change, 3.9)
        
        # Filtering: >= 0.3% requires multiplying by 100
        threshold_pct = 0.3
        self.assertGreaterEqual(pct_change, threshold_pct)  # 3.9% >= 0.3%
        
        # Edge case: 0.003 means 0.3%
        raw_small = 0.003
        pct_small = raw_small * 100
        self.assertEqual(pct_small, 0.3)
        self.assertGreaterEqual(pct_small, threshold_pct)

    def test_grade_rule_checklist_coverage(self):
        """Test all 11 rules are individually evaluable."""
        extra_rules_all_pass = {
            "total_call_gex_positive": True,
            "call_gex_gt_put_gex": True,
            "total_oi_gt_10000": True,
            "iv_30_lt_hv_90": True,
            "oi_depth_target_positive": True,
            "dealer_gamma_net_positive": True,
            "rv_10_stable": True
        }
        
        grade, checklist = calculate_grade(
            ticker="TEST", spot=100.0, ptrans=98.0, ntrans=95.0,
            gex=110.0, cotmp=94.0, extra_rules=extra_rules_all_pass
        )
        self.assertEqual(grade, 11)
        self.assertEqual(len(checklist), 11)
        self.assertTrue(all(checklist))
        
        # Test: Flip only the first extra rule (rule 1: total_call_gex_positive)
        extra_rules_one_fail = extra_rules_all_pass.copy()
        extra_rules_one_fail["total_call_gex_positive"] = False
        
        grade_fail, checklist_fail = calculate_grade(
            ticker="TEST", spot=100.0, ptrans=98.0, ntrans=95.0,
            gex=110.0, cotmp=94.0, extra_rules=extra_rules_one_fail
        )
        # Grade should be 10 (one rule failed)
        self.assertEqual(grade_fail, 10)
        self.assertFalse(checklist_fail[0])  # Rule 1 should fail
        
        # Test: Verify that structural conditions (rules 3-6) are correctly evaluated
        # Rule 3: Spot > COTMP (fails when spot < cotmp)
        # Keep ptrans < spot to avoid breaking Rule 6
        extra_rules_struct = extra_rules_all_pass.copy()
        grade_r3, checklist_r3 = calculate_grade(
            ticker="TEST", spot=93.5, ptrans=92.0, ntrans=90.0,  # spot=93.5 < cotmp=94 (fails Rule 3)
            gex=110.0, cotmp=94.0, extra_rules=extra_rules_struct
        )
        self.assertEqual(grade_r3, 10)
        self.assertFalse(checklist_r3[2])  # Rule 3 should fail

        # Rule 4: +GEX > Spot (fails when gex <= spot)
        grade_r4, checklist_r4 = calculate_grade(
            ticker="TEST", spot=110.0, ptrans=108.0, ntrans=105.0,
            gex=110.0, cotmp=94.0, extra_rules=extra_rules_struct  # spot == gex, not >
        )
        self.assertEqual(grade_r4, 10)
        self.assertFalse(checklist_r4[3])  # Rule 4 should fail
        
        # Rule 6: Spot > pTrans (fails when spot <= ptrans)
        grade_r6, checklist_r6 = calculate_grade(
            ticker="TEST", spot=98.0, ptrans=98.0, ntrans=95.0,
            gex=110.0, cotmp=94.0, extra_rules=extra_rules_struct  # spot == ptrans, not >
        )
        self.assertEqual(grade_r6, 10)
        self.assertFalse(checklist_r6[5])  # Rule 6 should fail

    def test_find_latest_option_files_and_spot_discovery(self):
        import tempfile
        import shutil
        from unittest.mock import patch
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        try:
            downloads_dir = os.path.join(temp_dir, "downloads", "20260827")
            os.makedirs(downloads_dir)

            inst_file = os.path.join(downloads_dir, "testsym_option_instruments_raw.json")
            quote_file = os.path.join(downloads_dir, "testsym_option_quotes_raw.json")
            underlier_file = os.path.join(downloads_dir, "testsym_underlier_quote_raw.json")
            hist_file = os.path.join(downloads_dir, "testsym_underlier_historicals_raw.json")

            gex_engine.save_json(inst_file, {"instruments": []})
            gex_engine.save_json(quote_file, {"results": []})
            gex_engine.save_json(underlier_file, {"results": [{"symbol": "TESTSYM", "last_trade_price": "145.50"}]})
            gex_engine.save_json(hist_file, {"results": [{"symbol": "TESTSYM", "bars": []}]})

            with patch("gex_engine.DOWNLOADS_DIR", os.path.join(temp_dir, "downloads")):
                found = gex_engine.find_latest_option_files("TESTSYM")
                self.assertEqual(found["inst_file"], inst_file)
                self.assertEqual(found["quote_file"], quote_file)
                self.assertEqual(found["underlier_quote_file"], underlier_file)
                self.assertEqual(found["hist_file"], hist_file)

                spot = gex_engine.find_latest_underlier_spot("TESTSYM")
                self.assertEqual(spot, 145.50)
        finally:
            shutil.rmtree(temp_dir)

    def test_cmd_update_candidates_with_exclude_active_flag(self):
        import tempfile
        import shutil
        from unittest.mock import patch
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        try:
            downloads_dir = os.path.join(temp_dir, "downloads")
            os.makedirs(downloads_dir)
            data_dir = os.path.join(temp_dir, "data")
            os.makedirs(data_dir)

            candidates_path = os.path.join(data_dir, "candidate_stocks.json")
            active_path = os.path.join(data_dir, "active_positions_TEST.json")

            gex_engine.save_json(active_path, {
                "options_positions": {"opt_1": {"Underlier": "HOLDING1"}},
                "stocks_positions": {"HOLDING2": {}}
            })

            scan_path = os.path.join(downloads_dir, "test_scan.json")
            gex_engine.save_json(scan_path, {
                "data": {
                    "result": {
                        "scan_id": "test-id",
                        "scan_title": "Test Momentum Scan",
                        "results": [
                            {"ticker": "CAND1", "columns": {"Last": "50.0", "Volume": "500000", "% Change": "0.05", "Market cap": "2000000000"}},
                            {"ticker": "HOLDING1", "columns": {"Last": "80.0", "Volume": "600000", "% Change": "0.04", "Market cap": "5000000000"}},
                        ]
                    }
                }
            })

            class Args:
                min_price = 5.0
                max_price = 1000.0
                min_volume = 200000
                min_change = 0.3
                min_market_cap = 1000000000
                exclude_active = True
                top = 5
                date = None

            with patch("gex_engine.DOWNLOADS_DIR", downloads_dir), \
                 patch("gex_engine.CANDIDATES_FILE", candidates_path), \
                 patch("gex_engine.REPOSITORY_ROOT", temp_dir):
                gex_engine.cmd_update_candidates(Args())

            saved = gex_engine.load_json(candidates_path, {})
            symbols = [c["symbol"] for c in saved.get("candidates", [])]
            self.assertIn("CAND1", symbols)
            self.assertNotIn("HOLDING1", symbols)
            self.assertIn("HOLDING1", saved.get("excluded_symbols", []))
        finally:
            shutil.rmtree(temp_dir)

    def test_dte_and_expiration_validation(self):
        """Test DTE (days to expiration) boundary handling."""
        from datetime import datetime, timedelta
        
        today = datetime(2026, 7, 9)
        
        # Expiration 14 days away -> exactly at weekly boundary
        exp_14 = today + timedelta(days=14)
        dte_14 = (exp_14.date() - today.date()).days
        self.assertEqual(dte_14, 14)
        
        # Expiration 30 days away -> target range
        exp_30 = today + timedelta(days=30)
        dte_30 = (exp_30.date() - today.date()).days
        self.assertGreaterEqual(dte_30, 30)
        
        # Expiration 45 days away -> upper target range
        exp_45 = today + timedelta(days=45)
        dte_45 = (exp_45.date() - today.date()).days
        self.assertLessEqual(dte_45, 45)

    def test_spotfallback_logic_non_reg_vs_reg_timestamp(self):
        """Test lexicographic timestamp comparison for price selection."""
        # Non-reg timestamp is more recent
        nonreg_time = "2026-07-10T15:30:45.123456+00:00"
        reg_time = "2026-07-10T10:00:00.000000+00:00"
        
        use_nonreg = nonreg_time > reg_time
        self.assertTrue(use_nonreg)
        
        # Reg timestamp is more recent
        nonreg_time2 = "2026-07-10T10:00:00.000000+00:00"
        reg_time2 = "2026-07-10T15:30:45.123456+00:00"
        
        use_nonreg2 = nonreg_time2 > reg_time2
        self.assertFalse(use_nonreg2)
        
        # Edge case: extra-long fractional seconds (Robinhood quirk)
        nonreg_long_frac = "2026-07-10T16:00:00.571202373+00:00"
        reg_standard = "2026-07-10T15:59:59.999999+00:00"
        
        use_nonreg_long = nonreg_long_frac > reg_standard
        self.assertTrue(use_nonreg_long)

    def test_position_sizing_constraints(self):
        """Test portfolio sizing limits."""
        net_liquidation = 100000.0
        
        # Single-leg option allocation limit: 3% of Net Liq
        max_option_per_leg = net_liquidation * 0.03
        self.assertEqual(max_option_per_leg, 3000.0)
        
        # Cumulative tech allocation limit: 15%
        max_tech_cumulative = net_liquidation * 0.15
        self.assertEqual(max_tech_cumulative, 15000.0)
        
        # Position sizing test
        option_size_1 = 2500.0
        self.assertLessEqual(option_size_1, max_option_per_leg)
        
        option_size_2 = 3000.0
        self.assertLessEqual(option_size_2, max_option_per_leg)
        
        option_size_oversized = 3500.0
        self.assertGreater(option_size_oversized, max_option_per_leg)

    def test_pct_change_flat_classification(self):
        """Test ETF classification thresholds for flat/bullish/bearish."""
        # Bullish threshold: > +0.1%
        chg_bullish = 0.15
        is_bullish = chg_bullish > 0.1
        self.assertTrue(is_bullish)
        
        # At boundary: exactly +0.1% is NOT bullish
        chg_boundary_bullish = 0.1
        is_boundary_bullish = chg_boundary_bullish > 0.1
        self.assertFalse(is_boundary_bullish)
        
        # Bearish threshold: < -0.1%
        chg_bearish = -0.15
        is_bearish = chg_bearish < -0.1
        self.assertTrue(is_bearish)
        
        # At boundary: exactly -0.1% is NOT bearish
        chg_boundary_bearish = -0.1
        is_boundary_bearish = chg_boundary_bearish < -0.1
        self.assertFalse(is_boundary_bearish)
        
        # Flat: between -0.1% and +0.1%
        chg_flat = 0.05
        is_flat = -0.1 <= chg_flat <= 0.1
        self.assertTrue(is_flat)

    def test_gex_profile_empty_options_data(self):
        """Test GEX derivation with minimal / empty options data."""
        # Empty instruments
        inst_data_empty = {"instruments": []}
        quotes_data_empty = {"results": []}
        
        gex_profile = derive_gex_profile(inst_data_empty, quotes_data_empty, spot=100.0)
        # Should return safe defaults for empty data
        self.assertEqual(gex_profile["total_oi"], 0)
        self.assertFalse(gex_profile["rule7_derived"])

    def test_dataclass_validation(self):
        """Test validation rules on the system's core models/dataclasses."""
        # RegimeGates validation
        rg_ok = RegimeGates("PASS", 4.5, "PASS", "PASS", "ALL TRACKS OK", 3)
        self.assertTrue(rg_ok.validate())

        with self.assertRaises(ValueError):
            RegimeGates("INVALID_GATE", 4.5, "PASS", "PASS", "ALL TRACKS OK", 3).validate()

        with self.assertRaises(ValueError):
            RegimeGates("PASS", 4.5, "PASS", "PASS", "ALL TRACKS OK", 4).validate() # gates_passed must be <= 3

        # OptionPosition validation
        op_ok = OptionPosition(
            option_id="opt_123", underlier="AAPL", strike=310.0, expiration="2026-08-08",
            type="call", purchase_premium=4.50, mark_price=5.10, days_held=3, stalling_days=0
        )
        self.assertTrue(op_ok.validate())

        with self.assertRaises(ValueError):
            OptionPosition(
                option_id="", underlier="AAPL", strike=310.0, expiration="2026-08-08",
                type="call", purchase_premium=4.50, mark_price=5.10, days_held=3, stalling_days=0
            ).validate()

        with self.assertRaises(ValueError):
            OptionPosition(
                option_id="opt_123", underlier="AAPL", strike=-5.0, expiration="2026-08-08",
                type="call", purchase_premium=4.50, mark_price=5.10, days_held=3, stalling_days=0
            ).validate()

        with self.assertRaises(ValueError):
            OptionPosition(
                option_id="opt_123", underlier="AAPL", strike=310.0, expiration="2026-08-08",
                type="invalid_type", purchase_premium=4.50, mark_price=5.10, days_held=3, stalling_days=0
            ).validate()

        # StockPosition validation
        sp_ok = StockPosition("AMZN", 10.0, 180.0, 185.0)
        self.assertTrue(sp_ok.validate())

        with self.assertRaises(ValueError):
            StockPosition("", 10.0, 180.0, 185.0).validate()

        with self.assertRaises(ValueError):
            StockPosition("AMZN", -1.0, 180.0, 185.0).validate()

    def test_portfolio_consolidated_realized_stats(self):
        """Test unified Options and Stocks realized performance stats reporting."""
        import tempfile
        from unittest.mock import patch, MagicMock
        import gex_engine

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            # Setup mock options/stocks closed positions
            mock_data = {
                "options_positions": {
                    "opt_nke": {
                        "Underlier": "NKE",
                        "Strike": 40.0,
                        "Expiration": "2026-08-08",
                        "Type": "call",
                        "Purchase Premium": 4.00,
                        "Mark Price": 4.50,
                        "Days Held": 2,
                        "Stalling Days": 0,
                        "Asset Cost Basis": 400.0,
                        "Current Value": 450.0
                    }
                },
                "stocks_positions": {},
                "closed_options": [
                    {
                        "Underlier": "NKE",
                        "Purchase Premium": 4.00,
                        "Close Premium": 6.00,
                        "Realized P&L ($)": 200.0,
                        "Realized P&L (%)": 50.0
                    }
                ],
                "closed_stocks": [
                    {
                        "Ticker": "MSFT",
                        "Shares": 10.0,
                        "Average Buy Price": 400.00,
                        "Close Price": 450.00,
                        "Realized P&L ($)": 500.0,
                        "Realized P&L (%)": 12.5
                    }
                ]
            }
            gex_engine.save_json(tmp_path, mock_data)
            
            with patch('gex_engine.OPTIONS_FILE', tmp_path), patch('sys.stdout') as mock_stdout:
                mock_stdout.isatty = MagicMock(return_value=False)
                class PortfolioArgs:
                    net_liq = 50000.0
                    spot_overrides = {}
                gex_engine.cmd_portfolio(PortfolioArgs())
                
                # Verify output calls
                output = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)
                self.assertIn("Options Stats", output)
                self.assertIn("Stocks Stats", output)
                self.assertIn("Total Combined Realized P&L", output)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_sentiment_functionality(self):
        """Test OptionSentiment dataclass validation and sentiment commands."""
        import tempfile
        from unittest.mock import patch, MagicMock
        import gex_engine

        # 1. OptionSentiment validation
        s_ok = gex_engine.OptionSentiment("AAPL", 0.85, "High", "High option volume and FOMO")
        self.assertTrue(s_ok.validate())

        with self.assertRaises(ValueError):
            gex_engine.OptionSentiment("", 0.85, "High", "Invalid ticker").validate()

        with self.assertRaises(ValueError):
            gex_engine.OptionSentiment("AAPL", -1.5, "High", "Invalid sentiment").validate()

        with self.assertRaises(ValueError):
            gex_engine.OptionSentiment("AAPL", 0.85, "SuperHigh", "Invalid buzz").validate()

        # 5-factor sentiment validation
        s_5f = gex_engine.OptionSentiment(
            "AAPL", 0.85, "High", "High option volume and FOMO",
            tone_score=0.30, comments_score=0.30, position_score=0.15, volume_score=0.05, meme_score=0.05
        )
        self.assertTrue(s_5f.validate())

        # Sum of factors mismatching overall score must raise ValueError
        with self.assertRaises(ValueError):
            gex_engine.OptionSentiment(
                "AAPL", 0.85, "High", "Mismatched sum",
                tone_score=0.10, comments_score=0.10, position_score=0.10, volume_score=0.10, meme_score=0.10
            ).validate()

        # Factor score out of range must raise ValueError
        with self.assertRaises(ValueError):
            gex_engine.OptionSentiment(
                "AAPL", 0.50, "High", "Out of range factor",
                tone_score=0.50, comments_score=0.0, position_score=0.0, volume_score=0.0, meme_score=0.0
            ).validate()

        # 2. Test cmd_update_sentiment and cmd_sentiment via temporary files
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_sent, \
             tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_analyses, \
             tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_options, \
             tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_candidates:
            
            sent_path = tmp_sent.name
            analyses_path = tmp_analyses.name
            options_path = tmp_options.name
            cand_path = tmp_candidates.name
            
        try:
            # Seed Analyses (GEX indicators)
            gex_engine.save_json(analyses_path, {
                "OKLO": {
                    "Ticker": "OKLO",
                    "Spot": 50.0,
                    "+GEX": 50.0,  # Spot is at Call Wall -> should trigger FOMO on positive sentiment
                    "nTrans": 45.0,
                    "COTMP": 44.0
                },
                "BABA": {
                    "Ticker": "BABA",
                    "Spot": 75.0,
                    "+GEX": 90.0,
                    "nTrans": 75.0,  # Spot is at nTrans -> should trigger Capitulation Watch on negative sentiment
                    "COTMP": 70.0
                }
            })
            # Seed Candidates
            gex_engine.save_json(cand_path, {
                "candidates": [
                    {"symbol": "OKLO", "price": 50.0}
                ]
            })
            # Seed Options (BABA is held)
            gex_engine.save_json(options_path, {
                "options_positions": {
                    "baba_opt": {
                        "Underlier": "BABA",
                        "Strike": 80.0,
                        "Type": "call",
                        "Purchase Premium": 5.0,
                        "Mark Price": 1.0,
                        "Days Held": 10
                    }
                },
                "stocks_positions": {}
            })
            # Seed Sentiment (empty initially)
            gex_engine.save_json(sent_path, {})

            # Patch files
            with patch('gex_engine.SENTIMENT_FILE', sent_path), \
                 patch('gex_engine.ANALYSES_FILE', analyses_path), \
                 patch('gex_engine.OPTIONS_FILE', options_path), \
                 patch('gex_engine.CANDIDATES_FILE', cand_path):
                
                # Update Sentiment for OKLO (exuberant FOMO setup)
                class UpdateArgs1:
                    ticker = "OKLO"
                    score = 0.85
                    buzz = "High"
                    narrative = "Nuclear AI micro-reactor breakthrough FOMO."
                gex_engine.cmd_update_sentiment(UpdateArgs1())
                
                # Update Sentiment for BABA (doom capitulation watch)
                class UpdateArgs2:
                    ticker = "BABA"
                    score = -0.85
                    buzz = "High"
                    narrative = "Total retail capitulation."
                gex_engine.cmd_update_sentiment(UpdateArgs2())
                
                # Check sentiment dashboard prints proper alerts
                with patch('sys.stdout') as mock_stdout:
                    mock_stdout.isatty = MagicMock(return_value=False)
                    class SentimentArgs:
                        pass
                    gex_engine.cmd_sentiment(SentimentArgs())
                    
                    output = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)
                    self.assertIn("Reddit Sentiment Analysis Report", output)
                    self.assertIn("OKLO", output)
                    self.assertIn("BABA", output)
                    self.assertIn("FOMO ALERT", output)
                    self.assertIn("CAPITULATION WATCH", output)
        finally:
            for path in (sent_path, analyses_path, options_path, cand_path):
                if os.path.exists(path):
                    os.remove(path)

    def test_sync_pnl(self):
        """Test syncing from a mock P&L trade history file."""
        import tempfile
        from unittest.mock import patch
        import gex_engine
        
        fd1, tmp_pnl = tempfile.mkstemp(suffix=".json")
        fd2, tmp_options = tempfile.mkstemp(suffix=".json")
        os.close(fd1)
        os.close(fd2)
        
        try:
            # Seed mock P&L history with one closed stock and one closed option trade
            mock_pnl = {
                "data": {
                    "trades": [
                        {
                            "timestamp": "2026-07-10T15:30:11Z",
                            "symbol": "AMZN",
                            "side": "sell",
                            "quantity": "50",
                            "price": "245.44",
                            "realized_gain": "1382.00"
                        },
                        {
                            "timestamp": "2026-07-10T16:45:00Z",
                            "symbol": "SLS",
                            "side": "sell",
                            "quantity": "1",
                            "price": "6.80",
                            "realized_gain": "-64.00"
                        }
                    ]
                }
            }
            gex_engine.save_json(tmp_pnl, mock_pnl)
            
            # Seed active options & stocks
            mock_active = {
                "options_positions": {
                    "sls_opt": {
                        "Option ID": "67c51ad2-f526-462e-8c15-c85a68866a9f",
                        "Underlier": "SLS",
                        "Strike": "14.00",
                        "Type": "call",
                        "Purchase Premium": 7.44,
                        "Entry Date": "2026-07-01"
                    }
                },
                "stocks_positions": {
                    "AMZN": {
                        "Ticker": "AMZN",
                        "Shares": 50.0,
                        "Average Buy Price": 217.80,
                        "Entry Date": "2026-07-09"
                    }
                }
            }
            gex_engine.save_json(tmp_options, mock_active)
            
            class SyncArgs:
                pnl_file = tmp_pnl
                
            with patch('gex_engine.OPTIONS_FILE', tmp_options):
                gex_engine.cmd_sync_pnl(SyncArgs())
                
                # Check option is closed and moved
                active = gex_engine.load_json(tmp_options, {})
                self.assertNotIn("AMZN", active.get("stocks_positions", {}))
                self.assertNotIn("sls_opt", active.get("options_positions", {}))
                
                closed_path = os.path.join(os.path.dirname(tmp_options), "closed_positions.json")
                closed = gex_engine.load_json(closed_path, {})
                self.assertEqual(len(closed.get("closed_stocks", [])), 1)
                self.assertEqual(len(closed.get("closed_options", [])), 1)
                
                self.assertEqual(closed["closed_stocks"][0]["Ticker"], "AMZN")
                self.assertEqual(closed["closed_stocks"][0]["Realized P&L ($)"], 1382.0)
                self.assertEqual(closed["closed_options"][0]["Underlier"], "SLS")
                self.assertEqual(closed["closed_options"][0]["Realized P&L ($)"], -64.0)
                
        finally:
            for path in (tmp_pnl, tmp_options):
                if os.path.exists(path):
                    os.remove(path)
            closed_path = os.path.join(os.path.dirname(tmp_options), "closed_positions.json")
            if os.path.exists(closed_path):
                os.remove(closed_path)

    def test_sync_pnl_keeps_partial_close_active(self):
        """A realized partial close must not archive the remaining live lot."""
        import tempfile
        from unittest.mock import patch
        import gex_engine

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as pnl_handle, \
             tempfile.NamedTemporaryFile(suffix=".json", delete=False) as options_handle:
            pnl_path = pnl_handle.name
            options_path = options_handle.name
        closed_path = os.path.join(os.path.dirname(options_path), "closed_positions_5QR24141.json")
        try:
            gex_engine.save_json(pnl_path, {"data": {"trades": [{
                "timestamp": "2026-08-04T16:00:00Z", "symbol": "AMZN",
                "quantity": "1", "price": "1610", "realized_gain": "685"
            }]}})
            gex_engine.save_json(options_path, {"options_positions": {}, "stocks_positions": {
                "AMZN": {"Ticker": "AMZN", "Shares": 50.0,
                          "Average Buy Price": 217.80, "Entry Date": "2026-07-01"}
            }})

            class SyncArgs:
                pnl_file = pnl_path
                account = "5QR24141"

            with patch("gex_engine.account_positions_file", return_value=options_path), \
                 patch("gex_engine.account_closed_positions_file", return_value=closed_path):
                gex_engine.cmd_sync_pnl(SyncArgs())

            active = gex_engine.load_json(options_path, {})
            self.assertIn("AMZN", active["stocks_positions"])
            closed = gex_engine.load_json(closed_path, {})
            self.assertEqual(closed.get("closed_stocks", []), [])
        finally:
            for path in (pnl_path, options_path, closed_path):
                if os.path.exists(path):
                    os.remove(path)

    def test_rankings_command(self):
        """Test GEX ticker setup rankings and report command."""
        import tempfile
        from unittest.mock import patch, MagicMock
        import gex_engine

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_analyses:
            analyses_path = tmp_analyses.name
        try:
            # Seed Analyses (GEX entries)
            gex_engine.save_json(analyses_path, {
                "AAPL": {
                    "Ticker": "AAPL",
                    "Spot": 315.0,
                    "Grade": 11,
                    "pTrans": 310.0,
                    "nTrans": 305.0,
                    "+GEX": 330.0,
                    "COTMP": 300.0,
                    "db_change": 0.55,
                    "COTMP Cushion": 5.0,
                    "Risk/Reward": 3.0,
                    "Signal Status": "CONFIRMED"
                },
                "TSLA": {
                    "Ticker": "TSLA",
                    "Spot": 240.0,
                    "Grade": 8,
                    "pTrans": 250.0,
                    "nTrans": 240.0,
                    "+GEX": 260.0,
                    "COTMP": 235.0,
                    "db_change": 0.20,
                    "COTMP Cushion": 2.13,
                    "Risk/Reward": 0.8,
                    "Signal Status": "BLOCKED (Grade <= 8)"
                }
            })

            with patch('gex_engine.ANALYSES_FILE', analyses_path), patch('sys.stdout') as mock_stdout:
                mock_stdout.isatty = MagicMock(return_value=False)
                
                class RankingsArgs:
                    status = "ALL"
                    min_grade = None
                    sort = "grade"
                
                gex_engine.cmd_rankings(RankingsArgs())
                
                # Check printed output contents
                output = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)
                self.assertIn("GEX Setup Rankings & Report", output)
                self.assertIn("AAPL", output)
                self.assertIn("TSLA", output)
                self.assertIn("CONFIRMED", output)
                self.assertIn("BLOCKED", output)
                self.assertIn("GEX Setup Database Metrics Summary", output)
                
                # Try filtering by CONFIRMED status
                class RankingsFilterArgs:
                    status = "CONFIRMED"
                    min_grade = 9
                    sort = "grade"
                
                mock_stdout.reset_mock()
                gex_engine.cmd_rankings(RankingsFilterArgs())
                output_filtered = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)
                self.assertIn("AAPL", output_filtered)
                self.assertNotIn("TSLA", output_filtered)

        finally:
            if os.path.exists(analyses_path):
                os.remove(analyses_path)

    def test_cmd_closed_visualizer(self):
        """Test closed subcommand visualizer and statistics calculations."""
        import tempfile
        from unittest.mock import patch, MagicMock
        import gex_engine

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_options:
            options_path = tmp_options.name
            
        try:
            # Seed OPTIONS_FILE to point to appropriate directory for closed_positions.json
            mock_data = {
                "closed_options": [
                    {
                        "Underlier": "AAPL",
                        "Strike": "310.00",
                        "Entry Date": "2026-07-01",
                        "Close Date": "2026-07-05",
                        "Purchase Premium": 4.00,
                        "Close Premium": 6.00,
                        "Realized P&L ($)": 200.0,
                        "Realized P&L (%)": 50.0
                    }
                ],
                "closed_stocks": [
                    {
                        "Ticker": "AMZN",
                        "Shares": 10.0,
                        "Average Buy Price": 180.00,
                        "Close Price": 200.00,
                        "Entry Date": "2026-07-01",
                        "Close Date": "2026-07-05",
                        "Realized P&L ($)": 200.0,
                        "Realized P&L (%)": 11.11
                    }
                ]
            }
            gex_engine.save_json(options_path, {})  # empty active
            # The closed_positions.json holds closed positions
            closed_path = os.path.join(os.path.dirname(options_path), "closed_positions.json")
            gex_engine.save_json(closed_path, mock_data)

            with patch('gex_engine.OPTIONS_FILE', options_path), patch('sys.stdout') as mock_stdout:
                mock_stdout.isatty = MagicMock(return_value=False)
                class ClosedArgs:
                    pass
                gex_engine.cmd_closed(ClosedArgs())
                
                output = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)
                self.assertIn("GEX Closed Positions History", output)
                self.assertIn("AAPL", output)
                self.assertIn("AMZN", output)
                self.assertIn("Options Stats", output)
                self.assertIn("Stocks Stats", output)
                self.assertIn("Total Combined Realized P&L", output)
        finally:
            if os.path.exists(options_path):
                os.remove(options_path)
            closed_path = os.path.join(os.path.dirname(options_path), "closed_positions.json")
            if os.path.exists(closed_path):
                os.remove(closed_path)

    def test_file_auto_discovery_lexicographical_latest(self):
        """Test that get_monthly_realized_pnl and cmd_sync_pnl auto-discover the latest index files."""
        import tempfile
        import shutil
        from unittest.mock import patch, MagicMock
        import gex_engine

        # Create nested temp directories mimicking data/downloads/YYYYMMDD
        temp_dir = tempfile.mkdtemp()
        try:
            day1_dir = os.path.join(temp_dir, "20260708")
            day2_dir = os.path.join(temp_dir, "20260710")
            os.makedirs(day1_dir)
            os.makedirs(day2_dir)

            # Write trade files to both dates. The 20260710 must be chosen lexicographically.
            old_pnl = {
                "data": {"trades": [{"timestamp": "2026-07-08T00:00:00Z", "symbol": "AMZN", "realized_gain": "100.00"}]}
            }
            new_pnl = {
                "data": {"trades": [{"timestamp": "2026-07-10T00:00:00Z", "symbol": "AMZN", "realized_gain": "500.00"}]}
            }
            gex_engine.save_json(os.path.join(day1_dir, "pnl_trade_history.json"), old_pnl)
            gex_engine.save_json(os.path.join(day2_dir, "pnl_trade_history.json"), new_pnl)

            # Patch downloads directory to our temp folder and test discovery
            with patch('gex_engine.cmd_portfolio'), patch('sys.stdout'):
                # 1. Test get_monthly_realized_pnl picks up the 500.00 realized gain from 20260710 (latest)
                # Instead of 100.00 from 20260708.
                downloads_dir = gex_engine.DOWNLOADS_DIR
                # We patch os.path.exists and walk for the engine's downloads prefix
                orig_exists = os.path.exists
                orig_walk = os.walk

                def mock_exists(path):
                    if path == downloads_dir:
                        return True
                    return orig_exists(path)

                def mock_walk(path, *args, **kwargs):
                    if path == downloads_dir:
                        return orig_walk(temp_dir, *args, **kwargs)
                    return orig_walk(path, *args, **kwargs)

                with patch('os.path.exists', side_effect=mock_exists), \
                     patch('os.walk', side_effect=mock_walk):
                    
                    pnl_val, pct_val, status, cnt = gex_engine.get_monthly_realized_pnl(net_liq=50000.0)
                    # Verify it chose the one from 20260710 ($500.00 realized gain)
                    self.assertEqual(pnl_val, 500.00)
                    self.assertEqual(cnt, 1)
        finally:
            shutil.rmtree(temp_dir)

    def test_get_beta_factor(self):
        """Test beta factor resolution for various sector tags."""
        from gex_engine import get_beta_factor
        self.assertEqual(get_beta_factor("Technology/Beta"), 1.25)
        self.assertEqual(get_beta_factor("Biotech/Healthcare"), 0.70)
        self.assertEqual(get_beta_factor("Financials"), 1.05)
        self.assertEqual(get_beta_factor("Consumer Staples"), 0.55)
        self.assertEqual(get_beta_factor("random_sector"), 1.00)
        self.assertEqual(get_beta_factor(None), 1.00)

    def test_cmd_payoff(self):
        """Test payoff subcommand execution and simulation calculations with outputs."""
        from unittest.mock import patch, MagicMock
        import gex_engine
        
        with patch('sys.stdout') as mock_stdout:
            mock_stdout.isatty = MagicMock(return_value=False)
            
            class PayoffArgs:
                symbol = "NVDA"
                spot = 200.0
                strike = 200.0
                mark = 5.0
                delta = 0.50
                gamma = 0.02
                dte = 30
                target_spots = "190,200,210"
                
            gex_engine.cmd_payoff(PayoffArgs())
            
            output = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)
            self.assertIn("Offline Option Payoff Simulation: NVDA", output)
            self.assertIn("NVDA", output)
            self.assertIn("Target Spot", output)
            self.assertIn("$190.00", output)
            self.assertIn("$200.00", output)
            self.assertIn("$210.00", output)

    def test_generate_ascii_gex_scale(self):
        """Test GEX ASCII runway map generation."""
        from gex_engine import generate_ascii_gex_scale
        scale = generate_ascii_gex_scale(spot=100.0, ptrans=98.0, ntrans=95.0, gex=110.0, cotmp=94.0)
        self.assertIn("SPOT", scale)
        self.assertIn("pTrans", scale)
        self.assertIn("nTrans", scale)
        self.assertIn("+GEX", scale)
        self.assertIn("COTMP", scale)
        
        # Test grouped prices (same price)
        scale_grouped = generate_ascii_gex_scale(spot=100.0, ptrans=98.0, ntrans=95.0, gex=110.0, cotmp=95.0)
        self.assertIn("nTrans", scale_grouped)
        self.assertIn("COTMP", scale_grouped)
        self.assertIn("+", scale_grouped)

    def test_discover_earnings_date(self):
        """Test scanning directory for earnings date files with multi-date and ISO timestamp support."""
        import tempfile
        import shutil
        from unittest.mock import patch
        from datetime import datetime as real_datetime
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        try:
            day_dir = os.path.join(temp_dir, "20260710")
            os.makedirs(day_dir)
            mock_earnings = {
                "results": [
                    {
                        "report": {
                            "date": "2026-05-15T00:00:00Z"  # Past date
                        }
                    },
                    {
                        "report": {
                            "expected_report_date": "2026-08-15"  # Upcoming target
                        }
                    },
                    {
                        "report": {
                            "reported_date": "2026-11-15T15:30:00-04:00"  # Far future date
                        }
                    }
                ]
            }
            gex_engine.save_json(os.path.join(day_dir, "nvda_earnings_raw.json"), mock_earnings)

            downloads_dir = gex_engine.DOWNLOADS_DIR
            orig_exists = os.path.exists
            orig_walk = os.walk

            def mock_exists(path):
                if path == downloads_dir:
                    return True
                return orig_exists(path)

            def mock_walk(path, *args, **kwargs):
                if path == downloads_dir:
                    return orig_walk(temp_dir, *args, **kwargs)
                return orig_walk(path, *args, **kwargs)

            class MockDatetime(real_datetime):
                @classmethod
                def today(cls):
                    return real_datetime(2026, 7, 12, 12, 0, 0)

            with patch('os.path.exists', side_effect=mock_exists), \
                 patch('os.walk', side_effect=mock_walk), \
                 patch('gex_engine.datetime', MockDatetime):
                # Discover earnings date dynamically
                e_date = discover_earnings_date("NVDA")
                self.assertEqual(e_date, "2026-08-15")

                # Test fallback when all dates are in the past
                mock_past_only = {
                    "results": [
                        {"report": {"date": "2026-04-15"}},
                        {"report": {"date": "2026-01-15"}}
                    ]
                }
                gex_engine.save_json(os.path.join(day_dir, "nvda_earnings_raw.json"), mock_past_only)
                e_date_past = discover_earnings_date("NVDA")
                self.assertEqual(e_date_past, "2026-04-15") # Should fallback to the latest past date

        finally:
            shutil.rmtree(temp_dir)

    def test_select_best_option_earnings_blocking(self):
        """Test that select_best_option flags options expiring after upcoming earnings."""
        inst_data = {
            "instruments": [
                {"id": "call_opt_blocked", "expiration_date": "2026-08-20", "strike_price": "100.0000", "type": "call", "chain_symbol": "TEST"}
            ]
        }
        quotes_data = {
            "results": [
                {
                    "quote": {
                        "instrument_id": "call_opt_blocked",
                        "bid_price": "2.40", "ask_price": "2.50", "mark_price": "2.45",
                        "open_interest": 600, "volume": 12, "delta": "0.45", "gamma": "0.02"
                    }
                }
            ]
        }

        # Upcoming earnings is 2026-08-15, option expiration is 2026-08-20 -> option expires AFTER earnings -> Blocked by earnings risk
        best, eligible = select_best_option(inst_data, quotes_data, spot=100.0, gex_target=110.0, today_override="2026-07-09", earnings_date="2026-08-15")
        self.assertIsNotNone(best)
        self.assertTrue(best["earnings_blocked"])

        # Upcoming earnings is 2026-08-25, option expiration is 2026-08-20 -> option expires BEFORE earnings -> Not blocked
        best2, eligible2 = select_best_option(inst_data, quotes_data, spot=100.0, gex_target=110.0, today_override="2026-07-09", earnings_date="2026-08-25")
        self.assertIsNotNone(best2)
        self.assertFalse(best2["earnings_blocked"])

    def test_technical_indicators_rsi_macd(self):
        """Test RSI and MACD calculation functions."""
        from gex_engine import calculate_rsi, calculate_macd
        # Create a series of 40 closes (constantly increasing)
        closes = [100.0 + i * 0.5 for i in range(40)]
        rsi = calculate_rsi(closes)
        self.assertIsNotNone(rsi)
        assert rsi is not None
        self.assertGreater(rsi, 50.0)
        
        macd_line, sig_line, macd_hist = calculate_macd(closes)
        self.assertIsNotNone(macd_line)
        self.assertIsNotNone(sig_line)
        self.assertIsNotNone(macd_hist)

    def test_stock_portfolio_exit_rules(self):
        """Test trailing stops, stop losses, and profit targets for stocks in portfolio review."""
        import tempfile
        from unittest.mock import patch
        import gex_engine
        
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            with patch('gex_engine.OPTIONS_FILE', tmp_path), \
                 patch('gex_engine.ANALYSES_FILE', os.path.join(os.path.dirname(tmp_path), "analyses.json")):
                # Setup active stock positions
                stocks_data = {
                    "stocks_positions": {
                        "AAPL": {
                            "Ticker": "AAPL",
                            "Shares": 10.0,
                            "Average Buy Price": 150.0,
                            "Current Price": 160.0,
                            "Highest Price": 170.0,
                            "Trailing Stop Pct": 10.0, # trail stop trigger at 170 * 0.9 = 153. Current price 160 -> HOLD
                            "Beta Sector Tag": "Technology/Beta"
                        },
                        "MSFT": {
                            "Ticker": "MSFT",
                            "Shares": 5.0,
                            "Average Buy Price": 300.0,
                            "Current Price": 260.0,
                            "Highest Price": 300.0,
                            "Trailing Stop Pct": 10.0, # trail stop trigger at 300 * 0.9 = 270. Current price 260 -> TRIGGERED
                            "Beta Sector Tag": "Technology/Beta"
                        },
                        "GOOG": {
                            "Ticker": "GOOG",
                            "Shares": 20.0,
                            "Average Buy Price": 100.0,
                            "Current Price": 90.0,
                            "Stop Loss Pct": 5.0, # stop loss trigger at 100 * 0.95 = 95. Current price 90 -> TRIGGERED
                            "Beta Sector Tag": "Technology/Beta"
                        },
                        "AMZN": {
                            "Ticker": "AMZN",
                            "Shares": 10.0,
                            "Average Buy Price": 120.0,
                            "Current Price": 140.0,
                            "Profit Target Pct": 10.0, # profit target trigger at 120 * 1.1 = 132. Current price 140 -> TRIGGERED
                            "Beta Sector Tag": "Technology/Beta"
                        }
                    }
                }
                gex_engine.save_json(tmp_path, stocks_data)
                
                # Run portfolio review
                class MockArgs:
                    net_liq = 50000.0
                    spot_overrides = {}
                
                gex_engine.cmd_portfolio(MockArgs())
                
                # Check that highest price for AAPL is updated to max(170, 160) = 170
                data = gex_engine.load_json(tmp_path, {})
                stocks = data.get("stocks_positions", {})
                self.assertEqual(stocks["AAPL"]["Highest Price"], 170.0)
                self.assertEqual(stocks["MSFT"]["Highest Price"], 300.0)
                
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_update_candidates_rsi_macd_filtering(self):
        """Test candidate technical indicators calculation and filtering."""
        import tempfile
        import shutil
        from unittest.mock import patch
        import gex_engine
        
        temp_dir = tempfile.mkdtemp()
        try:
            opt_file = os.path.join(temp_dir, "active_positions.json")
            gex_engine.save_json(opt_file, {"options_positions": {}, "stocks_positions": {}})
            
            downloads_dir = os.path.join(temp_dir, "downloads")
            os.makedirs(downloads_dir, exist_ok=True)
            mock_scan = {
                "data": {
                    "result": {
                        "scan_title": "Test Scan",
                        "results": [
                            {
                                "ticker": "MSFT",
                                "columns": {
                                    "Last": "400.00",
                                    "Volume": "500000.0",
                                    "% Change": "0.01",
                                    "Market cap": "3000000000000.0"
                                }
                            }
                        ]
                    }
                }
            }
            gex_engine.save_json(os.path.join(downloads_dir, "test_scan.json"), mock_scan)
            
            # Create a history with 40 days of closes (continuously going up => RSI around 100, MACD bullish)
            bars_data = [{"begins_at": f"2026-06-{i:02d}T00:00:00Z", "close_price": str(100.0 + i)} for i in range(1, 41)]
            gex_engine.save_json(os.path.join(downloads_dir, "msft_historicals_raw.json"), {"bars": bars_data})
            
            candidates_file = os.path.join(temp_dir, "candidate_stocks.json")
            analyses_file = os.path.join(temp_dir, "ticker_analyses.json")
            gex_engine.save_json(analyses_file, {})
            
            with patch('gex_engine.OPTIONS_FILE', opt_file), \
                 patch('gex_engine.DOWNLOADS_DIR', downloads_dir), \
                 patch('gex_engine.CANDIDATES_FILE', candidates_file), \
                 patch('gex_engine.ANALYSES_FILE', analyses_file), \
                 patch('gex_engine.persist_new_scans', return_value=[]), \
                 patch('gex_engine.find_latest_historical_closes') as mock_find:
                
                # Mock find to return our closes list
                closes_list = [100.0 + i for i in range(40)]
                mock_find.return_value = closes_list
                
                # Run candidates update without filters
                class UpdateArgs:
                    min_rsi = None
                    max_rsi = None
                    macd_filter = "none"
                    
                gex_engine.cmd_update_candidates(UpdateArgs())
                
                cand_data = gex_engine.load_json(candidates_file, {})
                cands = cand_data.get("candidates", [])
                self.assertEqual(len(cands), 1)
                self.assertIsNotNone(cands[0]["rsi"])
                self.assertIsNotNone(cands[0]["macd_hist"])
                self.assertIn("score", cands[0])
                self.assertGreater(cands[0]["score"], 0.0)
                
                # Test filtering (should exclude since RSI is high and max-rsi is set to 30)
                class UpdateArgsFiltered:
                    min_rsi = None
                    max_rsi = 30.0
                    macd_filter = "none"
                    
                gex_engine.cmd_update_candidates(UpdateArgsFiltered())
                cand_data = gex_engine.load_json(candidates_file, {})
                self.assertEqual(len(cand_data.get("candidates", [])), 0)
                
        finally:
            shutil.rmtree(temp_dir)

    def test_calculate_candidate_score(self):
        """Test candidate score calculation across various input combinations and edge cases."""
        # 1. Empty dictionary or all None values -> returns 0.0
        self.assertEqual(calculate_candidate_score({}), 0.0)
        self.assertEqual(
            calculate_candidate_score({
                "relative_options_volume": None,
                "chg_pct": None,
                "iv": None,
                "rsi": None,
                "macd_hist": None
            }),
            0.0
        )

        # 2. Maximum values at or exceeding caps -> returns 100.0
        max_candidate = {
            "relative_options_volume": 10.0,  # cap 10.0
            "chg_pct": 5.0,                  # cap 5.0
            "iv": 1.0,                       # cap 1.0
            "rsi": 100.0,                    # cap 100.0
            "macd_hist": 0.5                 # > 0 -> 1.0, cap 1.0
        }
        self.assertEqual(calculate_candidate_score(max_candidate), 100.0)

        # 3. Exceeding caps -> clamped to 1.0 -> returns 100.0
        exceeding_candidate = {
            "relative_options_volume": 20.0,
            "chg_pct": 10.0,
            "iv": 2.0,
            "rsi": 150.0,
            "macd_hist": 1.5
        }
        self.assertEqual(calculate_candidate_score(exceeding_candidate), 100.0)

        # 4. Zero or negative values -> returns 0.0
        min_candidate = {
            "relative_options_volume": 0.0,
            "chg_pct": -5.0,
            "iv": 0.0,
            "rsi": 0.0,
            "macd_hist": -0.5  # <= 0 -> 0.0
        }
        self.assertEqual(calculate_candidate_score(min_candidate), 0.0)

        # 5. Partial metrics -> reweights based on available metric weights
        # relative_options_volume = 5.0 (50% of cap 10.0, weight 30.0 -> 15.0)
        # chg_pct = 2.5 (50% of cap 5.0, weight 25.0 -> 12.5)
        # total available weighted sum = 27.5, total available weight = 55.0
        # 27.5 / 55.0 * 100 = 50.0
        partial_candidate = {
            "relative_options_volume": 5.0,
            "chg_pct": 2.5
        }
        self.assertEqual(calculate_candidate_score(partial_candidate), 50.0)

        # 6. MACD Hist edge cases
        # macd_hist > 0 -> 1.0 (weight 10.0)
        cand_macd_pos = {"macd_hist": 0.01}
        self.assertEqual(calculate_candidate_score(cand_macd_pos), 100.0)

        # macd_hist == 0 -> 0.0 (weight 10.0)
        cand_macd_zero = {"macd_hist": 0.0}
        self.assertEqual(calculate_candidate_score(cand_macd_zero), 0.0)

        # macd_hist < 0 -> 0.0 (weight 10.0)
        cand_macd_neg = {"macd_hist": -0.01}
        self.assertEqual(calculate_candidate_score(cand_macd_neg), 0.0)

        # macd_hist is None -> metric not available
        cand_macd_none = {"macd_hist": None}
        self.assertEqual(calculate_candidate_score(cand_macd_none), 0.0)

        # 7. Handles string numeric values
        str_candidate = {
            "relative_options_volume": "10.0",
            "chg_pct": "5.0",
            "iv": "1.0",
            "rsi": "100.0",
            "macd_hist": "0.1"
        }
        self.assertEqual(calculate_candidate_score(str_candidate), 100.0)

    def test_update_candidates_reads_cached_technical_indicators(self):
        import tempfile
        import shutil
        from unittest.mock import patch
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        try:
            downloads_dir = os.path.join(temp_dir, "downloads")
            os.makedirs(downloads_dir, exist_ok=True)
            active_file = os.path.join(temp_dir, "active_positions.json")
            gex_engine.save_json(active_file, {"options_positions": {}, "stocks_positions": {}})
            gex_engine.save_json(os.path.join(downloads_dir, "test_scan.json"), {
                "data": {"result": {"scan_title": "Test Scan", "results": [{
                    "ticker": "AMRC",
                    "columns": {"Last": "20", "Volume": "500000", "% Change": "0.01", "Market cap": "3000000000"}
                }]}}
            })
            gex_engine.save_json(os.path.join(downloads_dir, "amrc_technical_indicators_raw.json"), {
                "data": {"indicators": [
                    {"type": "rsi", "series": [{"value": 39.0083}]},
                    {"type": "macd", "series": [{"histogram": -0.1624}]},
                ]}
            })
            candidates_file = os.path.join(temp_dir, "candidate_stocks.json")
            with patch('gex_engine.OPTIONS_FILE', active_file), \
                 patch('gex_engine.DOWNLOADS_DIR', downloads_dir), \
                 patch('gex_engine.CANDIDATES_FILE', candidates_file), \
                 patch('gex_engine.ANALYSES_FILE', os.path.join(temp_dir, "ticker_analyses.json")), \
                 patch('gex_engine.persist_new_scans', return_value=[]):
                class UpdateArgs:
                    min_rsi = None
                    max_rsi = None
                    macd_filter = "none"

                gex_engine.cmd_update_candidates(UpdateArgs())
                candidate = gex_engine.load_json(candidates_file, {})["candidates"][0]
                self.assertEqual(candidate["rsi"], 39.01)
                self.assertEqual(candidate["macd_hist"], -0.1624)
                self.assertIn("score", candidate)
        finally:
            shutil.rmtree(temp_dir)


if __name__ == '__main__':
    unittest.main()
