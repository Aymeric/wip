"""
Dynamic Delta Rolling and Profit Ratcheting Risk Module for GEX Options Trading System.
Provides systematic evaluation for rolling winning or deep-in-the-money options:
- Delta Expansion (Delta >= 0.70)
- Profit Acceleration (ROI >= +50%, >= +100%)
- Profit Ratchet Trailing Floors (+25% and +50% minimum profit locks)
- Target Contract Selection (Delta 0.40-0.50, 30-45 DTE)
- Net Credit & Capital Extraction Calculations
"""

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from src.gex.quant.greeks import calculate_black_scholes_gamma
from src.gex.screening.selector import select_best_option


@dataclass
class RollRecommendation:
    """Represents a quantitative roll recommendation for an active option position."""
    option_id: str
    underlier: str
    contract_desc: str
    strike: float
    expiration: str
    dte: int
    delta: Optional[float]
    purchase_premium: float
    mark_price: float
    contracts: float
    unrealized_pnl_pct: float
    unrealized_pnl_dollar: float
    eligible: bool
    triggers: List[str] = field(default_factory=list)
    ratchet_stop_floor_pct: Optional[float] = None
    ratchet_description: str = "No Ratchet"
    target_strike: Optional[float] = None
    target_dte: int = 35
    target_delta: float = 0.45
    target_mark: Optional[float] = None
    estimated_net_credit: Optional[float] = None
    capital_extracted: Optional[float] = None
    capital_at_risk_reduction_pct: Optional[float] = None
    action: str = "HOLD_CURRENT"

    def to_dict(self) -> Dict[str, Any]:
        """Serializes recommendation to a dictionary."""
        return {
            "option_id": self.option_id,
            "underlier": self.underlier,
            "contract_desc": self.contract_desc,
            "strike": self.strike,
            "expiration": self.expiration,
            "dte": self.dte,
            "delta": round(self.delta, 4) if self.delta is not None else None,
            "purchase_premium": round(self.purchase_premium, 2),
            "mark_price": round(self.mark_price, 2),
            "contracts": self.contracts,
            "unrealized_pnl_pct": round(self.unrealized_pnl_pct, 2),
            "unrealized_pnl_dollar": round(self.unrealized_pnl_dollar, 2),
            "eligible": self.eligible,
            "triggers": self.triggers,
            "ratchet_stop_floor_pct": round(self.ratchet_stop_floor_pct, 2) if self.ratchet_stop_floor_pct is not None else None,
            "ratchet_description": self.ratchet_description,
            "target_strike": round(self.target_strike, 2) if self.target_strike is not None else None,
            "target_dte": self.target_dte,
            "target_delta": round(self.target_delta, 2),
            "target_mark": round(self.target_mark, 2) if self.target_mark is not None else None,
            "estimated_net_credit": round(self.estimated_net_credit, 2) if self.estimated_net_credit is not None else None,
            "capital_extracted": round(self.capital_extracted, 2) if self.capital_extracted is not None else None,
            "capital_at_risk_reduction_pct": round(self.capital_at_risk_reduction_pct, 2) if self.capital_at_risk_reduction_pct is not None else None,
            "action": self.action,
        }


def calculate_profit_ratchet(
    unrealized_pnl_pct: float,
    max_profit_pct: Optional[float] = None,
) -> Tuple[Optional[float], str]:
    """
    Computes systematic profit-ratchet floors based on accrued ROI:
    - Tier 2 Ratchet (ROI >= +100%): Trailing floor ratchets to lock in at least +50% gain.
    - Tier 1 Ratchet (ROI >= +50%): Trailing floor ratchets to lock in at least +25% gain.
    - Standard Trailing Stop (max_profit >= 30%): 20% giveback floor (locks in 80% of peak).
    """
    if unrealized_pnl_pct >= 100.0:
        return 50.0, "Tier 2 Ratchet (+50.0% minimum profit lock-in)"
    elif unrealized_pnl_pct >= 50.0:
        return 25.0, "Tier 1 Ratchet (+25.0% minimum profit lock-in)"
    elif max_profit_pct is not None and max_profit_pct >= 30.0:
        floor = max_profit_pct * 0.80
        return round(floor, 2), f"Trailing Volatility Stop (20% giveback floor: {floor:+.1f}%)"
    return None, "Standard Monitoring (No Ratchet Active)"


