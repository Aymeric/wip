"""
Pre-Earnings Vega Run-Up Harvester.
Systematically scans, prices, and models pre-earnings implied volatility run-ups
between 25 and 15 calendar days before scheduled earnings with IV Rank <= 40%,
enforcing a mandatory exit date exactly 14 calendar days before earnings (Rule 7).
"""

from datetime import date, datetime, timedelta, timezone
import math
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from src.gex.core.config import (
    CANDIDATES_FILE,
    DOWNLOADS_DIR,
    validate_safe_path,
)
from src.gex.storage.persistence import load_json
from src.gex.core.models import PreEarningsCandidate
from src.gex.quant.greeks import calculate_black_scholes_vega
from src.gex.quant.indicators import calculate_iv_percentile, calculate_iv_rank


def _parse_date(val: Any) -> Optional[date]:
    """Parse a date string or timestamp into a date object."""
    if not val:
        return None
    if isinstance(val, (datetime, date)):
        return val if isinstance(val, date) else val.date()
    val_str = str(val).strip()
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", val_str)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def calculate_pre_earnings_vega_setup(
    symbol: str,
    spot: float,
    earnings_date: str,
    session_date: str,
    current_iv: float,
    historical_ivs: Sequence[float],
    min_days: int = 15,
    max_days: int = 25,
    max_iv_rank: float = 40.0,
    option_strike: Optional[float] = None,
    option_dte: int = 35,
    option_ask: Optional[float] = None,
    option_expiration: Optional[str] = None,
) -> Optional[PreEarningsCandidate]:
    """
    Evaluates an individual underlier for the Pre-Earnings Vega Run-Up setup.

    Args:
        symbol: Underlier ticker symbol (e.g. AAPL)
        spot: Current stock spot price
        earnings_date: Scheduled earnings report date (YYYY-MM-DD)
        session_date: Effective analysis session date (YYYY-MM-DD)
        current_iv: Current 30-day ATM implied volatility (e.g. 0.30 for 30%)
        historical_ivs: Historical daily IV series for IV Rank calculation
        min_days: Minimum calendar days to earnings (default: 15)
        max_days: Maximum calendar days to earnings (default: 25)
        max_iv_rank: Maximum permissible IV Rank (default: 40.0%)
        option_strike: Strike price of target call contract (defaults to ATM spot)
        option_dte: Days to expiration of target contract (defaults to 35 DTE)
        option_ask: Per-share premium of target contract (defaults to estimated ~4% spot)
        option_expiration: Target contract expiration string (YYYY-MM-DD)

    Returns:
        PreEarningsCandidate if the setup meets all criteria, or None.
    """
    if spot <= 0 or current_iv <= 0:
        return None

    earn_dt = _parse_date(earnings_date)
    sess_dt = _parse_date(session_date)
    if not earn_dt or not sess_dt:
        return None

    days_to_earnings = (earn_dt - sess_dt).days
    # Gate 1: 15 to 25 calendar days window before earnings
    if not (min_days <= days_to_earnings <= max_days):
        return None

    # Gate 2: Calculate IV Rank & Percentile
    iv_rank = calculate_iv_rank(current_iv, historical_ivs)
    iv_percentile = calculate_iv_percentile(current_iv, historical_ivs)

    # If valid IV Rank exists, ensure it is <= max_iv_rank (volatility not yet priced in)
    if iv_rank is not None and iv_rank > max_iv_rank:
        return None

    # Mandatory Exit Date: Exactly 14 calendar days before earnings (Rule 7 blackout boundary)
    mandatory_exit_dt = earn_dt - timedelta(days=14)
    mandatory_exit_date = mandatory_exit_dt.strftime("%Y-%m-%d")

    # Target Contract Specification
    strike = option_strike if (option_strike and option_strike > 0) else round(spot, 2)
    dte = max(1, option_dte)
    if not option_expiration:
        exp_dt = sess_dt + timedelta(days=dte)
        option_expiration = exp_dt.strftime("%Y-%m-%d")

    # Analytical Black-Scholes Vega
    vega = calculate_black_scholes_vega(spot=spot, strike=strike, dte_days=dte, iv=current_iv)

    # Implied Volatility Expansion Modeling
    valid_hist = [x for x in historical_ivs if x is not None and x > 0 and math.isfinite(x)]
    if valid_hist:
        historical_high_iv = max(valid_hist)
        # Project expansion capturing 50% of range towards historical high, minimum +5% vol
        projected_expansion = max(0.05, (historical_high_iv - current_iv) * 0.50)
        projected_iv_target = current_iv + projected_expansion
    else:
        historical_high_iv = current_iv * 1.50
        projected_expansion = current_iv * 0.25  # +25% relative expansion
        projected_iv_target = current_iv + projected_expansion

    # Projected Vega PnL ($ per contract = Vega * Delta_IV * 100 shares)
    projected_vega_pnl = vega * projected_expansion * 100.0

    # Option premium estimate (per share)
    ask = option_ask if (option_ask and option_ask > 0) else max(0.50, round(spot * 0.04, 2))
    contract_cost = ask * 100.0

    projected_return_pct = (projected_vega_pnl / contract_cost) * 100.0 if contract_cost > 0 else 0.0

    return PreEarningsCandidate(
        symbol=symbol.upper(),
        spot=spot,
        earnings_date=earn_dt.strftime("%Y-%m-%d"),
        days_to_earnings=days_to_earnings,
        mandatory_exit_date=mandatory_exit_date,
        current_iv=current_iv,
        iv_rank=iv_rank,
        iv_percentile=iv_percentile,
        historical_high_iv=historical_high_iv,
        projected_iv_target=projected_iv_target,
        projected_iv_expansion=projected_expansion,
        option_strike=strike,
        option_expiration=option_expiration,
        option_dte=dte,
        option_vega=vega,
        option_ask=ask,
        projected_vega_pnl=projected_vega_pnl,
        projected_return_pct=projected_return_pct,
        setup_grade="CONFIRMED",
    )


