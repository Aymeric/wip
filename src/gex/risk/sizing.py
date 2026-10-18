"""
Position sizing and risk allocation module for GEX Options Trading System.
Implements the Portfolio Sizing Threshold and Micro-Account Rules:
- Standard Accounts (Net Liq >= $10,000):
    - Single-Leg Sizing Limit: <= 3.0% to 5.0% of Net Liq
    - Sector Concentration Cap: <= 15.0% of Net Liq
- Micro-Accounts (Net Liq < $10,000, e.g. ••••9961):
    - Percentage caps are marked EXEMPT
    - Sized for a 1-contract minimum allocation, bounded strictly by available cash buying power.
"""

from typing import Dict, Any, Optional

MICRO_ACCOUNT_NET_LIQ_THRESHOLD = 10000.0
DEFAULT_SINGLE_LEG_MAX_PCT = 0.03
DEFAULT_SECTOR_MAX_PCT = 0.15


def is_micro_account(net_liq: float) -> bool:
    """Returns True if the portfolio is classified as a Micro-Account (< $10,000)."""
    return net_liq < MICRO_ACCOUNT_NET_LIQ_THRESHOLD


def calculate_position_sizing(
    net_liq: float,
    cash_buying_power: float,
    contract_premium: float,
    sector_exposure: float = 0.0,
    single_leg_cap_pct: float = DEFAULT_SINGLE_LEG_MAX_PCT,
    sector_cap_pct: float = DEFAULT_SECTOR_MAX_PCT,
) -> Dict[str, Any]:
    """
    Calculates permissible contract count and sizing clearance.

    Args:
        net_liq: Portfolio Net Liquidation value in USD.
        cash_buying_power: Available cash buying power in USD.
        contract_premium: Price per share of option contract (total cost = premium * 100).
        sector_exposure: Current cost basis invested in this sector.
        single_leg_cap_pct: Max percentage allocation per trade for standard accounts (default: 0.03).
        sector_cap_pct: Max sector concentration percentage for standard accounts (default: 0.15).

    Returns:
        dict: Sizing budget, max allowed contracts, and compliance statuses.
    """
    cost_per_contract = contract_premium * 100.0 if contract_premium > 0 else 0.0
    micro = is_micro_account(net_liq)

    if cost_per_contract <= 0:
        return {
            "is_micro_account": micro,
            "max_contracts": 0,
            "cost_per_contract": 0.0,
            "total_budget": 0.0,
            "sizing_status": "BLOCKED",
            "reason": "Invalid or zero contract premium",
            "single_leg_limit_status": "PASS",
            "sector_limit_status": "PASS",
        }

    if micro:
        # Micro-Account rules: EXEMPT from percentage constraints; 1-contract minimum bounded by cash
        can_afford = cash_buying_power >= cost_per_contract
        max_contracts = 1 if can_afford else 0
        status = "PASS" if can_afford else "FAIL (Insufficient Buying Power)"
        reason = "Micro-Account (1-contract allocation bounded by cash)" if can_afford else "Cash buying power below 1-contract cost"

        return {
            "is_micro_account": True,
            "max_contracts": max_contracts,
            "cost_per_contract": cost_per_contract,
            "total_budget": cost_per_contract if can_afford else 0.0,
            "sizing_status": status,
            "reason": reason,
            "single_leg_limit_status": "EXEMPT",
            "sector_limit_status": "EXEMPT",
        }

    # Standard Account rules (Net Liq >= $10,000)
    single_leg_budget = net_liq * single_leg_cap_pct
    sector_remaining = max(0.0, (net_liq * sector_cap_pct) - sector_exposure)
    effective_budget = min(single_leg_budget, sector_remaining, cash_buying_power)

    max_contracts = int(effective_budget // cost_per_contract) if cost_per_contract > 0 else 0

    single_leg_pass = cost_per_contract <= single_leg_budget if max_contracts > 0 else True
    sector_pass = (sector_exposure + (max_contracts * cost_per_contract)) <= (net_liq * sector_cap_pct)

    status = "PASS" if max_contracts >= 1 else "FAIL (Budget or Sizing Limit Exceeded)"

    return {
        "is_micro_account": False,
        "max_contracts": max_contracts,
        "cost_per_contract": cost_per_contract,
        "total_budget": max_contracts * cost_per_contract,
        "single_leg_budget": single_leg_budget,
        "sector_remaining_budget": sector_remaining,
        "sizing_status": status,
        "single_leg_limit_status": "PASS" if single_leg_pass else "FAIL",
        "sector_limit_status": "PASS" if sector_pass else "FAIL",
    }
