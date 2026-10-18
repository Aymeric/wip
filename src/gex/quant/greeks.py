"""
Quantitative option pricing and Greeks calculation module.
Provides analytical Black-Scholes Greeks with robust edge-case handling.
"""

import math
from typing import Optional


def calculate_black_scholes_gamma(
    spot: float,
    strike: float,
    dte_days: float,
    iv: float,
    risk_free_rate: float = 0.04,
) -> float:
    """
    Calculates analytical Black-Scholes option Gamma (dDelta / dSpot).

    Gamma = N'(d1) / (S * sigma * sqrt(T))
    where:
        T = max(dte_days, 0.5) / 365.25
        d1 = [ln(S / K) + (r + 0.5 * sigma^2) * T] / (sigma * sqrt(T))
        N'(d1) = (1 / sqrt(2 * pi)) * exp(-0.5 * d1^2)

    Args:
        spot: Current spot price of the underlying asset.
        strike: Option strike price.
        dte_days: Days to expiration (e.g. 30.0).
        iv: Implied volatility as a decimal ratio (e.g. 0.35 for 35% IV).
        risk_free_rate: Annualized risk-free interest rate (default: 0.04).

    Returns:
        float: Analytical option Gamma, or 0.0 if inputs are invalid.
    """
    if spot <= 0.0 or strike <= 0.0 or iv <= 0.0:
        return 0.0

    t = max(dte_days, 0.5) / 365.25
    sigma_sqrt_t = iv * math.sqrt(t)
    if sigma_sqrt_t <= 0.0:
        return 0.0

    try:
        d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * iv * iv) * t) / sigma_sqrt_t
        n_prime_d1 = (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * d1 * d1)
        gamma = n_prime_d1 / (spot * sigma_sqrt_t)
        return gamma if math.isfinite(gamma) else 0.0
    except (ValueError, OverflowError, ZeroDivisionError):
        return 0.0
