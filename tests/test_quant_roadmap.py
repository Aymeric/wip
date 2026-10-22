"""
Unit tests for roadmap implementations:
1. Analytical Black-Scholes Gamma calculations and fallback in GEX profile derivation.
2. Effective (DTE-weighted) GEX metrics.
3. Typed domain models (OptionQuote, GexProfile, ScannerCandidate, RegimeStatus).
4. System alert dispatching.
"""

import os
import unittest
from src.gex.quant.greeks import calculate_black_scholes_gamma
from src.gex.core.models import OptionQuote, GexProfile, ScannerCandidate, RegimeStatus
from src.gex_engine import derive_gex_profile, dispatch_system_alert


class TestRoadmapImplementations(unittest.TestCase):

    def test_calculate_black_scholes_gamma_standard(self):
        # Spot 100, Strike 100 (ATM), 30 DTE, 30% IV
        gamma_atm = calculate_black_scholes_gamma(spot=100.0, strike=100.0, dte_days=30.0, iv=0.30)
        self.assertGreater(gamma_atm, 0.0)
        # Deep OTM Strike 140
        gamma_otm = calculate_black_scholes_gamma(spot=100.0, strike=140.0, dte_days=30.0, iv=0.30)
        self.assertGreater(gamma_otm, 0.0)
        # ATM gamma should be strictly greater than deep OTM gamma
        self.assertGreater(gamma_atm, gamma_otm)

    def test_calculate_black_scholes_gamma_edge_cases(self):
        # Invalid / zero parameters should safely return 0.0 without exception
        self.assertEqual(calculate_black_scholes_gamma(spot=0.0, strike=100.0, dte_days=30.0, iv=0.30), 0.0)
        self.assertEqual(calculate_black_scholes_gamma(spot=100.0, strike=0.0, dte_days=30.0, iv=0.30), 0.0)
        self.assertEqual(calculate_black_scholes_gamma(spot=100.0, strike=100.0, dte_days=30.0, iv=0.0), 0.0)
        self.assertEqual(calculate_black_scholes_gamma(spot=-10.0, strike=100.0, dte_days=30.0, iv=0.30), 0.0)

    def test_derive_gex_profile_bs_gamma_fallback(self):
        # Instruments with expiration_date, but quotes have gamma=0.0 or missing gamma
        inst_data = {
            "instruments": [
                {"id": "p1", "strike_price": "95.00", "type": "put", "expiration_date": "2026-11-20"},
                {"id": "c1", "strike_price": "105.00", "type": "call", "expiration_date": "2026-11-20"},
            ]
        }
        quotes_data = {
            "results": [
                {"quote": {"instrument_id": "p1", "open_interest": 1000, "gamma": "0.0", "implied_volatility": "0.35"}},
                {"quote": {"instrument_id": "c1", "open_interest": 1500, "gamma": None, "implied_volatility": "0.35"}},
            ]
        }
        profile = derive_gex_profile(inst_data, quotes_data, spot=100.0)
        # Broker provided 0.0/None for gamma, but analytical fallback should populate total_call_gex and total_put_gex
        self.assertGreater(profile["total_call_gex"], 0.0)
        self.assertGreater(profile["total_put_gex"], 0.0)
        self.assertGreater(profile["effective_call_gex"], 0.0)
        self.assertGreater(profile["effective_put_gex"], 0.0)
        self.assertIn("net_gex", profile)
        self.assertIn("net_effective_gex", profile)

    def test_domain_models_instantiation(self):
        q = OptionQuote(
            instrument_id="opt_123",
            strike=105.0,
            option_type="call",
            expiration_date="2026-11-20",
            bid=2.50,
            ask=2.60,
            mark=2.55,
            open_interest=500,
            gamma=0.025,
            delta=0.45,
            implied_volatility=0.32,
            dte=33,
        )
        self.assertEqual(q.strike, 105.0)
        self.assertEqual(q.option_type, "call")

        cand = ScannerCandidate(
            symbol="NVDA",
            price=135.50,
            chg_pct=2.45,
            iv=0.42,
            relative_options_volume=1.8,
            market_cap=3300000000000.0,
        )
        self.assertEqual(cand.symbol, "NVDA")
        self.assertEqual(cand.source, "scanner")

        reg = RegimeStatus(
            basket_gate="PASS",
            bull_bear_ratio=4.5,
            bull_bear_gate="PASS",
            vix_delta_gate="PASS",
            system_authorization="ALL TRACKS OK",
        )
        self.assertEqual(reg.system_authorization, "ALL TRACKS OK")

        # GexProfile typed model instantiation
        profile = GexProfile(
            spot=100.0,
            total_oi=5000,
            derived_cotmp=105.0,
            derived_ptrans=103.5,
            derived_ntrans=96.5,
            derived_gex=110.0,
            total_call_gex=25000.0,
            total_put_gex=15000.0,
            effective_call_gex=23000.0,
            effective_put_gex=14000.0,
            net_gex=10000.0,
            net_effective_gex=9000.0,
            iv_sum=150.0,
            iv_count=50,
            flip_strikes=[96.5, 103.5],
            put_wall=90.0,
            rule1_derived=True,
            rule2_derived=True,
            rule7_derived=False,
            rule9_derived=True,
            rule10_derived=True,
        )
        self.assertEqual(profile.spot, 100.0)
        self.assertEqual(profile.derived_ptrans, 103.5)
        self.assertEqual(profile.derived_ntrans, 96.5)
        self.assertEqual(profile.flip_strikes, [96.5, 103.5])
        self.assertEqual(profile.put_wall, 90.0)

        # to_dict verification
        d = profile.to_dict()
        self.assertEqual(d["derived_ptrans"], 103.5)
        self.assertEqual(d["flip_strikes"], [96.5, 103.5])
        self.assertEqual(d["put_wall"], 90.0)

        # from_dict verification
        reconstructed = GexProfile.from_dict(d, spot=100.0)
        self.assertEqual(reconstructed.spot, 100.0)
        self.assertEqual(reconstructed.derived_ptrans, 103.5)
        self.assertEqual(reconstructed.derived_ntrans, 96.5)
        self.assertEqual(reconstructed.flip_strikes, [96.5, 103.5])
        self.assertEqual(reconstructed.put_wall, 90.0)
        self.assertEqual(reconstructed.to_dict(), d)

    def test_gex_profile_from_derive_gex_profile_roundtrip(self):
        # Verify seamless integration with derive_gex_profile output dict
        inst_data = {
            "instruments": [
                {"id": "p1", "strike_price": "90.00", "type": "put", "expiration_date": "2026-11-20"},
                {"id": "p2", "strike_price": "95.00", "type": "put", "expiration_date": "2026-11-20"},
                {"id": "c1", "strike_price": "105.00", "type": "call", "expiration_date": "2026-11-20"},
                {"id": "c2", "strike_price": "110.00", "type": "call", "expiration_date": "2026-11-20"},
            ]
        }
        quotes_data = {
            "results": [
                {"quote": {"instrument_id": "p1", "open_interest": 3000, "gamma": "0.03", "implied_volatility": "0.35"}},
                {"quote": {"instrument_id": "p2", "open_interest": 2000, "gamma": "0.04", "implied_volatility": "0.35"}},
                {"quote": {"instrument_id": "c1", "open_interest": 2500, "gamma": "0.04", "implied_volatility": "0.35"}},
                {"quote": {"instrument_id": "c2", "open_interest": 3500, "gamma": "0.03", "implied_volatility": "0.35"}},
            ]
        }
        raw_profile = derive_gex_profile(inst_data, quotes_data, spot=100.0)
        gex_obj = GexProfile.from_dict(raw_profile, spot=100.0)

        self.assertEqual(gex_obj.spot, 100.0)
        self.assertIsNotNone(gex_obj.derived_ptrans)
        self.assertIsNotNone(gex_obj.derived_ntrans)
        self.assertIsNotNone(gex_obj.put_wall)
        self.assertIsInstance(gex_obj.flip_strikes, list)

        # Roundtrip to dict
        roundtrip_dict = gex_obj.to_dict()
        for k in ["derived_ptrans", "derived_ntrans", "put_wall", "flip_strikes", "net_gex"]:
            self.assertEqual(roundtrip_dict[k], raw_profile[k])

    def test_dispatch_system_alert_noop_without_config(self):
        # Should cleanly return False when no webhook or desktop notification is configured
        result = dispatch_system_alert(title="Test Alert", message="Test Message", webhook_url=None)
        self.assertFalse(result)

    def test_compute_exit_rule_state_stops(self):
        from src.gex.risk.stops import compute_exit_rule_state

        # Normal HOLD
        state, action, time_st, dist_ntrans, dist_max = compute_exit_rule_state(
            spot=105.0, purchase_premium=3.0, mark_price=3.5, ptrans=100.0, ntrans=95.0,
            gex_t1=115.0, days_held=2, stalling_counter=0, dte=35
        )
        self.assertEqual(state, "HOLD")
        self.assertEqual(action, "No Action")

        # Stop 1 (Structural Stop: Spot < nTrans)
        state, action, _, _, _ = compute_exit_rule_state(
            spot=94.0, purchase_premium=3.0, mark_price=2.0, ptrans=100.0, ntrans=95.0,
            gex_t1=115.0, days_held=3, stalling_counter=0, dte=30
        )
        self.assertIn("Structural Stop", state)
        self.assertIn("Immediate Exit", action)

        # Stop 3 (Theta Stop: DTE <= 14 days)
        state, action, time_st, _, _ = compute_exit_rule_state(
            spot=104.0, purchase_premium=3.0, mark_price=2.8, ptrans=100.0, ntrans=95.0,
            gex_t1=115.0, days_held=4, stalling_counter=0, dte=12
        )
        self.assertIn("Theta Stop", state)
        self.assertIn("THETA EXHAUSTION", time_st)

        # Stop 5 (Catastrophic Risk Stop: Loss <= -50%)
        state, action, _, _, _ = compute_exit_rule_state(
            spot=102.0, purchase_premium=4.0, mark_price=1.8, ptrans=100.0, ntrans=95.0,
            gex_t1=115.0, days_held=3, stalling_counter=0, dte=28
        )
        self.assertIn("Catastrophic Risk Stop", state)
        self.assertIn("Immediate Exit", action)

    def test_indicators_modular(self):
        from src.gex.quant.indicators import calculate_rsi, calculate_bollinger_bands, calculate_atr

        # RSI with monotonic increase should be 100
        rsi = calculate_rsi([10.0 + i for i in range(20)], period=14)
        self.assertIsNotNone(rsi)
        self.assertEqual(rsi, 100.0)

        # Bollinger Bands
        closes = [100.0 + i * 0.5 for i in range(25)]
        mid, upper, lower = calculate_bollinger_bands(closes, period=20, num_std=2.0)
        self.assertIsNotNone(mid)
        self.assertGreater(upper, mid)
        self.assertLess(lower, mid)

        # ATR
        highs = [102.0] * 20
        lows = [98.0] * 20
        closes = [100.0] * 20
        atr = calculate_atr(highs, lows, closes, period=14)
        self.assertIsNotNone(atr)
        self.assertAlmostEqual(atr, 4.0, places=1)

    def test_sqlite_sync_and_queries(self):
        import tempfile
        from src.gex.storage.db import (
            init_db,
            sync_closed_positions_to_db,
            query_trade_metrics,
            save_gex_snapshot,
            query_latest_gex_snapshot,
        )

        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            test_db = tmp.name

            sample_closed = {
                "closed_options": [
                    {
                        "Option ID": "opt_win_1",
                        "Underlier": "NVDA",
                        "Strike": 120.0,
                        "Expiration": "2026-11-20",
                        "Entry Date": "2026-10-01",
                        "Close Date": "2026-10-15",
                        "Purchase Premium": 4.5,
                        "Close Premium": 7.0,
                        "Realized P&L ($)": 250.0,
                        "Realized P&L (%)": 55.56,
                        "Quantity": 1.0,
                        "Close Reason": "Target Hit",
                        "Target Mode": "T1",
                        "Account": "TEST_ACC",
                    },
                    {
                        "Option ID": "opt_loss_1",
                        "Underlier": "AAPL",
                        "Strike": 220.0,
                        "Expiration": "2026-11-20",
                        "Entry Date": "2026-10-02",
                        "Close Date": "2026-10-10",
                        "Purchase Premium": 3.0,
                        "Close Premium": 1.5,
                        "Realized P&L ($)": -150.0,
                        "Realized P&L (%)": -50.0,
                        "Quantity": 1.0,
                        "Close Reason": "Stop Hit",
                        "Target Mode": "T1",
                        "Account": "TEST_ACC",
                    },
                ],
                "closed_stocks": [
                    {
                        "Ticker": "MSFT",
                        "Trade ID": "stk_win_1",
                        "Shares": 10.0,
                        "Average Buy Price": 400.0,
                        "Close Price": 420.0,
                        "Entry Date": "2026-10-01",
                        "Close Date": "2026-10-14",
                        "Realized P&L ($)": 200.0,
                        "Realized P&L (%)": 5.0,
                        "Account": "TEST_ACC",
                    }
                ],
            }

            synced = sync_closed_positions_to_db(sample_closed, account="TEST_ACC", db_path=test_db)
            self.assertEqual(synced, 3)

            metrics = query_trade_metrics(account="TEST_ACC", db_path=test_db)
            self.assertEqual(metrics["total_trades"], 3)
            self.assertEqual(metrics["wins"], 2)
            self.assertEqual(metrics["losses"], 1)
            self.assertAlmostEqual(metrics["win_rate"], 66.67, places=1)
            self.assertEqual(metrics["total_realized_pnl"], 300.0)
            self.assertGreater(metrics["profit_factor"], 1.0)
            self.assertGreater(metrics["avg_holding_days"], 0.0)

            # Test GEX snapshot persistence
            save_gex_snapshot(
                symbol="NVDA",
                session_date="2026-10-18",
                spot=125.50,
                ptrans=120.0,
                ntrans=115.0,
                call_wall=130.0,
                put_wall=110.0,
                net_gex=1500000.0,
                db_path=test_db,
            )
            snapshot = query_latest_gex_snapshot("NVDA", db_path=test_db)
            self.assertIsNotNone(snapshot)
            self.assertEqual(snapshot["symbol"], "NVDA")
            self.assertEqual(snapshot["spot"], 125.50)
            self.assertEqual(snapshot["call_wall"], 130.0)

    def test_init_db_path_traversal_prevention(self):
        from src.gex.storage.db import init_db
        with self.assertRaises(ValueError):
            init_db("../../etc/passwd.db")
        with self.assertRaises(ValueError):
            init_db("/etc/passwd.db")

    def test_multi_account_cache_isolation(self):
        from src.gex_engine import _JSON_FILE_CACHE, clear_account_cache

        _JSON_FILE_CACHE[("data/active_positions_ACC1.json", 100.0)] = {"options_positions": {}}
        _JSON_FILE_CACHE[("data/active_positions_ACC2.json", 100.0)] = {"options_positions": {}}

        evicted = clear_account_cache("ACC1")
        self.assertEqual(evicted, 1)
        self.assertNotIn(("data/active_positions_ACC1.json", 100.0), _JSON_FILE_CACHE)
        self.assertIn(("data/active_positions_ACC2.json", 100.0), _JSON_FILE_CACHE)

        # Clear remaining
        clear_account_cache()
        self.assertEqual(len(_JSON_FILE_CACHE), 0)

    def test_cmd_audit_all_execution(self):
        import io
        import json
        from unittest.mock import patch
        from src.gex_engine import cmd_audit_all

        class MockArgs:
            account = ""
            json = True
            alert = False
            net_liq = 50000.0

        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            cmd_audit_all(MockArgs())
            output = fake_out.getvalue()
            data = json.loads(output)
            self.assertIn("summary", data)
            self.assertIn("regime", data)
            self.assertIn("pending_exits", data)
            self.assertIn("accounts", data)
            self.assertGreaterEqual(data["summary"]["total_positions"], 0)

    def test_find_flip_strikes_linear_interpolation(self):
        from src.gex.quant.greeks import find_flip_strikes

        # Test 1: Simple linear interpolation between 100 and 110
        # G(100) = -50, G(110) = 50 -> midpoint 105.0
        gex = {100.0: -50.0, 110.0: 50.0}
        flips = find_flip_strikes(gex)
        self.assertEqual(len(flips), 1)
        self.assertAlmostEqual(flips[0], 105.0, places=4)

        # Test 2: Asymmetric linear interpolation
        # G(100) = -200, G(110) = 100 -> 100 + 10 * (200 / 300) = 106.6667
        gex_asym = {100.0: -200.0, 110.0: 100.0}
        flips_asym = find_flip_strikes(gex_asym)
        self.assertEqual(len(flips_asym), 1)
        self.assertAlmostEqual(flips_asym[0], 100.0 + 10.0 * (200.0 / 300.0), places=4)

        # Test 3: Multiple zero crossings
        # 90 (+100) -> 100 (-100) -> 110 (+100)
        # Flip 1: 90 + 10 * 0.5 = 95.0
        # Flip 2: 100 + 10 * 0.5 = 105.0
        gex_multi = {90.0: 100.0, 100.0: -100.0, 110.0: 100.0}
        flips_multi = find_flip_strikes(gex_multi)
        self.assertEqual(len(flips_multi), 2)
        self.assertAlmostEqual(flips_multi[0], 95.0, places=4)
        self.assertAlmostEqual(flips_multi[1], 105.0, places=4)

    def test_find_flip_strikes_exact_zero_and_edges(self):
        from src.gex.quant.greeks import find_flip_strikes

        # Test exact zero at a strike
        gex_zero = {95.0: -50.0, 100.0: 0.0, 105.0: 50.0}
        flips = find_flip_strikes(gex_zero)
        self.assertIn(100.0, flips)

        # Test monotonic (no zero crossing)
        gex_mono = {90.0: 10.0, 100.0: 20.0, 110.0: 30.0}
        self.assertEqual(find_flip_strikes(gex_mono), [])

        # Empty and single strike
        self.assertEqual(find_flip_strikes({}), [])
        self.assertEqual(find_flip_strikes({100.0: 50.0}), [])
        self.assertEqual(find_flip_strikes({100.0: 0.0}), [])


    def test_select_transition_points(self):
        from src.gex.quant.greeks import select_transition_points

        # Flips above and below spot: Spot = 100.0, flips = [95.0, 105.0]
        # pTrans = min(K* >= 100) = 105.0
        # nTrans = max(K* < 100) = 95.0
        p, n = select_transition_points([95.0, 105.0], spot=100.0, cotmp=92.0, put_wall=90.0)
        self.assertEqual(p, 105.0)
        self.assertEqual(n, 95.0)
        self.assertGreater(p, n)

        # Flips only above spot: Spot = 100.0, flips = [105.0, 110.0]
        # pTrans = 105.0, nTrans falls back to COTMP / Put Wall (< 105.0)
        p, n = select_transition_points([105.0, 110.0], spot=100.0, cotmp=95.0, put_wall=90.0)
        self.assertEqual(p, 105.0)
        self.assertEqual(n, 95.0)
        self.assertGreater(p, n)

        # Flips only below spot: Spot = 100.0, flips = [88.0, 93.0]
        # nTrans = 93.0, pTrans falls back
        p, n = select_transition_points([88.0, 93.0], spot=100.0, cotmp=90.0, put_wall=85.0)
        self.assertEqual(n, 93.0)
        self.assertGreater(p, n)

        # No flips: fallback to COTMP and Put Wall with Rule 4 invariant enforcement
        p, n = select_transition_points([], spot=100.0, cotmp=95.0, put_wall=90.0)
        self.assertGreater(p, n)

    def test_derive_gex_profile_zero_crossing_integration(self):
        from src.gex_engine import derive_gex_profile

        # Synthetic chain with clear zero-crossing around 100.0:
        # Calls dominant at 105, 110. Puts dominant at 90, 95.
        chain = [
            {"strike_price": "90.00", "type": "put", "open_interest": 1000, "gamma": 0.05, "implied_volatility": "0.30"},
            {"strike_price": "95.00", "type": "put", "open_interest": 800, "gamma": 0.05, "implied_volatility": "0.30"},
            {"strike_price": "100.00", "type": "call", "open_interest": 500, "gamma": 0.05, "implied_volatility": "0.30"},
            {"strike_price": "100.00", "type": "put", "open_interest": 500, "gamma": 0.05, "implied_volatility": "0.30"},
            {"strike_price": "105.00", "type": "call", "open_interest": 800, "gamma": 0.05, "implied_volatility": "0.30"},
            {"strike_price": "110.00", "type": "call", "open_interest": 1000, "gamma": 0.05, "implied_volatility": "0.30"},
        ]

        inst_data = {
            "instruments": [
                {"id": f"opt_{i}", "strike_price": item["strike_price"], "type": item["type"]}
                for i, item in enumerate(chain)
            ]
        }
        quotes_data = {
            "results": [
                {
                    "quote": {
                        "instrument_id": f"opt_{i}",
                        "open_interest": item["open_interest"],
                        "gamma": str(item["gamma"]),
                        "implied_volatility": item["implied_volatility"],
                    }
                }
                for i, item in enumerate(chain)
            ]
        }

        profile = derive_gex_profile(inst_data, quotes_data, spot=98.0)
        self.assertIn("flip_strikes", profile)
        self.assertIn("put_wall", profile)
        self.assertGreater(profile["derived_ptrans"], profile["derived_ntrans"])




