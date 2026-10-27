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


def find_flip_strikes(gex_by_strike: dict) -> list:
    """
    Finds continuous zero-crossing strikes where net GEX flips between positive and negative.
    Matches the linear interpolation implementation in gamma-exposure.ts:

        K* = K_{i-1} + (K_i - K_{i-1}) * (|netGEX_{i-1}| / (|netGEX_{i-1}| + |netGEX_i|))

    Args:
        gex_by_strike: Mapping from strike price (float) to net GEX value (float).

    Returns:
        List of continuous interpolated zero-crossing strike prices in ascending order.
    """
    if not gex_by_strike:
        return []

    # Performance optimization (Bolt):
    # Sort strike-GEX items directly using C-level tuple comparison (`items.sort()`)
    # and eliminate redundant list comprehensions, lambda sorting keys, and built-in function calls.
    items = list(gex_by_strike.items())
    if len(items) < 2:
        return []

    items.sort()

    flip_strikes: list = []
    prev_flip = None

    for i in range(1, len(items)):
        k_prev, g_prev = items[i - 1]
        k_curr, g_curr = items[i]

        # True zero-crossing between opposite signs
        if (g_prev < 0.0 and g_curr > 0.0) or (g_prev > 0.0 and g_curr < 0.0):
            abs_gp = g_prev if g_prev >= 0.0 else -g_prev
            abs_gc = g_curr if g_curr >= 0.0 else -g_curr
            denom = abs_gp + abs_gc
            if denom > 0.0:
                k_star = round(k_prev + (k_curr - k_prev) * (abs_gp / denom), 4)
                if prev_flip is None or abs(k_star - prev_flip) > 1e-6:
                    flip_strikes.append(k_star)
                    prev_flip = k_star
        elif g_prev == 0.0 and g_curr != 0.0:
            if i >= 2 and items[i - 2][1] * g_curr < 0:
                k_star = round(k_prev, 4)
                if prev_flip is None or abs(k_star - prev_flip) > 1e-6:
                    flip_strikes.append(k_star)
                    prev_flip = k_star

    return flip_strikes


def select_transition_points(
    flip_strikes: list,
    spot: float,
    cotmp: Optional[float] = None,
    put_wall: Optional[float] = None,
    secondary_put_wall: Optional[float] = None,
) -> tuple:
    """
    Selects pTrans and nTrans transition levels based on zero-crossing flip strikes:
        pTrans = min(K* >= Spot)
        nTrans = max(K* < Spot)

    Applies fallback to COTMP / Put Wall when no zero-crossing exists.
    Enforces the Rule 4 invariant (pTrans > nTrans).

    Args:
        flip_strikes: Sequence of interpolated zero-crossing strike prices.
        spot: Current underlying spot price.
        cotmp: Weighted average put strike (COTMP).
        put_wall: Strike with largest put GEX / open interest concentration.
        secondary_put_wall: Strike below put_wall with secondary put concentration.

    Returns:
        tuple[float, float]: (pTrans, nTrans) where pTrans > nTrans strictly holds.
    """
    flips_above = [k for k in flip_strikes if k >= spot]
    flips_below = [k for k in flip_strikes if k < spot]

    ptrans: Optional[float] = min(flips_above) if flips_above else None
    ntrans: Optional[float] = max(flips_below) if flips_below else None

    default_put_wall = put_wall if put_wall is not None and put_wall > 0 else spot * 0.95
    default_cotmp = cotmp if cotmp is not None and cotmp > 0 else default_put_wall
    default_secondary_put = (
        secondary_put_wall
        if secondary_put_wall is not None and secondary_put_wall > 0
        else default_put_wall * 0.95
    )

    # Fallback for pTrans if no flip >= spot
    if ptrans is None:
        if ntrans is not None:
            # Zero-crossing below spot exists, but none >= spot.
            # Enforce pTrans > nTrans invariant using fallback
            if default_put_wall > ntrans:
                ptrans = default_put_wall
            elif default_cotmp > ntrans:
                ptrans = default_cotmp
            elif spot > ntrans:
                ptrans = spot
            else:
                ptrans = ntrans * 1.05
        else:
            # No zero-crossings at all: fallback to Put Wall or COTMP
            ptrans = default_put_wall if default_put_wall <= spot else default_cotmp

    # Fallback for nTrans if no flip < spot
    if ntrans is None:
        candidates = [c for c in (default_secondary_put, default_put_wall, default_cotmp) if c < ptrans]
        if candidates:
            ntrans = max(candidates)
        else:
            ntrans = ptrans * 0.95

    # Enforce Rule 4 invariant: pTrans > nTrans
    if ptrans <= ntrans:
        candidates = [c for c in (default_secondary_put, default_put_wall, default_cotmp) if c < ptrans]
        if candidates:
            ntrans = max(candidates)
        else:
            ntrans = ptrans * 0.95

    return (round(ptrans, 2), round(ntrans, 2))


