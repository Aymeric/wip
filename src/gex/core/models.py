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
            "rule1_derived": self.rule1_derived,
            "rule2_derived": self.rule2_derived,
            "rule7_derived": self.rule7_derived,
            "rule9_derived": self.rule9_derived,
            "rule10_derived": self.rule10_derived,
        }


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
