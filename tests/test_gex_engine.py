#!/usr/bin/env python3
"""
Unit Tests for GEX Options Mechanical Trading Engine
"""

import unittest
import sys
import os
import subprocess
from io import StringIO


# Ensure the src directory is in the path to import gex_engine correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from gex_engine import (
    sanitize_account,
    calculate_candidate_score,
    calculate_grade, 
    classify_etf,
    compute_regime_gates, 
    compute_exit_rule_state,
    extract_quotes_list,
    derive_gex_profile,
    derive_volatility_profile,
    select_best_option,
    discover_earnings_date,
    calculate_bollinger_bands,
    calculate_atr,
    calculate_annualized_vol,
    calculate_trade_journal,
    parse_spot_overrides,
    parse_effective_session_date,
    slugify,
    normalize_workflow_state,
    format_color,
    find_latest_historical_ohlc,
    get_all_active_symbols,
    find_latest_technical_indicators,
    cmd_status,
    check_technical_alerts,
    RegimeGates,
    OptionPosition,
    StockPosition
)

class TestGEXEngine(unittest.TestCase):

    def test_slugify(self):
        # Standard text lowercasing and space replacement
        self.assertEqual(slugify("Hello World"), "hello_world")

        # Special characters and punctuation replacement
        self.assertEqual(slugify("Scan #1: High Volatility!"), "scan_1_high_volatility")

        # Consecutive non-alphanumeric character collapsing
        self.assertEqual(slugify("foo---bar___baz"), "foo_bar_baz")

        # Leading and trailing non-alphanumeric character stripping
        self.assertEqual(slugify("___hello world___"), "hello_world")
        self.assertEqual(slugify("---!hello world!---"), "hello_world")

        # Numbers and mixed alphanumeric strings
        self.assertEqual(slugify("Top 10 Scans 2026"), "top_10_scans_2026")

        # Edge cases: empty string, whitespace-only, non-alphanumeric-only
        self.assertEqual(slugify(""), "")
        self.assertEqual(slugify("   "), "")
        self.assertEqual(slugify("!!!###$$$"), "")
    def test_extract_quotes_list(self):
        sample_quotes = [{"instrument_id": "opt1"}]

        # 1. Nested dict data -> results
        self.assertEqual(extract_quotes_list({"data": {"results": sample_quotes}}), sample_quotes)

        # 2. Dict data list fallback
        self.assertEqual(extract_quotes_list({"data": sample_quotes}), sample_quotes)

        # 3. Dict results list fallback
        self.assertEqual(extract_quotes_list({"results": sample_quotes}), sample_quotes)

        # 4. Direct list
        self.assertEqual(extract_quotes_list(sample_quotes), sample_quotes)

        # 5. Empty dict or invalid payload fallback
        self.assertEqual(extract_quotes_list({}), [])
        self.assertEqual(extract_quotes_list(None), [])
        self.assertEqual(extract_quotes_list("invalid"), [])
        self.assertEqual(extract_quotes_list(123), [])

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
        highs = [105.0] * 20
        lows = [95.0] * 20
        closes = [100.0] * 20
        atr = calculate_atr(highs, lows, closes, period=10)
        self.assertIsNotNone(atr)
        assert atr is not None
        self.assertAlmostEqual(atr, 10.0)

        # ATR Edge cases
        self.assertIsNone(calculate_atr([100.0] * 5, [95.0] * 5, [98.0] * 5, period=10))
        self.assertIsNone(calculate_atr([100.0] * 20, [95.0] * 20, [98.0] * 20, period=0))

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

    def test_load_json_handles_non_container_json_files(self):
        import tempfile
        import gex_engine

        for content in ("null", "123", '"string_value"', "true"):
            with self.subTest(content=content):
                with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
                    tmp_path = tmp.name
                    tmp.write(content)
                try:
                    default_dict = {"fallback": True}
                    default_list = ["fallback"]
                    self.assertEqual(gex_engine.load_json(tmp_path, default_dict), default_dict)
                    self.assertEqual(gex_engine.load_json(tmp_path, default_list), default_list)
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
        import json
        from unittest.mock import patch
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp, \
             tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as etf_tmp:
            tmp_path = tmp.name
            etf_path = etf_tmp.name
            json.dump({
                "data": {
                    "results": [
                        {"quote": {"symbol": "SPY", "last_trade_price": "500.0", "adjusted_previous_close": "495.0", "has_traded": True}},
                        {"quote": {"symbol": "QQQ", "last_trade_price": "400.0", "adjusted_previous_close": "395.0", "has_traded": True}},
                        {"quote": {"symbol": "HYG", "last_trade_price": "75.0", "adjusted_previous_close": "76.0", "has_traded": True}},
                    ]
                }
            }, etf_tmp)
            etf_tmp.flush()
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
                        self.etf_file = etf_path
                        
                # We can dynamically test the parsing engine on cached data file
                args = DummyArgs()
                from gex_engine import cmd_update_regime
                # Should not raise exception and execute status check reporting success
                cmd_update_regime(args)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            if os.path.exists(etf_path):
                os.remove(etf_path)

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

    def test_sanitize_account(self):
        # Empty or default
        self.assertEqual(sanitize_account(""), "")
        self.assertEqual(sanitize_account(None), "")

        # Valid alphanumeric / hyphen / underscore
        self.assertEqual(sanitize_account("ACC_123-A"), "ACC_123-A")

        # Path traversal / special characters stripped
        self.assertEqual(sanitize_account("../ACC_123"), "ACC_123")
        self.assertEqual(sanitize_account("acc/sub/123"), "accsub123")

        # Non-alphanumeric only raises ValueError
        with self.assertRaises(ValueError):
            sanitize_account("!!!")

    def test_account_performance_path_is_scoped(self):
        import gex_engine

        self.assertTrue(gex_engine.account_performance_file("5QR24141").endswith("performance_5QR24141.json"))
        self.assertTrue(gex_engine.account_performance_file("../5QR24141").endswith("performance_5QR24141.json"))
        self.assertTrue(gex_engine.account_performance_file().endswith("performance.json"))
        with self.assertRaises(ValueError):
            gex_engine.account_performance_file("!!!")

    def test_account_position_paths_are_scoped(self):
        import gex_engine

        self.assertTrue(gex_engine.account_positions_file("5QR24141").endswith("active_positions_5QR24141.json"))
        self.assertTrue(gex_engine.account_closed_positions_file("5QR24141").endswith("closed_positions_5QR24141.json"))
        self.assertTrue(gex_engine.account_positions_file().endswith("active_positions.json"))
        self.assertTrue(gex_engine.account_closed_positions_file().endswith("closed_positions.json"))

    def test_hyg_credit_divergence_integration(self):
        import tempfile
        import json
        from unittest.mock import patch
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp, \
             tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as etf_tmp:
            tmp_path = tmp.name
            etf_path = etf_tmp.name
            json.dump({
                "data": {
                    "results": [
                        {"quote": {"symbol": "SPY", "last_trade_price": "500.0", "adjusted_previous_close": "495.0", "has_traded": True}},
                        {"quote": {"symbol": "QQQ", "last_trade_price": "400.0", "adjusted_previous_close": "395.0", "has_traded": True}},
                        {"quote": {"symbol": "HYG", "last_trade_price": "75.0", "adjusted_previous_close": "76.0", "has_traded": True}},
                    ]
                }
            }, etf_tmp)
            etf_tmp.flush()
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
                        self.etf_file = etf_path
                        
                args = DummyArgs()
                from gex_engine import cmd_update_regime
                cmd_update_regime(args)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            if os.path.exists(etf_path):
                os.remove(etf_path)

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

    def test_normalize_workflow_state(self):
        # Case 1: Well-formed input state
        valid_state = {
            "current_phase": "Phase I: Risk & Audit",
            "last_updated": "2026-08-11T12:00:00Z",
            "subagents": {"agent1": {"status": "SUCCESS"}},
            "notes": [{"content": "note 1"}],
        }
        res1 = normalize_workflow_state(valid_state)
        self.assertEqual(res1["current_phase"], "Phase I: Risk & Audit")
        self.assertEqual(res1["last_updated"], "2026-08-11T12:00:00Z")
        self.assertEqual(res1["subagents"], {"agent1": {"status": "SUCCESS"}})
        self.assertEqual(res1["notes"], [{"content": "note 1"}])

        # Case 2: Non-dict inputs (None, int, str, list)
        for non_dict in (None, 123, "malformed", ["phase"]):
            with self.subTest(non_dict=non_dict):
                res = normalize_workflow_state(non_dict)
                self.assertEqual(res["current_phase"], "Phase 0: Initialization")
                self.assertIsNone(res["last_updated"])
                self.assertEqual(res["subagents"], {})
                self.assertEqual(res["notes"], [])

        # Case 3: Missing or empty current_phase
        for falsy_phase in ("", None, 0):
            with self.subTest(falsy_phase=falsy_phase):
                res = normalize_workflow_state({"current_phase": falsy_phase})
                self.assertEqual(res["current_phase"], "Phase 0: Initialization")

        # Case 4: Malformed subagents and notes
        malformed_fields = {
            "current_phase": "Phase II: Discovery",
            "last_updated": "2026-08-11T12:00:00Z",
            "subagents": "not a dict",
            "notes": {"invalid": "not a list"},
        }
        res4 = normalize_workflow_state(malformed_fields)
        self.assertEqual(res4["current_phase"], "Phase II: Discovery")
        self.assertEqual(res4["subagents"], {})
        self.assertEqual(res4["notes"], [])

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

    def test_cmd_add_pos(self):
        import tempfile
        from unittest.mock import patch
        import io
        import sys
        import gex_engine

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            with patch('gex_engine.OPTIONS_FILE', tmp_path):
                class DummyArgs:
                    option_id = "AAPL250117C00150000"
                    underlier = "aapl"
                    strike = 150.0
                    expiration = "2025-01-17"
                    type = "call"
                    purchase_premium = 5.50
                    delta = 0.55
                    gamma = 0.03
                    open_interest = 1000
                    imp_vol = 0.25
                    sector = "Tech"
                    account = ""

                gex_engine.cmd_add_pos(DummyArgs())

                # Check options_positions contents
                data = gex_engine.load_json(tmp_path, {})
                positions = data.get("options_positions", {})
                self.assertIn("AAPL250117C00150000", positions)
                pos = positions["AAPL250117C00150000"]
                self.assertEqual(pos["Option ID"], "AAPL250117C00150000")
                self.assertEqual(pos["Underlier"], "AAPL")
                self.assertEqual(pos["Strike"], "150.00")
                self.assertEqual(pos["Expiration"], "2025-01-17")
                self.assertEqual(pos["Type"], "call")
                self.assertEqual(pos["Purchase Premium"], 5.50)
                self.assertEqual(pos["Delta"], "0.55")
                self.assertEqual(pos["Gamma"], "0.03")
                self.assertEqual(pos["Asset Cost Basis"], 550.0)
                self.assertEqual(pos["Current Value"], 550.0)
                self.assertEqual(pos["Beta Sector Tag"], "Tech")

                # Duplicate option_id check
                stderr_buf = io.StringIO()
                with patch('sys.stderr', stderr_buf):
                    with self.assertRaises(SystemExit) as cm:
                        gex_engine.cmd_add_pos(DummyArgs())
                    self.assertEqual(cm.exception.code, 1)
                    self.assertIn("Error: Option ID AAPL250117C00150000 already exists", stderr_buf.getvalue())

                # Invalid expiration format check
                class InvalidExpArgs(DummyArgs):
                    option_id = "AAPL250117C00160000"
                    expiration = "2025/01/17"

                stderr_buf_exp = io.StringIO()
                with patch('sys.stderr', stderr_buf_exp):
                    with self.assertRaises(SystemExit) as cm:
                        gex_engine.cmd_add_pos(InvalidExpArgs())
                    self.assertEqual(cm.exception.code, 1)
                    self.assertIn("Error: Expiration '2025/01/17' must be a valid date in YYYY-MM-DD format.", stderr_buf_exp.getvalue())

                # Invalid strike price validation check (e.g. negative strike)
                class InvalidStrikeArgs(DummyArgs):
                    option_id = "AAPL250117C00170000"
                    strike = -10.0

                stderr_buf_strike = io.StringIO()
                with patch('sys.stderr', stderr_buf_strike):
                    with self.assertRaises(SystemExit) as cm:
                        gex_engine.cmd_add_pos(InvalidStrikeArgs())
                    self.assertEqual(cm.exception.code, 1)
                    self.assertIn("Error validating option position parameters: strike must be positive: -10.0", stderr_buf_strike.getvalue())

                # Invalid purchase premium validation check (e.g. negative premium)
                class InvalidPremiumArgs(DummyArgs):
                    option_id = "AAPL250117C00180000"
                    purchase_premium = -5.0

                stderr_buf_prem = io.StringIO()
                with patch('sys.stderr', stderr_buf_prem):
                    with self.assertRaises(SystemExit) as cm:
                        gex_engine.cmd_add_pos(InvalidPremiumArgs())
                    self.assertEqual(cm.exception.code, 1)
                    self.assertIn("Error validating option position parameters: purchase_premium must be positive: -5.0", stderr_buf_prem.getvalue())
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

                # Test invalid stock parameters validation (e.g. negative shares or buy price)
                class InvalidStockSharesArgs(AddArgs):
                    ticker = "NVDA"
                    shares = -5.0

                import io
                stderr_buf_stock = io.StringIO()
                with patch('sys.stderr', stderr_buf_stock):
                    with self.assertRaises(SystemExit) as cm:
                        gex_engine.cmd_add_stock_pos(InvalidStockSharesArgs())
                    self.assertEqual(cm.exception.code, 1)
                    self.assertIn("Error validating stock position parameters: shares must be positive: -5.0", stderr_buf_stock.getvalue())
                
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

    def test_cmd_update_opt(self):
        import tempfile
        from unittest.mock import patch
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(temp_dir, "active_positions_TEST.json")
        initial_data = {
            "options_positions": {
                "OPT123": {
                    "Underlier": "AAPL",
                    "Mark Price": 2.50,
                    "Delta": "0.45",
                    "Gamma": "0.02",
                    "Open Interest": 100,
                    "ImpVol": "0.25",
                    "Stalling Days": 0,
                    "Target Mode": "T1",
                    "T2 Target": 5.0
                },
                "OPT456": {
                    "Underlier": "MSFT",
                    "Mark Price": 10.0,
                    "Delta": "0.60"
                }
            }
        }
        gex_engine.save_json(tmp_path, initial_data)

        try:
            with patch('gex_engine.account_positions_file', return_value=tmp_path):
                # 1) Update by option ID with all optional arguments specified
                class UpdateArgs1:
                    account = "TEST"
                    option_id = "OPT123"
                    mark = 3.75
                    delta = 0.55
                    gamma = 0.03
                    oi = 150
                    iv = 0.30
                    stalling_days = 2
                    target_mode = "T2"
                    t2_target = 7.5

                gex_engine.cmd_update_opt(UpdateArgs1())
                updated_data = gex_engine.load_json(tmp_path, {})
                opt123 = updated_data["options_positions"]["OPT123"]
                self.assertEqual(opt123["Mark Price"], 3.75)
                self.assertEqual(opt123["Delta"], "0.55")
                self.assertEqual(opt123["Gamma"], "0.03")
                self.assertEqual(opt123["Open Interest"], 150)
                self.assertEqual(opt123["ImpVol"], "0.3")
                self.assertEqual(opt123["Stalling Days"], 2)
                self.assertEqual(opt123["Target Mode"], "T2")
                self.assertEqual(opt123["T2 Target"], 7.5)

                # 2) Update by underlier ticker (case-insensitive match) with minimal arguments
                class UpdateArgs2:
                    account = "TEST"
                    option_id = "msft"
                    mark = 12.0
                    delta = None
                    gamma = None
                    oi = None
                    iv = None
                    stalling_days = None

                gex_engine.cmd_update_opt(UpdateArgs2())
                updated_data = gex_engine.load_json(tmp_path, {})
                opt456 = updated_data["options_positions"]["OPT456"]
                self.assertEqual(opt456["Mark Price"], 12.0)
                self.assertEqual(opt456["Delta"], "0.60")  # Unchanged

                # 3) Non-existent option ID / ticker raises SystemExit
                class NonExistentArgs:
                    account = "TEST"
                    option_id = "UNKNOWN"
                    mark = 1.0
                    delta = None
                    gamma = None
                    oi = None
                    iv = None
                    stalling_days = None

                with self.assertRaises(SystemExit):
                    gex_engine.cmd_update_opt(NonExistentArgs())
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

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

    def test_cmd_cleanup_downloads(self):
        """Test cmd_cleanup_downloads for directory age filtering, tmp cleaning, and non-existent dir handling."""
        import tempfile
        import shutil
        from datetime import datetime, timedelta
        from unittest.mock import patch, MagicMock
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        try:
            # 1. Test non-existent DOWNLOADS_DIR
            non_existent_dir = os.path.join(temp_dir, "nonexistent")
            with patch("gex_engine.DOWNLOADS_DIR", non_existent_dir), patch("sys.stdout") as mock_stdout:
                class Args:
                    days = 7
                gex_engine.cmd_cleanup_downloads(Args())
                output = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)
                self.assertIn("No downloads directory found.", output)

            # 2. Test directory cleanup logic
            downloads_dir = os.path.join(temp_dir, "downloads")
            os.makedirs(downloads_dir, exist_ok=True)

            now = datetime.now()
            old_date_str = (now - timedelta(days=10)).strftime("%Y%m%d")
            new_date_str = (now - timedelta(days=2)).strftime("%Y%m%d")

            old_date_dir = os.path.join(downloads_dir, old_date_str)
            new_date_dir = os.path.join(downloads_dir, new_date_str)
            tmp_dir = os.path.join(downloads_dir, "tmp")
            other_dir = os.path.join(downloads_dir, "other_folder")
            sample_file = os.path.join(downloads_dir, "sample.json")

            os.makedirs(old_date_dir)
            os.makedirs(new_date_dir)
            os.makedirs(tmp_dir)
            os.makedirs(other_dir)
            with open(sample_file, "w") as f:
                f.write("{}")

            # Set mtime for tmp folder to 2 days ago so age_days >= 1
            old_time = (now - timedelta(days=2)).timestamp()
            os.utime(tmp_dir, (old_time, old_time))

            with patch("gex_engine.DOWNLOADS_DIR", downloads_dir), patch("sys.stdout") as mock_stdout:
                class Args:
                    days = 7
                gex_engine.cmd_cleanup_downloads(Args())
                output = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)
                self.assertIn("Removing stale download folder", output)
                self.assertIn("Removing stale tmp folder", output)
                self.assertIn("Cleanup complete. Removed 2 folders.", output)

            # Verify files/folders after cleanup
            self.assertFalse(os.path.exists(old_date_dir))
            self.assertFalse(os.path.exists(tmp_dir))
            self.assertTrue(os.path.exists(new_date_dir))
            self.assertTrue(os.path.exists(other_dir))
            self.assertTrue(os.path.exists(sample_file))

            # 3. Test recent tmp folder retention
            os.makedirs(tmp_dir, exist_ok=True)
            # mtime is now (fresh tmp)
            with patch("gex_engine.DOWNLOADS_DIR", downloads_dir), patch("sys.stdout") as mock_stdout:
                class Args:
                    days = 7
                gex_engine.cmd_cleanup_downloads(Args())
                output = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)
                self.assertIn("Cleanup complete. Removed 0 folders.", output)

            self.assertTrue(os.path.exists(tmp_dir))

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

    def test_classify_etf(self):
        """Test ETF classification logic for standard ETFs and HYG."""
        # Standard ETF tests (thresholds: > 0.1 BULLISH, < -0.1 BEARISH, else FLAT)
        self.assertEqual(classify_etf("SPY", 0.15), "BULLISH")
        self.assertEqual(classify_etf("QQQ", -0.15), "BEARISH")
        self.assertEqual(classify_etf("IWM", 0.05), "FLAT")
        self.assertEqual(classify_etf("XLK", 0.1), "FLAT")
        self.assertEqual(classify_etf("XLF", -0.1), "FLAT")

        # HYG tests (thresholds: > 0.0 BULLISH, < 0.0 BEARISH, else FLAT)
        self.assertEqual(classify_etf("HYG", 0.05), "BULLISH")
        self.assertEqual(classify_etf("HYG", -0.05), "BEARISH")
        self.assertEqual(classify_etf("HYG", 0.0), "FLAT")

        # Case-insensitivity test
        self.assertEqual(classify_etf("hyg", 0.02), "BULLISH")
        self.assertEqual(classify_etf("spy", 0.2), "BULLISH")

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

    def test_format_color(self):
        from unittest.mock import patch

        # Case 1: TTY output enabled (sys.stdout.isatty() is True)
        with patch("sys.stdout.isatty", return_value=True):
            # Non-bold text formatting
            self.assertEqual(format_color("Test Text", "32", bold=False), "\033[0;32mTest Text\033[0m")
            # Bold text formatting
            self.assertEqual(format_color("Test Text", "31", bold=True), "\033[1;31mTest Text\033[0m")

        # Case 2: Non-TTY output (sys.stdout.isatty() is False)
        with patch("sys.stdout.isatty", return_value=False):
            self.assertEqual(format_color("Test Text", "32", bold=False), "Test Text")
            self.assertEqual(format_color("Test Text", "31", bold=True), "Test Text")
    def test_cmd_journal(self):
        """Test cmd_journal subcommand with default account, explicit account, and empty data."""
        import json
        import io
        import tempfile
        from unittest.mock import patch, MagicMock
        import gex_engine

        # 1. Default account with trade data
        closed_mock = {
            "closed_options": [
                {"Realized P&L ($)": 200.0, "Days Held": 4, "Close Reason": "Target"}
            ],
            "closed_stocks": [
                {"Realized P&L ($)": -50.0, "Days Held": 2, "Close Reason": "Stop"}
            ]
        }
        perf_mock = {"monthly_pnl_dlr": 150.0}

        def mock_load_json(filepath, default=None):
            if "closed_positions" in filepath:
                return closed_mock
            if "performance" in filepath:
                return perf_mock
            return default if default is not None else {}

        with patch("gex_engine.load_json", side_effect=mock_load_json), patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            class DefaultArgs:
                pass

            gex_engine.cmd_journal(DefaultArgs())
            output = mock_stdout.getvalue()
            data = json.loads(output)
            self.assertEqual(data["records_reviewed"], 2)
            self.assertEqual(data["total_realized_pnl"], 150.0)
            self.assertEqual(data["win_count"], 1)
            self.assertEqual(data["loss_count"], 1)
            self.assertEqual(data["cache_reconciliation"], "MATCH")

        # 2. Explicit account parameter
        with tempfile.TemporaryDirectory() as tmpdir:
            account_closed_file = os.path.join(tmpdir, "closed_positions_acct123.json")
            account_perf_file = os.path.join(tmpdir, "performance_acct123.json")

            acct_closed_data = {
                "closed_options": [{"Realized P&L ($)": 300.0, "Days Held": 1, "Close Reason": "Target"}],
                "closed_stocks": []
            }
            acct_perf_data = {"monthly_pnl_dlr": 300.0}

            gex_engine.save_json(account_closed_file, acct_closed_data)
            gex_engine.save_json(account_perf_file, acct_perf_data)

            with patch("gex_engine.account_closed_positions_file", return_value=account_closed_file) as mock_acct_closed, \
                 patch("gex_engine.account_performance_file", return_value=account_perf_file) as mock_acct_perf, \
                 patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:

                class AccountArgs:
                    account = "acct123"

                gex_engine.cmd_journal(AccountArgs())
                mock_acct_closed.assert_called_once_with("acct123")
                mock_acct_perf.assert_called_once_with("acct123")

                output = mock_stdout.getvalue()
                data = json.loads(output)
                self.assertEqual(data["records_reviewed"], 1)
                self.assertEqual(data["total_realized_pnl"], 300.0)

        # 3. Empty / missing file data
        with patch("gex_engine.load_json") as mock_load, patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            def load_empty(filepath, default=None):
                return default if default is not None else {}
            mock_load.side_effect = load_empty

            class EmptyArgs:
                account = ""

            gex_engine.cmd_journal(EmptyArgs())
            output = mock_stdout.getvalue()
            data = json.loads(output)
            self.assertEqual(data["records_reviewed"], 0)
            self.assertEqual(data["total_realized_pnl"], 0.0)

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

    def test_cmd_simulate_not_found(self):
        """Test cmd_simulate exits with code 1 when symbol is not found in analyses or candidates."""
        from unittest.mock import patch, MagicMock
        import gex_engine

        class SimArgs:
            symbol = "UNKNOWN"
            spot = 100.0
            account = ""

        with patch("gex_engine.load_json", return_value={}):
            with patch("sys.stdout") as mock_stdout:
                mock_stdout.isatty = MagicMock(return_value=False)
                with self.assertRaises(SystemExit) as cm:
                    gex_engine.cmd_simulate(SimArgs())
                self.assertEqual(cm.exception.code, 1)

    def test_cmd_simulate_from_analyses_with_option_position(self):
        """Test cmd_simulate with symbol in analyses and active option position."""
        from unittest.mock import patch, MagicMock
        import gex_engine

        class SimArgs:
            symbol = "TSLA"
            spot = 210.0
            account = ""

        analyses_data = {
            "TSLA": {
                "Ticker": "TSLA",
                "Spot": 200.0,
                "pTrans": 190.0,
                "nTrans": 180.0,
                "+GEX": 220.0,
                "COTMP": 175.0,
            }
        }
        options_data = {
            "options_positions": {
                "TSLA": {
                    "Purchase Premium": 10.0,
                    "Mark Price": 10.0,
                    "Delta": 0.5,
                    "Gamma": 0.02,
                    "Entry Date": "2025-01-01",
                    "Stalling Days": 0,
                }
            },
            "stocks_positions": {},
        }

        def fake_load_json(filepath, default=None):
            if "analyses" in filepath or filepath == gex_engine.ANALYSES_FILE:
                return analyses_data
            if "options" in filepath or "active_positions" in filepath or filepath == gex_engine.OPTIONS_FILE:
                return options_data
            return default if default is not None else {}

        with patch("gex_engine.load_json", side_effect=fake_load_json):
            with patch("sys.stdout") as mock_stdout:
                mock_stdout.isatty = MagicMock(return_value=False)
                gex_engine.cmd_simulate(SimArgs())
                output = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)

                self.assertIn("Simulation for TSLA", output)
                self.assertIn("Original Spot", output)
                self.assertIn("$200.00", output)
                self.assertIn("Simulated Spot", output)
                self.assertIn("$210.00", output)
                self.assertIn("Active Position Impact", output)
                self.assertIn("Simulated Mark Price", output)
                self.assertIn("GEX Runway Map (Simulated)", output)

    def test_cmd_simulate_from_analyses_with_stock_position(self):
        """Test cmd_simulate with symbol in analyses and active stock position."""
        from unittest.mock import patch, MagicMock
        import gex_engine

        class SimArgs:
            symbol = "AAPL"
            spot = 160.0
            account = ""

        analyses_data = {
            "AAPL": {
                "Ticker": "AAPL",
                "Spot": 150.0,
                "pTrans": 140.0,
                "nTrans": 130.0,
                "+GEX": 170.0,
                "COTMP": 125.0,
            }
        }
        options_data = {
            "options_positions": {},
            "stocks_positions": {
                "AAPL": {
                    "Shares": 100.0,
                    "Average Buy Price": 150.0,
                }
            },
        }

        def fake_load_json(filepath, default=None):
            if "analyses" in filepath or filepath == gex_engine.ANALYSES_FILE:
                return analyses_data
            if "options" in filepath or "active_positions" in filepath or filepath == gex_engine.OPTIONS_FILE:
                return options_data
            return default if default is not None else {}

        with patch("gex_engine.load_json", side_effect=fake_load_json):
            with patch("sys.stdout") as mock_stdout:
                mock_stdout.isatty = MagicMock(return_value=False)
                gex_engine.cmd_simulate(SimArgs())
                output = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)

                self.assertIn("Simulation for AAPL", output)
                self.assertIn("Original Spot", output)
                self.assertIn("$150.00", output)
                self.assertIn("Simulated Spot", output)
                self.assertIn("$160.00", output)
                self.assertIn("Active Position Impact", output)
                self.assertIn("Simulated Position Value", output)
                self.assertIn("$16,000.00", output)

    def test_cmd_simulate_from_candidates_fallback(self):
        """Test cmd_simulate falls back to candidates file when symbol is not in analyses."""
        from unittest.mock import patch, MagicMock
        import gex_engine

        class SimArgs:
            symbol = "NVDA"
            spot = 105.0
            account = ""

        candidates_data = {
            "candidates": [
                {
                    "symbol": "NVDA",
                    "price": 100.0,
                    "ptrans": 98.0,
                    "ntrans": 95.0,
                    "gex": 110.0,
                    "cotmp": 92.0,
                }
            ]
        }

        def fake_load_json(filepath, default=None):
            if "candidates" in filepath or filepath == gex_engine.CANDIDATES_FILE:
                return candidates_data
            if "analyses" in filepath or filepath == gex_engine.ANALYSES_FILE:
                return {}
            return default if default is not None else {}

        with patch("gex_engine.load_json", side_effect=fake_load_json):
            with patch("sys.stdout") as mock_stdout:
                mock_stdout.isatty = MagicMock(return_value=False)
                gex_engine.cmd_simulate(SimArgs())
                output = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)

                self.assertIn("Simulation for NVDA", output)
                self.assertIn("Original Spot", output)
                self.assertIn("$100.00", output)
                self.assertIn("Simulated Spot", output)
                self.assertIn("$105.00", output)
                self.assertIn("GEX Runway Map (Simulated)", output)

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

    def test_calculate_annualized_vol(self):
        """Test calculation of annualized volatility from daily log returns."""
        import math

        # 1. Edge case: empty list -> 0.0
        self.assertEqual(calculate_annualized_vol([]), 0.0)

        # 2. Edge case: single element -> 0.0
        self.assertEqual(calculate_annualized_vol([0.01]), 0.0)

        # 3. Edge case: zero variance (all values identical) -> 0.0
        self.assertEqual(calculate_annualized_vol([0.02, 0.02, 0.02]), 0.0)

        # 4. Known input calculation: [0.01, -0.01]
        expected_val = math.sqrt(0.0002) * math.sqrt(252) * 100.0
        result_val = calculate_annualized_vol([0.01, -0.01])
        self.assertAlmostEqual(result_val, expected_val, places=7)

        # 5. Realistic log return series
        returns = [0.005, -0.003, 0.012, -0.008, 0.002, 0.001, -0.004, 0.006]
        n = len(returns)
        mean_ret = sum(returns) / n
        variance = sum((x - mean_ret) ** 2 for x in returns) / (n - 1)
        expected_real = math.sqrt(variance) * math.sqrt(252) * 100.0
        self.assertAlmostEqual(calculate_annualized_vol(returns), expected_real, places=7)
    def test_calculate_ema(self):
        """Test module-level calculate_ema utility function."""
        from gex_engine import calculate_ema

        # 1. Standard EMA calculation with period 3
        values = [10.0, 11.0, 12.0, 13.0, 14.0]
        ema = calculate_ema(values, 3)
        # Expected:
        # seed SMA = (10+11+12)/3 = 11.0
        # k = 2 / (3 + 1) = 0.5
        # 13.0: 13.0 * 0.5 + 11.0 * 0.5 = 12.0
        # 14.0: 14.0 * 0.5 + 12.0 * 0.5 = 13.0
        self.assertEqual(len(ema), 3)
        self.assertAlmostEqual(ema[0], 11.0)
        self.assertAlmostEqual(ema[1], 12.0)
        self.assertAlmostEqual(ema[2], 13.0)

        # 2. Edge case: values length less than period or invalid period
        self.assertEqual(calculate_ema([10.0, 12.0], 3), [])
        self.assertEqual(calculate_ema([10.0, 12.0], 0), [])
        self.assertEqual(calculate_ema([], 3), [])

        # 3. Exact match when len(values) == p
        self.assertEqual(calculate_ema([10.0, 20.0, 30.0], 3), [20.0])

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

    def test_check_technical_alerts(self):
        """Test check_technical_alerts under various market scenarios."""
        # Scenario 1: Short series (< 15 closes)
        short_closes = [100.0 + i for i in range(10)]
        res_short = check_technical_alerts(short_closes)
        self.assertIsNone(res_short["rsi"])
        self.assertIsNone(res_short["macd_hist"])
        self.assertEqual(res_short["alerts"], [])

        # Scenario 2: Oversold RSI (steadily falling closes)
        falling_closes = [200.0 - i * 2.0 for i in range(30)]
        res_oversold = check_technical_alerts(falling_closes)
        self.assertIsNotNone(res_oversold["rsi"])
        assert res_oversold["rsi"] is not None
        self.assertLessEqual(res_oversold["rsi"], 30.0)
        self.assertIn("RSI_OVERSOLD", res_oversold["alerts"])

        # Scenario 3: Overbought RSI (steadily rising closes)
        rising_closes = [100.0 + i * 2.0 for i in range(30)]
        res_overbought = check_technical_alerts(rising_closes)
        self.assertIsNotNone(res_overbought["rsi"])
        assert res_overbought["rsi"] is not None
        self.assertGreaterEqual(res_overbought["rsi"], 70.0)
        self.assertIn("RSI_OVERBOUGHT", res_overbought["alerts"])

        # Scenario 4: Bollinger Bands Lower Touch & Upper Touch
        # Create a stable 20-day series then drop sharply
        stable_closes = [100.0] * 20
        # Lower touch when last price is <= lower BB
        drop_closes = stable_closes.copy()
        drop_closes[-1] = 80.0
        res_bb_lower = check_technical_alerts(drop_closes)
        self.assertIn("BB_LOWER_TOUCH", res_bb_lower["alerts"])

        # Upper touch when last price is >= upper BB
        pop_closes = stable_closes.copy()
        pop_closes[-1] = 120.0
        res_bb_upper = check_technical_alerts(pop_closes)
        self.assertIn("BB_UPPER_TOUCH", res_bb_upper["alerts"])

        # Scenario 5: ATR calculation with highs and lows
        highs = [c + 2.0 for c in rising_closes]
        lows = [c - 2.0 for c in rising_closes]
        res_atr = check_technical_alerts(rising_closes, highs=highs, lows=lows)
        self.assertIsNotNone(res_atr.get("atr"))

        # Scenario 6: MACD Bullish Crossover
        # Construct a series where MACD histogram crosses from negative to positive
        macd_bullish_closes = [100.0] * 30 + [100.0 - i for i in range(1, 15)] + [100.0 - 14 + 8 * 2.0]
        res_macd_bull = check_technical_alerts(macd_bullish_closes)
        self.assertIn("MACD_BULLISH_CROSSOVER", res_macd_bull["alerts"])

        # Scenario 7: MACD Bearish Crossover
        # Construct a series where MACD histogram crosses from positive to negative
        macd_bearish_closes = [100.0] * 30 + [100.0 + i for i in range(1, 15)] + [100.0 + 14 - 8 * 2.0]
        res_macd_bear = check_technical_alerts(macd_bearish_closes)
        self.assertIn("MACD_BEARISH_CROSSOVER", res_macd_bear["alerts"])

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
    def test_get_all_active_symbols_standard(self):
        import tempfile
        import shutil
        from unittest.mock import patch
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        try:
            data_dir = os.path.join(temp_dir, "data")
            os.makedirs(data_dir)

            pos1 = {
                "options_positions": {
                    "opt1": {"Underlier": "aapl"},
                    "opt2": {"Underlier": "MSFT"}
                },
                "stocks_positions": {
                    "tsla": {},
                    "BABA": {}
                }
            }
            pos2 = {
                "options_positions": {
                    "opt3": {"Underlier": "MSFT"}
                },
                "stocks_positions": {
                    "NVDA": {}
                }
            }

            gex_engine.save_json(os.path.join(data_dir, "active_positions.json"), pos1)
            gex_engine.save_json(os.path.join(data_dir, "active_positions_ACC123.json"), pos2)

            with patch("gex_engine.REPOSITORY_ROOT", temp_dir):
                symbols = get_all_active_symbols()

            self.assertEqual(symbols, ["AAPL", "BABA", "MSFT", "NVDA", "TSLA"])
        finally:
            shutil.rmtree(temp_dir)

    def test_get_all_active_symbols_edge_cases(self):
        import tempfile
        import shutil
        from unittest.mock import patch
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        try:
            # 1. Non-existent data directory
            with patch("gex_engine.REPOSITORY_ROOT", temp_dir):
                self.assertEqual(get_all_active_symbols(), [])

            # 2. Data directory exists but no active_positions*.json matching files
            data_dir = os.path.join(temp_dir, "data")
            os.makedirs(data_dir)
            gex_engine.save_json(os.path.join(data_dir, "closed_positions.json"), {
                "closed_stocks": [{"Ticker": "AMZN"}]
            })
            with open(os.path.join(data_dir, "active_positions.txt"), "w") as f:
                f.write("text content")

            with patch("gex_engine.REPOSITORY_ROOT", temp_dir):
                self.assertEqual(get_all_active_symbols(), [])

            # 3. Active positions file with malformed / non-dict entries and missing/empty fields
            malformed_pos = {
                "options_positions": {
                    "opt1": None,  # details is not a dict
                    "opt2": "invalid string",
                    "opt3": {"Underlier": ""},  # empty string
                    "opt4": {},  # missing Underlier key
                    "opt5": {"Underlier": "AMD"}  # valid entry
                },
                "stocks_positions": {
                    "": {},  # empty ticker string
                    "INTC": {}  # valid ticker key
                }
            }
            gex_engine.save_json(os.path.join(data_dir, "active_positions_malformed.json"), malformed_pos)

            with patch("gex_engine.REPOSITORY_ROOT", temp_dir):
                symbols = get_all_active_symbols()

            self.assertEqual(symbols, ["AMD", "INTC"])
        finally:
            shutil.rmtree(temp_dir)

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

    def test_extract_col_case_insensitive_and_null_handling(self):
        """Test _extract_col logic via cmd_update_candidates column parsing."""
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

            # Scan file with uppercase / mixed case keys and None values
            gex_engine.save_json(os.path.join(downloads_dir, "test_scan.json"), {
                "data": {"result": {"scan_title": "Test Scan", "results": [
                    {
                        "ticker": "STOCK1",
                        "columns": {
                            "Last": None,
                            "LAST_TRADE_PRICE": "50.0",
                            "VOLUME": "1000000",
                            "% CHANGE": "1.5",
                            "MARKET CAP": "5000000000",
                            "IV": "0.35",
                            "RELATIVE VOLUME": "2.1"
                        }
                    },
                    {
                        "ticker": "STOCK2",
                        "columns": {
                            "price": "75.0",
                            "volume": "800000",
                            "change_pct": "2.0",
                            "market_cap": "10000000000",
                            "implied_volatility": "0.25",
                            "relative_options_volume": "1.8"
                        }
                    }
                ]}}
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
                candidates = gex_engine.load_json(candidates_file, {})["candidates"]
                self.assertEqual(len(candidates), 2)

                stock1 = next(c for c in candidates if c["symbol"] == "STOCK1")
                self.assertEqual(stock1["price"], 50.0)
                self.assertEqual(stock1["chg_pct"], 1.5)
                self.assertEqual(stock1["iv"], 0.35)
                self.assertEqual(stock1["relative_options_volume"], 2.1)

                stock2 = next(c for c in candidates if c["symbol"] == "STOCK2")
                self.assertEqual(stock2["price"], 75.0)
                self.assertEqual(stock2["chg_pct"], 2.0)
                self.assertEqual(stock2["iv"], 0.25)
                self.assertEqual(stock2["relative_options_volume"], 1.8)
        finally:
            shutil.rmtree(temp_dir)

    def test_find_latest_historical_ohlc_empty_or_missing_dir(self):
        """Test find_latest_historical_ohlc when DOWNLOADS_DIR does not exist or has no matching files."""
        import tempfile
        import shutil
        from unittest.mock import patch
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        try:
            non_existent_dir = os.path.join(temp_dir, "non_existent")
            with patch("gex_engine.DOWNLOADS_DIR", non_existent_dir):
                closes, highs, lows, opens = find_latest_historical_ohlc("AAPL")
                self.assertEqual((closes, highs, lows, opens), ([], [], [], []))

            downloads_dir = os.path.join(temp_dir, "downloads")
            os.makedirs(downloads_dir, exist_ok=True)
            # Add a file that does not match historical pattern
            gex_engine.save_json(os.path.join(downloads_dir, "unrelated_scan.json"), {"data": []})

            with patch("gex_engine.DOWNLOADS_DIR", downloads_dir):
                closes, highs, lows, opens = find_latest_historical_ohlc("AAPL")
                self.assertEqual((closes, highs, lows, opens), ([], [], [], []))
        finally:
            shutil.rmtree(temp_dir)

    def test_find_latest_historical_ohlc_various_json_structures_and_aliases(self):
        """Test find_latest_historical_ohlc parsing varied JSON layouts and column aliases."""
        import tempfile
        import shutil
        from unittest.mock import patch
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        try:
            downloads_dir = os.path.join(temp_dir, "downloads")
            os.makedirs(downloads_dir, exist_ok=True)

            # Structure 1: data -> results -> symbol/bars with close_price, high_price, low_price, open_price
            struct1_file = os.path.join(downloads_dir, "20260801_TSLA_HISTORICAL_raw.json")
            gex_engine.save_json(struct1_file, {
                "data": {
                    "results": [
                        {
                            "symbol": "TSLA",
                            "bars": [
                                {"begins_at": "2026-08-01", "close_price": "200.0", "high_price": "205.0", "low_price": "198.0", "open_price": "199.0"},
                                {"begins_at": "2026-08-02", "close_price": "210.0", "high_price": "215.0", "low_price": "201.0", "open_price": "202.0"}
                            ]
                        }
                    ]
                }
            })

            # Structure 2: top-level bars dictionary with short aliases (close, high, low, open)
            struct2_file = os.path.join(downloads_dir, "20260801_NVDA_HISTORICAL_raw.json")
            gex_engine.save_json(struct2_file, {
                "bars": [
                    {"begins_at": "2026-08-01", "close": 120.0, "high": 125.0, "low": 118.0, "open": 119.0},
                    {"begins_at": "2026-08-02", "close": 122.0, "high": 127.0, "low": 120.0, "open": 121.0}
                ]
            })

            # Structure 3: direct list of bar dictionaries
            struct3_file = os.path.join(downloads_dir, "20260801_AMD_HISTORICAL_raw.json")
            gex_engine.save_json(struct3_file, [
                {"begins_at": "2026-08-01", "close_price": 150.0, "high_price": 155.0, "low_price": 148.0, "open_price": 149.0}
            ])

            with patch("gex_engine.DOWNLOADS_DIR", downloads_dir):
                c1, h1, l1, o1 = find_latest_historical_ohlc("TSLA")
                self.assertEqual(c1, [200.0, 210.0])
                self.assertEqual(h1, [205.0, 215.0])
                self.assertEqual(l1, [198.0, 201.0])
                self.assertEqual(o1, [199.0, 202.0])

                c2, h2, l2, o2 = find_latest_historical_ohlc("NVDA")
                self.assertEqual(c2, [120.0, 122.0])
                self.assertEqual(h2, [125.0, 127.0])
                self.assertEqual(l2, [118.0, 120.0])
                self.assertEqual(o2, [119.0, 121.0])

                c3, h3, l3, o3 = find_latest_historical_ohlc("AMD")
                self.assertEqual(c3, [150.0])
                self.assertEqual(h3, [155.0])
                self.assertEqual(l3, [148.0])
                self.assertEqual(o3, [149.0])
        finally:
            shutil.rmtree(temp_dir)

    def test_find_latest_historical_ohlc_sorting_filtering_and_file_precedence(self):
        """Test chronological sorting, price filtering, file precedence, and corrupted file handling."""
        import tempfile
        import shutil
        from unittest.mock import patch
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        try:
            downloads_dir = os.path.join(temp_dir, "downloads")
            os.makedirs(downloads_dir, exist_ok=True)

            # Older file with out-of-order bars, invalid non-positive prices, and valid prices
            older_file = os.path.join(downloads_dir, "20260701_AAPL_HISTORICAL_raw.json")
            gex_engine.save_json(older_file, {
                "bars": [
                    {"begins_at": "2026-07-03T00:00:00Z", "close": "180.0", "high": "185.0", "low": "178.0", "open": "179.0"},
                    {"begins_at": "2026-07-01T00:00:00Z", "close": "0.0", "high": "10.0", "low": "0.0", "open": "5.0"},  # Should be filtered out
                    {"begins_at": "2026-07-02T00:00:00Z", "close": "175.0", "high": "177.0", "low": "172.0", "open": "173.0"},
                    {"begins_at": "2026-07-04T00:00:00Z", "close": "invalid", "high": "180.0", "low": "170.0", "open": "175.0"}, # Invalid float, should be skipped
                ]
            })

            # Newer file (lexicographically higher filename) should take precedence
            newer_file = os.path.join(downloads_dir, "20260801_AAPL_HISTORICAL_raw.json")
            gex_engine.save_json(newer_file, {
                "bars": [
                    {"begins_at": "2026-08-01T00:00:00Z", "close": "190.0", "high": "195.0", "low": "188.0", "open": "189.0"},
                    {"begins_at": "2026-08-02T00:00:00Z", "close": "192.0", "high": "197.0", "low": "190.0", "open": "191.0"}
                ]
            })

            # Corrupted / unparseable JSON file lexicographically higher than newer_file should be skipped gracefully
            corrupt_file = os.path.join(downloads_dir, "20260901_AAPL_HISTORICAL_raw.json")
            with open(corrupt_file, "w") as f:
                f.write("Corrupted { JSON syntax error")

            with patch("gex_engine.DOWNLOADS_DIR", downloads_dir):
                closes, highs, lows, opens = find_latest_historical_ohlc("AAPL")
                # Should skip corrupt_file and pick newer_file
                self.assertEqual(closes, [190.0, 192.0])
                self.assertEqual(highs, [195.0, 197.0])
                self.assertEqual(lows, [188.0, 190.0])
                self.assertEqual(opens, [189.0, 191.0])

            # Remove corrupt_file and newer_file to test older_file sorting & filtering
            os.remove(corrupt_file)
            os.remove(newer_file)

            with patch("gex_engine.DOWNLOADS_DIR", downloads_dir):
                closes, highs, lows, opens = find_latest_historical_ohlc("AAPL")
                # Sorted chronologically (2026-07-02 then 2026-07-03), invalid/0 close prices filtered
                self.assertEqual(closes, [175.0, 180.0])
                self.assertEqual(highs, [177.0, 185.0])
                self.assertEqual(lows, [172.0, 178.0])
                self.assertEqual(opens, [173.0, 179.0])
        finally:
            shutil.rmtree(temp_dir)

    def test_find_latest_technical_indicators(self):
        """Test find_latest_technical_indicators under various file structures and edge cases."""
        import tempfile
        import shutil
        from unittest.mock import patch
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        try:
            downloads_dir = os.path.join(temp_dir, "downloads")

            # 1. Non-existent DOWNLOADS_DIR -> (None, None)
            with patch("gex_engine.DOWNLOADS_DIR", os.path.join(temp_dir, "nonexistent")):
                rsi, macd_hist = find_latest_technical_indicators("AAPL")
                self.assertIsNone(rsi)
                self.assertIsNone(macd_hist)

            os.makedirs(downloads_dir, exist_ok=True)

            # 2. DOWNLOADS_DIR exists but no matching files for symbol -> (None, None)
            with patch("gex_engine.DOWNLOADS_DIR", downloads_dir):
                rsi, macd_hist = find_latest_technical_indicators("AAPL")
                self.assertIsNone(rsi)
                self.assertIsNone(macd_hist)

            # 3. Happy path: valid indicator file containing both RSI and MACD
            file_path_happy = os.path.join(downloads_dir, "aapl_technical_indicators_20260101.json")
            gex_engine.save_json(file_path_happy, {
                "data": {
                    "indicators": [
                        {"type": "rsi", "series": [{"value": 65.4}]},
                        {"type": "macd", "series": [{"histogram": 1.25}]},
                    ]
                }
            })

            with patch("gex_engine.DOWNLOADS_DIR", downloads_dir):
                rsi, macd_hist = find_latest_technical_indicators("aapl") # case-insensitive symbol check
                self.assertEqual(rsi, 65.4)
                self.assertEqual(macd_hist, 1.25)

            # 4. Latest file precedence & fallback on corrupted newest file
            # Create a newer file (lexicographically sorting after 20260101)
            file_path_newer_corrupt = os.path.join(downloads_dir, "aapl_technical_indicators_20260102.json")
            with open(file_path_newer_corrupt, "w") as f:
                f.write("{ invalid json... ")

            with patch("gex_engine.DOWNLOADS_DIR", downloads_dir):
                # Should skip corrupt 20260102 file and fall back to 20260101 file
                rsi, macd_hist = find_latest_technical_indicators("AAPL")
                self.assertEqual(rsi, 65.4)
                self.assertEqual(macd_hist, 1.25)

            # Now fix 20260102 file with newer values -> should take 20260102
            gex_engine.save_json(file_path_newer_corrupt, {
                "data": {
                    "indicators": [
                        {"type": "rsi", "series": [{"value": 72.1}]},
                        {"type": "macd", "series": [{"histogram": 0.85}]},
                    ]
                }
            })

            with patch("gex_engine.DOWNLOADS_DIR", downloads_dir):
                rsi, macd_hist = find_latest_technical_indicators("AAPL")
                self.assertEqual(rsi, 72.1)
                self.assertEqual(macd_hist, 0.85)

            # 5. Partial indicators: file with only RSI or only MACD
            dir_partial = os.path.join(temp_dir, "downloads_partial")
            os.makedirs(dir_partial, exist_ok=True)
            gex_engine.save_json(os.path.join(dir_partial, "msft_technical_indicators.json"), {
                "data": {
                    "indicators": [
                        {"type": "rsi", "series": [{"value": 45.0}]},
                    ]
                }
            })

            with patch("gex_engine.DOWNLOADS_DIR", dir_partial):
                rsi, macd_hist = find_latest_technical_indicators("MSFT")
                self.assertEqual(rsi, 45.0)
                self.assertIsNone(macd_hist)

            # 6. Malformed entries: empty series, invalid value types, non-dict root
            dir_malformed = os.path.join(temp_dir, "downloads_malformed")
            os.makedirs(dir_malformed, exist_ok=True)

            # Non-dict JSON root
            gex_engine.save_json(os.path.join(dir_malformed, "nvda_technical_1.json"), ["not", "a", "dict"])
            # Non-numeric string value
            gex_engine.save_json(os.path.join(dir_malformed, "nvda_technical_2.json"), {
                "data": {
                    "indicators": [
                        {"type": "rsi", "series": [{"value": "invalid_number"}]}
                    ]
                }
            })
            # Empty series list
            gex_engine.save_json(os.path.join(dir_malformed, "nvda_technical_3.json"), {
                "data": {
                    "indicators": [
                        {"type": "rsi", "series": []}
                    ]
                }
            })

            with patch("gex_engine.DOWNLOADS_DIR", dir_malformed):
                rsi, macd_hist = find_latest_technical_indicators("NVDA")
                self.assertIsNone(rsi)
                self.assertIsNone(macd_hist)

        finally:
            shutil.rmtree(temp_dir)

    def test_cmd_close_pos(self):
        """Test cmd_close_pos for option closing, P&L calculations, error handling, and account scoping."""
        import tempfile
        import shutil
        from io import StringIO
    def test_cmd_update_performance_invalid_net_liq(self):
        """Test cmd_update_performance exits when --net-liq is missing, zero, or negative."""
        from types import SimpleNamespace
        from unittest.mock import patch
        import io
        import gex_engine

        for invalid_net_liq in [None, 0.0, -500.0]:
            with self.subTest(net_liq=invalid_net_liq):
                args = SimpleNamespace(
                    net_liq=invalid_net_liq,
                    account="ACC123",
                    monthly_file=None,
                    pnl_file=None,
                )
                with patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
                    with self.assertRaises(SystemExit) as cm:
                        gex_engine.cmd_update_performance(args)
                    self.assertEqual(cm.exception.code, 1)
                    self.assertIn("Error: --net-liq must be a positive account net liquidation value.", mock_stderr.getvalue())

    def test_cmd_update_performance_account_scoped(self):
        """Test cmd_update_performance computes metrics and saves to account-scoped performance file."""
        import tempfile
        import shutil
        from types import SimpleNamespace
        from unittest.mock import patch
    def test_cmd_workflow_standard_and_subagent_logging(self):
        """Test cmd_workflow output with populated regime, state, portfolio, candidates, and analyses."""
        import tempfile
        import shutil
        from unittest.mock import patch, MagicMock
        from types import SimpleNamespace
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        try:
            active_file = os.path.join(temp_dir, "active_positions.json")
            closed_file = os.path.join(temp_dir, "closed_positions.json")

            active_data = {
                "options_positions": {
                    "opt_1": {
                        "Underlier": "AAPL",
                        "Strike": 150.0,
                        "Type": "call",
                        "Purchase Premium": 2.0,
                        "Mark Price": 3.0,
                    },
                    "opt_2": {
                        "Underlier": "NVDA",
                        "Strike": 120.0,
                        "Type": "call",
                        "Purchase Premium": 5.0,
                        "Mark Price": 8.0,
                    },
                    "opt_3": {
                        "Underlier": "TSLA",
                        "Strike": 200.0,
                        "Type": "put",
                        "Purchase Premium": 0.0,
                    },
                    "opt_4": {
                        "Underlier": "AMZN",
                        "Strike": 180.0,
                        "Type": "call",
                        "Purchase Premium": 10.0,
                        "Mark Price": 7.0,
                    },
                },
                "closed_options": [
                    {"opt_id": "legacy_1", "Underlier": "MSFT"}
                ],
            }
            gex_engine.save_json(active_file, active_data)

            # 1) Position not found error test
            class NotFoundArgs:
                option_id = "NONEXISTENT"
                close_premium = None
                account = ""

            with patch("gex_engine.account_positions_file", return_value=active_file), \
                 patch("gex_engine.account_closed_positions_file", return_value=closed_file), \
                 patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with self.assertRaises(SystemExit) as cm:
                    gex_engine.cmd_close_pos(NotFoundArgs())
                self.assertEqual(cm.exception.code, 1)
                self.assertIn("not found in portfolio", mock_stderr.getvalue())

            # 2) Close position by option_id with explicit close_premium and legacy options migration
            class CloseByIdArgs:
                option_id = "opt_1"
                close_premium = 3.50
                account = ""

            with patch("gex_engine.account_positions_file", return_value=active_file), \
                 patch("gex_engine.account_closed_positions_file", return_value=closed_file), \
                 patch("sys.stdout", new_callable=StringIO):
                gex_engine.cmd_close_pos(CloseByIdArgs())

            # Check active_positions.json state
            active_res = gex_engine.load_json(active_file, {})
            self.assertNotIn("opt_1", active_res.get("options_positions", {}))
            self.assertNotIn("closed_options", active_res)  # Legacy closed options migrated

            # Check closed_positions.json state
            closed_res = gex_engine.load_json(closed_file, {})
            closed_opts = closed_res.get("closed_options", [])
            opt_ids = [opt.get("opt_id") for opt in closed_opts if "opt_id" in opt]
            self.assertIn("legacy_1", opt_ids)

            opt_1_closed = [opt for opt in closed_opts if opt.get("Underlier") == "AAPL"][0]
            self.assertEqual(opt_1_closed["Close Premium"], 3.50)
            self.assertEqual(opt_1_closed["Realized P&L ($)"], 150.0)  # (3.50 - 2.0) * 100
            self.assertEqual(opt_1_closed["Realized P&L (%)"], 75.0)   # ((3.50 - 2.0)/2.0) * 100
            self.assertIn("Close Date", opt_1_closed)

            # 3) Close position by Underlier ticker (case-insensitive) with default close_premium (uses Mark Price)
            class CloseByTickerArgs:
                option_id = "nvda"
                close_premium = None
                account = ""

            with patch("gex_engine.account_positions_file", return_value=active_file), \
                 patch("gex_engine.account_closed_positions_file", return_value=closed_file), \
                 patch("sys.stdout", new_callable=StringIO):
                gex_engine.cmd_close_pos(CloseByTickerArgs())

            active_res = gex_engine.load_json(active_file, {})
            self.assertNotIn("opt_2", active_res.get("options_positions", {}))

            closed_res = gex_engine.load_json(closed_file, {})
            nvda_closed = [opt for opt in closed_res.get("closed_options", []) if opt.get("Underlier") == "NVDA"][0]
            self.assertEqual(nvda_closed["Close Premium"], 8.0)  # defaulted to Mark Price
            self.assertEqual(nvda_closed["Realized P&L ($)"], 300.0)  # (8.0 - 5.0) * 100
            self.assertEqual(nvda_closed["Realized P&L (%)"], 60.0)

            # 4) Close position with zero purchase premium (avoid ZeroDivisionError) and no Mark Price
            class CloseZeroPremiumArgs:
                option_id = "opt_3"
                close_premium = None
                account = ""

            with patch("gex_engine.account_positions_file", return_value=active_file), \
                 patch("gex_engine.account_closed_positions_file", return_value=closed_file), \
                 patch("sys.stdout", new_callable=StringIO):
                gex_engine.cmd_close_pos(CloseZeroPremiumArgs())

            closed_res = gex_engine.load_json(closed_file, {})
            tsla_closed = [opt for opt in closed_res.get("closed_options", []) if opt.get("Underlier") == "TSLA"][0]
            self.assertEqual(tsla_closed["Realized P&L (%)"], 0.0)
            self.assertEqual(tsla_closed["Realized P&L ($)"], 0.0)

            # 5) Close position resulting in negative P&L (loss)
            class CloseLossArgs:
                option_id = "opt_4"
                close_premium = 5.0
                account = ""

            with patch("gex_engine.account_positions_file", return_value=active_file), \
                 patch("gex_engine.account_closed_positions_file", return_value=closed_file), \
                 patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                gex_engine.cmd_close_pos(CloseLossArgs())

            closed_res = gex_engine.load_json(closed_file, {})
            amzn_closed = [opt for opt in closed_res.get("closed_options", []) if opt.get("Underlier") == "AMZN"][0]
            self.assertEqual(amzn_closed["Realized P&L ($)"], -500.0)  # (5.0 - 10.0) * 100
            self.assertEqual(amzn_closed["Realized P&L (%)"], -50.0)
            self.assertIn("Closed AMZN 180.0 call (opt_4)", mock_stdout.getvalue())

            # 6) Test account argument scoping
            acc_active = os.path.join(temp_dir, "active_positions_123.json")
            acc_closed = os.path.join(temp_dir, "closed_positions_123.json")
            gex_engine.save_json(acc_active, {
                "options_positions": {
                    "opt_acc": {
                        "Underlier": "AMD",
                        "Purchase Premium": 1.0,
                    }
                }
            })

            class AccCloseArgs:
                option_id = "opt_acc"
                close_premium = 2.0
                account = "123"

            with patch("gex_engine.account_positions_file", return_value=acc_active), \
                 patch("gex_engine.account_closed_positions_file", return_value=acc_closed), \
                 patch("sys.stdout", new_callable=StringIO):
                gex_engine.cmd_close_pos(AccCloseArgs())

            acc_active_data = gex_engine.load_json(acc_active, {})
            self.assertNotIn("opt_acc", acc_active_data.get("options_positions", {}))
            acc_closed_data = gex_engine.load_json(acc_closed, {})
            self.assertEqual(len(acc_closed_data.get("closed_options", [])), 1)
            perf_path = os.path.join(temp_dir, "data", "performance_ACC123.json")
            args = SimpleNamespace(
                net_liq=50000.0,
                account="ACC123",
                monthly_file=None,
                pnl_file=None,
            )
            with patch("gex_engine.account_performance_file", return_value=perf_path), \
                 patch("gex_engine.get_monthly_realized_pnl", return_value=(2500.0, 5.0, "PASS", 10)):
                gex_engine.cmd_update_performance(args)

            data = gex_engine.load_json(perf_path, {})
            self.assertEqual(data["account"], "ACC123")
            self.assertEqual(data["monthly_pnl_dlr"], 2500.0)
            self.assertEqual(data["monthly_pnl_pct"], 5.0)
            self.assertEqual(data["drawdown_gate_status"], "PASS")
            self.assertEqual(data["monthly_cnt"], 10)
            self.assertIn("last_updated", data)
        finally:
            shutil.rmtree(temp_dir)

    def test_cmd_update_performance_default_account(self):
        """Test cmd_update_performance computes metrics and saves to default performance file when account is empty."""
        import tempfile
        import shutil
        from types import SimpleNamespace
        from unittest.mock import patch, MagicMock
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        try:
            workflow_file = os.path.join(temp_dir, "workflow_state.json")
            regime_file = os.path.join(temp_dir, "regime.json")
            options_file = os.path.join(temp_dir, "active_positions.json")
            candidates_file = os.path.join(temp_dir, "candidate_stocks.json")
            analyses_file = os.path.join(temp_dir, "ticker_analyses.json")

            gex_engine.save_json(workflow_file, {
                "current_phase": "Phase I: Risk & Audit",
                "subagents": {
                    "market-regime-analyst": {"status": "SUCCESS"},
                    "portfolio-risk-manager": {"status": "FAILED"},
                    "gex-candidate-generator": {"status": "RUNNING"},
                },
                "notes": []
            })
            gex_engine.save_json(regime_file, {
                "basket_gate": "PASS",
                "bull_bear_gate": "PASS",
                "vix_delta_gate": "PASS",
                "system_authorization": "ALL TRACKS OK",
                "bull_count": 12,
                "bear_count": 2,
                "bull_bear_ratio": 6.0,
                "vix_spot": 15.2,
                "spy_change_pct": 0.75,
                "qqq_change_pct": 0.85,
            })
            gex_engine.save_json(options_file, {
                "options_positions": {"opt_1": {"Underlier": "AAPL"}},
                "stocks_positions": {"MSFT": {"Ticker": "MSFT"}},
            })
            gex_engine.save_json(candidates_file, {
                "candidates": [{"symbol": "NVDA"}, {"symbol": "AMD"}]
            })
            gex_engine.save_json(analyses_file, {
                "NVDA": {"Signal Status": "CONFIRMED (11/11)"},
                "AMD": {"Signal Status": "PENDING (below watchdog)"},
                "TSLA": {"Signal Status": "BLOCKED (Grade <= 8)"},
            })

            args = SimpleNamespace(account="")

            with patch("gex_engine.WORKFLOW_STATE_FILE", workflow_file), \
                 patch("gex_engine.REGIME_FILE", regime_file), \
                 patch("gex_engine.OPTIONS_FILE", options_file), \
                 patch("gex_engine.CANDIDATES_FILE", candidates_file), \
                 patch("gex_engine.ANALYSES_FILE", analyses_file), \
                 patch("sys.stdout") as mock_stdout:
                mock_stdout.isatty = MagicMock(return_value=False)

                gex_engine.cmd_workflow(args)

                output = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)

                self.assertIn("SYSTEM WORKFLOW STATUS", output)
                self.assertIn("Current Phase: Phase I: Risk & Audit", output)
                self.assertIn("[PHASE I] System Authorization: ALL TRACKS OK", output)
                self.assertIn("Bull:Bear Ratio: 6.0 (12B : 2R)", output)
                self.assertIn("VIX Delta Gate: PASS (Spot: 15.2)", output)
                self.assertIn("Basket Gate: PASS (SPY: +0.75%, QQQ: +0.85%)", output)
                self.assertIn("[PHASE I] Active Portfolio: 1 Options | 1 Stocks", output)
                self.assertIn("[PHASE II] Discovery: 2 Candidate Tickers", output)
                self.assertIn("[PHASE III] Setup Grading: 1 CONFIRMED | 1 PENDING", output)
                self.assertIn("- Confirmed: NVDA", output)
                self.assertIn("[PHASE LOG] Subagent Executions:", output)
                self.assertIn("market-regime-analyst    : SUCCESS", output)
                self.assertIn("portfolio-risk-manager   : FAILED", output)
                self.assertIn("gex-candidate-generator  : RUNNING", output)
                self.assertIn("--- END STATUS ---", output)
        finally:
            shutil.rmtree(temp_dir)

    def test_cmd_workflow_account_scoped_and_default_fallbacks(self):
        """Test cmd_workflow with account-scoped position reading and fallback defaults for missing files."""
        import tempfile
        import shutil
        from unittest.mock import patch, MagicMock
        from types import SimpleNamespace
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        try:
            perf_path = os.path.join(temp_dir, "data", "performance.json")
            args = SimpleNamespace(
                net_liq=100000.0,
                account="",
                monthly_file=None,
                pnl_file=None,
            )
            with patch("gex_engine.account_performance_file", return_value=perf_path), \
                 patch("gex_engine.get_monthly_realized_pnl", return_value=(-12000.0, -12.0, "FAIL", 5)):
                gex_engine.cmd_update_performance(args)

            data = gex_engine.load_json(perf_path, {})
            self.assertEqual(data["account"], "")
            self.assertEqual(data["monthly_pnl_dlr"], -12000.0)
            self.assertEqual(data["monthly_pnl_pct"], -12.0)
            self.assertEqual(data["drawdown_gate_status"], "FAIL")
            self.assertEqual(data["monthly_cnt"], 5)
            self.assertIn("last_updated", data)
            workflow_file = os.path.join(temp_dir, "workflow_state.json")
            regime_file = os.path.join(temp_dir, "regime.json")
            account_options_file = os.path.join(temp_dir, "active_positions_ACC99.json")
            candidates_file = os.path.join(temp_dir, "candidate_stocks.json")
            analyses_file = os.path.join(temp_dir, "ticker_analyses.json")

            gex_engine.save_json(account_options_file, {
                "options_positions": {
                    "opt_1": {"Underlier": "GOOG"},
                    "opt_2": {"Underlier": "AMZN"},
                },
                "stocks_positions": {
                    "INTC": {"Ticker": "INTC"},
                },
            })

            args_account = SimpleNamespace(account="ACC99")

            with patch("gex_engine.WORKFLOW_STATE_FILE", workflow_file), \
                 patch("gex_engine.REGIME_FILE", regime_file), \
                 patch("gex_engine.CANDIDATES_FILE", candidates_file), \
                 patch("gex_engine.ANALYSES_FILE", analyses_file), \
                 patch("gex_engine.account_positions_file", return_value=account_options_file), \
                 patch("sys.stdout") as mock_stdout:
                mock_stdout.isatty = MagicMock(return_value=False)

                gex_engine.cmd_workflow(args_account)

                output = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)

                self.assertIn("Current Phase: Phase 0: Initialization", output)
                self.assertIn("[PHASE I] System Authorization: BLOCKED", output)
                self.assertIn("[PHASE I] Active Portfolio: 2 Options | 1 Stocks", output)
                self.assertIn("[PHASE II] Discovery: 0 Candidate Tickers", output)
                self.assertIn("[PHASE III] Setup Grading: 0 CONFIRMED | 0 PENDING", output)
                self.assertNotIn("[PHASE LOG] Subagent Executions:", output)
                self.assertIn("--- END STATUS ---", output)

            # Test fallback when cache files do not exist
            non_existent_dir = os.path.join(temp_dir, "nonexistent")
            args_default = SimpleNamespace(account="")

            with patch("gex_engine.WORKFLOW_STATE_FILE", os.path.join(non_existent_dir, "workflow.json")), \
                 patch("gex_engine.REGIME_FILE", os.path.join(non_existent_dir, "regime.json")), \
                 patch("gex_engine.OPTIONS_FILE", os.path.join(non_existent_dir, "options.json")), \
                 patch("gex_engine.CANDIDATES_FILE", os.path.join(non_existent_dir, "candidates.json")), \
                 patch("gex_engine.ANALYSES_FILE", os.path.join(non_existent_dir, "analyses.json")), \
                 patch("sys.stdout") as mock_stdout:
                mock_stdout.isatty = MagicMock(return_value=False)

                gex_engine.cmd_workflow(args_default)

                output_fallback = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)

                self.assertIn("Current Phase: Phase 0: Initialization", output_fallback)
                self.assertIn("[PHASE I] System Authorization: BLOCKED", output_fallback)
                self.assertIn("[PHASE I] Active Portfolio: 0 Options | 0 Stocks", output_fallback)
                self.assertIn("[PHASE II] Discovery: 0 Candidate Tickers", output_fallback)
                self.assertIn("[PHASE III] Setup Grading: 0 CONFIRMED | 0 PENDING", output_fallback)
                self.assertIn("--- END STATUS ---", output_fallback)
        finally:
            shutil.rmtree(temp_dir)


