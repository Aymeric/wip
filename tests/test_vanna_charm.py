"""
Unit tests for Milestone 5.9: Second-Order Dealer Exposure Modeling (Vanna & Charm Profiles).
Tests analytical Black-Scholes Vanna and Charm, profile aggregation, asymmetry/tilt metrics,
domain model serialization, and presentation formatting.
"""

import math
import unittest
from typing import Any, Dict, List

from src.gex.quant.greeks import (
    calculate_black_scholes_gamma,
    calculate_black_scholes_vanna,
    calculate_black_scholes_charm,
)
from src.gex.quant.gex import derive_gex_profile
from src.gex.core.models import GexProfile
from src.gex.presentation.formatters import format_vanna_charm_summary


class TestVannaCharmAnalytics(unittest.TestCase):
    """Tests analytical Black-Scholes Vanna and Charm formulas and edge cases."""

    def test_vanna_calculation_standard(self):
        """Validates Black-Scholes Vanna against standard analytical properties."""
        spot = 100.0
        dte = 30.0
        iv = 0.30
        r = 0.04

        # For OTM call (K = 110 > S = 100), d2 < 0, so Vanna = -N'(d1)*d2 / sigma > 0
        vanna_otm = calculate_black_scholes_vanna(spot, 110.0, dte, iv, r)
        self.assertGreater(vanna_otm, 0.0)

        # For ITM call (K = 90 < S = 100), d2 > 0, so Vanna < 0
        vanna_itm = calculate_black_scholes_vanna(spot, 90.0, dte, iv, r)
        self.assertLess(vanna_itm, 0.0)

        # Vanna should be a finite float
        self.assertTrue(math.isfinite(vanna_otm))
        self.assertTrue(math.isfinite(vanna_itm))

    def test_vanna_zero_crossing_at_d2_zero(self):
        """When d2 == 0, Vanna is exactly 0.0."""
        spot = 100.0
        dte = 365.25  # T = 1.0 year
        iv = 0.20
        r = 0.05
        # d2 = [ln(S/K) + (r - 0.5*sigma^2)*T] / (sigma*sqrt(T)) = 0
        # => ln(S/K) = -(r - 0.5*sigma^2)*T = -(0.05 - 0.02) = -0.03
        # => K = S * exp(0.03)
        strike_d2_zero = spot * math.exp((r - 0.5 * iv * iv) * 1.0)
        vanna = calculate_black_scholes_vanna(spot, strike_d2_zero, dte, iv, r)
        self.assertAlmostEqual(vanna, 0.0, places=6)

    def test_vanna_edge_cases(self):
        """Tests robust handling of invalid inputs for Vanna."""
        self.assertEqual(calculate_black_scholes_vanna(0.0, 100.0, 30.0, 0.3), 0.0)
        self.assertEqual(calculate_black_scholes_vanna(-10.0, 100.0, 30.0, 0.3), 0.0)
        self.assertEqual(calculate_black_scholes_vanna(100.0, 0.0, 30.0, 0.3), 0.0)
        self.assertEqual(calculate_black_scholes_vanna(100.0, -50.0, 30.0, 0.3), 0.0)
        self.assertEqual(calculate_black_scholes_vanna(100.0, 100.0, 30.0, 0.0), 0.0)
        self.assertEqual(calculate_black_scholes_vanna(100.0, 100.0, 30.0, -0.2), 0.0)
        # Even with 0 DTE, max(dte, 0.5) prevents zero division
        vanna_zero_dte = calculate_black_scholes_vanna(100.0, 105.0, 0.0, 0.3)
        self.assertTrue(math.isfinite(vanna_zero_dte))

    def test_charm_calculation_standard(self):
        """Validates daily Charm calculation across standard moneyness."""
        spot = 100.0
        dte = 30.0
        iv = 0.30
        r = 0.04

        charm_atm = calculate_black_scholes_charm(spot, 100.0, dte, iv, r)
        self.assertTrue(math.isfinite(charm_atm))
        # Daily charm is typically of order 10^-3 to 10^-4 per day
        self.assertLess(abs(charm_atm), 0.1)

    def test_charm_edge_cases(self):
        """Tests robust handling of invalid inputs for Charm."""
        self.assertEqual(calculate_black_scholes_charm(0.0, 100.0, 30.0, 0.3), 0.0)
        self.assertEqual(calculate_black_scholes_charm(-10.0, 100.0, 30.0, 0.3), 0.0)
        self.assertEqual(calculate_black_scholes_charm(100.0, 0.0, 30.0, 0.3), 0.0)
        self.assertEqual(calculate_black_scholes_charm(100.0, -50.0, 30.0, 0.3), 0.0)
        self.assertEqual(calculate_black_scholes_charm(100.0, 100.0, 30.0, 0.0), 0.0)
        self.assertEqual(calculate_black_scholes_charm(100.0, 100.0, 30.0, -0.2), 0.0)
        charm_zero_dte = calculate_black_scholes_charm(100.0, 100.0, 0.0, 0.3)
        self.assertTrue(math.isfinite(charm_zero_dte))


