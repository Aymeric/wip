"""
Automated Portfolio Beta-Weighted Macro Hedging Engine for GEX Options Trading System.

Calculates aggregate portfolio beta-weighted directional delta:
    Delta_{portfolio, SPY} = sum_i (beta_i * Delta_i * (S_i / S_SPY))

Derives optimal index hedge allocations (SPY/QQQ Bear Put Debit Spreads)
linked to Market Regime Gates transitions (Stop 4: Macro / Regime Stop),
preventing premature liquidation of high-conviction structural holds.
"""

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.gex.risk.sizing import is_micro_account

# Typical beta factors relative to SPY
BETA_SECTOR_MAP = {
    "tech": 1.25,
    "semimod": 1.25,
    "semiconductor": 1.25,
    "beta": 1.25,
    "technology": 1.25,
    "cyclical": 1.15,
    "discretion": 1.15,
    "consumer": 1.15,
    "communic": 1.10,
    "social": 1.10,
    "finan": 1.05,
    "bank": 1.05,
    "industr": 1.00,
    "material": 0.90,
    "energy": 0.85,
    "oil": 0.85,
    "resource": 0.85,
    "health": 0.70,
    "pharm": 0.70,
    "biotech": 0.70,
    "estate": 0.65,
    "reit": 0.65,
    "staple": 0.55,
    "defensive": 0.55,
    "utilit": 0.35,
    "bond": 0.40,
    "hyg": 0.40,
    "credit": 0.40,
    "equity": 1.00,
}

# High-profile single-ticker beta overrides
BETA_TICKER_OVERRIDES = {
    "NVDA": 1.75,
    "TSLA": 2.00,
    "AAPL": 1.10,
    "MSFT": 1.15,
    "AMZN": 1.20,
    "META": 1.30,
    "GOOGL": 1.15,
    "GOOG": 1.15,
    "AMD": 1.60,
    "SPY": 1.00,
    "QQQ": 1.20,
    "IWM": 1.15,
    "DIA": 0.85,
}


def get_ticker_or_sector_beta(symbol: str, sector: Optional[str] = None) -> float:
    """
    Returns beta factor relative to SPY based on ticker override or sector tag.
    """
    sym = symbol.upper().strip() if symbol else ""
    if sym in BETA_TICKER_OVERRIDES:
        return BETA_TICKER_OVERRIDES[sym]

    tag = (sector or "equity").lower().strip()
    # Check healthcare/biotech first so "biotech" does not match "tech"
    if "health" in tag or "pharm" in tag or "biotech" in tag:
        return 0.70
    elif "tech" in tag or "semimod" in tag or "semiconductor" in tag or "beta" in tag:
        return 1.25
    elif "finan" in tag or "bank" in tag:
        return 1.05
    elif "energy" in tag or "oil" in tag or "resource" in tag:
        return 0.85
    elif "staple" in tag or "defensive" in tag:
        return 0.55
    elif "utilit" in tag:
        return 0.35
    elif "material" in tag:
        return 0.90
    elif "industr" in tag:
        return 1.00
    elif "cyclical" in tag or "discretion" in tag or "consumer" in tag:
        return 1.15
    elif "communic" in tag or "social" in tag:
        return 1.10
    elif "estate" in tag or "reit" in tag:
        return 0.65
    elif "bond" in tag or "hyg" in tag or "credit" in tag:
        return 0.40
    else:
        return 1.00


@dataclass
class PositionDeltaExposure:
    """Represents the delta and beta-weighted exposure of an individual holding."""
    symbol: str
    asset_type: str  # "Option" or "Stock"
    identifier: str
    quantity: float
    spot: float
    raw_delta: float
    delta_shares: float
    dollar_delta_exposure: float
    sector: str
    beta: float
    beta_weighted_dollar_exposure: float
    spy_equivalent_delta_shares: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "asset_type": self.asset_type,
            "identifier": self.identifier,
            "quantity": self.quantity,
            "spot": self.spot,
            "raw_delta": self.raw_delta,
            "delta_shares": round(self.delta_shares, 2),
            "dollar_delta_exposure": round(self.dollar_delta_exposure, 2),
            "sector": self.sector,
            "beta": round(self.beta, 2),
            "beta_weighted_dollar_exposure": round(self.beta_weighted_dollar_exposure, 2),
            "spy_equivalent_delta_shares": round(self.spy_equivalent_delta_shares, 2),
        }