def scan_pre_earnings_candidates(
    symbols: Optional[Sequence[str]] = None,
    session_date: Optional[str] = None,
    min_days: int = 15,
    max_days: int = 25,
    max_iv_rank: float = 40.0,
    downloads_dir: Optional[str] = None,
    candidates_file: Optional[str] = None,
    strict_iv_rank: bool = False,
) -> List[PreEarningsCandidate]:
    """
    Scans candidate underliers and identifies setups entering the Pre-Earnings Vega Run-Up ramp.

    Args:
        symbols: Optional list of tickers to scan (defaults to candidate_stocks.json universe)
        session_date: Analysis date (defaults to current UTC date)
        min_days: Minimum days to earnings (default: 15)
        max_days: Maximum days to earnings (default: 25)
        max_iv_rank: Upper limit for baseline IV Rank (default: 40.0)
        downloads_dir: Directory containing market data downloads
        candidates_file: Path to candidate_stocks.json
        strict_iv_rank: If True, excludes underliers with insufficient historical IV for IV Rank

    Returns:
        List[PreEarningsCandidate] sorted by projected_return_pct descending.
    """
    import src.gex_engine as ge

    effective_downloads = downloads_dir or getattr(ge, "DOWNLOADS_DIR", DOWNLOADS_DIR)
    effective_cand_file = candidates_file or getattr(ge, "CANDIDATES_FILE", CANDIDATES_FILE)

    if not session_date:
        session_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    target_symbols: List[str] = []
    if symbols:
        target_symbols = [s.strip().upper() for s in symbols if s.strip()]
    else:
        # Load candidate stocks from candidates_file
        if os.path.exists(effective_cand_file):
            try:
                cdata = load_json(effective_cand_file, {})
                for c in cdata.get("candidates", []):
                    sym = c.get("symbol") or c.get("ticker")
                    if sym and sym.upper() not in target_symbols:
                        target_symbols.append(sym.upper())
            except Exception:
                pass

    if not target_symbols:
        return []

    # Pre-index downloads files for performance
    file_list = None
    if os.path.exists(effective_downloads):
        file_list = ge._get_downloads_files(effective_downloads)

    results: List[PreEarningsCandidate] = []

    for sym in target_symbols:
        # 1. Discover earnings date
        earnings_date = ge.discover_earnings_date(sym, file_list=file_list)
        if not earnings_date:
            continue

        # 2. Get spot price
        spot = ge.find_latest_underlier_spot(sym)
        if spot is None or spot <= 0:
            continue

        # 3. Retrieve IV data
        current_iv: Optional[float] = None
        historical_ivs: List[float] = []

        # Check candidate file cache first
        if os.path.exists(effective_cand_file):
            try:
                cdata = load_json(effective_cand_file, {})
                for c in cdata.get("candidates", []):
                    if (c.get("symbol") or c.get("ticker") or "").upper() == sym:
                        if c.get("iv") is not None and c["iv"] > 0:
                            current_iv = float(c["iv"])
                        break
            except Exception:
                pass

        # Check historical closes / indicators for IV observations
        try:
            closes_file = ge.find_latest_historical_closes(sym)
            if closes_file and os.path.exists(closes_file):
                c_json = load_json(closes_file, {})
                # Extract historical IVs if present, else fallback to historical vol
                hist_data = c_json.get("results") or c_json.get("data") or []
                for row in hist_data:
                    if isinstance(row, dict) and "implied_volatility" in row:
                        val = row.get("implied_volatility")
                        if val is not None and float(val) > 0:
                            historical_ivs.append(float(val))
        except Exception:
            pass

        # Check options files for live ATM quote IV
        if current_iv is None and file_list:
            try:
                inst_f, quote_f = ge.find_latest_option_files(sym)
                if quote_f and os.path.exists(quote_f):
                    q_data = load_json(quote_f, {})
                    quotes = ge.extract_quotes_list(q_data)
                    for q in quotes:
                        iv_val = q.get("implied_volatility")
                        if iv_val:
                            try:
                                f_iv = float(iv_val)
                                if f_iv > 0:
                                    current_iv = f_iv
                                    break
                            except ValueError:
                                pass
            except Exception:
                pass

        # Fallback default baseline IV if not found
        if current_iv is None or current_iv <= 0:
            current_iv = 0.35  # default 35% IV proxy

        if strict_iv_rank and len(historical_ivs) < 20:
            continue

        candidate = calculate_pre_earnings_vega_setup(
            symbol=sym,
            spot=spot,
            earnings_date=earnings_date,
            session_date=session_date,
            current_iv=current_iv,
            historical_ivs=historical_ivs,
            min_days=min_days,
            max_days=max_days,
            max_iv_rank=max_iv_rank,
        )
        if candidate:
            results.append(candidate)

    # Sort descending by projected return percentage
    results.sort(key=lambda c: c.projected_return_pct, reverse=True)
    return results