def estimate_target_contract_pricing(
    spot: float,
    current_strike: float,
    current_iv: float = 0.35,
    target_delta: float = 0.45,
    target_dte: int = 35,
) -> Tuple[float, float]:
    """
    Analytically approximates a target roll strike and mark premium when live option chain
    data is offline.
    Uses Black-Scholes approximations:
    - For call Delta ~0.45, target strike is ~3% above current spot.
    - Estimated premium uses standard volatility scaling.
    """
    if spot <= 0:
        return current_strike, 1.0

    # Target strike slightly OTM/ATM for Delta 0.45 (roughly spot * 1.025 to 1.03)
    target_strike = round(spot * 1.025, 1)
    if spot >= 50.0:
        # Round to nearest 2.50 or 5.00 interval
        interval = 2.50 if spot < 200.0 else 5.00
        target_strike = round(target_strike / interval) * interval

    # Analytical approximation of option premium: S * delta * iv * sqrt(t)
    t = target_dte / 365.25
    approx_vol = max(current_iv, 0.20)
    estimated_mark = max(spot * 0.02, spot * target_delta * approx_vol * math.sqrt(t))
    return round(target_strike, 2), round(estimated_mark, 2)


def evaluate_position_roll(
    position_data: Dict[str, Any],
    spot: float,
    chain_instruments: Optional[Any] = None,
    chain_quotes: Optional[Any] = None,
    threshold_delta: float = 0.70,
    threshold_gain: float = 50.0,
    today_override: Optional[Any] = None,
) -> RollRecommendation:
    """
    Evaluates an active option position against systematic dynamic delta rolling criteria.

    Args:
        position_data: Option position dictionary from active_positions.json
        spot: Current underlying spot price
        chain_instruments: Optional live options instruments for the underlier
        chain_quotes: Optional live options quotes for the underlier
        threshold_delta: Minimum delta triggering roll consideration (default: 0.70)
        threshold_gain: Minimum unrealized P&L % triggering roll consideration (default: 50.0%)
        today_override: Optional date override for backtesting/testing

    Returns:
        RollRecommendation: Full quantitative rolling analysis
    """
    opt_id = position_data.get("Option ID") or position_data.get("option_id") or "UNKNOWN"
    underlier = (position_data.get("Underlier") or position_data.get("underlier") or "UNKNOWN").upper()
    strike = float(position_data.get("Strike") or position_data.get("strike") or 0.0)
    expiration = str(position_data.get("Expiration") or position_data.get("expiration") or "")
    opt_type = str(position_data.get("Type") or position_data.get("type") or "call").lower()

    purchase_premium = float(position_data.get("Purchase Premium") or position_data.get("purchase_premium") or 0.0)
    mark_price = float(position_data.get("Mark Price") or position_data.get("mark_price") or purchase_premium)

    # Resolve contract quantity
    contracts = 1.0
    cost_basis = position_data.get("Asset Cost Basis")
    if cost_basis and purchase_premium > 0:
        contracts = round(float(cost_basis) / (purchase_premium * 100.0), 2)
    elif "Quantity" in position_data:
        contracts = float(position_data["Quantity"])
    elif "contracts" in position_data:
        contracts = float(position_data["contracts"])

    # Resolve DTE
    dte = 0
    ref_today = today_override if today_override is not None else date.today()
    if isinstance(ref_today, str):
        try:
            ref_today = datetime.strptime(ref_today, "%Y-%m-%d").date()
        except ValueError:
            ref_today = date.today()
    elif isinstance(ref_today, datetime):
        ref_today = ref_today.date()

    if expiration:
        try:
            exp_date = datetime.strptime(expiration, "%Y-%m-%d").date()
            dte = (exp_date - ref_today).days
        except ValueError:
            dte = 0

    # Resolve Delta
    delta = None
    raw_delta = position_data.get("Delta") or position_data.get("delta")
    if raw_delta is not None:
        try:
            delta = float(raw_delta)
        except (ValueError, TypeError):
            delta = None

    # Resolve IV
    iv = 0.35
    raw_iv = position_data.get("ImpVol") or position_data.get("imp_vol") or position_data.get("iv")
    if raw_iv is not None:
        try:
            iv = float(raw_iv)
        except (ValueError, TypeError):
            iv = 0.35

    # P&L calculations
    dollar_gain = (mark_price - purchase_premium) * 100.0 * contracts
    pl_pct = ((mark_price - purchase_premium) / purchase_premium * 100.0) if purchase_premium > 0 else 0.0

    # Check triggers
    triggers = []
    eligible = False

    # Trigger 1: Delta expansion (Delta >= threshold_delta, e.g. 0.70)
    if delta is not None and abs(delta) >= threshold_delta:
        eligible = True
        triggers.append(f"DELTA_EXPANSION: Delta {abs(delta):.2f} >= {threshold_delta:.2f} (convexity compressed)")

    # Trigger 2: Profit acceleration (ROI >= threshold_gain, e.g. +50.0% or +100.0%)
    if pl_pct >= threshold_gain:
        eligible = True
        triggers.append(f"PROFIT_ACCELERATION: Accrued ROI {pl_pct:+.1f}% >= +{threshold_gain:.1f}%")

    # Trigger 3: Theta decay approach on profitable trade (DTE <= 21 with positive P&L)
    if 0 < dte <= 21 and pl_pct > 0.0:
        eligible = True
        triggers.append(f"THETA_PRESERVATION: DTE {dte} <= 21 on winning trade ({pl_pct:+.1f}%)")

    # Profit ratchet floor
    ratchet_floor, ratchet_desc = calculate_profit_ratchet(pl_pct)

    # Contract description
    contract_desc = f"{underlier} {expiration} ${strike:.2f} {opt_type.upper()}"

    # Determine target roll contract
    target_strike = None
    target_dte = 35
    target_delta = 0.45
    target_mark = None

    if chain_instruments and chain_quotes:
        best_opt, _ = select_best_option(
            inst_data=chain_instruments,
            quotes_data=chain_quotes,
            spot=spot,
            today_override=ref_today,
            target_delta=target_delta,
            min_dte=30,
            max_dte=45,
        )
        if best_opt:
            target_strike = float(best_opt.get("strike", 0.0))
            target_mark = float(best_opt.get("mark", 0.0))
            target_dte = int(best_opt.get("dte", 35))
            if "delta" in best_opt and best_opt["delta"] is not None:
                target_delta = float(best_opt["delta"])

    if target_strike is None or target_mark is None:
        target_strike, target_mark = estimate_target_contract_pricing(
            spot=spot,
            current_strike=strike,
            current_iv=iv,
            target_delta=target_delta,
            target_dte=target_dte,
        )

    # Net credit calculations
    estimated_net_credit = round(mark_price - target_mark, 2)
    capital_extracted = round(estimated_net_credit * 100.0 * contracts, 2)
    risk_reduction_pct = round(((mark_price - target_mark) / mark_price * 100.0), 2) if mark_price > 0 else 0.0

    action = "HOLD_CURRENT"
    if eligible:
        action = "ROLL_RECOMMENDED"
    elif ratchet_floor is not None:
        action = "PROFIT_RATCHET_ACTIVE"

    return RollRecommendation(
        option_id=opt_id,
        underlier=underlier,
        contract_desc=contract_desc,
        strike=strike,
        expiration=expiration,
        dte=dte,
        delta=delta,
        purchase_premium=purchase_premium,
        mark_price=mark_price,
        contracts=contracts,
        unrealized_pnl_pct=pl_pct,
        unrealized_pnl_dollar=dollar_gain,
        eligible=eligible,
        triggers=triggers,
        ratchet_stop_floor_pct=ratchet_floor,
        ratchet_description=ratchet_desc,
        target_strike=target_strike,
        target_dte=target_dte,
        target_delta=target_delta,
        target_mark=target_mark,
        estimated_net_credit=estimated_net_credit,
        capital_extracted=capital_extracted,
        capital_at_risk_reduction_pct=risk_reduction_pct,
        action=action,
    )


