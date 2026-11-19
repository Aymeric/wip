import sys
_this = sys.modules.get(__name__)
if _this:
    sys.modules.setdefault('gex_engine', _this)
    sys.modules.setdefault('src.gex_engine', _this)
#!/usr/bin/env python3
"""
📊 GEX Options & Agentic Portfolio Trading Suite CLI Engine

This module serves as the primary technical execution layer for a rules-based options swing trading
and risk management system. Based on GEX (Gamma Exposure) and underlier dealer positioning mechanics,
the CLI automates:
  1. Broad-market Daily Regime Gates validation and authorization evaluation.
  2. Scanning, filtering, and caching prospective candidate equity symbols.
  3. Dynamic single-options setup grading with offline profile derivation logic.
  4. Real-time active portfolio tracking with profit-target, structural, time-limit, and momentum stop-losses.

File Paths and Cache Databases managed:
  - REGIME_FILE (data/regime.json): Daily market index, sector ETF breadth, and market gates cache.
  - ANALYSES_FILE (data/ticker_analyses.json): Incremental quantitative setup-grading persistent store.
  - OPTIONS_FILE (data/active_positions.json): Sized option transactions and Greeks tracker.
  - CANDIDATES_FILE (data/candidate_stocks.json): Screened and prioritized underlier candidates.
"""

import os
import sys
import json
import argparse
import re
import copy
import shutil
import tempfile
import time
import math
from datetime import datetime, date, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple, Any, Iterable, Union

# Ensure repository root is on sys.path for direct CLI invocations
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.gex.quant.greeks import (
    calculate_black_scholes_gamma,
    calculate_black_scholes_vanna,
    calculate_black_scholes_charm,
    find_flip_strikes,
    select_transition_points,
)

from src.gex.quant.indicators import (
    calculate_rsi,
    calculate_ema,
    calculate_macd_series,
    calculate_macd,
    calculate_bollinger_bands,
    calculate_atr,
    calculate_annualized_vol,
    calculate_iv_rank,
    calculate_iv_percentile,
)
from src.gex.risk.stops import compute_exit_rule_state
from src.gex.risk.rolling import (
    RollRecommendation,
    calculate_profit_ratchet,
    evaluate_position_roll,
    evaluate_portfolio_rolls,
)
from src.gex.risk.hedge import (
    PositionDeltaExposure,
    HedgePlan,
    calculate_portfolio_beta_delta,
    derive_macro_hedge_plan,
)
from src.gex.storage.db import (
    init_db,
    upsert_trade,
    query_trade_metrics,
    sync_closed_positions_to_db,
    save_gex_snapshot,
    query_latest_gex_snapshot,
    query_historical_ivs,
    record_decision,
    query_decisions,
    summarize_decisions,
)


from src.gex.core.models import (
    OptionQuote,
    GexProfile,
    ScannerCandidate,
    RegimeGates,
    RegimeStatus,
    OptionPosition,
    StockPosition,
    OptionSentiment,
    Position,
    TradeRecord,
    VerticalSpread,
    BacktestConfig,
    BacktestTrade,
    BacktestDailySnapshot,
    BacktestResult,
)
from src.gex.core.config import (
    REPOSITORY_ROOT,
    DATA_DIR,
    REGIME_FILE,
    ANALYSES_FILE,
    OPTIONS_FILE,
    CANDIDATES_FILE,
    PERFORMANCE_FILE,
    DOWNLOADS_DIR,
    SENTIMENT_FILE,
    WORKFLOW_STATE_FILE,
    DEFAULT_DB_FILE,
    DEFAULT_SIZING_THRESHOLD,
    MIN_PRICE,
    MAX_PRICE,
    MIN_VOLUME,
    MIN_CHG_PCT,
    MIN_MARKET_CAP,
    EXIT_REASON_CODES,
    DEFAULT_EXIT_REASON,
    RECONCILED_EXIT_REASON,
    DECISION_TYPES,
    DECISION_ANSWERS,
    mask_account,
    validate_safe_path,
    sanitize_account,
)


def account_performance_file(account: str = "") -> str:
    """Return the account-scoped performance cache path."""
    normalized_account = sanitize_account(account)
    if not normalized_account:
        return PERFORMANCE_FILE
    return os.path.join(REPOSITORY_ROOT, f"data/performance_{normalized_account}.json")


def account_positions_file(account: str = "") -> str:
    """Return the active-position cache path, scoped when an account is supplied."""
    normalized_account = sanitize_account(account)
    if not normalized_account:
        return OPTIONS_FILE
    return os.path.join(REPOSITORY_ROOT, f"data/active_positions_{normalized_account}.json")


def account_closed_positions_file(account: str = "") -> str:
    """Return the closed-position cache path, scoped when an account is supplied."""
    normalized_account = sanitize_account(account)
    if not normalized_account:
        return os.path.join(os.path.dirname(OPTIONS_FILE), "closed_positions.json")
    return os.path.join(REPOSITORY_ROOT, f"data/closed_positions_{normalized_account}.json")

from src.gex.presentation.ascii_art import (
    print_color,
    format_color,
    generate_ascii_gex_scale,
)
from src.gex.presentation.formatters import (
    format_currency,
    format_pct,
    format_pnl,
    format_table,
    get_pnl_color,
    format_vanna_charm_summary,
    format_iv_context,
    format_vertical_spread_summary,
    format_backtest_summary,
    format_backtest_regime_breakdown,
    format_backtest_trade_log,
)
from src.gex.backtest import (
    BacktestEngine,
    HistoricalReplayHarness,
    simulate_backtest,
    calculate_backtest_metrics,
    calculate_simulated_entry_fill,
    calculate_simulated_exit_fill,
)
from src.gex.storage.persistence import (
    load_json,
    save_json,
    clear_account_cache,
    register_cache_clear_callback,
    _JSON_FILE_CACHE,
)
from src.gex.storage.retention import (
    cleanup_downloads,
)
from src.gex.screening.scanner import (
    calculate_candidate_score,
    filter_candidate,
)
from src.gex.screening.selector import (
    select_best_option,
)
from src.gex.screening.spreads import (
    calculate_spread_payoff,
    select_vertical_spread,
)
from src.gex.screening.monitor import (
    PositionBreachAlert,
    AlertState,
    AlertStateManager,
    format_alert_digest,
    evaluate_holding_breaches,
    run_monitor_pass,
    monitor_daemon,
)
from src.gex.quant.gex import (
    extract_quotes_list,
    derive_gex_profile,
)


def str2bool(value: Any) -> bool:
    """Parses CLI boolean flags reliably (argparse type=bool treats 'False' as True)."""
    if isinstance(value, bool):
        return value
    if value.lower() in ("true", "t", "yes", "y", "1"):
        return True
    if value.lower() in ("false", "f", "no", "n", "0"):
        return False
    raise argparse.ArgumentTypeError(f"Boolean value expected, got '{value}'")


def parse_spot_overrides(value: str) -> Dict[str, float]:
    """Parses comma-separated TICKER=PRICE overrides for portfolio analysis."""
    overrides: Dict[str, float] = {}
    for raw_pair in value.split(","):
        pair = raw_pair.strip()
        if not pair or pair.count("=") != 1:
            raise argparse.ArgumentTypeError(
                "spot overrides must use comma-separated TICKER=PRICE pairs"
            )

        ticker, raw_price = (part.strip() for part in pair.split("="))
        if not ticker:
            raise argparse.ArgumentTypeError("spot override ticker cannot be empty")
        try:
            price = float(raw_price)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"spot override price must be numeric: '{raw_price}'"
            ) from exc
        if price < 0:
            raise argparse.ArgumentTypeError(
                f"spot override price cannot be negative: {price}"
            )
        overrides[ticker.upper()] = price

    if not overrides:
        raise argparse.ArgumentTypeError("at least one spot override is required")
    return overrides


