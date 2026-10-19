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
    """Calculates a normalized 0-100 screen score from available underlier metrics."""
    macd = candidate.get("macd_hist")
    macd_val = None
    if macd is not None:
        try:
            macd_val = 1.0 if float(macd) > 0.0 else 0.0
        except (ValueError, TypeError):
            macd_val = None

    weighted_metrics = (
        (candidate.get("relative_options_volume"), 30.0, 10.0),
        (candidate.get("chg_pct"), 25.0, 5.0),
        (candidate.get("iv"), 15.0, 1.0),
        (candidate.get("rsi"), 20.0, 100.0),
        (macd_val, 10.0, 1.0),
    )
    total_weighted_score = 0.0
    total_weight = 0.0

    for value, weight, cap in weighted_metrics:
        if value is not None:
            try:
                numeric_val = float(value)
                score = numeric_val / cap
                if score < 0.0:
                    score = 0.0
                elif score > 1.0:
                    score = 1.0
                total_weighted_score += score * weight
                total_weight += weight
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
