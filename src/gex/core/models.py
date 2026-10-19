"""
Domain models for the GEX Options Trading System.
Provides strongly typed dataclasses for positions, quotes, GEX profiles,
regime gates, sentiments, and candidate underliers with validation and
boundary ingestion adapters.
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

    @classmethod
    def from_robinhood(cls, quote_data: Dict[str, Any], instrument_data: Optional[Dict[str, Any]] = None) -> "OptionQuote":
        """Constructs an OptionQuote from raw Robinhood API quotes and optional instrument payloads."""
        quote = quote_data.get("quote", quote_data) if isinstance(quote_data, dict) else {}
        inst = instrument_data or {}
        if not inst and isinstance(quote_data, dict) and "instrument" in quote_data:
            inst = quote_data["instrument"]

        inst_id = str(quote.get("instrument_id") or inst.get("id") or "")
        strike = float(inst.get("strike_price") or quote.get("strike_price") or 0.0)
        option_type = str(inst.get("type") or quote.get("type") or "call").lower()
        exp_date = str(inst.get("expiration_date") or quote.get("expiration_date") or "")

        bid = float(quote.get("bid_price") or 0.0)
        ask = float(quote.get("ask_price") or 0.0)
        mark = float(quote.get("adjusted_mark_price") or quote.get("mark_price") or ((bid + ask) / 2.0 if (bid + ask) > 0 else 0.0))
        oi = int(quote.get("open_interest") or 0)

        greeks = quote.get("greeks") if isinstance(quote.get("greeks"), dict) else quote
        raw_gamma = greeks.get("gamma")
        raw_delta = greeks.get("delta")
        raw_iv = quote.get("implied_volatility") or greeks.get("implied_volatility")

        gamma = float(raw_gamma) if raw_gamma is not None else 0.0
        delta = float(raw_delta) if raw_delta is not None else None
        iv = float(raw_iv) if raw_iv is not None else 0.0

        dte = 0
        if exp_date:
            try:
                exp_dt = date.fromisoformat(exp_date[:10])
                dte = max((exp_dt - date.today()).days, 0)
            except Exception:
                pass

        return cls(
            instrument_id=inst_id,
            strike=strike,
            option_type=option_type,
            expiration_date=exp_date,
            bid=bid,
            ask=ask,
            mark=mark,
            open_interest=oi,
            gamma=gamma,
            delta=delta,
            implied_volatility=iv,
            dte=dte,
        )


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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScannerCandidate":
        """Constructs a ScannerCandidate from a dictionary representation."""
        return cls(
            symbol=str(data.get("symbol") or data.get("ticker") or "").upper(),
            price=float(data.get("price") or data.get("current_price") or 0.0),
            chg_pct=float(data.get("chg_pct") or data.get("percent_change") or 0.0),
            source=str(data.get("source") or "scanner"),
            iv=float(data["iv"]) if data.get("iv") is not None else None,
            relative_options_volume=float(data["relative_options_volume"]) if data.get("relative_options_volume") is not None else None,
            market_cap=float(data["market_cap"]) if data.get("market_cap") is not None else None,
            rsi=float(data["rsi"]) if data.get("rsi") is not None else None,
            macd_hist=float(data["macd_hist"]) if data.get("macd_hist") is not None else None,
        )


@dataclass(slots=True)
class RegimeGates:
    """Represents the daily market regime gates and authorization."""
    basket_gate: str
    bull_bear_ratio: float
    bull_bear_gate: str
    vix_delta_gate: str
    system_authorization: str
    gates_passed: int

    def validate(self) -> bool:
        """Validates internal gates metrics."""
        if self.basket_gate not in ("PASS", "FAIL"):
            raise ValueError(f"Invalid basket_gate: {self.basket_gate}")
        if self.bull_bear_gate not in ("PASS", "FAIL"):
            raise ValueError(f"Invalid bull_bear_gate: {self.bull_bear_gate}")
        if self.vix_delta_gate not in ("PASS", "FAIL"):
            raise ValueError(f"Invalid vix_delta_gate: {self.vix_delta_gate}")
        if not (0 <= self.gates_passed <= 3):
            raise ValueError(f"Invalid gates_passed: {self.gates_passed}")
        if self.bull_bear_ratio < 0:
            raise ValueError(f"Invalid bull_bear_ratio: {self.bull_bear_ratio}")
        return True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RegimeGates":
        """Constructs RegimeGates from a dictionary representation."""
        return cls(
            basket_gate=str(data.get("basket_gate", "FAIL")),
            bull_bear_ratio=float(data.get("bull_bear_ratio", 0.0)),
            bull_bear_gate=str(data.get("bull_bear_gate", "FAIL")),
            vix_delta_gate=str(data.get("vix_delta_gate", "FAIL")),
            system_authorization=str(data.get("system_authorization", "BLOCKED")),
            gates_passed=int(data.get("gates_passed", 0)),
        )


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
class OptionPosition:
    """Represents an active single-leg options contract holding."""
    option_id: str
    underlier: str
    strike: float
    expiration: str
    type: str  # 'call' or 'put'
    purchase_premium: float
    mark_price: float
    days_held: int
    stalling_days: int
    target_mode: str = "T1"
    t2_target: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    open_interest: Optional[int] = None
    imp_vol: Optional[float] = None
    beta_sector_tag: str = "Technology/Beta"
    entry_date: Optional[str] = None

    def validate(self) -> bool:
        """Validates option position parameters."""
        if not self.option_id:
            raise ValueError("option_id cannot be empty")
        if not self.underlier:
            raise ValueError("underlier cannot be empty")
        if self.strike <= 0:
            raise ValueError(f"strike must be positive: {self.strike}")
        if self.type.lower() not in ("call", "put"):
            raise ValueError(f"type must be 'call' or 'put': {self.type}")
        if self.purchase_premium <= 0:
            raise ValueError(f"purchase_premium must be positive: {self.purchase_premium}")
        if self.mark_price < 0:
            raise ValueError(f"mark_price cannot be negative: {self.mark_price}")
        if self.days_held < 1:
            raise ValueError(f"days_held must be >= 1: {self.days_held}")
        if self.stalling_days < 0:
            raise ValueError(f"stalling_days must be >= 0: {self.stalling_days}")
        if self.target_mode not in ("T1", "T2"):
            raise ValueError(f"target_mode must be 'T1' or 'T2': {self.target_mode}")
        if not self.expiration:
            raise ValueError("expiration cannot be empty")
        try:
            datetime.strptime(self.expiration, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"expiration must be a valid date in YYYY-MM-DD format: {self.expiration}")
        if self.entry_date:
            try:
                datetime.strptime(self.entry_date, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"entry_date must be a valid date in YYYY-MM-DD format: {self.entry_date}")
        return True

    @classmethod
    def from_dict(cls, data: Dict[str, Any], option_id: str = "") -> "OptionPosition":
        """Constructs an OptionPosition from dict supporting snake_case and UI-formatted keys."""
        oid = str(data.get("option_id") or data.get("Option ID") or option_id or "")
        underlier = str(data.get("underlier") or data.get("Underlier") or "").upper()
        strike = float(data.get("strike") or data.get("Strike") or 0.0)
        exp = str(data.get("expiration") or data.get("Expiration") or "")
        opt_type = str(data.get("type") or data.get("Type") or "call").lower()
        purchase_premium = float(data.get("purchase_premium") or data.get("Purchase Premium") or 0.0)
        mark = float(data.get("mark_price") or data.get("Mark Price") or data.get("mark") or 0.0)
        days_held = int(data.get("days_held") or data.get("Days Held") or 1)
        stalling = int(data.get("stalling_days") or data.get("Stalling Days") or 0)
        target_mode = str(data.get("target_mode") or data.get("Target Mode") or "T1")

        raw_delta = data.get("delta") or data.get("Delta")
        raw_gamma = data.get("gamma") or data.get("Gamma")
        raw_oi = data.get("open_interest") or data.get("Open Interest")
        raw_iv = data.get("imp_vol") or data.get("Implied Volatility") or data.get("iv")

        return cls(
            option_id=oid,
            underlier=underlier,
            strike=strike,
            expiration=exp,
            type=opt_type,
            purchase_premium=purchase_premium,
            mark_price=mark,
            days_held=days_held,
            stalling_days=stalling,
            target_mode=target_mode,
            t2_target=float(data["t2_target"]) if data.get("t2_target") is not None else None,
            delta=float(raw_delta) if raw_delta is not None else None,
            gamma=float(raw_gamma) if raw_gamma is not None else None,
            open_interest=int(raw_oi) if raw_oi is not None else None,
            imp_vol=float(raw_iv) if raw_iv is not None else None,
            beta_sector_tag=str(data.get("beta_sector_tag") or data.get("Sector Tag") or "Technology/Beta"),
            entry_date=data.get("entry_date") or data.get("Entry Date"),
        )


@dataclass(slots=True)
class StockPosition:
    """Represents an active equity holding."""
    ticker: str
    shares: float
    average_buy_price: float
    current_price: float
    beta_sector_tag: str = "Equity"
    entry_date: Optional[str] = None
    asset_cost_basis: float = 0.0
    current_value: float = 0.0
    highest_price: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    profit_target_pct: Optional[float] = None

    def validate(self) -> bool:
        """Validates stock position parameters."""
        if not self.ticker:
            raise ValueError("ticker cannot be empty")
        if self.shares <= 0:
            raise ValueError(f"shares must be positive: {self.shares}")
        if self.average_buy_price <= 0:
            raise ValueError(f"average_buy_price must be positive: {self.average_buy_price}")
        if self.current_price < 0:
            raise ValueError(f"current_price cannot be negative: {self.current_price}")
        if self.highest_price is not None and self.highest_price < 0:
            raise ValueError(f"highest_price cannot be negative: {self.highest_price}")
        if self.trailing_stop_pct is not None and self.trailing_stop_pct <= 0:
            raise ValueError(f"trailing_stop_pct must be positive: {self.trailing_stop_pct}")
        if self.stop_loss_pct is not None and self.stop_loss_pct <= 0:
            raise ValueError(f"stop_loss_pct must be positive: {self.stop_loss_pct}")
        if self.profit_target_pct is not None and self.profit_target_pct <= 0:
            raise ValueError(f"profit_target_pct must be positive: {self.profit_target_pct}")
        if self.entry_date:
            try:
                datetime.strptime(self.entry_date, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"entry_date must be a valid date in YYYY-MM-DD format: {self.entry_date}")
        return True

    @classmethod
    def from_dict(cls, data: Dict[str, Any], ticker: str = "") -> "StockPosition":
        """Constructs a StockPosition from dict supporting snake_case and UI-formatted keys."""
        sym = str(data.get("ticker") or data.get("symbol") or ticker or "").upper()
        shares = float(data.get("shares") or data.get("quantity") or 0.0)
        avg_price = float(data.get("average_buy_price") or data.get("avg_buy_price") or data.get("cost_basis", 0.0) / max(shares, 1.0))
        cur_price = float(data.get("current_price") or data.get("price") or 0.0)
        cost_basis = float(data.get("asset_cost_basis") or data.get("cost_basis") or (shares * avg_price))
        cur_val = float(data.get("current_value") or (shares * cur_price))

        return cls(
            ticker=sym,
            shares=shares,
            average_buy_price=avg_price,
            current_price=cur_price,
            beta_sector_tag=str(data.get("beta_sector_tag") or data.get("sector") or "Equity"),
            entry_date=data.get("entry_date") or data.get("Entry Date"),
            asset_cost_basis=cost_basis,
            current_value=cur_val,
            highest_price=float(data["highest_price"]) if data.get("highest_price") is not None else None,
            trailing_stop_pct=float(data["trailing_stop_pct"]) if data.get("trailing_stop_pct") is not None else None,
            stop_loss_pct=float(data["stop_loss_pct"]) if data.get("stop_loss_pct") is not None else None,
            profit_target_pct=float(data["profit_target_pct"]) if data.get("profit_target_pct") is not None else None,
        )


@dataclass(slots=True)
class OptionSentiment:
    """Represents a 5-factor retail sentiment profile for an underlier."""
    ticker: str
    sentiment: float
    buzz: str  # 'High', 'Medium', 'Low', 'None'
    narrative: str
    last_updated: Optional[str] = field(default=None)
    tone_score: float = field(default=0.0)
    comments_score: float = field(default=0.0)
    position_score: float = field(default=0.0)
    volume_score: float = field(default=0.0)
    meme_score: float = field(default=0.0)

    def validate(self) -> bool:
        """Validates sentiment parameters."""
        if not self.ticker:
            raise ValueError("ticker cannot be empty")
        if not (-1.0 <= self.sentiment <= 1.0):
            raise ValueError(f"sentiment must be between -1.0 and +1.0: {self.sentiment}")
        if self.buzz not in ("High", "Medium", "Low", "None", "Med"):
            raise ValueError(f"buzz must be High, Medium, Low, or None: {self.buzz}")

        # Validate 5-factor score subranges
        if not (-0.301 <= self.tone_score <= 0.301):
            raise ValueError(f"tone_score must be between -0.30 and +0.30: {self.tone_score}")
        if not (-0.301 <= self.comments_score <= 0.301):
            raise ValueError(f"comments_score must be between -0.30 and +0.30: {self.comments_score}")
        if not (-0.201 <= self.position_score <= 0.201):
            raise ValueError(f"position_score must be between -0.20 and +0.20: {self.position_score}")
        if not (-0.101 <= self.volume_score <= 0.101):
            raise ValueError(f"volume_score must be between -0.10 and +0.10: {self.volume_score}")
        if not (-0.101 <= self.meme_score <= 0.101):
            raise ValueError(f"meme_score must be between -0.10 and +0.10: {self.meme_score}")

        components_sum = self.tone_score + self.comments_score + self.position_score + self.volume_score + self.meme_score
        if abs(components_sum) > 0.001:
            if abs(components_sum - self.sentiment) > 0.021:
                raise ValueError(f"The sum of the 5-factors ({components_sum:+.2f}) must match the overall sentiment score ({self.sentiment:+.2f}) within ±0.02.")

        return True

    @classmethod
    def from_dict(cls, data: Dict[str, Any], ticker: str = "") -> "OptionSentiment":
        """Constructs OptionSentiment from dictionary representation."""
        return cls(
            ticker=str(data.get("ticker") or ticker or "").upper(),
            sentiment=float(data.get("sentiment", 0.0)),
            buzz=str(data.get("buzz", "None")),
            narrative=str(data.get("narrative", "")),
            last_updated=data.get("last_updated"),
            tone_score=float(data.get("tone_score", 0.0)),
            comments_score=float(data.get("comments_score", 0.0)),
            position_score=float(data.get("position_score", 0.0)),
            volume_score=float(data.get("volume_score", 0.0)),
            meme_score=float(data.get("meme_score", 0.0)),
        )


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