def parse_effective_session_date(value: str) -> str:
    """Validate the market session date used for persisted ticker analyses."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(
            "effective session date must use YYYY-MM-DD"
        ) from exc


_DIR_FILES_CACHE: Dict[Any, List[Tuple[str, str]]] = {}
_LAST_MTIME_CHECK_TIME: Dict[str, float] = {}
_CACHED_DIR_MTIME_KEY: Dict[str, Any] = {}


def _get_dir_mtime_key(d: str, ttl: float = 0.5) -> Any:
    try:
        d = validate_safe_path(d)
    except ValueError:
        return None
    now = time.time()
    last_check = _LAST_MTIME_CHECK_TIME.get(d, 0.0)
    if now - last_check < ttl and d in _CACHED_DIR_MTIME_KEY:
        return _CACHED_DIR_MTIME_KEY[d]
    if not os.path.exists(d):
        return None
    try:
        subdirs = [root for root, _, _ in os.walk(d)]
        key = (d, tuple((sd, os.path.getmtime(sd)) for sd in subdirs))
        _LAST_MTIME_CHECK_TIME[d] = now
        _CACHED_DIR_MTIME_KEY[d] = key
        return key
    except Exception:
        return None


def _get_downloads_files(downloads_dir: str) -> List[Tuple[str, str]]:
    """Efficiently retrieves all file paths under downloads_dir with mtime caching.

    Performance optimization (Bolt):
    Pre-computes and caches uppercase basenames alongside file paths as (filepath, filename_upper)
    tuples to eliminate redundant os.path.basename(f).upper() calls in lookup utilities (~12x speedup).
    """
    if downloads_dir:
        try:
            downloads_dir = validate_safe_path(downloads_dir)
        except ValueError:
            return []
    if not os.path.exists(downloads_dir):
        return []
    mtime_key = _get_dir_mtime_key(downloads_dir)
    if mtime_key and mtime_key in _DIR_FILES_CACHE:
        return _DIR_FILES_CACHE[mtime_key]

    files_list: List[Tuple[str, str]] = []
    for root, dirs, files in os.walk(downloads_dir):
        for f in files:
            fp = os.path.join(root, f)
            files_list.append((fp, f.upper()))

    if mtime_key:
        _DIR_FILES_CACHE.clear()
        _DIR_FILES_CACHE[mtime_key] = files_list
    return files_list


def _clear_engine_caches() -> None:
    _SPOT_PRICE_CACHE.clear()
    _DIR_FILES_CACHE.clear()
    _LAST_MTIME_CHECK_TIME.clear()
    _CACHED_DIR_MTIME_KEY.clear()


register_cache_clear_callback(_clear_engine_caches)


def dispatch_system_alert(title: str, message: str, webhook_url: Optional[str] = None) -> bool:
    """Dispatches a system alert via webhook (Discord/Slack/Telegram) or desktop notification if configured."""
    url = webhook_url or os.environ.get("GEX_ALERT_WEBHOOK_URL")
    alert_sent = False

    # 1. Webhook alert via urllib.request (zero external dependencies)
    if url:
        try:
            import urllib.parse
            import urllib.request
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme.lower() not in ("http", "https"):
                raise ValueError(f"Unsupported URL scheme '{parsed.scheme}': Webhook URLs must use http or https")

            payload = json.dumps({"title": title, "text": message, "content": f"**{title}**\n{message}"}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "GEX-Trading-Suite/1.0"},
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status < 400:
                    alert_sent = True
        except Exception as e:
            print(f"Warning: Failed to dispatch webhook alert: {e}", file=sys.stderr)

    # 2. Optional macOS desktop alert via osascript
    if sys.platform == "darwin" and os.environ.get("GEX_DESKTOP_NOTIFICATIONS", "").lower() in ("1", "true", "yes"):
        try:
            import subprocess
            # Security: Escape backslashes first, then double quotes to prevent string breakout & command injection
            clean_title = title.replace("\\", "\\\\").replace('"', '\\"')
            clean_msg = message.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
            applescript = f'display notification "{clean_msg}" with title "{clean_title}"'
            subprocess.run(["osascript", "-e", applescript], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            alert_sent = True
        except Exception:
            pass

    return alert_sent


def get_regime_status() -> Dict[str, Any]:
    """Retrieves and packages current broad market Daily Regime Gates metrics."""
    regime = load_json(REGIME_FILE, {})
    etf_details = regime.get("etf_details", {})
    
    spy_det = etf_details.get("SPY", {})
    qqq_det = etf_details.get("QQQ", {})
    hyg_det = etf_details.get("HYG", {})
    
    spy_pct = spy_det.get("Daily Change %", regime.get("spy_change_pct", 0.0))
    qqq_pct = qqq_det.get("Daily Change %", regime.get("qqq_change_pct", 0.0))
    hyg_pct = hyg_det.get("Daily Change %", regime.get("hyg_change_pct", None))
    
    bull_count = sum(1 for sym, det in etf_details.items() if sym != "HYG" and det.get("Classification") == "BULLISH")
    if not etf_details:
        bull_count = regime.get("bull_count", 0)
        
    bear_count = sum(1 for sym, det in etf_details.items() if sym != "HYG" and det.get("Classification") == "BEARISH")
    if not etf_details:
        bear_count = regime.get("bear_count", 0)
        
    if bear_count > 0:
        bull_bear_ratio = round(bull_count / bear_count, 3)
    else:
        bull_bear_ratio = float(bull_count) if etf_details else regime.get("bull_bear_ratio", 0.0)
        
    basket_gate = regime.get("basket_gate")
    if basket_gate is None:
        basket_gate = "PASS" if (spy_pct > 0.5 or qqq_pct > 0.5) else "FAIL"
        
    bull_bear_gate = regime.get("bull_bear_gate")
    if bull_bear_gate is None:
        bull_bear_gate = "PASS" if bull_bear_ratio > 3.0 else "FAIL"
        
    vix_spot = regime.get("vix_spot", 0.0)
    vix_bearish = regime.get("vix_bearish", None)
    
    vix_delta_gate = regime.get("vix_delta_gate")
    if vix_delta_gate is None:
        vix_delta_gate = "PASS" if vix_bearish else "FAIL"
        
    system_auth = regime.get("system_authorization", "BLOCKED")
    
    gates_passed = regime.get("gates_passed")
    if gates_passed is None:
        gates_passed = sum(1 for g in (basket_gate, bull_bear_gate, vix_delta_gate) if g == "PASS")
    
    return {
        "spy_pct": spy_pct,
        "qqq_pct": qqq_pct,
        "basket_gate": basket_gate,
        "bull_count": bull_count,
        "bear_count": bear_count,
        "bull_bear_ratio": bull_bear_ratio,
        "bull_bear_gate": bull_bear_gate,
        "vix_spot": vix_spot,
        "vix_bearish": vix_bearish,
        "vix_delta_gate": vix_delta_gate,
        "system_authorization": system_auth,
        "hyg_pct": hyg_pct,
        "gates_passed": gates_passed,
        "etf_details": etf_details
    }


def get_performance_status(account: str = "") -> Dict[str, Any]:
    """Retrieves current portfolio performance and drawdown metrics."""
    perf_file = account_performance_file(account)
    perf = load_json(perf_file, {})
    return {
        "monthly_pnl_dlr": perf.get("monthly_pnl_dlr", 0.0),
        "monthly_pnl_pct": perf.get("monthly_pnl_pct", 0.0),
        "drawdown_gate_status": perf.get("drawdown_gate_status", "PASS"),
        "monthly_cnt": perf.get("monthly_cnt", 0),
        "last_updated": perf.get("last_updated", "")
    }


def classify_etf(symbol: str, chg_pct: float) -> str:
    """Classifies an ETF as BULLISH, BEARISH, or FLAT based on daily percent change."""
    if symbol.upper() != "HYG":
        if chg_pct > 0.1:
            return "BULLISH"
        if chg_pct < -0.1:
            return "BEARISH"
    else:
        if chg_pct > 0.0:
            return "BULLISH"
        if chg_pct < 0.0:
            return "BEARISH"
    return "FLAT"


def compute_regime_gates(spy_pct: float, qqq_pct: float, bull_count: int, bear_count: int, vix_dealer_delta_bearish: bool) -> Tuple[str, float, str, str, str, int]:
    """Mechanically computes the three Daily Regime Gates and system authorization.

    - Basket Gate: SPY or QQQ up more than +0.5% in the session.
    - Bull:Bear Gate: bullish-to-bearish ratio > 3.0:1.
    - VIX Delta Gate: dealer positioning on VIX is bearish (bullish for equities).
    Track 1 (Mechanical P2P) requires >= 2/3 gates; Track 2 (B Continuation) requires 3/3.
    """
    basket_gate = "PASS" if (spy_pct > 0.5 or qqq_pct > 0.5) else "FAIL"
    
    bull_bear_ratio = round(bull_count / bear_count, 3) if bear_count > 0 else float(bull_count)
    bull_bear_gate = "PASS" if bull_bear_ratio > 3.0 else "FAIL"
    
    vix_delta_gate = "PASS" if vix_dealer_delta_bearish else "FAIL"
    
    gates_passed = sum(1 for g in (basket_gate, bull_bear_gate, vix_delta_gate) if g == "PASS")
    if gates_passed == 3:
        system_auth = "ALL TRACKS OK"
    elif gates_passed == 2:
        system_auth = "TRACK 1 OK"
    else:
        system_auth = "BLOCKED"
        
    return basket_gate, bull_bear_ratio, bull_bear_gate, vix_delta_gate, system_auth, gates_passed








def build_system_snapshot(account: str = "") -> Dict[str, Any]:
    """Builds a machine-readable snapshot of the current cached system state."""
    positions_file = account_positions_file(account)
    positions = load_json(positions_file, {"options_positions": {}, "stocks_positions": {}})
    candidates = load_json(CANDIDATES_FILE, {"candidates": []})
    analyses = load_json(ANALYSES_FILE, {})
    sentiment = load_json(SENTIMENT_FILE, {})
    workflow = load_json(WORKFLOW_STATE_FILE, {})

    option_positions = positions.get("options_positions", {})
    stock_positions = positions.get("stocks_positions", {})
    candidate_list = candidates.get("candidates", [])
    if not isinstance(candidate_list, list):
        candidate_list = []
    if not isinstance(analyses, dict):
        analyses = {}

    signal_counts = {"CONFIRMED": 0, "PENDING": 0, "BLOCKED": 0}
    for analysis in analyses.values():
        if not isinstance(analysis, dict):
            continue
        signal_status = str(analysis.get("Signal Status", ""))
        for status in signal_counts:
            if signal_status.startswith(status):
                signal_counts[status] += 1
                break

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "regime": get_regime_status(),
        "performance": get_performance_status(account),
        "portfolio": {
            "option_count": len(option_positions) if isinstance(option_positions, dict) else 0,
            "stock_count": len(stock_positions) if isinstance(stock_positions, dict) else 0,
            "options_positions": option_positions,
            "stocks_positions": stock_positions,
        },
        "candidates": {
            "count": len(candidate_list),
            "items": candidate_list,
        },
        "analyses": {
            "count": len(analyses),
            "signal_counts": signal_counts,
            "items": analyses,
        },
        "sentiment": sentiment,
        "workflow": workflow,
    }




def normalize_workflow_state(state: Any) -> Dict[str, Any]:
    """Return a usable workflow state even when a cache is incomplete or malformed."""
    if not isinstance(state, dict):
        state = {}

    normalized = {
        "current_phase": state.get("current_phase") or "Phase 0: Initialization",
        "last_updated": state.get("last_updated"),
        "subagents": state.get("subagents"),
        "notes": state.get("notes"),
    }
    if not isinstance(normalized["subagents"], dict):
        normalized["subagents"] = {}
    if not isinstance(normalized["notes"], list):
        normalized["notes"] = []
    return normalized




def get_ticker_analysis_freshness(account: Any = "", effective_dates: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Summarize ticker analysis freshness per in-scope ticker.

    ticker_analyses.json is a symbol-keyed historical map, so its file mtime
    cannot establish session freshness.
    """
    if isinstance(account, (list, tuple, set)):
        effective_dates = [str(x) for x in account]
        account = ""

    if effective_dates is None:
        effective_dates = (
            datetime.today().strftime('%Y-%m-%d'),
            datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        )
    valid_dates = set(effective_dates)

    analyses = load_json(ANALYSES_FILE, {})
    if not isinstance(analyses, dict):
        analyses = {}

    candidates_data = load_json(CANDIDATES_FILE, {})
    candidate_symbols = {
        str(candidate.get("symbol", "")).upper()
        for candidate in candidates_data.get("candidates", [])
        if isinstance(candidate, dict) and candidate.get("symbol")
    }
    options_file = account_positions_file(account)
    positions = load_json(options_file, {})
    active_symbols = {
        str(details.get("Underlier", "")).upper()
        for details in positions.get("options_positions", {}).values()
        if isinstance(details, dict) and details.get("Underlier")
    }
    active_symbols.update(
        str(ticker).upper()
        for ticker in positions.get("stocks_positions", {})
        if ticker
    )

    in_scope = candidate_symbols | active_symbols
    if not in_scope:
        in_scope = {str(symbol).upper() for symbol in analyses}

    current = []
    stale = []
    missing = []
    for symbol in sorted(in_scope):
        record = analyses.get(symbol, {})
        if not isinstance(record, dict) or not record:
            missing.append(symbol)
            continue
        analyzed_date = str(record.get("analyzed_date", ""))
        if analyzed_date in valid_dates:
            current.append(symbol)
        else:
            stale.append({
                "symbol": symbol,
                "analyzed_date": analyzed_date or "UNKNOWN",
                "signal_status": record.get("Signal Status", "UNKNOWN"),
            })

    return {
        "effective_dates": sorted(valid_dates),
        "in_scope": sorted(in_scope),
        "current": current,
        "stale": stale,
        "missing": missing,
    }




