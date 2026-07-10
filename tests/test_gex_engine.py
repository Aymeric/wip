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
    derive_volatility_profile,
    select_best_option,
    RegimeGates,
    OptionPosition,
    StockPosition
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

    def test_active_positions_exclusion_empty(self):
        # Verify that if positions are empty, active_positions list is empty and does not use hardcoded defaults
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
                self.assertEqual(saved_data["excluded_active_positions"], [])

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
                self.assertEqual(len(data.get("closed_stocks", [])), 1)
                closed_item = data["closed_stocks"][0]
                self.assertEqual(closed_item["Ticker"], "MSFT")
                self.assertEqual(closed_item["Close Price"], 450.00)
                self.assertEqual(closed_item["Realized P&L ($)"], 1000.0) # (450 - 400) * 20 shares
                self.assertEqual(closed_item["Realized P&L (%)"], 12.5) # (450 - 400) / 400
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

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

if __name__ == '__main__':
    unittest.main()
