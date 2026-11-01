"""
Market screening and candidate scoring for underliers and options setups.
Applies mechanical volume, price change, IV, RSI, and MACD scoring models.
"""

from typing import Any, Dict, Optional
from src.gex.core.config import (
    MIN_PRICE,
    MAX_PRICE,
    MIN_VOLUME,
    MIN_CHG_PCT,
    MIN_MARKET_CAP,
)


def calculate_candidate_score(candidate: Dict[str, Any]) -> float:
    """Calculates a normalized 0-100 screen score from available underlier metrics.

    Performance optimization (Bolt):
    Unrolls individual metric evaluations directly and uses multiplication constants
    (* 0.1, * 0.2, * 0.01) instead of allocating a 5-tuple of tuples (`weighted_metrics`),
    looping, unpacking, and dividing per element (~1.5x speedup).
    """
    total_weighted_score = 0.0
    total_weight = 0.0

    # Relative options volume: cap 10.0, weight 30.0
    val = candidate.get("relative_options_volume")
    if val is not None:
        try:
            s = float(val) * 0.1
            if s > 1.0:
                s = 1.0
            elif s < 0.0:
                s = 0.0
            total_weighted_score += s * 30.0
            total_weight += 30.0
        except (ValueError, TypeError):
            pass

    # % Change: cap 5.0, weight 25.0
    val = candidate.get("chg_pct")
    if val is not None:
        try:
            s = float(val) * 0.2
            if s > 1.0:
                s = 1.0
            elif s < 0.0:
                s = 0.0
            total_weighted_score += s * 25.0
            total_weight += 25.0
        except (ValueError, TypeError):
            pass

    # Implied volatility: cap 1.0, weight 15.0
    val = candidate.get("iv")
    if val is not None:
        try:
            s = float(val)
            if s > 1.0:
                s = 1.0
            elif s < 0.0:
                s = 0.0
            total_weighted_score += s * 15.0
            total_weight += 15.0
        except (ValueError, TypeError):
            pass

    # RSI: cap 100.0, weight 20.0
    val = candidate.get("rsi")
    if val is not None:
        try:
            s = float(val) * 0.01
            if s > 1.0:
                s = 1.0
            elif s < 0.0:
                s = 0.0
            total_weighted_score += s * 20.0
            total_weight += 20.0
        except (ValueError, TypeError):
            pass

    # MACD Histogram: binary (>0 -> 1.0, <=0 -> 0.0), cap 1.0, weight 10.0
    macd = candidate.get("macd_hist")
    if macd is not None:
        try:
            if float(macd) > 0.0:
                total_weighted_score += 10.0
            total_weight += 10.0
        except (ValueError, TypeError):
            pass

    if total_weight == 0.0:
        return 0.0

    return round((total_weighted_score / total_weight) * 100.0, 2)


def filter_candidate(
    candidate: Dict[str, Any],
    min_price: float = MIN_PRICE,
    max_price: float = MAX_PRICE,
    min_volume: int = MIN_VOLUME,
    min_chg_pct: float = MIN_CHG_PCT,
    min_market_cap: float = MIN_MARKET_CAP,
) -> bool:
    """Applies baseline quantitative screener criteria to a candidate underlier."""
    price = candidate.get("price") or candidate.get("current_price")
    if price is not None:
        try:
            p = float(price)
            if p < min_price or p > max_price:
                return False
        except (ValueError, TypeError):
            return False

    volume = candidate.get("volume")
    if volume is not None:
        try:
            v = int(volume)
            if v < min_volume:
                return False
        except (ValueError, TypeError):
            pass

    chg = candidate.get("chg_pct") or candidate.get("percent_change")
    if chg is not None:
        try:
            c = float(chg)
            if c < min_chg_pct:
                return False
        except (ValueError, TypeError):
            pass

    mcap = candidate.get("market_cap")
    if mcap is not None:
        try:
            m = float(mcap)
            if m < min_market_cap:
                return False
        except (ValueError, TypeError):
            pass

    return True