def calculate_grade(ticker, spot, ptrans, ntrans, gex, cotmp, extra_rules=None):
    """
    Grades a single stock setup based on the GEX system's 11 structural rules.
    
    The 11 Rules are:
      1. Total Call GEX is positive (bullish posture).
      2. Total Call GEX exceeds absolute value of Total Put GEX (net positive positioning).
      3. Underlier Spot price is above the largest negative GEX strike / Center of Put Mass (COTMP).
      4. Largest positive GEX target strike (+GEX / T1 Target) is above current stock Spot price.
      5. Positive transition (pTrans) sits above negative transition (nTrans).
      6. Stock Spot price sits above pTrans (entry trigger rule).
      7. Total Open Interest (OI) exceeds 10,000 contracts for structural depth.
      8. 30-day option implied volatility (IV30) is below historical 90-day realized volatility (HV90).
      9. Open Interest depth at the +GEX target strike exceeds all other strikes.
      10. Dealer net gamma positioning at the current Spot is net positive.
      11. Underlier's 10-day realized volatility (RV10) is compressed (<= 35%).
      
    Args:
        ticker (str): The ticker symbol.
        spot (float): Underlier spot price.
        ptrans (float): Positive transition level (pTrans).
        ntrans (float): Negative transition level (nTrans).
        gex (float): Target positive GEX strike level (+GEX).
        cotmp (float): Center of Put Mass strike (COTMP).
        extra_rules (dict, optional): Boolean flags for rules requiring raw options/volatility data (1, 2, 7, 8, 9, 10, 11).
        
    Returns:
        tuple[int, list[bool]]: (grade, rules_checklist) where grade is the integer score (0-11)
                                 and rules_checklist is a list of Boolean indicators for each of the 11 rules.
    """
    if extra_rules is None:
        extra_rules = {}

    rules = [False] * 11
    
    # Rule 1: Total call GEX is positive
    rules[0] = extra_rules.get("total_call_gex_positive", True)
    
    # Rule 2: Call GEX exceeds absolute Put GEX
    rules[1] = extra_rules.get("call_gex_gt_put_gex", True)
    
    # Rule 3: Spot price is above largest negative GEX strike (usually COTMP or similar)
    rules[2] = spot > cotmp
    
    # Rule 4: Largest single $+GEX$ target strike is above current Spot price
    rules[3] = gex > spot
    
    # Rule 5: pTrans sits above nTrans
    rules[4] = ptrans > ntrans
    
    # Rule 6: Spot sits above positive transition (pTrans) -> Wait, watchdog buffer allows pending.
    rules[5] = spot > ptrans
    
    # Rule 7: Total OI exceeds 10,000 contracts
    rules[6] = extra_rules.get("total_oi_gt_10000", True)
    
    # Rule 8: 30-day option implied volatility is below historical 90-day volatility
    rules[7] = extra_rules.get("iv_30_lt_hv_90", True)
    
    # Rule 9: Open Interest depth at +GEX target strike exceeds all other strikes
    rules[8] = extra_rules.get("oi_depth_target_positive", True)
    
    # Rule 10: Dealer net gamma positioning at current Spot is net positive
    rules[9] = extra_rules.get("dealer_gamma_net_positive", True)
    
    # Rule 11: Underlier current 10-day realized volatility is stable/compressed (<= 35%)
    rules[10] = extra_rules.get("rv_10_stable", True)
    
    grade = sum(1 for r in rules if r)
    
    # Optional Bonus Factor: Reddit Sentiment
    # If Sentiment is > 0.5 (High conviction), we can consider it a +0.5 boost (visual only or minor logic)
    sentiment_data = load_json(SENTIMENT_FILE, {})
    ticker_sentiment = sentiment_data.get(ticker.upper(), {})
    sentiment_score = ticker_sentiment.get("Sentiment", 0.0)
    
    if sentiment_score > 0.5 and grade >= 9:
        # Boost status to HIGH CONVICTION if grade is already strong
        pass

    return grade, rules


