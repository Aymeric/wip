"""
Domain models for the GEX Options Trading System.
Provides strongly typed dataclasses for positions, quotes, GEX profiles, and candidate underliers.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Any


@dataclass(slots=True)
class OptionQuote:
    """Represents a standardized option quote from broker or feed."""
    instrument_id: str
    strike: float
    option_type: str  # "call" or "put"
    expiration_date: str
    bid: float = 0.0
    ask: float = 0.0
    mark: float = 0.0
    open_interest: int = 0
    gamma: float = 0.0
    delta: Optional[float] = None
    implied_volatility: float = 0.0
    dte: int = 0


@dataclass(slots=True)
class GexProfile:
    """Represents dealer gamma positioning metrics derived from option chains."""
    spot: float
    total_oi: int
    derived_cotmp: float
    derived_ptrans: Optional[float]
    derived_ntrans: Optional[float]
    derived_gex: Optional[float]
    total_call_gex: float
    total_put_gex: float
    effective_call_gex: float = 0.0
    effective_put_gex: float = 0.0
    net_gex: float = 0.0
    net_effective_gex: float = 0.0
    iv_sum: float = 0.0
    iv_count: int = 0
    flip_strikes: List[float] = field(default_factory=list)
    put_wall: Optional[float] = None
    rule1_derived: bool = False
    rule2_derived: bool = False
    rule7_derived: bool = False
    rule9_derived: bool = False
    rule10_derived: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Converts GexProfile to dictionary representation for backward compatibility."""
        return {
            "total_oi": self.total_oi,
            "iv_sum": self.iv_sum,
            "iv_count": self.iv_count,
            "derived_cotmp": self.derived_cotmp,
            "derived_ptrans": self.derived_ptrans,
            "derived_ntrans": self.derived_ntrans,
            "derived_gex": self.derived_gex,
            "total_call_gex": self.total_call_gex,
            "total_put_gex": self.total_put_gex,
            "effective_call_gex": self.effective_call_gex,
            "effective_put_gex": self.effective_put_gex,
            "net_gex": self.net_gex,
            "net_effective_gex": self.net_effective_gex,
            "flip_strikes": list(self.flip_strikes),
            "put_wall": self.put_wall,
            "rule1_derived": self.rule1_derived,
            "rule2_derived": self.rule2_derived,
            "rule7_derived": self.rule7_derived,
            "rule9_derived": self.rule9_derived,
            "rule10_derived": self.rule10_derived,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], spot: float = 0.0) -> "GexProfile":
        """Reconstructs a GexProfile instance from a dictionary representation."""
        ptrans = data.get("derived_ptrans")
        ntrans = data.get("derived_ntrans")
        dgex = data.get("derived_gex")
        pwall = data.get("put_wall")
        raw_flips = data.get("flip_strikes") or []
        return cls(
            spot=float(data.get("spot", spot)),
            total_oi=int(data.get("total_oi", 0)),
            derived_cotmp=float(data.get("derived_cotmp", 0.0)),
            derived_ptrans=float(ptrans) if ptrans is not None else None,
            derived_ntrans=float(ntrans) if ntrans is not None else None,
            derived_gex=float(dgex) if dgex is not None else None,
            total_call_gex=float(data.get("total_call_gex", 0.0)),
            total_put_gex=float(data.get("total_put_gex", 0.0)),
            effective_call_gex=float(data.get("effective_call_gex", 0.0)),
            effective_put_gex=float(data.get("effective_put_gex", 0.0)),
            net_gex=float(data.get("net_gex", 0.0)),
            net_effective_gex=float(data.get("net_effective_gex", 0.0)),
            iv_sum=float(data.get("iv_sum", 0.0)),
            iv_count=int(data.get("iv_count", 0)),
            flip_strikes=[float(s) for s in raw_flips],
            put_wall=float(pwall) if pwall is not None else None,
            rule1_derived=bool(data.get("rule1_derived", False)),
            rule2_derived=bool(data.get("rule2_derived", False)),
            rule7_derived=bool(data.get("rule7_derived", False)),
            rule9_derived=bool(data.get("rule9_derived", False)),
            rule10_derived=bool(data.get("rule10_derived", False)),
        )


@dataclass(slots=True)
class ScannerCandidate:
    """Represents an underlier discovered by market scanners."""
    symbol: str
    price: float
    chg_pct: float
    source: str = "scanner"
    iv: Optional[float] = None
    relative_options_volume: Optional[float] = None
    market_cap: Optional[float] = None
    rsi: Optional[float] = None
    macd_hist: Optional[float] = None


@dataclass(slots=True)
class RegimeStatus:
    """Represents the daily market regime gates."""
    basket_gate: str          # "PASS" or "FAIL"
    bull_bear_ratio: float
    bull_bear_gate: str       # "PASS" or "FAIL"
    vix_delta_gate: str       # "PASS" or "FAIL"
    system_authorization: str  # e.g. "ALL TRACKS OK", "TRACK 1 OK", "DEFENSIVE"
    updated_at: Optional[str] = None


@dataclass(slots=True)
class Position:
    """Represents an active or tracked holding (equity or single-leg option)."""
    symbol: str
    asset_type: str  # "option" or "stock"
    quantity: float
    avg_buy_price: float
    current_spot: float
    mark_price: float
    cost_basis: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    exit_rule_state: str = "HOLD"
    proposed_action: str = "No Action"
    strike: Optional[float] = None
    expiration_date: Optional[str] = None
    dte: Optional[int] = None
    option_type: Optional[str] = None  # "call" or "put"
    account: Optional[str] = None


@dataclass(slots=True)
class TradeRecord:
    """Represents a closed transaction in the trade journal."""
    trade_id: str
    symbol: str
    asset_type: str  # "option" or "stock"
    entry_price: float
    exit_price: float
    quantity: float
    realized_pnl: float
    realized_pnl_pct: float
    opened_at: Optional[str] = None
    closed_at: Optional[str] = None
    holding_days: int = 0
    exit_reason: str = "MANUAL"
    target_mode: str = "T1"
    account: Optional[str] = None