@dataclass
class HedgePlan:
    """Represents a portfolio-wide beta-weighted macro hedge plan."""
    account: str
    net_liq: float
    cash_buying_power: float
    regime_status: str
    gates_passed: int
    hedge_required: bool
    hedge_status: str  # "NO_HEDGE_NEEDED", "DEFENSIVE_HEDGE", "FULL_MACRO_HEDGE"
    target_coverage_pct: float
    total_portfolio_dollar_delta: float
    total_beta_weighted_dollar_delta: float
    spy_price: float
    spy_equivalent_delta_shares: float
    tech_exposure_pct: float
    recommended_instrument: str  # "SPY" or "QQQ"
    recommended_structure: str  # "BEAR_PUT_SPREAD"
    target_dte: int
    reference_index_price: float
    long_put_strike: float
    short_put_strike: float
    spread_width: float
    net_delta_per_spread: float
    target_delta_shares_to_hedge: float
    target_contracts: int
    estimated_spread_debit: float
    total_estimated_cost: float
    max_protection_pnl: float
    post_hedge_net_delta_shares: float
    is_micro_account: bool
    positions: List[PositionDeltaExposure] = field(default_factory=list)
    hedge_rules: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "account": self.account,
            "net_liq": self.net_liq,
            "cash_buying_power": self.cash_buying_power,
            "regime_status": self.regime_status,
            "gates_passed": self.gates_passed,
            "hedge_required": self.hedge_required,
            "hedge_status": self.hedge_status,
            "target_coverage_pct": round(self.target_coverage_pct, 4),
            "total_portfolio_dollar_delta": round(self.total_portfolio_dollar_delta, 2),
            "total_beta_weighted_dollar_delta": round(self.total_beta_weighted_dollar_delta, 2),
            "spy_price": round(self.spy_price, 2),
            "spy_equivalent_delta_shares": round(self.spy_equivalent_delta_shares, 2),
            "tech_exposure_pct": round(self.tech_exposure_pct, 2),
            "recommended_instrument": self.recommended_instrument,
            "recommended_structure": self.recommended_structure,
            "target_dte": self.target_dte,
            "reference_index_price": round(self.reference_index_price, 2),
            "long_put_strike": self.long_put_strike,
            "short_put_strike": self.short_put_strike,
            "spread_width": round(self.spread_width, 2),
            "net_delta_per_spread": round(self.net_delta_per_spread, 2),
            "target_delta_shares_to_hedge": round(self.target_delta_shares_to_hedge, 2),
            "target_contracts": self.target_contracts,
            "estimated_spread_debit": round(self.estimated_spread_debit, 2),
            "total_estimated_cost": round(self.total_estimated_cost, 2),
            "max_protection_pnl": round(self.max_protection_pnl, 2),
            "post_hedge_net_delta_shares": round(self.post_hedge_net_delta_shares, 2),
            "is_micro_account": self.is_micro_account,
            "positions": [p.to_dict() for p in self.positions],
            "hedge_rules": self.hedge_rules,
            "notes": self.notes,
        }