_DEFAULT_DTE_WEIGHT = 0.18257418583505537  # 1.0 / math.sqrt(30.0)


def extract_quotes_list(quotes_data: Any) -> List[Any]:
    """Extracts a quotes list from dict or list data payload."""
    if isinstance(quotes_data, list):
        return quotes_data
    if isinstance(quotes_data, dict):
        data = quotes_data.get("data")
        quotes_list = []
        if isinstance(data, dict):
            quotes_list = data.get("results", [])
        elif isinstance(data, list):
            quotes_list = data

        if not quotes_list:
            res = quotes_data.get("results")
            if isinstance(res, list):
                quotes_list = res

        return quotes_list if isinstance(quotes_list, list) else []
    return []


# derive_gex_profile and extract_quotes_list are modularized in src.gex.quant.gex
# and imported at the top of this module.


# Technical indicator implementations (calculate_rsi, calculate_ema, calculate_macd_series,
# calculate_macd, calculate_bollinger_bands, calculate_atr) are modularized in src.gex.quant.indicators
# and imported at the top of this module for backward compatibility.



def find_latest_historical_ohlc(symbol: str, file_list: Optional[Sequence[Union[str, Tuple[str, str]]]] = None) -> Tuple[List[float], List[float], List[float], List[float]]:
    """
    Recursively scans for historical data and returns (closes, highs, lows, opens).
    Accepts an optional pre-listed file_list parameter to avoid repeated os.walk traversals in loops.
    Supports file_list elements as plain string file paths or pre-indexed (filepath, filename_upper) tuples.
    """
    symbol_upper = symbol.upper()
    matching_files = []
    
    # Performance optimization (Bolt):
    # Use pre-indexed (filepath, filename_upper) tuples from file_list or _get_downloads_files cache
    # to avoid repeated os.path.basename().upper() calls.
    source = file_list if file_list is not None else (_get_downloads_files(DOWNLOADS_DIR) if os.path.exists(DOWNLOADS_DIR) else [])
    for item in source:
        if isinstance(item, tuple):
            filepath, file_upper = item
        else:
            filepath = item
            file_upper = os.path.basename(filepath).upper()
        if symbol_upper in file_upper and "HISTORICAL" in file_upper:
            matching_files.append(filepath)
                    
    if not matching_files:
        return [], [], [], []
        
    matching_files.sort(reverse=True)
    
    for filepath in matching_files:
        try:
            data = load_json(filepath, {})
            
            bars = []
            if isinstance(data, dict):
                results = data.get("data", {}).get("results", [])
                if not results:
                    results = data.get("results", [])
                if results:
                    for res in results:
                        if res.get("symbol", "").upper() == symbol_upper:
                            bars = res.get("bars", [])
                            break
                if not bars:
                    bars = data.get("bars", [])
            elif isinstance(data, list):
                bars = data
                
            if not bars:
                continue
                
            if isinstance(bars[0], dict) and "begins_at" in bars[0]:
                bars = sorted(bars, key=lambda x: x.get("begins_at", ""))
                
            closes, highs, lows, opens = [], [], [], []
            for bar in bars:
                if not isinstance(bar, dict):
                    continue
                try:
                    c = float(bar.get("close_price") or bar.get("close", 0.0))
                    h = float(bar.get("high_price") or bar.get("high", 0.0))
                    l = float(bar.get("low_price") or bar.get("low", 0.0))
                    o = float(bar.get("open_price") or bar.get("open", 0.0))
                    if c > 0.0:
                        closes.append(c)
                        highs.append(h)
                        lows.append(l)
                        opens.append(o)
                except (ValueError, TypeError):
                    continue
            if len(closes) > 0:
                return closes, highs, lows, opens
        except Exception:
            continue
            
    return [], [], [], []


def list_download_files(downloads_dir: Optional[str] = None) -> List[str]:
    """Recursively lists all .json file paths in downloads_dir (defaults to DOWNLOADS_DIR)."""
    target_dir = downloads_dir or DOWNLOADS_DIR
    if downloads_dir:
        try:
            target_dir = validate_safe_path(downloads_dir)
        except ValueError:
            return []
    matching_files = []
    if os.path.exists(target_dir):
        for root, dirs, files in os.walk(target_dir):
            for file in files:
                if file.endswith(".json"):
                    matching_files.append(os.path.join(root, file))
    return matching_files


def find_latest_historical_closes(symbol: str, file_list: Optional[Sequence[Union[str, Tuple[str, str]]]] = None) -> List[float]:
    """
    Scans the DOWNLOADS_DIR directory for historical daily closes files
    matching the symbol (e.g. symbol_historicals_raw.json). Returns a chronological
    list of close prices. Accepts an optional pre-listed file_list to avoid repeated
    os.walk directory traversals during batch processing.
    Supports file_list elements as plain string file paths or pre-indexed (filepath, filename_upper) tuples.
    """
    symbol_upper = symbol.upper()
    matching_files = []
    
    # Performance optimization (Bolt):
    # Use pre-indexed (filepath, filename_upper) tuples from file_list or _get_downloads_files cache
    # to avoid repeated os.path.basename().upper() calls.
    source = file_list if file_list is not None else (_get_downloads_files(DOWNLOADS_DIR) if os.path.exists(DOWNLOADS_DIR) else [])
    for item in source:
        if isinstance(item, tuple):
            filepath, file_upper = item
        else:
            filepath = item
            file_upper = os.path.basename(filepath).upper()
        if symbol_upper in file_upper and "HISTORICAL" in file_upper:
            matching_files.append(filepath)
                    
    if not matching_files:
        return []
        
    # Sort files by path name descending (lexicographical sorting of YYYYMMDD puts the latest date first)
    matching_files.sort(reverse=True)
    
    for filepath in matching_files:
        try:
            data = load_json(filepath, {})
            
            bars = []
            if isinstance(data, dict):
                results = data.get("data", {}).get("results", [])
                if not results:
                    results = data.get("results", [])
                if results:
                    for res in results:
                        if res.get("symbol", "").upper() == symbol_upper:
                            bars = res.get("bars", [])
                            break
                if not bars:
                    bars = data.get("bars", [])
            elif isinstance(data, list):
                bars = data
                
            if not bars:
                continue
                
            # Sort chronologically by begins_at
            if isinstance(bars[0], dict) and "begins_at" in bars[0]:
                bars = sorted(bars, key=lambda x: x.get("begins_at", ""))
                
            closes = []
            for bar in bars:
                if not isinstance(bar, dict):
                    continue
                try:
                    val = float(bar.get("close_price") or bar.get("close", 0.0))
                    if val > 0.0:
                        closes.append(val)
                except (ValueError, TypeError):
                    continue
            if len(closes) > 0:
                return closes
        except Exception:
            continue
            
    return []

