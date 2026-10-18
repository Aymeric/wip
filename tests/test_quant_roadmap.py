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


if __name__ == "__main__":
    unittest.main()