class TestVannaCharmGexDerivation(unittest.TestCase):
    """Tests integration of Vanna and Charm into derive_gex_profile."""

    def setUp(self):
        self.inst_data = {
            "instruments": [
                {"id": "call_105", "strike_price": "105.0", "type": "call", "expiration_date": "2026-12-15"},
                {"id": "call_110", "strike_price": "110.0", "type": "call", "expiration_date": "2026-12-15"},
                {"id": "put_95", "strike_price": "95.0", "type": "put", "expiration_date": "2026-12-15"},
                {"id": "put_90", "strike_price": "90.0", "type": "put", "expiration_date": "2026-12-15"},
            ]
        }
        self.quotes_data = {
            "results": [
                {"instrument_id": "call_105", "open_interest": "500", "gamma": "0.03", "implied_volatility": "0.28"},
                {"instrument_id": "call_110", "open_interest": "300", "gamma": "0.02", "implied_volatility": "0.32"},
                {"instrument_id": "put_95", "open_interest": "400", "gamma": "0.025", "implied_volatility": "0.30"},
                {"instrument_id": "put_90", "open_interest": "200", "gamma": "0.015", "implied_volatility": "0.35"},
            ]
        }

    def test_derive_gex_profile_includes_vanna_charm(self):
        """Verifies derive_gex_profile populates all Vanna and Charm fields."""
        spot = 100.0
        profile = derive_gex_profile(self.inst_data, self.quotes_data, spot=spot)

        # Check all required keys exist
        expected_keys = [
            "total_call_vanna",
            "total_put_vanna",
            "net_vanna",
            "total_call_charm",
            "total_put_charm",
            "net_charm",
            "vanna_asymmetry_score",
            "charm_tilt",
        ]
        for key in expected_keys:
            self.assertIn(key, profile, f"Missing key: {key}")
            self.assertTrue(math.isfinite(profile[key]), f"Key {key} is not finite: {profile[key]}")

        # Non-zero metrics given non-zero open interest and valid IV
        self.assertNotEqual(profile["total_call_vanna"], 0.0)
        self.assertNotEqual(profile["total_put_vanna"], 0.0)
        self.assertEqual(profile["net_vanna"], profile["total_call_vanna"] - profile["total_put_vanna"])
        self.assertEqual(profile["net_charm"], profile["total_call_charm"] - profile["total_put_charm"])

        # Asymmetry and tilt bounds [-1.0, 1.0]
        self.assertGreaterEqual(profile["vanna_asymmetry_score"], -1.0)
        self.assertLessEqual(profile["vanna_asymmetry_score"], 1.0)
        self.assertGreaterEqual(profile["charm_tilt"], -1.0)
        self.assertLessEqual(profile["charm_tilt"], 1.0)

    def test_derive_gex_profile_empty_chain_fallbacks(self):
        """Verifies derive_gex_profile handles empty chains gracefully with zeros."""
        profile = derive_gex_profile([], [], spot=100.0)
        self.assertEqual(profile["total_call_vanna"], 0.0)
        self.assertEqual(profile["total_put_vanna"], 0.0)
        self.assertEqual(profile["net_vanna"], 0.0)
        self.assertEqual(profile["total_call_charm"], 0.0)
        self.assertEqual(profile["total_put_charm"], 0.0)
        self.assertEqual(profile["net_charm"], 0.0)
        self.assertEqual(profile["vanna_asymmetry_score"], 0.0)
        self.assertEqual(profile["charm_tilt"], 0.0)


