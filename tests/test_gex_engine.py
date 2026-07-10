#!/usr/bin/env python3
"""
Unit Tests for GEX Options Mechanical Trading Engine
"""

import unittest
import sys
import os

# Ensure the src directory is in the path to import gex_engine correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from gex_engine import (
    calculate_grade, 
    compute_regime_gates, 
    compute_exit_rule_state,
    derive_gex_profile,
    derive_volatility_profile
)

class TestGEXEngine(unittest.TestCase):

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
        # Spot is above +GEX (310), but options premium is in a loss (-89.2% like BABA in active_options)
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

if __name__ == '__main__':
    unittest.main()