def calculate_portfolio_beta_delta(
    options_positions: Dict[str, Any],
    stocks_positions: Dict[str, Any],
    spy_price: float,
    spot_overrides: Optional[Dict[str, float]] = None,
) -> Tuple[List[PositionDeltaExposure], float, float, float, float, float]:
    """
    Computes portfolio-wide raw delta, dollar delta, and beta-weighted delta exposure.

    Returns:
        positions_list: List of PositionDeltaExposure for each holding
        total_delta_shares: Unweighted directional delta shares
        total_dollar_delta: Unweighted dollar delta exposure
        total_beta_weighted_dollar_delta: Beta-weighted dollar exposure
        spy_equivalent_delta_shares: Total beta-weighted delta expressed as SPY shares
        tech_exposure_pct: Percentage of beta-weighted dollar delta in Tech/Beta sectors
    """
    positions_list: List[PositionDeltaExposure] = []
    total_delta_shares = 0.0
    total_dollar_delta = 0.0
    total_beta_weighted_dollar_delta = 0.0
    tech_dollar_delta = 0.0

    ref_spy = spy_price if spy_price > 0 else 550.0

    # 1. Evaluate Option Positions
    for opt_id, details in options_positions.items():
        symbol = str(details.get("Underlier", "")).upper()
        if not symbol:
            continue

        contracts = float(details.get("Contracts", 1.0))
        opt_type = str(details.get("Type", "call")).lower()

        # Resolve spot
        spot = None
        if spot_overrides and symbol in spot_overrides:
            spot = spot_overrides[symbol]
        if spot is None:
            spot = details.get("Current Spot") or details.get("Spot")
        if spot is None:
            spot = details.get("Strike", 100.0)
        spot = float(spot) if spot else 100.0

        # Resolve delta
        raw_delta = details.get("Delta")
        if raw_delta is None:
            raw_delta = 0.50 if opt_type == "call" else -0.50
        raw_delta = float(raw_delta)

        # Delta shares: Delta * 100 * contracts
        delta_shares = raw_delta * 100.0 * contracts
        dollar_exposure = delta_shares * spot

        sector = str(details.get("Beta Sector Tag") or details.get("Sector Tag") or "Technology/Beta")
        beta = get_ticker_or_sector_beta(symbol, sector)
        bw_dollar_exposure = dollar_exposure * beta
        spy_equiv_shares = bw_dollar_exposure / ref_spy

        total_delta_shares += delta_shares
        total_dollar_delta += dollar_exposure
        total_beta_weighted_dollar_delta += bw_dollar_exposure

        sec_lower = sector.lower()
        if "tech" in sec_lower or "semimod" in sec_lower or "beta" in sec_lower:
            tech_dollar_delta += bw_dollar_exposure

        positions_list.append(
            PositionDeltaExposure(
                symbol=symbol,
                asset_type="Option",
                identifier=opt_id,
                quantity=contracts,
                spot=spot,
                raw_delta=raw_delta,
                delta_shares=delta_shares,
                dollar_delta_exposure=dollar_exposure,
                sector=sector,
                beta=beta,
                beta_weighted_dollar_exposure=bw_dollar_exposure,
                spy_equivalent_delta_shares=spy_equiv_shares,
            )
        )

    # 2. Evaluate Stock Positions
    for ticker, details in stocks_positions.items():
        symbol = str(ticker).upper()
        shares = float(details.get("Shares", 0.0))
        if shares == 0:
            continue

        avg_price = float(details.get("Average Buy Price", 0.0))
        spot = None
        if spot_overrides and symbol in spot_overrides:
            spot = spot_overrides[symbol]
        if spot is None:
            spot = details.get("Current Price") or details.get("Spot")
        if spot is None:
            spot = avg_price if avg_price > 0 else 100.0
        spot = float(spot)

        raw_delta = 1.0  # 1 share = 1.0 delta
        delta_shares = shares * raw_delta
        dollar_exposure = delta_shares * spot

        sector = str(details.get("Beta Sector Tag") or details.get("Sector Tag") or details.get("sector") or "Equity")
        beta = get_ticker_or_sector_beta(symbol, sector)
        bw_dollar_exposure = dollar_exposure * beta
        spy_equiv_shares = bw_dollar_exposure / ref_spy

        total_delta_shares += delta_shares
        total_dollar_delta += dollar_exposure
        total_beta_weighted_dollar_delta += bw_dollar_exposure

        sec_lower = sector.lower()
        if "tech" in sec_lower or "semimod" in sec_lower or "beta" in sec_lower:
            tech_dollar_delta += bw_dollar_exposure

        positions_list.append(
            PositionDeltaExposure(
                symbol=symbol,
                asset_type="Stock",
                identifier=symbol,
                quantity=shares,
                spot=spot,
                raw_delta=raw_delta,
                delta_shares=delta_shares,
                dollar_delta_exposure=dollar_exposure,
                sector=sector,
                beta=beta,
                beta_weighted_dollar_exposure=bw_dollar_exposure,
                spy_equivalent_delta_shares=spy_equiv_shares,
            )
        )

    spy_equivalent_delta_shares = total_beta_weighted_dollar_delta / ref_spy

    tech_exposure_pct = 0.0
    if total_beta_weighted_dollar_delta > 0:
        tech_exposure_pct = (tech_dollar_delta / total_beta_weighted_dollar_delta) * 100.0

    return (
        positions_list,
        total_delta_shares,
        total_dollar_delta,
        total_beta_weighted_dollar_delta,
        spy_equivalent_delta_shares,
        tech_exposure_pct,
    )