def evaluate_portfolio_rolls(
    active_options: Dict[str, Any],
    spots: Optional[Dict[str, float]] = None,
    chains_by_underlier: Optional[Dict[str, Any]] = None,
    threshold_delta: float = 0.70,
    threshold_gain: float = 50.0,
    today_override: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Evaluates an entire portfolio of active options positions for roll opportunities.

    Args:
        active_options: Mapping of option_id to position details dictionary
        spots: Optional mapping of underlier ticker to current spot price
        chains_by_underlier: Optional mapping of underlier to (instruments, quotes) tuple
        threshold_delta: Minimum delta trigger (default: 0.70)
        threshold_gain: Minimum ROI % trigger (default: 50.0%)
        today_override: Optional date override for testing

    Returns:
        dict: Portfolio roll audit summary and detailed recommendation objects
    """
    spots = spots or {}
    chains_by_underlier = chains_by_underlier or {}

    recommendations: List[RollRecommendation] = []
    total_extractable_capital = 0.0
    eligible_count = 0

    for opt_id, pos in active_options.items():
        underlier = (pos.get("Underlier") or pos.get("underlier") or "").upper()
        spot = spots.get(underlier) or float(pos.get("Underlier Spot") or pos.get("Strike") or 100.0)

        chain_inst, chain_quotes = None, None
        if underlier in chains_by_underlier:
            chain_inst, chain_quotes = chains_by_underlier[underlier]

        rec = evaluate_position_roll(
            position_data=pos,
            spot=spot,
            chain_instruments=chain_inst,
            chain_quotes=chain_quotes,
            threshold_delta=threshold_delta,
            threshold_gain=threshold_gain,
            today_override=today_override,
        )
        recommendations.append(rec)
        if rec.eligible:
            eligible_count += 1
            if rec.capital_extracted and rec.capital_extracted > 0:
                total_extractable_capital += rec.capital_extracted

    return {
        "total_positions": len(recommendations),
        "eligible_roll_count": eligible_count,
        "total_extractable_capital": round(total_extractable_capital, 2),
        "thresholds": {
            "threshold_delta": threshold_delta,
            "threshold_gain_pct": threshold_gain,
        },
        "recommendations": [r.to_dict() for r in recommendations],
        "recommendation_objects": recommendations,
    }