class TestPhase2ModularArchitecture(unittest.TestCase):
    """Unit tests for Phase 2 domain packages and ingestion boundary adapters."""

    def test_core_config_paths_and_sanitization(self):
        from src.gex.core.config import (
            REPOSITORY_ROOT,
            validate_safe_path,
            sanitize_account,
            account_positions_file,
            account_closed_positions_file,
            account_performance_file,
        )
        self.assertTrue(os.path.isdir(REPOSITORY_ROOT))
        self.assertEqual(sanitize_account("••••9961"), "9961")
        self.assertEqual(sanitize_account("5QR24141"), "5QR24141")
        with self.assertRaises(ValueError):
            sanitize_account("!@#$%^")

        # Test account scoping
        pos_file = account_positions_file("9961")
        self.assertIn("active_positions_9961.json", pos_file)
        closed_file = account_closed_positions_file("9961")
        self.assertIn("closed_positions_9961.json", closed_file)
        perf_file = account_performance_file("9961")
        self.assertIn("performance_9961.json", perf_file)

        # Test path traversal prevention
        safe = validate_safe_path("data/regime.json")
        self.assertTrue(os.path.isabs(safe))
        with self.assertRaises(ValueError):
            validate_safe_path("../../etc/passwd")

    def test_model_ingestion_adapters(self):
        from src.gex.core.models import (
            OptionQuote,
            ScannerCandidate,
            OptionPosition,
            StockPosition,
            RegimeGates,
            OptionSentiment,
        )

        # 1. OptionQuote from Robinhood quote & instrument
        raw_quote = {
            "instrument_id": "opt_xyz",
            "bid_price": "2.10",
            "ask_price": "2.30",
            "open_interest": 1200,
            "gamma": "0.035",
            "delta": "0.45",
            "implied_volatility": "0.32",
        }
        raw_inst = {
            "id": "opt_xyz",
            "strike_price": "150.00",
            "type": "call",
            "expiration_date": "2026-11-20",
        }
        quote_obj = OptionQuote.from_robinhood(raw_quote, raw_inst)
        self.assertEqual(quote_obj.strike, 150.0)
        self.assertEqual(quote_obj.option_type, "call")
        self.assertEqual(quote_obj.mark, 2.20)
        self.assertEqual(quote_obj.delta, 0.45)
        self.assertEqual(quote_obj.gamma, 0.035)

        # 2. ScannerCandidate from dict
        cand_dict = {
            "ticker": "AAPL",
            "price": "185.50",
            "percent_change": "1.85",
            "relative_options_volume": "2.3",
            "iv": "0.28",
        }
        cand = ScannerCandidate.from_dict(cand_dict)
        self.assertEqual(cand.symbol, "AAPL")
        self.assertEqual(cand.price, 185.50)
        self.assertEqual(cand.relative_options_volume, 2.3)

        # 3. OptionPosition from dict with validation
        opt_pos_dict = {
            "Option ID": "pos_1",
            "Underlier": "NVDA",
            "Strike": 130.0,
            "Expiration": "2026-11-20",
            "Type": "call",
            "Purchase Premium": 4.50,
            "Mark Price": 5.20,
            "Days Held": 2,
            "Stalling Days": 0,
        }
        opt_pos = OptionPosition.from_dict(opt_pos_dict)
        self.assertTrue(opt_pos.validate())
        self.assertEqual(opt_pos.underlier, "NVDA")
        self.assertEqual(opt_pos.purchase_premium, 4.50)

        # 4. StockPosition from dict with validation
        stock_dict = {
            "symbol": "MSFT",
            "shares": 10.0,
            "average_buy_price": 400.0,
            "current_price": 415.0,
        }
        stock_pos = StockPosition.from_dict(stock_dict)
        self.assertTrue(stock_pos.validate())
        self.assertEqual(stock_pos.ticker, "MSFT")
        self.assertEqual(stock_pos.current_value, 4150.0)

        # 5. RegimeGates validation
        gates = RegimeGates(
            basket_gate="PASS",
            bull_bear_ratio=3.5,
            bull_bear_gate="PASS",
            vix_delta_gate="PASS",
            system_authorization="ALL TRACKS OK",
            gates_passed=3,
        )
        self.assertTrue(gates.validate())

        # 6. OptionSentiment 5-factor validation
        sentiment = OptionSentiment(
            ticker="TSLA",
            sentiment=0.35,
            buzz="High",
            narrative="Bullish catalyst",
            tone_score=0.15,
            comments_score=0.10,
            position_score=0.05,
            volume_score=0.03,
            meme_score=0.02,
        )
        self.assertTrue(sentiment.validate())

    def test_screening_scanner_and_selector(self):
        from src.gex.screening.scanner import calculate_candidate_score, filter_candidate
        from src.gex.screening.selector import select_best_option

        # Scanner candidate scoring
        high_score_cand = {
            "relative_options_volume": 3.0,
            "chg_pct": 2.5,
            "iv": 0.40,
            "rsi": 55.0,
            "macd_hist": 0.5,
        }
        score = calculate_candidate_score(high_score_cand)
        self.assertGreater(score, 45.0)

        # Filtering
        self.assertTrue(filter_candidate({"price": 50.0, "volume": 500000, "chg_pct": 1.2}))
        self.assertFalse(filter_candidate({"price": 2.0}))  # Below MIN_PRICE

        # Selector contract isolation
        inst_data = {
            "instruments": [
                {"id": "c1", "strike_price": "105.00", "type": "call", "expiration_date": "2026-11-20"},
                {"id": "c2", "strike_price": "110.00", "type": "call", "expiration_date": "2026-11-20"},
            ]
        }
        quotes_data = {
            "results": [
                {"quote": {"instrument_id": "c1", "bid_price": "2.40", "ask_price": "2.50", "open_interest": 1500, "delta": "0.45"}},
                {"quote": {"instrument_id": "c2", "bid_price": "1.20", "ask_price": "1.30", "open_interest": 800, "delta": "0.25"}},
            ]
        }
        best, eligible = select_best_option(inst_data, quotes_data, spot=100.0, gex_target=115.0, today_override="2026-10-18")
        self.assertIsNotNone(best)
        self.assertEqual(best["option_id"], "c1")
        self.assertEqual(best["strike"], 105.0)
        self.assertTrue(best["liquidity_passed"])

    def test_storage_persistence_atomic_and_retention(self):
        import tempfile
        from src.gex.storage.persistence import load_json, save_json, clear_account_cache
        from src.gex.storage.retention import cleanup_downloads

        with tempfile.TemporaryDirectory() as tmp_dir:
            fpath = os.path.join(tmp_dir, "test_atomic.json")
            data = {"status": "ok", "count": 42}
            save_json(fpath, data)
            loaded = load_json(fpath)
            self.assertEqual(loaded, data)

            # Test account cache clear
            evicted = clear_account_cache()
            self.assertGreaterEqual(evicted, 0)

            # Retention
            cleaned = cleanup_downloads(days=7, downloads_dir=tmp_dir)
            self.assertEqual(cleaned, 0)

            # Test path traversal protection in retention cleanup
            cleaned_traversal = cleanup_downloads(days=7, downloads_dir="../../../etc")
            self.assertEqual(cleaned_traversal, 0)

    def test_presentation_formatters_and_ascii(self):
        from src.gex.presentation.ascii_art import generate_ascii_gex_scale, format_color
        from src.gex.presentation.formatters import format_currency, format_pct, format_table

        # ASCII Runway
        scale = generate_ascii_gex_scale(spot=100.0, ptrans=103.0, ntrans=96.0, gex=110.0, cotmp=94.0)
        self.assertIn("SPOT", scale)
        self.assertIn("pTrans", scale)
        self.assertIn("nTrans", scale)
        self.assertIn("+GEX", scale)

        # Formatters
        self.assertEqual(format_currency(1234.5), "$1,234.50")
        self.assertEqual(format_pct(5.2), "+5.20%")
        self.assertEqual(format_pct(-3.1), "-3.10%")

        table = format_table(["Sym", "Price"], [["AAPL", 180.0], ["MSFT", 400.0]])
        self.assertIn("AAPL", table)
        self.assertIn("MSFT", table)

        empty_table = format_table(["Sym", "Price"], [])
        self.assertIn("No data available", empty_table)
        custom_empty_table = format_table(["Sym", "Price"], [], empty_message="No candidates found")
        self.assertIn("No candidates found", custom_empty_table)
        # Verify separator line width expands to match or exceed long empty message
        lines = custom_empty_table.split("\n")
        self.assertEqual(len(lines[0]), len(lines[2]))
        self.assertEqual(len(lines[1]), len(lines[2]))


if __name__ == "__main__":
    unittest.main()




