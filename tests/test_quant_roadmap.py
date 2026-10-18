"""
Unit tests for roadmap implementations:
1. Analytical Black-Scholes Gamma calculations and fallback in GEX profile derivation.
2. Effective (DTE-weighted) GEX metrics.
3. Typed domain models (OptionQuote, GexProfile, ScannerCandidate, RegimeStatus).
4. System alert dispatching.
"""

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


if __name__ == "__main__":
    unittest.main()