class TestGexProfileDomainModel(unittest.TestCase):
    """Tests GexProfile dataclass serialization and round-trip fidelity."""

    def test_gex_profile_serialization_round_trip(self):
        """Verifies GexProfile to_dict and from_dict round-trip with Vanna & Charm."""
        profile = GexProfile(
            spot=100.0,
            total_oi=1400,
            derived_cotmp=93.5,
            derived_ptrans=105.0,
            derived_ntrans=95.0,
            derived_gex=110.0,
            total_call_gex=50000.0,
            total_put_gex=30000.0,
            effective_call_gex=9000.0,
            effective_put_gex=5400.0,
            net_gex=20000.0,
            net_effective_gex=3600.0,
            total_call_vanna=12500.0,
            total_put_vanna=-4500.0,
            net_vanna=17000.0,
            total_call_charm=-150.0,
            total_put_charm=-80.0,
            net_charm=-70.0,
            vanna_asymmetry_score=0.75,
            charm_tilt=-0.08,
            iv_sum=1.2,
            iv_count=4,
            flip_strikes=[102.5],
            put_wall=95.0,
            rule1_derived=True,
            rule2_derived=True,
            rule7_derived=False,
            rule9_derived=True,
            rule10_derived=True,
        )

        d = profile.to_dict()
        self.assertEqual(d["total_call_vanna"], 12500.0)
        self.assertEqual(d["total_put_vanna"], -4500.0)
        self.assertEqual(d["net_vanna"], 17000.0)
        self.assertEqual(d["total_call_charm"], -150.0)
        self.assertEqual(d["total_put_charm"], -80.0)
        self.assertEqual(d["net_charm"], -70.0)
        self.assertEqual(d["vanna_asymmetry_score"], 0.75)
        self.assertEqual(d["charm_tilt"], -0.08)

        reconstructed = GexProfile.from_dict(d, spot=100.0)
        self.assertEqual(reconstructed.total_call_vanna, 12500.0)
        self.assertEqual(reconstructed.net_vanna, 17000.0)
        self.assertEqual(reconstructed.vanna_asymmetry_score, 0.75)
        self.assertEqual(reconstructed.charm_tilt, -0.08)

    def test_gex_profile_from_legacy_dict(self):
        """Verifies GexProfile gracefully defaults Vanna/Charm fields when parsing legacy dicts."""
        legacy_dict = {
            "spot": 100.0,
            "total_oi": 500,
            "derived_cotmp": 95.0,
            "total_call_gex": 1000.0,
            "total_put_gex": 800.0,
        }
        profile = GexProfile.from_dict(legacy_dict)
        self.assertEqual(profile.total_call_vanna, 0.0)
        self.assertEqual(profile.net_vanna, 0.0)
        self.assertEqual(profile.vanna_asymmetry_score, 0.0)
        self.assertEqual(profile.charm_tilt, 0.0)


class TestVannaCharmPresentation(unittest.TestCase):
    """Tests presentation formatting of Vanna and Charm metrics."""

    def test_format_vanna_charm_summary(self):
        """Verifies format_vanna_charm_summary creates descriptive text."""
        profile_data = {
            "net_vanna": 250000.0,
            "vanna_asymmetry_score": 0.45,
            "net_charm": -1250.0,
            "charm_tilt": 0.12,
        }
        summary = format_vanna_charm_summary(profile_data)
        self.assertIn("Second-Order Dealer Exposures (Vanna & Charm)", summary)
        self.assertIn("Net Vanna Exposure", summary)
        self.assertIn("+0.45", summary)
        self.assertIn("Bullish Vol Squeeze", summary)
        self.assertIn("Net Charm Exposure", summary)
        self.assertIn("+0.12", summary)
        self.assertIn("Positive Delta Decay Drift", summary)


if __name__ == "__main__":
    unittest.main()