def derive_macro_hedge_plan(
    account: str,
    net_liq: float,
    cash_buying_power: float,
    regime: Dict[str, Any],
    options_positions: Dict[str, Any],
    stocks_positions: Dict[str, Any],
    spy_price: float,
    qqq_price: float,
    target_coverage: Optional[float] = None,
    instrument_choice: str = "AUTO",
    spot_overrides: Optional[Dict[str, float]] = None,
) -> HedgePlan:
    """
    Derives an optimal macro hedge plan based on portfolio beta-weighted delta
    and current Market Regime Gates status.
    """
    ref_spy = spy_price if spy_price > 0 else 550.0
    ref_qqq = qqq_price if qqq_price > 0 else 480.0

    # 1. Compute portfolio exposures
    (
        positions,
        tot_delta_shares,
        tot_dollar_delta,
        tot_bw_dollar_delta,
        spy_equiv_shares,
        tech_exposure_pct,
    ) = calculate_portfolio_beta_delta(options_positions, stocks_positions, ref_spy, spot_overrides)

    # 2. Determine Regime State & Authorization
    regime_status = str(regime.get("system_authorization", "BLOCKED")).upper()
    gates_passed = int(regime.get("gates_passed", 0))

    # Determine automatic coverage if not explicitly overridden
    if target_coverage is not None:
        coverage_pct = max(0.0, min(1.0, float(target_coverage)))
        hedge_required = coverage_pct > 0.0 and spy_equiv_shares > 5.0
        if coverage_pct >= 0.75:
            hedge_status = "FULL_MACRO_HEDGE"
        elif coverage_pct > 0.0:
            hedge_status = "DEFENSIVE_HEDGE"
        else:
            hedge_status = "NO_HEDGE_NEEDED"
    else:
        if "ALL TRACKS OK" in regime_status or gates_passed == 3:
            coverage_pct = 0.0
            hedge_required = False
            hedge_status = "NO_HEDGE_NEEDED"
        elif "TRACK 1 OK" in regime_status or gates_passed == 2 or "DEFENSIVE" in regime_status:
            coverage_pct = 0.50
            hedge_required = spy_equiv_shares > 10.0
            hedge_status = "DEFENSIVE_HEDGE" if hedge_required else "NO_HEDGE_NEEDED"
        else:
            # BLOCKED or Stop 4
            coverage_pct = 1.00
            hedge_required = spy_equiv_shares > 10.0
            hedge_status = "FULL_MACRO_HEDGE" if hedge_required else "NO_HEDGE_NEEDED"

    # If portfolio has net flat or negative delta, no hedge is needed
    if spy_equiv_shares <= 0.0:
        hedge_required = False
        hedge_status = "NO_HEDGE_NEEDED"
        coverage_pct = 0.0

    # 3. Select Hedge Vehicle (SPY vs QQQ)
    chosen_inst = instrument_choice.upper().strip()
    if chosen_inst not in ("SPY", "QQQ"):
        # Auto-detect: if tech/beta exposure >= 50%, prefer QQQ
        if tech_exposure_pct >= 50.0:
            chosen_inst = "QQQ"
        else:
            chosen_inst = "SPY"

    target_ref_price = ref_qqq if chosen_inst == "QQQ" else ref_spy
    equiv_index_delta_shares = tot_bw_dollar_delta / target_ref_price if target_ref_price > 0 else 0.0

    # 4. Bear Put Debit Spread Architecture
    target_dte = 35
    target_delta_shares_to_hedge = equiv_index_delta_shares * coverage_pct if hedge_required else 0.0

    # Long Put (~ -0.35 Delta, ~2.0% OTM)
    long_put_strike = round(target_ref_price * 0.98, 0)
    # Short Put (~ -0.15 Delta, ~5.0% OTM)
    short_put_strike = round(target_ref_price * 0.95, 0)

    spread_width = max(5.0, long_put_strike - short_put_strike)
    # Adjust short put strike if width adjusted
    short_put_strike = long_put_strike - spread_width

    # Vertical put spread net delta ~ -0.20 per share (-20 delta shares per contract)
    net_delta_per_spread = -0.20
    contract_delta_shares = abs(net_delta_per_spread) * 100.0  # 20.0 shares

    # Typical 30-45 DTE 35/15 debit spread cost ~28% of spread width
    estimated_spread_debit = round(spread_width * 0.28, 2)

    # Contract sizing
    notes: List[str] = []
    micro = is_micro_account(net_liq)

    if hedge_required and target_delta_shares_to_hedge >= 10.0:
        raw_contracts = target_delta_shares_to_hedge / contract_delta_shares
        target_contracts = max(1, round(raw_contracts))
    else:
        target_contracts = 0

    # Budget checks & Micro-Account Guardrails
    cost_per_contract = estimated_spread_debit * 100.0
    total_cost = target_contracts * cost_per_contract

    if micro:
        notes.append("Micro-Account status active (< $10,000 Net Liq): exempt from percentage hedge caps.")
        if target_contracts > 1:
            notes.append(f"Downsized hedge allocation from {target_contracts} to 1-contract minimum for micro-account.")
            target_contracts = 1
            total_cost = target_contracts * cost_per_contract

        if cash_buying_power < total_cost and target_contracts > 0:
            target_contracts = 0
            total_cost = 0.0
            notes.append(f"Hedge execution blocked: Cash buying power (${cash_buying_power:,.2f}) insufficient for 1 contract (${cost_per_contract:,.2f}).")
    else:
        # Standard Account: Cap hedge outlay at 3.0% of Net Liq to prevent hedge drag
        max_hedge_budget = net_liq * 0.03
        if total_cost > max_hedge_budget and target_contracts > 1:
            capped_contracts = max(1, int(max_hedge_budget / cost_per_contract))
            notes.append(f"Hedge outlay capped at 3.0% Net Liq (${max_hedge_budget:,.2f}): adjusted from {target_contracts} to {capped_contracts} contracts.")
            target_contracts = capped_contracts
            total_cost = target_contracts * cost_per_contract

    max_protection_pnl = (spread_width - estimated_spread_debit) * 100.0 * target_contracts if target_contracts > 0 else 0.0
    post_hedge_delta_shares = equiv_index_delta_shares - (target_contracts * contract_delta_shares)

    # 5. Define Operational Hedge Rules
    hedge_rules = [
        "Rule H-1 (Regime Re-Authorization): Close hedge spread if Daily Regime Gates re-authorize to ALL TRACKS OK (3/3 gates pass).",
        f"Rule H-2 (Target Profit Harvest): Take profit if {chosen_inst} touches short strike (${short_put_strike:.2f}) or spread captures >= 75% max width.",
        "Rule H-3 (Theta Roll Gate): Roll forward to 30-45 DTE if DTE <= 14 days and regime remains blocked/defensive.",
        f"Rule H-4 (Defined Max Loss): 100% defined risk; max possible loss is strictly capped at initial debit paid (${total_cost:,.2f}).",
    ]

    return HedgePlan(
        account=account,
        net_liq=net_liq,
        cash_buying_power=cash_buying_power,
        regime_status=regime_status,
        gates_passed=gates_passed,
        hedge_required=hedge_required,
        hedge_status=hedge_status,
        target_coverage_pct=coverage_pct,
        total_portfolio_dollar_delta=tot_dollar_delta,
        total_beta_weighted_dollar_delta=tot_bw_dollar_delta,
        spy_price=ref_spy,
        spy_equivalent_delta_shares=spy_equiv_shares,
        tech_exposure_pct=tech_exposure_pct,
        recommended_instrument=chosen_inst,
        recommended_structure="BEAR_PUT_SPREAD",
        target_dte=target_dte,
        reference_index_price=target_ref_price,
        long_put_strike=long_put_strike,
        short_put_strike=short_put_strike,
        spread_width=spread_width,
        net_delta_per_spread=net_delta_per_spread,
        target_delta_shares_to_hedge=target_delta_shares_to_hedge,
        target_contracts=target_contracts,
        estimated_spread_debit=estimated_spread_debit,
        total_estimated_cost=total_cost,
        max_protection_pnl=max_protection_pnl,
        post_hedge_net_delta_shares=post_hedge_delta_shares,
        is_micro_account=micro,
        positions=positions,
        hedge_rules=hedge_rules,
        notes=notes,
    )