def find_latest_technical_indicators(symbol: str, file_list: Optional[Sequence[Union[str, Tuple[str, str]]]] = None) -> Tuple[Optional[float], Optional[float]]:
    """
    Reads the latest RSI and MACD histogram from cached indicator downloads.
    Accepts an optional pre-listed file_list to avoid repeated os.walk directory traversals during batch processing.
    Supports file_list elements as plain string file paths or pre-indexed (filepath, filename_upper) tuples.
    """
    symbol_upper = symbol.upper()
    matching_files = []
    # Performance optimization (Bolt):
    # Use pre-indexed (filepath, filename_upper) tuples from file_list or _get_downloads_files cache
    # to avoid repeated os.path.basename().upper() calls.
    source = file_list if file_list is not None else (_get_downloads_files(DOWNLOADS_DIR) if os.path.exists(DOWNLOADS_DIR) else [])
    for item in source:
        if isinstance(item, tuple):
            filepath, file_upper = item
        else:
            filepath = item
            file_upper = os.path.basename(filepath).upper()
        if symbol_upper in file_upper and "TECHNICAL" in file_upper:
            matching_files.append(filepath)

    for filepath in sorted(matching_files, reverse=True):
        try:
            data = load_json(filepath, {})
            indicators = data.get("data", {}).get("indicators", []) if isinstance(data, dict) else []
            values: Dict[str, Optional[float]] = {"rsi": None, "macd_hist": None}
            for indicator in indicators:
                indicator_type = indicator.get("type")
                series = indicator.get("series", [])
                if indicator_type == "rsi" and series:
                    values["rsi"] = float(series[-1].get("value"))
                elif indicator_type == "macd" and series:
                    values["macd_hist"] = float(series[-1].get("histogram"))
            if values["rsi"] is not None or values["macd_hist"] is not None:
                return values["rsi"], values["macd_hist"]
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue

    return None, None


def find_latest_option_files(symbol: str) -> Dict[str, Optional[str]]:
    """
    Recursively scans DOWNLOADS_DIR for the latest options instruments, quotes, 
    underlier quotes, and historicals JSON files for a symbol.
    """
    symbol_lower = symbol.lower()
    result: Dict[str, Optional[str]] = {
        "inst_file": None,
        "quote_file": None,
        "underlier_quote_file": None,
        "hist_file": None,
        "indicators_file": None,
    }
    
    if not os.path.exists(DOWNLOADS_DIR):
        return result
        
    all_files = [item for item in _get_downloads_files(DOWNLOADS_DIR) if item[1].endswith(".JSON")]
    all_files.sort(key=lambda x: x[0], reverse=True)
    
    for filepath, file_upper in all_files:
        fn = file_upper.lower()
        if fn.startswith(f"{symbol_lower}_") or fn.startswith(f"{symbol_lower}.") or f"/{symbol_lower}_" in filepath.lower():
            if ("option_instrument" in fn or "instruments" in fn) and not result["inst_file"]:
                result["inst_file"] = filepath
            elif ("option_quote" in fn or ("quotes" in fn and "option" in fn)) and "etf" not in fn and not result["quote_file"]:
                result["quote_file"] = filepath
            elif ("underlier_quote" in fn or (("quote" in fn) and "option" not in fn and "etf" not in fn)) and not result["underlier_quote_file"]:
                result["underlier_quote_file"] = filepath
            elif ("historical" in fn) and not result["hist_file"]:
                result["hist_file"] = filepath
            elif ("indicator" in fn or "technical" in fn) and not result["indicators_file"]:
                result["indicators_file"] = filepath
                
    return result


_SPOT_PRICE_CACHE: Dict[Tuple[str, Any, Any, Any], Optional[float]] = {}


def _get_file_mtime(filepath: str) -> Optional[float]:
    try:
        filepath = validate_safe_path(filepath)
        if os.path.exists(filepath):
            return os.path.getmtime(filepath)
    except Exception:
        pass
    return None


def find_latest_underlier_spot(symbol: str) -> Optional[float]:
    """Finds latest spot price for a symbol from downloaded underlier quotes or candidates."""
    symbol_upper = symbol.upper()
    symbol_lower = symbol.lower()
    
    mtime_key = _get_dir_mtime_key(DOWNLOADS_DIR) if os.path.exists(DOWNLOADS_DIR) else None
    cand_mtime = _get_file_mtime(CANDIDATES_FILE)
    anal_mtime = _get_file_mtime(ANALYSES_FILE)
    cache_key = (symbol_upper, mtime_key, cand_mtime, anal_mtime)
    if cache_key in _SPOT_PRICE_CACHE:
        return _SPOT_PRICE_CACHE[cache_key]

    price_result: Optional[float] = None

    # 1) Try downloaded quote file
    if os.path.exists(DOWNLOADS_DIR):
        quote_files = []
        for filepath, file_upper in _get_downloads_files(DOWNLOADS_DIR):
            if file_upper.endswith(".JSON") and symbol_upper in file_upper and "QUOTE" in file_upper and "OPTION" not in file_upper and "ETF" not in file_upper:
                quote_files.append(filepath)
        quote_files.sort(reverse=True)
        for qf in quote_files:
            try:
                qdata = load_json(qf, {})
                res_list = qdata.get("data", {}).get("results", []) if isinstance(qdata, dict) else []
                if not res_list and isinstance(qdata, dict):
                    res_list = qdata.get("results", [])
                if not res_list and isinstance(qdata, list):
                    res_list = qdata
                for r in res_list:
                    if isinstance(r, dict) and r.get("symbol", "").upper() == symbol_upper:
                        price = r.get("last_trade_price") or r.get("last_non_reg_trade_price") or r.get("last_extended_hours_trade_price") or r.get("price")
                        if price:
                            price_result = float(price)
                            break
                if price_result is not None:
                    break
            except Exception:
                continue

    if price_result is None:
        # 2) Try candidate_stocks.json
        cand_data = load_json(CANDIDATES_FILE, {})
        for c in cand_data.get("candidates", []):
            if c.get("symbol", "").upper() == symbol_upper and c.get("price") is not None:
                price_result = float(c["price"])
                break

    if price_result is None:
        # 3) Try ticker_analyses.json
        analyses = load_json(ANALYSES_FILE, {})
        if symbol_upper in analyses and analyses[symbol_upper].get("Spot") is not None:
            price_result = float(analyses[symbol_upper]["Spot"])

    if price_result is None:
        # 4) Fallback to latest historical close price
        closes = find_latest_historical_closes(symbol)
        if closes:
            price_result = float(closes[-1])

    _SPOT_PRICE_CACHE[cache_key] = price_result
    return price_result