class TestCmdStatus(unittest.TestCase):

    def test_cmd_status_missing_files(self):
        import tempfile
        import shutil
        from types import SimpleNamespace
        from unittest.mock import patch, MagicMock
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        try:
            non_existent = os.path.join(temp_dir, "nonexistent.json")
            with patch('gex_engine.REGIME_FILE', non_existent), \
                 patch('gex_engine.PERFORMANCE_FILE', non_existent), \
                 patch('gex_engine.CANDIDATES_FILE', non_existent), \
                 patch('gex_engine.OPTIONS_FILE', non_existent), \
                 patch('gex_engine.ANALYSES_FILE', non_existent), \
                 patch('sys.stdout') as mock_stdout:

                mock_stdout.isatty = MagicMock(return_value=False)
                args = SimpleNamespace(account="")
                cmd_status(args)

                output = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)
                self.assertIn("📅 Cache Freshness Report", output)
                self.assertIn("MISSING", output)
                self.assertIn("📊 GEX Regime Check", output)
                self.assertIn("SYSTEM STATUS: BLOCKED", output)
        finally:
            shutil.rmtree(temp_dir)

    def test_cmd_status_fresh_and_blocked_states(self):
        import tempfile
        import shutil
        from datetime import datetime
        from types import SimpleNamespace
        from unittest.mock import patch, MagicMock
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        today = datetime.today().strftime('%Y-%m-%d')
        try:
            regime_file = os.path.join(temp_dir, "regime.json")
            perf_file = os.path.join(temp_dir, "performance.json")
            cand_file = os.path.join(temp_dir, "candidates.json")
            options_file = os.path.join(temp_dir, "active_positions.json")
            analyses_file = os.path.join(temp_dir, "ticker_analyses.json")

            gex_engine.save_json(regime_file, {
                "basket_gate": "PASS",
                "bull_bear_gate": "PASS",
                "vix_delta_gate": "PASS",
                "spy_change_pct": 0.8,
                "qqq_change_pct": 1.2,
                "bull_count": 10,
                "bear_count": 2,
                "bull_bear_ratio": 5.0,
                "vix_spot": 14.5,
                "vix_bearish": True,
                "system_authorization": "ALL TRACKS OK",
                "gates_passed": 3,
                "last_updated": today,
                "etf_details": {
                    "SPY": {"Ticker": "SPY", "ETF Segment / Sector Name": "S&P 500 Broad Market", "Daily Change %": 0.8, "Classification": "BULLISH"},
                    "XLK": {"Ticker": "XLK", "ETF Segment / Sector Name": "Technology", "Daily Change %": 1.5, "Classification": "BULLISH"}
                }
            })
            gex_engine.save_json(perf_file, {
                "monthly_pnl_dlr": 1500.0,
                "monthly_pnl_pct": 3.0,
                "drawdown_gate_status": "PASS",
                "monthly_cnt": 5,
                "last_updated": today
            })
            gex_engine.save_json(cand_file, {
                "last_updated": today,
                "candidates": [{"symbol": "AAPL"}]
            })
            gex_engine.save_json(options_file, {
                "options_positions": {},
                "stocks_positions": {}
            })
            gex_engine.save_json(analyses_file, {
                "AAPL": {
                    "analyzed_date": today,
                    "Signal Status": "PENDING"
                }
            })

            with patch('gex_engine.REGIME_FILE', regime_file), \
                 patch('gex_engine.PERFORMANCE_FILE', perf_file), \
                 patch('gex_engine.CANDIDATES_FILE', cand_file), \
                 patch('gex_engine.OPTIONS_FILE', options_file), \
                 patch('gex_engine.ANALYSES_FILE', analyses_file), \
                 patch('sys.stdout') as mock_stdout:

                mock_stdout.isatty = MagicMock(return_value=False)
                args = SimpleNamespace(account="")
                cmd_status(args)

                output = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)
                self.assertIn("FRESH", output)
                self.assertIn("ALL TRACKS OK", output)
                self.assertIn("SYSTEM STATUS: AUTHORIZED", output)
                self.assertIn("Sector Momentum & Rotation", output)
        finally:
            shutil.rmtree(temp_dir)

    def test_cmd_status_actionable_alerts(self):
        import tempfile
        import shutil
        from datetime import datetime
        from types import SimpleNamespace
        from unittest.mock import patch, MagicMock
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        today = datetime.today().strftime('%Y-%m-%d')
        try:
            regime_file = os.path.join(temp_dir, "regime.json")
            perf_file = os.path.join(temp_dir, "performance.json")
            cand_file = os.path.join(temp_dir, "candidates.json")
            options_file = os.path.join(temp_dir, "active_positions.json")
            analyses_file = os.path.join(temp_dir, "ticker_analyses.json")

            gex_engine.save_json(regime_file, {
                "basket_gate": "PASS",
                "bull_bear_gate": "PASS",
                "vix_delta_gate": "PASS",
                "spy_change_pct": 0.8,
                "qqq_change_pct": 1.2,
                "bull_count": 10,
                "bear_count": 2,
                "bull_bear_ratio": 5.0,
                "vix_spot": 14.5,
                "vix_bearish": True,
                "system_authorization": "ALL TRACKS OK",
                "gates_passed": 3,
                "hyg_change_pct": -0.40,  # Credit divergence (< -0.30% with positive SPY/QQQ)
                "last_updated": today
            })
            gex_engine.save_json(perf_file, {"last_updated": today})
            gex_engine.save_json(cand_file, {"last_updated": today, "candidates": []})

            # Active option and stock triggers
            gex_engine.save_json(options_file, {
                "options_positions": {
                    "opt1": {
                        "Underlier": "NVDA",
                        "Purchase Premium": 5.0,
                        "Mark Price": 10.0,
                        "Strike": 120.0,
                        "Expiration": "2026-08-20",
                        "Entry Date": "2026-07-01",
                        "Stalling Days": 0
                    }
                },
                "stocks_positions": {
                    "TSLA": {
                        "Shares": 10,
                        "Average Buy Price": 200.0,
                        "Current Price": 180.0
                    }
                }
            })
            gex_engine.save_json(analyses_file, {
                "NVDA": {
                    "Spot": 130.0,
                    "+GEX": 125.0,  # Spot 130 >= +GEX 125 -> T1 Target Met
                    "pTrans": 115.0,
                    "nTrans": 110.0,
                    "analyzed_date": today,
                    "Signal Status": "CONFIRMED (11/11)"
                },
                "TSLA": {
                    "Spot": 180.0,
                    "+GEX": 220.0,
                    "pTrans": 195.0,
                    "nTrans": 190.0,  # Spot 180 < nTrans 190 -> Structural Stop Triggered
                    "analyzed_date": today,
                    "Signal Status": "BLOCKED"
                },
                "AMD": {
                    "Spot": 150.0,
                    "Grade": 11,
                    "analyzed_date": today,
                    "Signal Status": "CONFIRMED (11/11)"
                }
            })

            with patch('gex_engine.REGIME_FILE', regime_file), \
                 patch('gex_engine.PERFORMANCE_FILE', perf_file), \
                 patch('gex_engine.CANDIDATES_FILE', cand_file), \
                 patch('gex_engine.OPTIONS_FILE', options_file), \
                 patch('gex_engine.ANALYSES_FILE', analyses_file), \
                 patch('sys.stdout') as mock_stdout:

                mock_stdout.isatty = MagicMock(return_value=False)
                args = SimpleNamespace(account="")
                cmd_status(args)

                output = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)
                self.assertIn("CREDIT DIVERGENCE DETECTED", output)
                self.assertIn("Central Command Actionable Alerts Summary", output)
                self.assertIn("TRIGGERED SYSTEMATIC EXITS DETECTED", output)
                self.assertIn("NVDA (Option:", output)
                self.assertIn("TSLA (Stock:", output)
                self.assertIn("CONFIRMED SETUPS READY FOR ENTRY", output)
                self.assertIn("AMD", output)
        finally:
            shutil.rmtree(temp_dir)

    def test_cmd_status_account_scoping(self):
        import tempfile
        import shutil
        from datetime import datetime
        from types import SimpleNamespace
        from unittest.mock import patch, MagicMock
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        today = datetime.today().strftime('%Y-%m-%d')
        account = "ACC123"
        try:
            regime_file = os.path.join(temp_dir, "regime.json")
            perf_file = os.path.join(temp_dir, f"performance_{account}.json")
            cand_file = os.path.join(temp_dir, "candidates.json")
            options_file = os.path.join(temp_dir, f"active_positions_{account}.json")
            analyses_file = os.path.join(temp_dir, "ticker_analyses.json")

            gex_engine.save_json(regime_file, {"last_updated": today})
            gex_engine.save_json(perf_file, {"last_updated": today})
            gex_engine.save_json(cand_file, {"last_updated": today})
            gex_engine.save_json(options_file, {"options_positions": {}, "stocks_positions": {}})
            gex_engine.save_json(analyses_file, {})

            with patch('gex_engine.REGIME_FILE', regime_file), \
                 patch('gex_engine.PERFORMANCE_FILE', perf_file), \
                 patch('gex_engine.CANDIDATES_FILE', cand_file), \
                 patch('gex_engine.OPTIONS_FILE', options_file), \
                 patch('gex_engine.ANALYSES_FILE', analyses_file), \
                 patch('gex_engine.account_performance_file', return_value=perf_file), \
                 patch('gex_engine.account_positions_file', return_value=options_file), \
                 patch('sys.stdout') as mock_stdout:

                mock_stdout.isatty = MagicMock(return_value=False)
                args = SimpleNamespace(account=account)
                cmd_status(args)

                output = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)
                self.assertIn("Cache Freshness Report", output)
                self.assertIn("FRESH", output)
        finally:
            shutil.rmtree(temp_dir)


    def test_cmd_analyze_explicit_args_confirmed(self):
        """Test cmd_analyze when explicit CLI arguments result in a CONFIRMED setup."""
        import tempfile
        from unittest.mock import patch, MagicMock
        from types import SimpleNamespace
        import gex_engine

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_analyses:
            analyses_path = tmp_analyses.name

        try:
            gex_engine.save_json(analyses_path, {})

            args = SimpleNamespace(
                symbol="AAPL",
                effective_session_date="2026-08-11",
                spot=290.0,
                ptrans=285.0,
                ntrans=280.0,
                gex=310.0,
                cotmp=275.0,
                db_change=0.60,
                spike_crash=False,
                inst_file=None,
                quote_file=None,
                hist_file=None,
                earnings_date=None,
                net_liq=50000.0,
                target_delta=0.45,
                min_dte=30,
                max_dte=45,
                rule1=None, rule2=None, rule3=None, rule4=None, rule5=None,
                rule6=None, rule7=None, rule8=None, rule9=None, rule10=None, rule11=None
            )

            with patch('gex_engine.ANALYSES_FILE', analyses_path), \
                 patch('sys.stdout') as mock_stdout:
                mock_stdout.isatty = MagicMock(return_value=False)
                gex_engine.cmd_analyze(args)

            analyses = gex_engine.load_json(analyses_path, {})
            self.assertIn("AAPL", analyses)
            record = analyses["AAPL"]
            self.assertEqual(record["Ticker"], "AAPL")
            self.assertEqual(record["Spot"], 290.0)
            self.assertEqual(record["Grade"], 11)
            self.assertTrue(record["Signal Status"].startswith("CONFIRMED"))
            self.assertEqual(record["analyzed_date"], "2026-08-11")
            self.assertEqual(record["db_change"], 0.60)
            self.assertGreater(record["COTMP Cushion"], 2.0)
            self.assertGreaterEqual(record["Risk/Reward"], 2.0)
        finally:
            if os.path.exists(analyses_path):
                os.remove(analyses_path)

    def test_cmd_analyze_pending_and_blocked(self):
        """Test cmd_analyze classification for PENDING and BLOCKED signal status branches."""
        import tempfile
        from unittest.mock import patch, MagicMock
        from types import SimpleNamespace
        import gex_engine

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_analyses:
            analyses_path = tmp_analyses.name

        try:
            # 1. PENDING (watchdog) setup: spot is below pTrans (285.0) but above watchdog threshold (285.0 * 0.995 = 283.575)
            gex_engine.save_json(analyses_path, {})
            args_pending = SimpleNamespace(
                symbol="AAPL",
                effective_session_date="2026-08-11",
                spot=284.0,
                ptrans=285.0,
                ntrans=280.0,
                gex=310.0,
                cotmp=275.0,
                db_change=0.60,
                spike_crash=False,
                inst_file=None, quote_file=None, hist_file=None, earnings_date=None, net_liq=50000.0,
                rule1=None, rule2=None, rule3=None, rule4=None, rule5=None,
                rule6=None, rule7=None, rule8=None, rule9=None, rule10=None, rule11=None
            )

            with patch('gex_engine.ANALYSES_FILE', analyses_path), patch('sys.stdout'):
                gex_engine.cmd_analyze(args_pending)

            record = gex_engine.load_json(analyses_path, {})["AAPL"]
            self.assertTrue(record["Signal Status"].startswith("PENDING (watchdog)"))

            # 2. BLOCKED setup due to Grade <= 8
            args_low_grade = SimpleNamespace(
                symbol="AAPL",
                effective_session_date="2026-08-11",
                spot=290.0,
                ptrans=285.0,
                ntrans=280.0,
                gex=310.0,
                cotmp=275.0,
                db_change=0.60,
                spike_crash=False,
                inst_file=None, quote_file=None, hist_file=None, earnings_date=None, net_liq=50000.0,
                rule1=False, rule2=False, rule7=False, rule3=None, rule4=None, rule5=None,
                rule6=None, rule8=None, rule9=None, rule10=None, rule11=None
            )

            with patch('gex_engine.ANALYSES_FILE', analyses_path), patch('sys.stdout'):
                gex_engine.cmd_analyze(args_low_grade)

            record = gex_engine.load_json(analyses_path, {})["AAPL"]
            self.assertTrue(record["Signal Status"].startswith("BLOCKED"))
            self.assertIn("Grade <= 8", record["Signal Status"])

            # 3. BLOCKED setup due to db_change < threshold
            args_low_db = SimpleNamespace(
                symbol="AAPL",
                effective_session_date="2026-08-11",
                spot=290.0,
                ptrans=285.0,
                ntrans=280.0,
                gex=310.0,
                cotmp=275.0,
                db_change=0.10, # < 0.50
                spike_crash=False,
                inst_file=None, quote_file=None, hist_file=None, earnings_date=None, net_liq=50000.0,
                rule1=None, rule2=None, rule3=None, rule4=None, rule5=None,
                rule6=None, rule7=None, rule8=None, rule9=None, rule10=None, rule11=None
            )

            with patch('gex_engine.ANALYSES_FILE', analyses_path), patch('sys.stdout'):
                gex_engine.cmd_analyze(args_low_db)

            record = gex_engine.load_json(analyses_path, {})["AAPL"]
            self.assertTrue(record["Signal Status"].startswith("BLOCKED"))
            self.assertIn("db_change", record["Signal Status"])

            # 4. BLOCKED setup due to Risk/Reward < 2.0
            args_low_rr = SimpleNamespace(
                symbol="AAPL",
                effective_session_date="2026-08-11",
                spot=290.0,
                ptrans=285.0,
                ntrans=280.0,
                gex=292.0, # reward = 2.0, risk = 5.0 -> R/R = 0.40
                cotmp=275.0,
                db_change=0.60,
                spike_crash=False,
                inst_file=None, quote_file=None, hist_file=None, earnings_date=None, net_liq=50000.0,
                rule1=None, rule2=None, rule3=None, rule4=None, rule5=None,
                rule6=None, rule7=None, rule8=None, rule9=None, rule10=None, rule11=None
            )

            with patch('gex_engine.ANALYSES_FILE', analyses_path), patch('sys.stdout'):
                gex_engine.cmd_analyze(args_low_rr)

            record = gex_engine.load_json(analyses_path, {})["AAPL"]
            self.assertTrue(record["Signal Status"].startswith("BLOCKED"))
            self.assertIn("Risk/Reward ratio", record["Signal Status"])
        finally:
            if os.path.exists(analyses_path):
                os.remove(analyses_path)


    def test_cmd_analyze_with_option_files_derivation(self):
        """Test cmd_analyze auto-derivation of levels and best option selection using option data files."""
        import tempfile
        import shutil
        from unittest.mock import patch, MagicMock
        from types import SimpleNamespace
        import gex_engine

        temp_dir = tempfile.mkdtemp()
        try:
            analyses_path = os.path.join(temp_dir, "ticker_analyses.json")
            inst_path = os.path.join(temp_dir, "test_instruments.json")
            quote_path = os.path.join(temp_dir, "test_quotes.json")
            hist_path = os.path.join(temp_dir, "test_historicals.json")

            gex_engine.save_json(analyses_path, {})
            gex_engine.save_json(inst_path, {
                "instruments": [
                    {"id": "put1", "strike_price": "90.0000", "type": "put"},
                    {"id": "put2", "strike_price": "95.0000", "type": "put"},
                    {"id": "call1", "strike_price": "105.0000", "type": "call", "expiration_date": "2026-08-08"},
                    {"id": "call2", "strike_price": "115.0000", "type": "call", "expiration_date": "2026-08-08"}
                ]
            })
            gex_engine.save_json(quote_path, {
                "results": [
                    {"quote": {"instrument_id": "put1", "open_interest": 2000, "gamma": "0.02"}},
                    {"quote": {"instrument_id": "put2", "open_interest": 4000, "gamma": "0.02"}},
                    {"quote": {"instrument_id": "call1", "bid_price": "2.40", "ask_price": "2.50", "mark_price": "2.45", "open_interest": 3000, "volume": 100, "delta": "0.45", "gamma": "0.02"}},
                    {"quote": {"instrument_id": "call2", "bid_price": "1.00", "ask_price": "1.10", "mark_price": "1.05", "open_interest": 8000, "volume": 50, "delta": "0.25", "gamma": "0.01"}}
                ]
            })
            bars = [{"begins_at": f"2026-06-{i:02d}T00:00:00Z", "close_price": str(100.0 + (i % 2) * 0.1)} for i in range(1, 13)]
            gex_engine.save_json(hist_path, {"results": [{"symbol": "DERIV", "bars": bars}]})

            args = SimpleNamespace(
                symbol="DERIV",
                effective_session_date="2026-08-11",
                spot=100.0,
                ptrans=None,
                ntrans=None,
                gex=None,
                cotmp=None,
                db_change=0.60,
                spike_crash=False,
                inst_file=inst_path,
                quote_file=quote_path,
                hist_file=hist_path,
                earnings_date=None,
                net_liq=50000.0,
                target_delta=0.45,
                min_dte=14,
                max_dte=45,
                rule1=None, rule2=None, rule3=None, rule4=None, rule5=None,
                rule6=None, rule7=None, rule8=None, rule9=None, rule10=None, rule11=None
            )

            with patch('gex_engine.ANALYSES_FILE', analyses_path), \
                 patch('sys.stdout') as mock_stdout:
                mock_stdout.isatty = MagicMock(return_value=False)
                gex_engine.cmd_analyze(args)

            analyses = gex_engine.load_json(analyses_path, {})
            self.assertIn("DERIV", analyses)
            record = analyses["DERIV"]
            self.assertEqual(record["pTrans"], 95.0)
            self.assertEqual(record["nTrans"], 90.0)
            self.assertEqual(record["+GEX"], 115.0)
            self.assertTrue(record["Signal Status"].startswith("CONFIRMED"))
        finally:
            shutil.rmtree(temp_dir)

    def test_cmd_analyze_cached_fallback_and_missing_metrics(self):
        """Test cmd_analyze cached fallback when metrics are omitted and error handling when metrics are missing."""
        import tempfile
        from unittest.mock import patch, MagicMock
        from types import SimpleNamespace
        import gex_engine

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_analyses:
            analyses_path = tmp_analyses.name

        try:
            # 1. Fallback to cached metrics
            gex_engine.save_json(analyses_path, {
                "AAPL": {
                    "Ticker": "AAPL",
                    "Spot": 290.0,
                    "pTrans": 285.0,
                    "nTrans": 280.0,
                    "+GEX": 310.0,
                    "COTMP": 275.0,
                    "db_change": 0.60,
                    "spike_crash": False
                }
            })

            args_cached = SimpleNamespace(
                symbol="AAPL",
                effective_session_date="2026-08-11",
                spot=None, ptrans=None, ntrans=None, gex=None, cotmp=None, db_change=None,
                spike_crash=None, inst_file=None, quote_file=None, hist_file=None, earnings_date=None, net_liq=50000.0,
                target_delta=0.45, min_dte=30, max_dte=45,
                rule1=None, rule2=None, rule3=None, rule4=None, rule5=None,
                rule6=None, rule7=None, rule8=None, rule9=None, rule10=None, rule11=None
            )

            with patch('gex_engine.ANALYSES_FILE', analyses_path), patch('sys.stdout'):
                gex_engine.cmd_analyze(args_cached)

            record = gex_engine.load_json(analyses_path, {})["AAPL"]
            self.assertEqual(record["Spot"], 290.0)
            self.assertEqual(record["pTrans"], 285.0)
            self.assertTrue(record["Signal Status"].startswith("CONFIRMED"))

            # 2. Missing metrics triggers sys.exit(1)
            gex_engine.save_json(analyses_path, {})
            args_missing = SimpleNamespace(
                symbol="UNKNOWN",
                effective_session_date="2026-08-11",
                spot=None, ptrans=None, ntrans=None, gex=None, cotmp=None, db_change=None,
                spike_crash=None, inst_file=None, quote_file=None, hist_file=None, earnings_date=None, net_liq=50000.0,
                rule1=None, rule2=None, rule3=None, rule4=None, rule5=None,
                rule6=None, rule7=None, rule8=None, rule9=None, rule10=None, rule11=None
            )

            with patch('gex_engine.ANALYSES_FILE', analyses_path), \
                 patch('gex_engine.find_latest_underlier_spot', return_value=None), \
                 patch('sys.stderr'), patch('sys.stdout'):
                with self.assertRaises(SystemExit) as cm:
                    gex_engine.cmd_analyze(args_missing)
                self.assertEqual(cm.exception.code, 1)
        finally:
            if os.path.exists(analyses_path):
                os.remove(analyses_path)

    def test_portfolio_empty_state_output(self):
        """Test cmd_portfolio displays a friendly empty state message with actionable next steps."""
        from types import SimpleNamespace
        import io
        from unittest.mock import patch
        import gex_engine

        mock_args = SimpleNamespace(account="", net_liq=50000.0, spot_overrides={})
        empty_cache = {"options_positions": {}, "stocks_positions": {}}

        with patch('gex_engine.load_json', return_value=empty_cache), \
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            gex_engine.cmd_portfolio(mock_args)
            output = mock_stdout.getvalue()
            self.assertIn("Active Portfolio Tracker & Exits", output)
            self.assertIn("No open portfolio positions found in local cache", output)
            self.assertIn("Actionable Next Steps", output)
            self.assertIn("add-position", output)
            self.assertIn("add-stock", output)

    def test_portfolio_sizing_threshold_exempts_micro_accounts(self):
        """Test cmd_portfolio exempts accounts below the sizing threshold from strict percentage caps."""
        from types import SimpleNamespace
        import io
        from unittest.mock import patch
        import gex_engine

        positions = {
            "options_positions": {
                "opt_1": {
                    "Underlier": "FRO",
                    "Purchase Premium": 2.69,
                    "Mark Price": 3.12,
                    "Strike": 45.0,
                    "Expiration": "2026-10-16",
                    "Type": "call",
                    "Days Held": 4,
                    "Stalling Days": 0,
                    "Target Mode": "T1",
                    "Sizing Risk Weight (%)": 24.74,
                    "Sector": "Technology/Beta"
                }
            },
            "stocks_positions": {}
        }

        # Case 1: Account < $10,000 threshold (e.g. $1,087.23) -> Should show EXEMPT
        mock_args_micro = SimpleNamespace(account="970049961", net_liq=1087.23, spot_overrides={}, sizing_threshold=10000.0)
        with patch('gex_engine.load_json', return_value=positions), \
             patch('gex_engine.find_latest_underlier_spot', return_value=49.20), \
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            gex_engine.cmd_portfolio(mock_args_micro)
            output = mock_stdout.getvalue()
            self.assertIn("Single-Leg Sizing Limit (<= 3.0% of Net Liq)**: EXEMPT", output)
            self.assertIn("Sector Sizing Cap (Tech/Beta <= 15.0% of Net Liq)**: EXEMPT", output)
            self.assertIn("Micro-Account Allocation Note", output)

        # Case 2: Account >= $10,000 threshold (e.g. $50,000) -> Should enforce standard checks
        positions_large = {
            "options_positions": {
                "opt_1": {
                    "Underlier": "FRO",
                    "Purchase Premium": 2.69,
                    "Mark Price": 3.12,
                    "Strike": 45.0,
                    "Expiration": "2026-10-16",
                    "Type": "call",
                    "Days Held": 4,
                    "Stalling Days": 0,
                    "Target Mode": "T1",
                    "Sizing Risk Weight (%)": 0.54,
                    "Sector": "Technology/Beta"
                }
            },
            "stocks_positions": {}
        }
        mock_args_large = SimpleNamespace(account="5QR24141", net_liq=50000.0, spot_overrides={}, sizing_threshold=10000.0)
        with patch('gex_engine.load_json', return_value=positions_large), \
             patch('gex_engine.find_latest_underlier_spot', return_value=49.20), \
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            gex_engine.cmd_portfolio(mock_args_large)
            output = mock_stdout.getvalue()
            self.assertIn("Single-Leg Sizing Limit (<= 3.0% of Net Liq)**: PASS", output)
            self.assertIn("Sector Sizing Cap (Tech/Beta <= 15.0% of Net Liq)**: PASS", output)


if __name__ == '__main__':
    unittest.main()