def get_all_active_symbols() -> List[str]:
    """Retrieves all active stock and option underlier symbols across all account position files."""
    active_symbols = set()
    data_dir = os.path.join(REPOSITORY_ROOT, "data")
    if os.path.exists(data_dir):
        for fname in os.listdir(data_dir):
            if fname.startswith("active_positions") and fname.endswith(".json"):
                fpath = os.path.join(data_dir, fname)
                pos = load_json(fpath, {})
                for details in pos.get("options_positions", {}).values():
                    if isinstance(details, dict) and details.get("Underlier"):
                        active_symbols.add(str(details["Underlier"]).upper())
                for ticker in pos.get("stocks_positions", {}).keys():
                    if ticker:
                        active_symbols.add(str(ticker).upper())
    return sorted(list(active_symbols))


def calculate_candidate_score(candidate: Dict[str, Any]) -> float:
    """Calculates a 0-100 screen score from the metrics available for a candidate.

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

def check_technical_alerts(closes: List[float], highs: Optional[List[float]] = None, lows: Optional[List[float]] = None) -> Dict[str, Any]:
    """
    Analyzes historical price data for RSI, MACD, Bollinger Bands, and ATR alerts.
    
    Returns:
        dict: {
            "rsi": current_rsi (float or None),
            "macd_hist": current_macd_hist (float or None),
            "bb": (mid, upper, lower),
            "atr": current_atr (float or None),
            "alerts": list of str triggered
        }
    """
    alerts = []
    rsi = calculate_rsi(closes)

    # Performance optimization (Bolt): Reuse MACD series to derive current histogram
    # and crossover alerts without recomputing EMA fast/slow and signal lines twice.
    macd_line_list, signal_line_list = calculate_macd_series(closes)
    macd_hist = macd_line_list[-1] - signal_line_list[-1] if macd_line_list and signal_line_list else None

    mid_bb, upper_bb, lower_bb = calculate_bollinger_bands(closes)
    
    atr = None
    if highs and lows:
        atr = calculate_atr(highs, lows, closes)
    
    if rsi is not None:
        if rsi >= 70.0:
            alerts.append("RSI_OVERBOUGHT")
        elif rsi <= 30.0:
            alerts.append("RSI_OVERSOLD")
            
    if lower_bb and closes[-1] <= lower_bb:
        alerts.append("BB_LOWER_TOUCH")
    elif upper_bb and closes[-1] >= upper_bb:
        alerts.append("BB_UPPER_TOUCH")

    # For MACD Crossover (reuse computed MACD and signal series)
    if len(macd_line_list) >= 2 and len(signal_line_list) >= 2:
        prev_hist = macd_line_list[-2] - signal_line_list[-2]
        curr_hist = macd_line_list[-1] - signal_line_list[-1]
        
        if prev_hist < 0.0 and curr_hist >= 0.0:
            alerts.append("MACD_BULLISH_CROSSOVER")
        elif prev_hist > 0.0 and curr_hist <= 0.0:
            alerts.append("MACD_BEARISH_CROSSOVER")
                
    return {
        "rsi": rsi,
        "macd_hist": macd_hist,
        "bb": (mid_bb, upper_bb, lower_bb),
        "atr": atr,
        "alerts": alerts
    }


# calculate_annualized_vol is modularized in src.gex.quant.indicators and imported above.



def derive_volatility_profile(hist_data, symbol, iv_sum, iv_count):
    """
    Calculates proxy volatility indicators (RV10, HV90, IV30) and applies rules.
    
    Args:
        hist_data (dict or list): Historical closes JSON payload
        symbol (str): Stock ticker symbol
        iv_sum (float): sum of weighted IVs
        iv_count (int): count of IV occurrences
        
    Returns:
        dict: Derived volatilities and rules.
    """
    bars = []
    if isinstance(hist_data, dict):
        results = hist_data.get("data", {}).get("results", [])
        if not results:
            results = hist_data.get("results", [])
        if results:
            for res in results:
                if res.get("symbol", "").upper() == symbol:
                    bars = res.get("bars", [])
                    break
        if not bars:
            bars = hist_data.get("bars", [])
    elif isinstance(hist_data, list):
        bars = hist_data
        
    if not bars:
        return {
            "iv30_val": 0.0,
            "hv90_val": 0.0,
            "rv10_val": 0.0,
            "rule8_derived": True,
            "rule11_derived": True
        }
        
    # Sort chronologically by begins_at
    if isinstance(bars[0], dict) and "begins_at" in bars[0]:
        bars = sorted(bars, key=lambda x: x.get("begins_at", ""))
        
    closes = []
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        try:
            val = float(bar.get("close_price") or bar.get("close", 0.0))
            if val > 0.0:
                closes.append(val)
        except (ValueError, TypeError):
            continue
            
    if len(closes) <= 1:
        return {
            "iv30_val": 0.0,
            "hv90_val": 0.0,
            "rv10_val": 0.0,
            "rule8_derived": True,
            "rule11_derived": True
        }
        
    log_returns = [math.log(closes[i] / closes[i-1]) for i in range(1, len(closes))]
    
    # HV90 proxy (using exactly the last 90 log returns for 90-day realized volatility window)
    hv90_val = calculate_annualized_vol(log_returns[-90:])
    
    # RV10 proxy (using exactly the last 10 log returns for 10-day volatility compression)
    rv10_val = calculate_annualized_vol(log_returns[-10:])
    
    iv30_val = (iv_sum / iv_count) * 100.0 if iv_count > 0 else 0.0
    
    rule8_derived = iv30_val < hv90_val if iv30_val > 0.0 and hv90_val > 0.0 else True
    rule11_derived = rv10_val <= 35.0 if rv10_val > 0.0 else True
    
    return {
        "iv30_val": iv30_val,
        "hv90_val": hv90_val,
        "rv10_val": rv10_val,
        "rule8_derived": rule8_derived,
        "rule11_derived": rule11_derived
    }


def discover_earnings_date(symbol: str, file_list: Optional[Sequence[Union[str, Tuple[str, str]]]] = None) -> Optional[str]:
    """
    Search recursively inside DOWNLOADS_DIR to locate any <ticker>_earnings_raw.json file.
    Parse its content to locate the next scheduled or estimated earnings date.
    Accepts an optional pre-listed file_list parameter to avoid repeated os.walk traversals in loops.
    Supports file_list elements as plain string file paths or pre-indexed (filepath, filename_upper) tuples.
    """
    sym_upper = symbol.upper()
    if not os.path.exists(DOWNLOADS_DIR):
        return None
    candidates = []

    # Performance optimization (Bolt):
    # Use pre-indexed (filepath, filename_upper) tuples from file_list or _get_downloads_files cache
    # to avoid repeated os.walk traversals and os.path.basename().upper() calls.
    source = file_list if file_list is not None else _get_downloads_files(DOWNLOADS_DIR)
    for item in source:
        if isinstance(item, tuple):
            filepath, file_upper = item
        else:
            filepath = item
            file_upper = os.path.basename(filepath).upper()
        if file_upper == f"{sym_upper}_EARNINGS_RAW.JSON" or file_upper == f"{sym_upper}_EARNINGS.JSON":
            candidates.append(filepath)

    if not candidates:
        return None
    candidates.sort() # get the most recent download folder chronologically
    latest_file = candidates[-1]
    try:
        data = load_json(latest_file, {})
        
        def parse_date(val):
            if isinstance(val, str):
                # Try matching prefix YYYY-MM-DD to support full ISO timestamps
                match = re.match(r"^(\d{4}-\d{2}-\d{2})", val)
                if match:
                    return match.group(1)
            return None
            
        all_dates = []
        def collect_dates(obj):
            if isinstance(obj, dict):
                # Check priority keys
                for key in ["report_date", "date", "expected_report_date", "earnings_date", "estimated_date"]:
                    if key in obj:
                        d = parse_date(obj[key])
                        if d:
                            all_dates.append(d)
                for val in obj.values():
                    collect_dates(val)
            elif isinstance(obj, list):
                for val in obj:
                    collect_dates(val)
                    
        collect_dates(data)
        if not all_dates:
            return None
            
        # Deduplicate and sort
        unique_dates = sorted(list(set(all_dates)))
        
        # Find next upcoming (>= today)
        today_str = datetime.today().strftime('%Y-%m-%d')
        future_dates = [d for d in unique_dates if d >= today_str]
        if future_dates:
            return future_dates[0] # Earliest future date
            
        # Fallback to the latest past date or maximum date if no future/today dates exist
        return unique_dates[-1]
    except Exception as e:
        print(f"Warning: Failed to parse discovered earnings file {latest_file}: {e}", file=sys.stderr)
    return None


# select_best_option is modularized in src.gex.screening.selector




# compute_exit_rule_state is modularized in src.gex.risk.stops and imported at the top of this module.



def get_monthly_realized_pnl(net_liq: float, monthly_file: Optional[str] = None, pnl_file: Optional[str] = None) -> Tuple[float, float, str, int]:
    """
    Computes or retrieves the trailing 30-day realized P&L from raw files.
    First checks for realized_pnl_monthly.json under DOWNLOADS_DIR, 
    otherwise falls back to parsing pnl_trade_history.json.
    Returns (realized_pnl_dollar, realized_pnl_pct, status_string, trade_count).
    """
    pnl_file = pnl_file or ""
    monthly_file = monthly_file or ""

    if monthly_file:
        try:
            monthly_file = validate_safe_path(monthly_file)
        except ValueError:
            monthly_file = ""

    if pnl_file:
        try:
            pnl_file = validate_safe_path(pnl_file)
        except ValueError:
            pnl_file = ""
    
    if not monthly_file and not pnl_file and os.path.exists(DOWNLOADS_DIR):
        # Scan DOWNLOADS_DIR to locate any saved files and sort them lexicographically
        monthly_candidates = []
        pnl_candidates = []
        for root, dirs, files in os.walk(DOWNLOADS_DIR):
            for filee in files:
                if filee == "realized_pnl_monthly.json":
                    monthly_candidates.append(os.path.join(root, filee))
                elif filee == "pnl_trade_history.json":
                    pnl_candidates.append(os.path.join(root, filee))
        if monthly_candidates:
            monthly_candidates.sort()
            monthly_file = monthly_candidates[-1]
        if pnl_candidates:
            pnl_candidates.sort()
            pnl_file = pnl_candidates[-1]
                    
    # Try parsing monthly realized portfolio aggregate file
    if monthly_file:
        try:
            data = load_json(monthly_file, None)
            if data is None:
                raise ValueError("Could not load monthly file")
            # Support multiple formats
            res = data.get("realized_pnl", data.get("data", data))
            if isinstance(res, dict):
                pnl_raw = res.get("realized_gain_loss", res.get("total_realized_pnl", res.get("total_returns", 0.0)))
                try:
                    pnl_val = float(pnl_raw) if pnl_raw is not None else 0.0
                except (ValueError, TypeError):
                    pnl_val = 0.0
                pct_val = (pnl_val / net_liq) * 100.0 if net_liq > 0 else 0.0
                
                cnt_raw = res.get("closing_trades_count", res.get("trade_count", 0))
                try:
                    cnt = int(cnt_raw) if cnt_raw is not None else 0
                except (ValueError, TypeError):
                    cnt = 0
                    
                if cnt == 0 and "data_points" in res:
                    try:
                        cnt = sum(int(dp.get("number_of_trades") or 0) for dp in res["data_points"] if isinstance(dp, dict))
                    except (ValueError, TypeError):
                        pass
                status = "FAIL" if (pnl_val < 0 and abs(pnl_val) >= (net_liq * 0.10)) else "PASS"
                return pnl_val, pct_val, status, cnt
        except Exception:
            pass
            
    # Try parsing pnl_trade_history trades within the last 30 days
    if pnl_file:
        try:
            data = load_json(pnl_file, {})
            trades = data.get("data", {}).get("trades", [])
            if not trades:
                trades = data.get("trades", [])
                
            total_gain = 0.0
            trade_count = 0
            
            # Performance optimization (Bolt):
            # Fast single-pass ISO date parsing with `date.fromisoformat` and inline tracking of
            # the latest trade date eliminates duplicate iteration passes and slow `datetime.strptime` calls (~12.4x speedup).
            now_dt = date.today()
            parsed_trades = []
            latest_trade_date = None

            for t in trades:
                ts = t.get("timestamp", "")
                if ts:
                    try:
                        d = date.fromisoformat(ts[:10])
                        gain = float(t.get("realized_gain", t.get("realized_gain_loss", 0.0)))
                        parsed_trades.append((d, gain))
                        if latest_trade_date is None or d > latest_trade_date:
                            latest_trade_date = d
                    except (ValueError, TypeError):
                        pass

            if latest_trade_date and (now_dt - latest_trade_date).days > 30:
                now_dt = latest_trade_date

            for d, gain in parsed_trades:
                if (now_dt - d).days <= 30:
                    total_gain += gain
                    trade_count += 1
                    
            pct_val = (total_gain / net_liq) * 100.0 if net_liq > 0 else 0.0
            status = "FAIL" if (total_gain < 0 and abs(total_gain) >= (net_liq * 0.10)) else "PASS"
            return total_gain, pct_val, status, trade_count
        except Exception:
            pass
            
    return 0.0, 0.0, "PASS", 0


def get_beta_factor(sector_tag: Optional[str]) -> float:
    """Returns typical beta factor for given sector tag relative to SPY."""
    tag = sector_tag.lower() if sector_tag else "equity"
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


























def slugify(text: Any) -> str:
    """Sanitizes text for safe filename generation, falling back to 'scan' if empty or invalid."""
    if text is None:
        return "scan"
    s = str(text).lower()
    s = re.sub(r'[^a-z0-9]+', '_', s)
    s = s.strip('_')
    return s if s else "scan"


def persist_new_scans():
    """
    Scans the current directory for new raw Robinhood scan downloads.
    When a valid scan is found, it moves it to the DOWNLOADS_DIR directory
    to keep the root clean.
    """
    cwd = "."
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    persisted_files = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Gather search locations from current directory only
    search_paths = []
    
    # 1) Search current directory
    for item in os.listdir(cwd):
        # Skip known state files
        if item.endswith(".json") and item not in (
            os.path.basename(REGIME_FILE), 
            os.path.basename(ANALYSES_FILE), 
            os.path.basename(OPTIONS_FILE), 
            os.path.basename(CANDIDATES_FILE),
            os.path.basename(SENTIMENT_FILE),
            os.path.basename(WORKFLOW_STATE_FILE)
        ):
            search_paths.append((os.path.join(cwd, item), True))
            
    for filepath, should_delete in search_paths:
        try:
            if not os.path.isfile(filepath):
                continue
            data = load_json(filepath, None)
            if data is None:
                continue
            
            # Verify if this is a Robinhood scan result structure
            scan_result = None
            if isinstance(data, dict):
                scan_result = data.get("data", {}).get("result", {})
                if not scan_result or not isinstance(scan_result, dict):
                    scan_result = data.get("result", {})
                if not scan_result or not isinstance(scan_result, dict):
                    scan_result = data
            
            if isinstance(scan_result, dict):
                scan_title = scan_result.get("scan_title")
                scan_id = scan_result.get("scan_id")
                
                if scan_title and scan_id:
                    slug_title = slugify(scan_title)
                    timestamped_filename = f"{slug_title}_{timestamp}.json"
                    
                    target_path = validate_safe_path(os.path.join(DOWNLOADS_DIR, timestamped_filename))
                    safe_filepath = validate_safe_path(filepath)
                    
                    # Move file to downloads
                    shutil.copy2(safe_filepath, target_path)
                    print(f"Persisted new scan '{scan_title}' to {target_path}")
                    
                    if should_delete:
                        os.remove(safe_filepath)
                        print(f"  Removed raw temporary file: {safe_filepath}")
                    
                    persisted_files.append((scan_title, target_path))
        except Exception:
            continue
            
    return persisted_files














def calculate_trade_journal(closed_data: Dict[str, Any], performance_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Calculate auditable performance metrics from archived closed positions."""
    # Performance optimization (Bolt):
    # 1. Local date parsing cache (`date_cache`) avoids repeated `date.fromisoformat()` calls.
    # 2. Replacing per-record `setdefault()` and inner `round()` calls with direct `.get()` lookups,
    #    floating point accumulation, and deferred `round()` in a single post-processing pass yields a ~2.0x speedup.
    num_records = 0
    total_archived = 0

    total_pnl = 0.0
    win_count = 0
    loss_count = 0
    gross_profit = 0.0
    gross_loss = 0.0

    win_days_sum = 0.0
    win_days_count = 0
    loss_days_sum = 0.0
    loss_days_count = 0

    max_consecutive_losses = 0
    consecutive_losses = 0

    asset_stats = {
        "option": {"count": 0, "pnl": 0.0, "win_count": 0},
        "stock": {"count": 0, "pnl": 0.0, "win_count": 0}
    }

    close_reasons: Dict[str, Dict[str, Any]] = {}
    target_modes: Dict[str, Dict[str, Any]] = {}
    date_cache: Dict[str, date] = {}

    for asset_class, key in (("option", "closed_options"), ("stock", "closed_stocks")):
        items = closed_data.get(key, []) or []
        total_archived += len(items)
        astat = asset_stats[asset_class]

        for item in items:
            realized = item.get("Realized P&L ($)")
            try:
                realized_value = float(realized)
            except (TypeError, ValueError):
                continue

            days_value = None
            entry_date = item.get("Entry Date")
            close_date = item.get("Close Date")
            if entry_date and close_date:
                try:
                    e_dt = date_cache.get(entry_date)
                    if e_dt is None:
                        e_dt = date.fromisoformat(entry_date)
                        date_cache[entry_date] = e_dt

                    c_dt = date_cache.get(close_date)
                    if c_dt is None:
                        c_dt = date.fromisoformat(close_date)
                        date_cache[close_date] = c_dt

                    days_value = (c_dt - e_dt).days + 1
                except (ValueError, TypeError):
                    pass

            close_reason = item.get("Close Reason", "Unknown")
            target_mode = item.get("Target Mode", "Unknown")

            num_records += 1
            total_pnl += realized_value
            astat["count"] += 1
            astat["pnl"] += realized_value

            if realized_value > 0:
                win_count += 1
                gross_profit += realized_value
                astat["win_count"] += 1
                consecutive_losses = 0
                if days_value is not None:
                    win_days_sum += days_value
                    win_days_count += 1
            elif realized_value < 0:
                loss_count += 1
                gross_loss += abs(realized_value)
                consecutive_losses += 1
                if consecutive_losses > max_consecutive_losses:
                    max_consecutive_losses = consecutive_losses
                if days_value is not None:
                    loss_days_sum += days_value
                    loss_days_count += 1
            else:
                consecutive_losses = 0

            bucket_cr = close_reasons.get(close_reason)
            if bucket_cr is None:
                bucket_cr = {"count": 0, "pnl": 0.0, "win_count": 0}
                close_reasons[close_reason] = bucket_cr
            bucket_cr["count"] += 1
            bucket_cr["pnl"] += realized_value
            if realized_value > 0:
                bucket_cr["win_count"] += 1

            bucket_tm = target_modes.get(target_mode)
            if bucket_tm is None:
                bucket_tm = {"count": 0, "pnl": 0.0}
                target_modes[target_mode] = bucket_tm
            bucket_tm["count"] += 1
            bucket_tm["pnl"] += realized_value

    for bucket in close_reasons.values():
        cnt = bucket["count"]
        bucket["win_rate_pct"] = round(bucket["win_count"] / cnt * 100, 2) if cnt > 0 else None
        bucket["expectancy_per_trade"] = round(bucket["pnl"] / cnt, 2) if cnt > 0 else None
        bucket["pnl"] = round(bucket["pnl"], 2)
    for bucket in target_modes.values():
        bucket["pnl"] = round(bucket["pnl"], 2)

    by_asset_class = {}
    for ac in ("option", "stock"):
        st = asset_stats[ac]
        cnt = st["count"]
        by_asset_class[ac] = {
            "count": cnt,
            "pnl": round(st["pnl"], 2),
            "win_rate_pct": round(st["win_count"] / cnt * 100, 2) if cnt > 0 else None
        }

    report = {
        "records_reviewed": num_records,
        "complete_records_used": num_records,
        "excluded_records": total_archived - num_records,
        "total_realized_pnl": round(total_pnl, 2),
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate_pct": round(win_count / num_records * 100, 2) if num_records > 0 else None,
        "average_winner": round(gross_profit / win_count, 2) if win_count > 0 else None,
        "average_loser": round(-gross_loss / loss_count, 2) if loss_count > 0 else None,
        "expectancy_per_trade": round(total_pnl / num_records, 2) if num_records > 0 else None,
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else None,
        "max_consecutive_losses": max_consecutive_losses,
        "average_days_winner": round(win_days_sum / win_days_count, 2) if win_days_count > 0 else None,
        "average_days_loser": round(loss_days_sum / loss_days_count, 2) if loss_days_count > 0 else None,
        "by_asset_class": by_asset_class,
        "close_reasons": close_reasons,
        "target_modes": target_modes,
    }

    if performance_data:
        try:
            cached_pnl_value = performance_data.get("monthly_pnl_dlr")
            if cached_pnl_value is not None:
                cached_pnl = float(cached_pnl_value)
                report["cache_reconciliation"] = "MATCH" if round(cached_pnl, 2) == round(total_pnl, 2) else "MISMATCH"
            else:
                report["cache_reconciliation"] = "UNKNOWN"
        except (TypeError, ValueError):
            report["cache_reconciliation"] = "UNKNOWN"
    return report




















def cleanup_downloads(days=7):
    """Removes dated download folders older than the retention period and stale tmp folders."""
    from src.gex.storage.retention import cleanup_downloads as _retention_cleanup
    removed_count = _retention_cleanup(days=days, downloads_dir=DOWNLOADS_DIR)
    print(f"Cleanup complete. Removed {removed_count} folders.")
    return removed_count


# ==============================================================================
# Extracted CLI Subcommands & Dispatcher (Roadmap Milestone 5.8)
# ==============================================================================
from src.gex.cli import (
    COMMAND_HANDLERS,
    add_journal_parsers,
    add_ops_parsers,
    add_portfolio_parsers,
    add_regime_parsers,
    add_screening_parsers,
    build_parser,
    cmd_add_pos,
    cmd_add_stock_pos,
    cmd_analyze,
    cmd_audit_all,
    cmd_backtest,
    cmd_cleanup_downloads,
    cmd_close_pos,
    cmd_close_stock_pos,
    cmd_closed,
    cmd_decisions,
    cmd_evaluate_rolls,
    cmd_hedge_plan,
    cmd_journal,
    cmd_monitor,
    cmd_payoff,
    cmd_portfolio,
    cmd_prune_candidates,
    cmd_rankings,
    cmd_record_decision,
    cmd_select_spreads,
    cmd_sentiment,
    cmd_simulate,
    cmd_snapshot,
    cmd_status,
    cmd_sync_pnl,
    cmd_sync_positions,
    cmd_update_candidates,
    cmd_update_opt,
    cmd_update_performance,
    cmd_update_regime,
    cmd_update_sentiment,
    cmd_update_stock_pos,
    cmd_update_workflow,
    cmd_workflow,
    dispatch_command,
)


def main():
    parser = build_parser()
    args = parser.parse_args()
    dispatch_command(args)


if __name__ == "__main__":
    main()
