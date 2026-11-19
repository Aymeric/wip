"""
CLI commands for ticker screening, setup grading, Reddit sentiment analysis, and vertical debit spreads.
Provides handlers and subparser definitions for:
- analyze
- update-candidates
- prune-candidates
- sentiment
- update-sentiment
- rankings
- select-spreads
- payoff
- simulate
"""

import csv
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Sequence

from src.gex.core.models import OptionSentiment
from src.gex.core.config import (
    DEFAULT_SIZING_THRESHOLD,
    MIN_PRICE,
    MAX_PRICE,
    MIN_VOLUME,
    MIN_CHG_PCT,
    MIN_MARKET_CAP,
    validate_safe_path,
)
from src.gex.presentation.ascii_art import (
    format_color,
    generate_ascii_gex_scale,
    print_color,
)
from src.gex.presentation.formatters import (
    format_currency,
    format_pct,
    format_pnl,
    format_table,
    get_pnl_color,
    format_vertical_spread_summary,
    format_iv_context,
    format_vanna_charm_summary,
)
from src.gex.quant.gex import derive_gex_profile
from src.gex.quant.indicators import (
    calculate_iv_percentile,
    calculate_iv_rank,
    calculate_macd,
    calculate_rsi,
)
from src.gex.risk.stops import compute_exit_rule_state
from src.gex.screening.scanner import calculate_candidate_score, filter_candidate
from src.gex.screening.selector import select_best_option
from src.gex.screening.spreads import select_vertical_spread
from src.gex.storage.db import (
    query_historical_ivs,
    save_gex_snapshot,
)


from src.gex.cli.proxy import ge

_get_downloads_files = lambda *a, **k: ge._get_downloads_files(*a, **k)
account_positions_file = lambda *a, **k: ge.account_positions_file(*a, **k)
account_performance_file = lambda *a, **k: ge.account_performance_file(*a, **k)
account_closed_positions_file = lambda *a, **k: ge.account_closed_positions_file(*a, **k)
load_json = lambda *a, **k: ge.load_json(*a, **k)
save_json = lambda *a, **k: ge.save_json(*a, **k)
get_regime_status = lambda *a, **k: ge.get_regime_status(*a, **k)
get_performance_status = lambda *a, **k: ge.get_performance_status(*a, **k)
find_latest_underlier_spot = lambda *a, **k: ge.find_latest_underlier_spot(*a, **k)
find_latest_option_files = lambda *a, **k: ge.find_latest_option_files(*a, **k)
find_latest_historical_ohlc = lambda *a, **k: ge.find_latest_historical_ohlc(*a, **k)
find_latest_historical_closes = lambda *a, **k: ge.find_latest_historical_closes(*a, **k)
find_latest_technical_indicators = lambda *a, **k: ge.find_latest_technical_indicators(*a, **k)
check_technical_alerts = lambda *a, **k: ge.check_technical_alerts(*a, **k)
get_beta_factor = lambda *a, **k: ge.get_beta_factor(*a, **k)
get_monthly_realized_pnl = lambda *a, **k: ge.get_monthly_realized_pnl(*a, **k)
get_all_active_symbols = lambda *a, **k: ge.get_all_active_symbols(*a, **k)
list_download_files = lambda *a, **k: ge.list_download_files(*a, **k)
persist_new_scans = lambda *a, **k: ge.persist_new_scans(*a, **k)
calculate_trade_journal = lambda *a, **k: ge.calculate_trade_journal(*a, **k)
build_system_snapshot = lambda *a, **k: ge.build_system_snapshot(*a, **k)
dispatch_system_alert = lambda *a, **k: ge.dispatch_system_alert(*a, **k)
normalize_workflow_state = lambda *a, **k: ge.normalize_workflow_state(*a, **k)
cleanup_downloads = lambda *a, **k: ge.cleanup_downloads(*a, **k)
classify_etf = lambda *a, **k: ge.classify_etf(*a, **k)
compute_regime_gates = lambda *a, **k: ge.compute_regime_gates(*a, **k)
get_ticker_analysis_freshness = lambda *a, **k: ge.get_ticker_analysis_freshness(*a, **k)
calculate_grade = lambda *a, **k: ge.calculate_grade(*a, **k)
derive_volatility_profile = lambda *a, **k: ge.derive_volatility_profile(*a, **k)
discover_earnings_date = lambda *a, **k: ge.discover_earnings_date(*a, **k)


def add_screening_parsers(subparsers: Any) -> None:
    """Registers screening command parsers."""
    from src.gex.cli.parser import str2bool, parse_effective_session_date

    p_analyze = subparsers.add_parser("analyze", help="Grades dynamic options candidate setups.")
    p_analyze.add_argument("symbol", type=str, help="Ticker symbol (e.g. AAPL, AMD)")
    p_analyze.add_argument(
        "--effective-session-date",
        type=parse_effective_session_date,
        required=True,
        help="Authoritative latest completed market session date (YYYY-MM-DD)",
    )
    p_analyze.add_argument("--spot", type=float, help="Current spot price")
    p_analyze.add_argument("--ptrans", type=float, help="Positive transition level")
    p_analyze.add_argument("--ntrans", type=float, help="Negative transition level")
    p_analyze.add_argument("--gex", type=float, help="Target positive GEX target level (+GEX / T1)")
    p_analyze.add_argument("--cotmp", type=float, help="Center of Put Mass strike price")
    p_analyze.add_argument("--db-change", type=float, dest="db_change", help="Delta Balance Session change")
    p_analyze.add_argument("--spike-crash", action="store_true", dest="spike_crash", help="Trigger Spike-Crash check warning.")
    p_analyze.add_argument("--inst-file", type=str, help="Option instruments JSON file for derivation")
    p_analyze.add_argument("--quote-file", type=str, help="Option quotes JSON file for derivation")
    p_analyze.add_argument("--hist-file", type=str, help="Underlier historical daily closes JSON file for volatility derivation")
    p_analyze.add_argument("--earnings-date", type=str, dest="earnings_date", help="Upcoming quarterly earnings release date (YYYY-MM-DD)")
    p_analyze.add_argument("--net-liq", type=float, dest="net_liq", help="Estimated Portfolio Net Liq value for sizing checks")
    p_analyze.add_argument("--sizing-threshold", type=float, dest="sizing_threshold", default=DEFAULT_SIZING_THRESHOLD, help=f"Portfolio Net Liq threshold for strict percentage sizing (default: {DEFAULT_SIZING_THRESHOLD})")
    p_analyze.add_argument("--target-delta", type=float, dest="target_delta", default=0.45, help="Option selection target delta (default: 0.45)")
    p_analyze.add_argument("--min-dte", type=int, dest="min_dte", default=30, help="Option selection minimum DTE (default: 30)")
    p_analyze.add_argument("--max-dte", type=int, dest="max_dte", default=45, help="Option selection maximum DTE (default: 45)")
    p_analyze.add_argument("--spread", action="store_true", help="Evaluate defined-risk vertical debit call spreads")

    # Grade Checklist overrides if needed
    p_analyze.add_argument("--rule1", type=str2bool, help="Overriding total call GEX is positive (True/False)")
    p_analyze.add_argument("--rule2", type=str2bool, help="Overriding call GEX exceeds PUT GEX (True/False)")
    p_analyze.add_argument("--rule7", type=str2bool, help="Overriding Total OI > 10,000 contracts (True/False)")
    p_analyze.add_argument("--rule8", type=str2bool, help="Overriding IV < HV (True/False)")
    p_analyze.add_argument("--rule9", type=str2bool, help="Overriding OI Target strike is largest (True/False)")
    p_analyze.add_argument("--rule10", type=str2bool, help="Overriding Dealer Spot net gamma positive (True/False)")
    p_analyze.add_argument("--rule11", type=str2bool, help="Overriding Underlier RV_10 <= 35%% (True/False)")

    # portfolio subcommand

    p_candidates = subparsers.add_parser("update-candidates", help="Persist downloaded scans and update candidate_stocks.json.")
    p_candidates.add_argument("--min-price", type=float, dest="min_price", default=MIN_PRICE, help=f"Minimum stock price (default: {MIN_PRICE})")
    p_candidates.add_argument("--max-price", type=float, dest="max_price", default=MAX_PRICE, help=f"Maximum stock price (default: {MAX_PRICE})")
    p_candidates.add_argument("--min-volume", type=float, dest="min_volume", default=MIN_VOLUME, help=f"Minimum average trading volume (default: {MIN_VOLUME})")
    p_candidates.add_argument("--min-change", type=float, dest="min_change", default=MIN_CHG_PCT, help=f"Minimum stock price day change percent (default: {MIN_CHG_PCT})")
    p_candidates.add_argument("--min-market-cap", type=float, dest="min_market_cap", default=MIN_MARKET_CAP, help=f"Minimum market capitalization (default: {MIN_MARKET_CAP})")
    p_candidates.add_argument("--min-rsi", type=float, help="Filter out candidates with RSI below this threshold (e.g. 30)")
    p_candidates.add_argument("--max-rsi", type=float, help="Filter out candidates with RSI above this threshold (e.g. 70)")
    p_candidates.add_argument("--macd-filter", type=str, choices=["bullish", "bearish", "none"], default="none", help="Filter by MACD Histogram status (bullish: >0, bearish: <0)")
    p_candidates.add_argument("--top", type=int, default=10, help="Number of top candidates to display in output table (default: 10)")
    p_candidates.add_argument("--date", type=str, help="Filter scans by date folder or string (e.g. 20260827)")
    p_candidates.add_argument("--exclude-active", action="store_true", dest="exclude_active", help="Exclude active portfolio positions from candidates")
    p_candidates.add_argument("--include-active", action="store_true", dest="include_active", help="Do not exclude active portfolio positions from candidates")

    # prune-candidates subcommand
    p_prune = subparsers.add_parser("prune-candidates", help="Identify outdated entries from GEX_DAILY_CANDIDATES watchlist.")
    p_prune.add_argument("--watchlist-file", type=str, help="Path to raw get_watchlist_items JSON output")
    p_prune.add_argument("--symbols", nargs="+", help="Specific symbols to evaluate for pruning")
    p_prune.add_argument("--json", action="store_true", help="Output results in JSON format")

    # sentiment subcommand
    p_sent = subparsers.add_parser("sentiment", help="Display Reddit sentiment analysis dashboard and divergence alerts.")
    p_sent.add_argument("--account", type=str, default="", help="Optional account number used to scope the position cache")

    # update-sentiment subcommand
    p_up_sent = subparsers.add_parser("update-sentiment", help="Register/update Reddit sentiment data for a ticker.")
    p_up_sent.add_argument("ticker", type=str, help="Ticker symbol (e.g. BABA)")
    p_up_sent.add_argument("--score", type=float, required=True, help="Sentiment score from -1.0 (capitulation) to +1.0 (FOMO)")
    p_up_sent.add_argument("--buzz", type=str, choices=["High", "Medium", "Low", "None", "Med"], required=True, help="Discussion volume / buzz")
    p_up_sent.add_argument("--narrative", type=str, required=True, help="Core narrative thesis / catalysts")
    p_up_sent.add_argument("--tone", type=float, default=0.0, help="Tone score / Title & Body Directional Bias (-0.30 to +0.30)")
    p_up_sent.add_argument("--comments", type=float, default=0.0, help="Comments polarity score (-0.30 to +0.30)")
    p_up_sent.add_argument("--position", type=float, default=0.0, help="Retail positioning conviction score (-0.20 to +0.20)")
    p_up_sent.add_argument("--volume-score", type=float, default=0.0, help="Upvote & Discussion intensity score (-0.10 to +0.10)")
    p_up_sent.add_argument("--meme", type=float, default=0.0, help="Hype slang & Meme/Emoji density score (-0.10 to +0.10)")

    # sync-pnl subcommand

    p_rankings = subparsers.add_parser("rankings", help="Displays a beautiful ranked report of all historically analyzed ticker setups.")
    p_rankings.add_argument("--status", type=str, choices=["ALL", "CONFIRMED", "PENDING", "BLOCKED"], default="ALL", help="Filter by signal status (default: ALL)")
    p_rankings.add_argument("--min-grade", type=int, dest="min_grade", help="Filter by minimum structural grade (0 to 11)")
    p_rankings.add_argument("--sort", type=str, choices=["grade", "spot", "cushion", "rr", "status"], default="grade", help="Sort the rankings table (default: grade)")

    # closed subcommand

    p_spreads = subparsers.add_parser("select-spreads", help="Selects defined-risk vertical debit call spreads pairing ATM calls with +GEX call walls.")
    p_spreads.add_argument("--symbol", type=str, required=True, help="Underlier ticker symbol (e.g. NVDA, AAPL)")
    p_spreads.add_argument("--spot", type=float, help="Current underlier spot price (defaults to cached spot)")
    p_spreads.add_argument("--gex", type=float, help="+GEX target strike / Call Wall (defaults to cached +GEX)")
    p_spreads.add_argument("--inst-file", type=str, help="Option instruments JSON file")
    p_spreads.add_argument("--quote-file", type=str, help="Option quotes JSON file")
    p_spreads.add_argument("--earnings-date", type=str, help="Upcoming earnings date (YYYY-MM-DD)")
    p_spreads.add_argument("--target-delta", type=float, default=0.45, help="Target long leg delta (default: 0.45)")
    p_spreads.add_argument("--min-dte", type=int, default=30, help="Minimum target DTE (default: 30)")
    p_spreads.add_argument("--max-dte", type=int, default=45, help="Maximum target DTE (default: 45)")
    p_spreads.add_argument("--json", action="store_true", help="Output results as JSON")


    p_payoff = subparsers.add_parser("payoff", help="Runs an offline option payoff simulation scenario grid.")
    p_payoff.add_argument("symbol", type=str, help="Ticker symbol (e.g. NVDA)")
    p_payoff.add_argument("--spot", type=float, required=True, help="Current underlier spot price")
    p_payoff.add_argument("--strike", type=float, required=True, help="Option strike price")
    p_payoff.add_argument("--mark", type=float, required=True, help="Option current Mark contract premium")
    p_payoff.add_argument("--delta", type=float, default=0.50, help="Option delta (default: 0.50)")
    p_payoff.add_argument("--gamma", type=float, default=0.01, help="Option gamma (default: 0.01)")
    p_payoff.add_argument("--dte", type=int, default=30, help="Option days to expiration (default: 30)")
    p_payoff.add_argument("--target-spots", type=str, dest="target_spots", help="Comma-separated custom underlier spot prices to evaluate")

    # simulate subcommand
    p_sim = subparsers.add_parser("simulate", help="Simulates price movements for active positions or candidates.")
    p_sim.add_argument("symbol", help="Ticker symbol")
    p_sim.add_argument("spot", type=float, help="Simulated spot price")
    p_sim.add_argument("--account", type=str, default="", help="Optional account number used to scope the position cache")

    # pre-earnings-candidates subcommand (Roadmap 5.11 Pre-Earnings Vega Run-Up Harvester)
    p_pre_earn = subparsers.add_parser("pre-earnings-candidates", help="Scan underliers entering pre-earnings IV expansion ramp (15-25 DTE, IV Rank <= 40%%).")
    p_pre_earn.add_argument("--symbols", nargs="+", help="Specific ticker symbols to evaluate")
    p_pre_earn.add_argument("--min-days", type=int, default=15, help="Minimum days to earnings (default: 15)")
    p_pre_earn.add_argument("--max-days", type=int, default=25, help="Maximum days to earnings (default: 25)")
    p_pre_earn.add_argument("--max-iv-rank", type=float, default=40.0, help="Maximum IV Rank threshold (default: 40.0)")
    p_pre_earn.add_argument("--strict-iv-rank", action="store_true", help="Require at least 20 historical IV observations for IV Rank")
    p_pre_earn.add_argument("--session-date", type=str, help="Market session date (YYYY-MM-DD)")
    p_pre_earn.add_argument("--json", action="store_true", help="Output machine-readable JSON format")





def cmd_analyze(args):
    """Grades and analyzes options setups for a given ticker."""
    symbol = args.symbol.upper()
    analyses = load_json(ge.ANALYSES_FILE, {})
    
    cached = analyses.get(symbol, {})
    
    # Fallback spot from candidates or downloads if not passed and not cached
    spot = args.spot if args.spot is not None else cached.get("Spot")
    if spot is None:
        spot = find_latest_underlier_spot(symbol)

    # Discover and resolve upcoming earnings schedule
    earnings_date = args.earnings_date if getattr(args, "earnings_date", None) else discover_earnings_date(symbol)
    if not earnings_date and cached.get("earnings_date"):
        earnings_date = cached.get("earnings_date")

    inst_data = None
    quotes_data = None
    vol_profile = None

    # Discover option files if not explicitly passed
    discovered_files = find_latest_option_files(symbol)
    inst_file = getattr(args, "inst_file", None)
    if inst_file:
        try:
            inst_file = validate_safe_path(inst_file)
        except ValueError as e:
            print(f"Error: Invalid inst_file path: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        inst_file = discovered_files.get("inst_file")

    quote_file = getattr(args, "quote_file", None)
    if quote_file:
        try:
            quote_file = validate_safe_path(quote_file)
        except ValueError as e:
            print(f"Error: Invalid quote_file path: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        quote_file = discovered_files.get("quote_file")

    hist_file = getattr(args, "hist_file", None)
    if hist_file:
        try:
            hist_file = validate_safe_path(hist_file)
        except ValueError as e:
            print(f"Error: Invalid hist_file path: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        hist_file = discovered_files.get("hist_file")

    # If inst-file and quote-file exist, perform mechanical local GEX profile derivation
    gex_profile: Optional[Dict[str, Any]] = None
    if inst_file and quote_file:
        try:
            inst_data = load_json(inst_file, None)
            quotes_data = load_json(quote_file, None)
                
            calc_spot = spot if spot is not None else 100.0
            gex_profile = derive_gex_profile(inst_data, quotes_data, calc_spot)
            
            # Map parameters from gex_profile dict
            total_oi = gex_profile["total_oi"]
            total_call_gex = gex_profile["total_call_gex"]
            total_put_gex = gex_profile["total_put_gex"]
            derived_ptrans = gex_profile["derived_ptrans"]
            derived_ntrans = gex_profile["derived_ntrans"]
            derived_gex = gex_profile["derived_gex"]
            derived_cotmp = gex_profile["derived_cotmp"]
            
            # Set rule arguments if they are None
            if args.ptrans is None: args.ptrans = round(derived_ptrans, 2)
            if args.ntrans is None: args.ntrans = round(derived_ntrans, 2)
            if args.gex is None: args.gex = round(derived_gex, 2)
            if args.cotmp is None: args.cotmp = round(derived_cotmp, 2)
            
            if getattr(args, "rule1", None) is None: args.rule1 = gex_profile["rule1_derived"]
            if getattr(args, "rule2", None) is None: args.rule2 = gex_profile["rule2_derived"]
            if getattr(args, "rule7", None) is None: args.rule7 = gex_profile["rule7_derived"]
            if getattr(args, "rule9", None) is None: args.rule9 = gex_profile["rule9_derived"]
            if getattr(args, "rule10", None) is None: args.rule10 = gex_profile["rule10_derived"]
            
            if total_oi > 0 and inst_data and quotes_data:
                if hist_file:
                    try:
                        hist_data = load_json(hist_file, None)
                        
                        vol_profile = derive_volatility_profile(hist_data, symbol, gex_profile["iv_sum"], gex_profile["iv_count"])
                        
                        if getattr(args, "rule8", None) is None: args.rule8 = vol_profile["rule8_derived"]
                        if getattr(args, "rule11", None) is None: args.rule11 = vol_profile["rule11_derived"]
                        
                        print(format_color(f"📈 Volatility Profile Derivation complete for {symbol}:", "32", bold=True))
                        print(f"  -> IV30 Proxy: {vol_profile['iv30_val']:.2f}% vs HV90 Proxy: {vol_profile['hv90_val']:.2f}% (Rule8: {vol_profile['rule8_derived']})")
                        print(f"  -> RV10: {vol_profile['rv10_val']:.2f}% (Rule11 Setup Vol Compression: {'PASS' if vol_profile['rule11_derived'] else 'FAIL'})")
                    except Exception as ve:
                        print(f"Error deriving volatility indices from historical price files: {ve}", file=sys.stderr)
                
                print(format_color(f"🤖 Upgraded GEX Derivation complete for {symbol}:", "32", bold=True))
                print(f"  -> COTMP: ${derived_cotmp:.2f}, pTrans: ${derived_ptrans:.2f}, nTrans: ${derived_ntrans:.2f}, +GEX: ${derived_gex:.2f}")
                print(f"  -> Call GEX: ${total_call_gex:,.2f}, Put GEX: ${total_put_gex:,.2f} (Rule2: {gex_profile['rule2_derived']})")
        except Exception as e:
            print(f"Error deriving GEX profile from option data files: {e}", file=sys.stderr)

    ptrans = args.ptrans if args.ptrans is not None else cached.get("pTrans")
    ntrans = args.ntrans if args.ntrans is not None else cached.get("nTrans")
    gex = args.gex if args.gex is not None else cached.get("+GEX")
    cotmp = args.cotmp if args.cotmp is not None else cached.get("COTMP")
    db_change = args.db_change if args.db_change is not None else cached.get("db_change")
    if db_change is None:
        db_change = 0.0
    spike_crash = args.spike_crash if args.spike_crash is not None else cached.get("spike_crash", False)
    
    if spot is None or ptrans is None or ntrans is None or gex is None or cotmp is None:
        print(f"Error: Missing required metrics for {symbol}. Pass them via command line arguments, provide option data files, or ensure they exist in {ge.ANALYSES_FILE}.", file=sys.stderr)
        print("Required fields: --spot, --ptrans, --ntrans, --gex, --cotmp, --db-change", file=sys.stderr)
        sys.exit(1)

    # Cast to float to satisfy type checker after null check
    spot = float(spot)
    ptrans = float(ptrans)
    ntrans = float(ntrans)
    gex = float(gex)
    cotmp = float(cotmp)
    db_change = float(db_change)
        
    # Calculate Grade (rule overrides fall back to cached values, then True)
    rule_overrides = {
        "rule1": args.rule1 if args.rule1 is not None else cached.get("rule1", True),
        "rule2": args.rule2 if args.rule2 is not None else cached.get("rule2", True),
        "rule7": args.rule7 if args.rule7 is not None else cached.get("rule7", True),
        "rule8": args.rule8 if args.rule8 is not None else cached.get("rule8", True),
        "rule9": args.rule9 if args.rule9 is not None else cached.get("rule9", True),
        "rule10": args.rule10 if args.rule10 is not None else cached.get("rule10", True),
        "rule11": args.rule11 if args.rule11 is not None else cached.get("rule11", True),
    }
    extra_rules = {
        "total_call_gex_positive": rule_overrides["rule1"],
        "call_gex_gt_put_gex": rule_overrides["rule2"],
        "total_oi_gt_10000": rule_overrides["rule7"],
        "iv_30_lt_hv_90": rule_overrides["rule8"],
        "oi_depth_target_positive": rule_overrides["rule9"],
        "dealer_gamma_net_positive": rule_overrides["rule10"],
        "rv_10_stable": rule_overrides["rule11"],
    }
    
    grade, rule_checklist = calculate_grade(symbol, spot, ptrans, ntrans, gex, cotmp, extra_rules)
    
    # Calculate COTMP Cushion
    # Formula: ((Spot - COTMP) / COTMP) * 100
    cotmp_cushion = round(((spot - cotmp) / cotmp) * 100, 2)
    
    # Calculate Risk/Reward
    # Formula: Reward = (+GEX - Spot), Risk = Spot - pTrans
    reward = gex - spot
    risk = spot - ptrans
    rr_ratio = round(reward/risk, 2) if risk > 0 else 999.0

    best_option_cached = None
    proposed_option_expiration = None
    earnings_gate_status = "N/A (No contract to evaluate against)"
    days_out_str = "N/A"
    
    if earnings_date:
        try:
            today_dt = datetime.today().date()
            earnings_dt = datetime.strptime(earnings_date, "%Y-%m-%d").date()
            days_out = (earnings_dt - today_dt).days
            days_out_str = f"{days_out:d} days out"
        except (ValueError, TypeError):
            pass

    if inst_data is not None and quotes_data is not None:
        target_delta = getattr(args, "target_delta", 0.45)
        min_dte = getattr(args, "min_dte", 30)
        max_dte = getattr(args, "max_dte", 45)
        best_option, _ = select_best_option(
            inst_data, quotes_data, spot, gex,
            target_delta=target_delta, min_dte=min_dte, max_dte=max_dte,
            earnings_date=earnings_date
        )
        if best_option:
            best_option_cached = best_option
            proposed_option_expiration = best_option['expiration_date']
            
            if earnings_date:
                if best_option.get("earnings_blocked", False):
                    earnings_gate_status = "FAIL - BLOCKED BY EARNINGS RISK (Earnings occur before expiration; IV Crush Danger)"
                else:
                    earnings_gate_status = "PASS (Earnings event occurs after option expiration)"

    # Define Signal Status & Classification
    # Watchdog buffer is 0.5% below pTrans. If Spot reaches watchdog buffer or above setup rules
    watchdog_threshold = ptrans * 0.995
    
    status = "BLOCKED"
    reasons = []
    
    if grade < 9:
        reasons.append(f"Grade <= 8 ({grade}/11)")
    
    # db_change filter: must satisfy db_change >= 0.50 (Grade 11 DEEP = 0.30)
    db_threshold = 0.50
    if grade == 11 and cotmp_cushion >= 1.0 and cotmp_cushion < 2.0:
        db_threshold = 0.30
    if cached.get("pegged_1_00_sessions", 0) >= 2:
        db_threshold = 0.0  # Exempt
        
    if db_change < db_threshold:
        reasons.append(f"db_change {db_change:.2f} < threshold {db_threshold:.2f}")
        
    # COTMP Cushion target: Spot >= 2.0% above COTMP (Grade 11 or high db_change >= 0.50 can use 1.0%)
    cushion_threshold = 2.0
    if grade == 11 or db_change >= 0.50:
        cushion_threshold = 1.0
        
    if cotmp_cushion < cushion_threshold:
        reasons.append(f"COTMP Cushion {cotmp_cushion:.2f}% < threshold {cushion_threshold:.2f}%")
        
    if spike_crash:
        reasons.append("Spike-Crash Pattern profile detected")
        
    if rr_ratio < 2.0:
        reasons.append(f"Risk/Reward ratio {rr_ratio:.2f} < 2.00")

    if best_option_cached and best_option_cached.get("earnings_blocked", False):
        reasons.append("Option contract blocked by Earnings IV-Crush Risk")
        
    if not reasons:
        if spot >= ptrans:
            status = "CONFIRMED"
        elif spot >= watchdog_threshold:
            status = f"PENDING (watchdog)"
        else:
            status = "PENDING (below watchdog)"
    else:
        status = f"BLOCKED ({', '.join(reasons)})"
        
    iv30 = cached.get("iv30_val")
    hv90 = cached.get("hv90_val")
    rv10 = cached.get("rv10_val")
    if 'vol_profile' in locals() and vol_profile is not None:
        iv30 = vol_profile.get("iv30_val")
        hv90 = vol_profile.get("hv90_val")
        rv10 = vol_profile.get("rv10_val")

    current_iv = None
    if gex_profile and gex_profile.get("iv_count", 0) > 0:
        current_iv = round((gex_profile["iv_sum"] / gex_profile["iv_count"]) * 100.0, 2)
    elif cached.get("current_iv") is not None:
        current_iv = cached.get("current_iv")

    try:
        save_gex_snapshot(
            symbol=symbol,
            spot=spot,
            ptrans=ptrans,
            ntrans=ntrans,
            gex=gex,
            cotmp=cotmp,
            net_gex=gex_profile.get("net_gex", 0.0) if gex_profile else 0.0,
            total_oi=gex_profile.get("total_oi", 0) if gex_profile else 0,
            iv=current_iv,
            session_date=args.effective_session_date,
        )
    except Exception:
        pass

    hist_ivs = query_historical_ivs(symbol)
    iv_rank = calculate_iv_rank(current_iv, hist_ivs) if current_iv is not None else None
    iv_percentile = calculate_iv_percentile(current_iv, hist_ivs) if current_iv is not None else None

    # Update analyses file
    analyses[symbol] = {
        "Ticker": symbol,
        "Spot": round(spot, 2),
        "Grade": grade,
        "pTrans": round(ptrans, 2),
        "nTrans": round(ntrans, 2),
        "+GEX": round(gex, 2),
        "COTMP": round(cotmp, 2),
        "db_change": round(db_change, 2),
        "COTMP Cushion": cotmp_cushion,
        "Risk/Reward": rr_ratio,
        "iv30_val": round(iv30, 2) if iv30 is not None else None,
        "hv90_val": round(hv90, 2) if hv90 is not None else None,
        "rv10_val": round(rv10, 2) if rv10 is not None else None,
        "current_iv": current_iv,
        "iv_rank": round(iv_rank, 2) if iv_rank is not None else None,
        "iv_percentile": round(iv_percentile, 2) if iv_percentile is not None else None,
        "Signal Status": status,
        "analyzed_date": args.effective_session_date,
        "spike_crash": bool(spike_crash),
        "earnings_date": earnings_date,
        "earnings_gate_status": "FAIL" if (best_option_cached and best_option_cached.get("earnings_blocked", False)) else "PASS" if earnings_date else "N/A",
        **rule_overrides
    }
    # Keep count of pegged sessions if db_change is exactly 1.00
    if db_change == 1.00:
        analyses[symbol]["pegged_1_00_sessions"] = cached.get("pegged_1_00_sessions", 0) + 1
    else:
        analyses[symbol]["pegged_1_00_sessions"] = 0
        
    save_json(ge.ANALYSES_FILE, analyses)
    
    # Print results formatted perfectly
    grade_color = "32" if grade >= 9 else "31"
    db_color = "32" if db_change >= db_threshold else "31"
    cushion_color = "32" if cotmp_cushion >= cushion_threshold else "31"
    sc_color = "31" if spike_crash else "32"
    rr_color = "32" if rr_ratio >= 2.0 else "31"
    
    status_fmt = format_color(status, "32" if status.startswith("CONFIRMED") else ("33" if status.startswith("PENDING") else "31"), bold=True)
    
    print(f"### 🔍 Setup Breakdown: {symbol}")
    print(f"- **Current Spot**: ${spot:.2f}")
    print(f"- **Key Gamma Levels**:")
    print(f"  - pTrans (Positive Transition): ${ptrans:.2f}")
    print(f"  - nTrans (Negative Transition): ${ntrans:.2f}")
    print(f"  - +GEX (T1 Target): ${gex:.2f}")
    print(f"  - COTMP (Center of Put Mass): ${cotmp:.2f}")
    if gex_profile:
        print(f"  {format_vanna_charm_summary(gex_profile)}")
    print(f"- **IV Regime Context**: {format_iv_context(current_iv, iv_rank, iv_percentile, len(hist_ivs))}")
    
    scale_str = generate_ascii_gex_scale(spot, ptrans, ntrans, gex, cotmp)
    print(f"\n### 🛣️ Dealer GEX Structural Runway Map")
    print(f"  {scale_str}\n")

    print(f"### 📅 Earnings Calendar Safety Check:")
    print(f"- **Upcoming Earnings Date**: {earnings_date or 'N/A'}" + (f" ({days_out_str})" if earnings_date else ""))
    print(f"- **Proposed Option Expiration**: {proposed_option_expiration or 'N/A'}")
    eg_color = "32" if "PASS" in earnings_gate_status else ("31" if "FAIL" in earnings_gate_status else "37")
    eg_fmt = format_color(earnings_gate_status, eg_color, bold=("FAIL" in earnings_gate_status))
    print(f"- **Earnings Gate Status**: {eg_fmt}\n")
    
    print(f"- **Core Filters**:")
    print(f"  1. **Structural Grade**: {format_color(f'{grade}/11', grade_color)} (Status: {format_color('PASS' if grade >= 9 else 'FAIL', grade_color, bold=True)})")
    print(f"  2. **db_change (Delta Balance Change)**: {format_color(f'{db_change:.2f}', db_color)} (Status: {format_color('PASS' if db_change >= db_threshold else 'FAIL', db_color, bold=True)})")
    print(f"  3. **COTMP Cushion**: {format_color(f'{cotmp_cushion:.2f}%', cushion_color)} (Status: {format_color('PASS' if cotmp_cushion >= cushion_threshold else 'FAIL', cushion_color, bold=True)})")
    print(f"  4. **Spike-Crash Check**: {format_color('FAIL - Blocked' if spike_crash else 'PASS - No Pattern', sc_color, bold=True)}")
    print(f"  5. **Risk/Reward Ratio**: {format_color(f'{rr_ratio:.2f}:1', rr_color)} (Status: {format_color('PASS' if rr_ratio >= 2.0 else 'FAIL', rr_color, bold=True)})")
    
    # Detailed 11-Rule Breakdown for structural GEX evaluation
    rule_descriptions = [
        "Total Call GEX is positive (bullish posture)",
        "Total Call GEX exceeds absolute value of Total Put GEX (net positive positioning)",
        "Underlier Spot price is above Center of Put Mass (COTMP)",
        "Largest positive GEX target strike (+GEX / T1 Target) is above current stock Spot price",
        "Positive transition (pTrans) sits above negative transition (nTrans)",
        "Stock Spot price sits above pTrans (entry trigger rule)",
        "Total Open Interest (OI) exceeds 10,000 contracts for structural depth",
        "30-day option implied volatility (IV30) is below historical 90-day realized volatility (HV90)",
        "Open Interest depth at the +GEX target strike exceeds all other strikes",
        "Dealer net gamma positioning at the current Spot is net positive",
        "Underlier's 10-day realized volatility (RV10) is compressed (<= 35%)"
    ]
    print("\n### 📋 Structural GEX 11-Rule Checklist Breakdown")
    for i, passed in enumerate(rule_checklist):
        rule_num = i + 1
        indicator = format_color("  [PASS]", "32", bold=True) if passed else format_color("  [FAIL]", "31", bold=True)
        print(f"{indicator} Rule {rule_num:02d}: {rule_descriptions[i]}")
        
    print(f"\n### 🚀 Status & Action")
    print(f"- **Signal Status**: {status_fmt}")
    if status.startswith("CONFIRMED"):
        print_color(f"- **Recommended Play**: Underlier Spot is above pTrans. Look for bullish Option contract entry targeting ${gex:.2f}.", "32", bold=True)
    elif status.startswith("PENDING"):
        print_color(f"- **Recommended Play**: Setup valid. Standard watch list entry activated. Look for 5-minute close above pTrans (${ptrans:.2f}) to trigger execution.", "33", bold=True)
    else:
        print_color(f"- **Recommended Play**: NO ENTRY. Setup blocked by system safeguards.", "31", bold=True)

    max_contracts_cached = 0
    cost_per_contract_cached = 0.0

    if best_option_cached:
        best_option = best_option_cached
        eb_status_str = ""
        if best_option.get("earnings_blocked", False):
            eb_status_str = format_color(" | 🔴 BLOCKED BY EARNINGS RISK", "31", bold=True)
            
        print(f"\n### 🎯 Option Selection Recommendation")
        print(f"- **Target Contract**: Call Option strike ${best_option['strike']:.2f} expiring {best_option['expiration_date']} (DTE: {best_option['dte']}){eb_status_str}")
        print(f"- **Option ID**: {best_option['option_id']}")
        print(f"- **Greeks & Pricing**:")
        print(f"  - Mark Price: ${best_option['mark']:.2f} (Ask: ${best_option['ask']:.2f}, Bid: ${best_option['bid']:.2f}, Spread: ${best_option['spread']:.2f})")
        delta_str = f"{best_option['delta']:.4f}" if best_option['delta'] is not None else "N/A"
        gamma_str = f"{best_option['gamma']:.4f}" if best_option['gamma'] is not None else "N/A"
        print(f"  - Delta: {delta_str} | Gamma: {gamma_str} | Implied Vol: {best_option['iv']*100:.1f}%")
        print(f"  - Liquidity Metrics: Open Interest: {best_option['oi']} | Volume: {best_option['vol']}")
        
        # Print spread and liquidity warnings
        flags = []
        if not best_option['spread_ok']:
            flags.append("HIGH-SPREAD RISK")
        if not best_option['oi_ok']:
            flags.append("LOW-OI RISK")
        if best_option.get("earnings_blocked", False):
            flags.append("EARNINGS IV-CRUSH RISK")
        
        if flags:
            flag_str = " | ".join(flags)
            print(format_color(f"  - ⚠️ WARNING: [{flag_str}] contract has wide bid-ask spread, insufficient open interest, or upcoming earnings risk.", "33", bold=True))
        else:
            print(format_color("  - ✅ LIQUIDITY GATE: PASS", "32"))

        # Sizing / Constraints calculator
        net_liq = getattr(args, "net_liq", None)
        if net_liq is None:
            net_liq = 50000.0

        sizing_threshold = getattr(args, "sizing_threshold", None)
        if sizing_threshold is None:
            sizing_threshold = DEFAULT_SIZING_THRESHOLD
        
        cost_per_contract = best_option['mark'] * 100.0
        cost_per_contract_cached = cost_per_contract
        is_micro_account = net_liq < sizing_threshold

        if is_micro_account:
            # Micro-Account (< $10,000 Net Liq): 1-contract minimum sizing applies, bounded strictly by available buying power
            if cost_per_contract > 0 and cost_per_contract <= net_liq:
                max_contracts = 1
                max_risk = cost_per_contract
            else:
                max_contracts = 0
                max_risk = 0.0
        else:
            max_risk = net_liq * 0.03
            if cost_per_contract > 0:
                max_contracts = int(max_risk // cost_per_contract)
            else:
                max_contracts = 0
        max_contracts_cached = max_contracts
            
        print(f"- **Aggregate Sizing Simulation**:")
        print(f"  - Portfolio Net Liq Reference: ${net_liq:,.2f}")
        if is_micro_account:
            print(f"  - Sizing Mode: {format_color(f'Micro-Account (< ${sizing_threshold:,.0f} Net Liq)', '33', bold=True)} (1-Contract Minimum Sizing, exempt from <=3.0% cap)")
            print(f"  - Single-Leg Max Sizing Allowed: {format_color(f'1 contract up to Net Liq (${net_liq:,.2f})', '33')}")
            if cost_per_contract > net_liq:
                print(format_color(f"  - ⚠️ INSUFFICIENT BUYING POWER: Contract cost (${cost_per_contract:,.2f}) exceeds account Net Liq (${net_liq:,.2f}).", "31", bold=True))
        else:
            print(f"  - Single-Leg Max Sizing Allowed (3.0% Net Liq): ${max_risk:,.2f}")
        print(f"  - Estimated Sizing Recommendation: {format_color(f'{max_contracts} contracts', '32', bold=True)} at ${best_option['mark']:.2f} per premium (Total Premium: ${max_contracts * cost_per_contract:,.2f})")

        # Render Option Payoff Projection Matrix Table
        print(f"\n### 📊 Option Payoff Projection Matrix")
        print("  This matrix simulates target contract value using Delta & Gamma price adjustment")
        print("  and is adjusted for square-root-of-time extrinsic decay.")
        print("  " + "-" * 141)
        print(f"  {'Target Spot':<20} | {'Underlier %':<11} | {'Scenario / Level':<24} | {'Day 0 (Instant)':<17} | {'Day 3 Held':<17} | {'Day 7 Held':<17} | {'Day 14 Held'}")
        print("  " + "-" * 141)
        
        # Scenarios to print
        scenarios = []
        if ntrans is not None and ntrans > 0:
            scenarios.append((ntrans, "nTrans (Structural Stop)"))
        if ptrans is not None and ptrans > 0:
            scenarios.append((ptrans, "pTrans (Transition/Entry)"))
        scenarios.append((spot, "Baseline Spot (Current)"))
        
        midway = spot + (gex - spot) / 2.0
        scenarios.append((midway, "T1 Halfway Level"))
        
        if gex is not None and gex > 0:
            scenarios.append((gex, "+GEX (T1 Target)"))
            t2_stretch = gex + (gex - spot) * 0.5
            scenarios.append((t2_stretch, "T2 (Stretch Target)"))
            
        # Filter and sort unique target spots
        unique_scenarios = {}
        for s_price, s_name in scenarios:
            s_price = round(s_price, 2)
            if s_price not in unique_scenarios:
                unique_scenarios[s_price] = s_name
                
        import math
        for s_price in sorted(unique_scenarios.keys()):
            s_name = unique_scenarios[s_price]
            pct_chg = ((s_price - spot) / spot) * 100.0 if spot > 0 else 0.0
            underlier_chg_str = f"{pct_chg:+.2f}%"
            
            delta_s = s_price - spot
            opt_strike = best_option['strike']
            opt_mark = best_option['mark']
            opt_delta = best_option['delta'] if best_option['delta'] is not None else 0.45
            opt_gamma = best_option['gamma'] if best_option['gamma'] is not None else 0.01
            opt_dte = best_option['dte'] if best_option['dte'] is not None else 30
            
            # Instantaneous (Day 0)
            intrinsic_target = max(0.0, s_price - opt_strike)
            instant_mark = max(intrinsic_target, opt_mark + (opt_delta * delta_s) + (0.5 * opt_gamma * (delta_s ** 2)))
            instant_pnl = ((instant_mark - opt_mark) / opt_mark) * 100.0 if opt_mark > 0 else 0.0
            
            # Day 3 Held
            extrinsic_instant = instant_mark - intrinsic_target
            t_decay_factor_3 = math.sqrt(max(0, opt_dte - 3) / opt_dte) if opt_dte > 0 else 0.0
            day3_mark = intrinsic_target + extrinsic_instant * t_decay_factor_3
            day3_pnl = ((day3_mark - opt_mark) / opt_mark) * 100.0 if opt_mark > 0 else 0.0
            
            # Day 7 Held
            t_decay_factor_7 = math.sqrt(max(0, opt_dte - 7) / opt_dte) if opt_dte > 0 else 0.0
            day7_mark = intrinsic_target + extrinsic_instant * t_decay_factor_7
            day7_pnl = ((day7_mark - opt_mark) / opt_mark) * 100.0 if opt_mark > 0 else 0.0
            
            # Day 14 Held
            t_decay_factor_14 = math.sqrt(max(0, opt_dte - 14) / opt_dte) if opt_dte > 0 else 0.0
            day14_mark = intrinsic_target + extrinsic_instant * t_decay_factor_14
            day14_pnl = ((day14_mark - opt_mark) / opt_mark) * 100.0 if opt_mark > 0 else 0.0
            
            is_spot_row = abs(s_price - spot) < 0.01
            s_price_label = f"${s_price:.2f} (Baseline Spot)" if is_spot_row else f"${s_price:.2f}"
            s_price_str = f"{s_price_label:<20}"
            s_name_str = f"{s_name:<24}"
            
            def fmt_pnl_cell(m_val, p_val, width=17):
                raw_str = f"${m_val:.2f} ({p_val:+.1f}%)"
                raw_padded = raw_str.ljust(width)
                p_color = get_pnl_color(p_val)
                p_bold = p_val >= 20.0 or p_val <= -20.0
                return format_color(raw_padded, p_color, bold=p_bold)
                
            cell_d0 = fmt_pnl_cell(instant_mark, instant_pnl)
            cell_d3 = fmt_pnl_cell(day3_mark, day3_pnl)
            cell_d7 = fmt_pnl_cell(day7_mark, day7_pnl)
            cell_d14 = fmt_pnl_cell(day14_mark, day14_pnl)
            
            spot_col_color = "35" if is_spot_row else "37"
            spot_fmt_str = format_color(s_price_str, spot_col_color, bold=is_spot_row)
            chg_fmt_str = format_color(f"{underlier_chg_str:<11}", "32" if pct_chg > 0 else ("31" if pct_chg < 0 else "37"), bold=(is_spot_row or (gex is not None and abs(s_price - gex) < 0.01)))
            
            print(f"  {spot_fmt_str} | {chg_fmt_str} | {s_name_str} | {cell_d0} | {cell_d3} | {cell_d7} | {cell_d14}")
            
        print("  " + "-" * 141)

        # High-IV Defined-Risk Vertical Spread Alternative (Milestone 6.1)
        show_spread = getattr(args, "spread", False) or (iv_rank is not None and iv_rank > 70.0)
        best_spread = None
        if show_spread and inst_data and quotes_data:
            best_spread, all_spreads = select_vertical_spread(
                inst_data, quotes_data, spot, gex_target=gex, earnings_date=earnings_date
            )
            if best_spread:
                analyses[symbol]["recommended_vertical_spread"] = best_spread.to_dict()
                save_json(ge.ANALYSES_FILE, analyses)
                print()
                print_color("### 🛡️ High-IV Regime Defined-Risk Alternative: Vertical Debit Spread", "36", bold=True)
                if iv_rank is not None and iv_rank > 70.0:
                    print_color(f"  -> Implied Volatility is elevated (IV Rank: {iv_rank:.1f} > 70.0). Vertical debit spread mitigates theta decay and IV crush.", "33")
                print(format_vertical_spread_summary(best_spread))

    # Render Execution Approval Requests for systematic entry setups
    regime = get_regime_status()
    auth = regime.get("system_authorization", "BLOCKED")
    
    if "Option contract blocked by Earnings IV-Crush Risk" in reasons:
        print_color(f"\n⚠️ ENTRY BLOCKED: Option contract is blocked by Earnings IV-Crush Risk. No entry authorized.", "31", bold=True)
    elif "BLOCK" not in auth and (status.startswith("CONFIRMED") or status.startswith("PENDING")):
        print_color("\n" + "=" * 95, "32", bold=True)
        print_color("🔔                        EXECUTION APPROVAL REQUEST (PROPOSED ENTRY)", "32", bold=True)
        print_color("=" * 95, "32", bold=True)
        print_color(f"[ACTION REQUIRED] Confirm GEX underlier entry setup and routing for {symbol}:", "37", bold=True)
        print(f"\n  Asset: {format_color(symbol, '35', bold=True)} (Underlier Spot: ${spot:.2f})")
        print(f"  -> STATUS: {status_fmt}")
        if status.startswith("CONFIRMED"):
            print(f"  -> PLAY: Underlier Spot is above pTrans (${ptrans:.2f}). Look for bullish Option contract entry targeting ${gex:.2f}.")
        else:
            print(f"  -> PLAY: Setup valid but pending trigger. Look for 5-minute close above pTrans (${ptrans:.2f}) to execute.")
            
        if best_option_cached:
            print(f"  -> CONTRACT: Call Strike ${best_option_cached['strike']:.2f} Expiring {best_option_cached['expiration_date']} (DTE: {best_option_cached['dte']})")
            print(f"  -> SIZING: {max_contracts_cached} contracts at ${best_option_cached['mark']:.2f} per premium (Total Premium: ${max_contracts_cached * cost_per_contract_cached:,.2f})")
            
        print_color("\n  -> INSTRUCTIONS: To authorize entry routing, respond with 'YES' in chat to trigger agentic-trader.", "37")
        print_color("=" * 95 + "\n", "32", bold=True)
    elif "BLOCK" in auth and (status.startswith("CONFIRMED") or status.startswith("PENDING")):
        print_color(f"\n⚠️ ENTRY BLOCKED: Broad-market daily regime ({auth}) is currently prohibiting new entries. No action taken.", "31", bold=True)


def cmd_update_candidates(args):
    """Sources, persists, filters, and saves candidates from raw scan files."""
    # First persist any new scan downloads
    persist_new_scans()
    
    # Pre-list download directory files once for candidate indicator lookups to avoid O(N) os.walk traversals in loops
    download_files = list_download_files(ge.DOWNLOADS_DIR)

    # Identify active positions to optionally exclude if requested
    active_symbols = set(get_all_active_symbols())
    exclude_active = getattr(args, "exclude_active", False)
    excluded_actives = set()

    # Load existing candidates to preserve those manually added or sourced from Reddit
    existing_data = load_json(ge.CANDIDATES_FILE, {"candidates": []})
    candidates = {}
    for c in existing_data.get("candidates", []):
        sym = c.get("symbol", "").upper()
        if exclude_active and sym in active_symbols:
            excluded_actives.add(sym)
            continue
        if c.get("source") == "reddit":
            candidates[sym] = c
            
    if candidates:
        print(f"Preserving {len(candidates)} existing Reddit-sourced candidates.")
    
    min_price = getattr(args, "min_price", MIN_PRICE)
    max_price = getattr(args, "max_price", MAX_PRICE)
    min_volume = getattr(args, "min_volume", MIN_VOLUME)
    min_change = getattr(args, "min_change", MIN_CHG_PCT)
    min_market_cap = getattr(args, "min_market_cap", MIN_MARKET_CAP)
    date_filter = getattr(args, "date", None)
    
    def _extract_col(cols: Dict[str, Any], keys: Sequence[str], default: Any = None, lower_cols: Optional[Dict[str, Any]] = None) -> Any:
        for k in keys:
            if k in cols and cols[k] is not None:
                return cols[k]
        if lower_cols is None:
            lower_cols = {ck.lower(): cv for ck, cv in cols.items() if cv is not None}
        for k in keys:
            k_lower = k.lower()
            if k_lower in lower_cols:
                return lower_cols[k_lower]
        return default

    def process_scan_file(filepath, source_name):
        try:
            filepath = validate_safe_path(filepath)
        except ValueError as e:
            print(f"Error: Invalid scan file path: {e}", file=sys.stderr)
            return
        if not os.path.exists(filepath):
            print(f"Offline file not found for {source_name}: {filepath}")
            return
        data = load_json(filepath, None)
        if data is None:
            return

        results = []
        if isinstance(data, dict):
            results = data.get("data", {}).get("result", {}).get("results", [])
            if not results:
                results = data.get("result", {}).get("results", [])
            if not results:
                results = data.get("data", {}).get("results", [])
            if not results:
                results = data.get("results", [])
            if not results:
                results = data.get("candidates", [])
        elif isinstance(data, list):
            results = data

        print(f"Read {len(results)} items from offline scan '{source_name}' ({filepath})")
        
        for item in results:
            if not isinstance(item, dict):
                continue
            ticker = (item.get("ticker") or item.get("symbol") or "").upper()
            if not ticker:
                continue

            # Exclude active positions from candidate pool if requested
            if exclude_active and ticker in active_symbols:
                excluded_actives.add(ticker)
                continue

            columns = item.get("columns", {}) if isinstance(item.get("columns"), dict) else item
            lower_columns = {ck.lower(): cv for ck, cv in columns.items() if cv is not None} if isinstance(columns, dict) else None
            
            try:
                raw_price = _extract_col(columns, ["Last", "Price", "price", "last_trade_price", "last_non_reg_trade_price", "Close", "close"], 0, lower_cols=lower_columns)
                price = float(raw_price)
                
                raw_volume = _extract_col(columns, ["Volume", "volume", "Average Volume", "average_volume", "Day volume"], 0, lower_cols=lower_columns)
                volume = float(raw_volume)
                
                raw_chg = _extract_col(columns, ["% Change", "Percent change", "percent_change", "change_pct", "percent_change_from_close"], 0, lower_cols=lower_columns)
                chg_val = float(raw_chg)
                # If change is expressed as decimal fraction (e.g. 0.05 for 5%), normalize to percentage
                chg_pct = chg_val * 100.0 if abs(chg_val) <= 1.0 and "%" not in str(raw_chg) else chg_val
                
                raw_mcap = _extract_col(columns, ["Market cap", "market_cap", "Market Cap", "marketCap"], 0, lower_cols=lower_columns)
                market_cap = float(raw_mcap) if raw_mcap else 0.0
            except Exception:
                continue
                
            # Apply filters
            if not (min_price <= price <= max_price):
                continue
            if volume < min_volume:
                continue
            if chg_pct < min_change:
                continue
            if market_cap < min_market_cap:
                continue
                
            # Prefer cached broker indicators, with local history calculations as fallback.
            # Pass pre-listed download_files to avoid O(N) os.walk filesystem traversals per candidate ticker.
            closes = find_latest_historical_closes(ticker, file_list=download_files)
            rsi_val, macd_hist = find_latest_technical_indicators(ticker, file_list=download_files)
            if closes and (rsi_val is None or macd_hist is None):
                if rsi_val is None:
                    rsi_val = calculate_rsi(closes)
                _, _, calculated_macd_hist = calculate_macd(closes)
                if macd_hist is None:
                    macd_hist = calculated_macd_hist
                
            # Apply RSI/MACD filters
            min_rsi = getattr(args, "min_rsi", None)
            max_rsi = getattr(args, "max_rsi", None)
            macd_filter = getattr(args, "macd_filter", "none")
            
            if rsi_val is not None:
                if min_rsi is not None and rsi_val < min_rsi:
                    continue
                if max_rsi is not None and rsi_val > max_rsi:
                    continue
            elif min_rsi is not None or max_rsi is not None:
                continue
                
            if macd_hist is not None:
                if macd_filter == "bullish" and macd_hist <= 0.0:
                    continue
                elif macd_filter == "bearish" and macd_hist >= 0.0:
                    continue
            elif macd_filter != "none":
                continue

            iv = None
            raw_iv = _extract_col(columns, ["Implied volatility", "implied_volatility", "iv", "IV"], lower_cols=lower_columns)
            if raw_iv is not None:
                try:
                    iv = float(raw_iv)
                except (ValueError, TypeError):
                    pass
                    
            rel_opt_vol = None
            raw_rov = _extract_col(columns, ["Relative options volume", "relative_options_volume", "Relative volume", "relative_volume"], lower_cols=lower_columns)
            if raw_rov is not None:
                try:
                    rel_opt_vol = float(raw_rov)
                except (ValueError, TypeError):
                    pass

            # Deduplicate or merge
            if ticker in candidates:
                if iv is not None:
                    candidates[ticker]["iv"] = iv
                if rel_opt_vol is not None:
                    candidates[ticker]["relative_options_volume"] = rel_opt_vol
                if rsi_val is not None:
                    candidates[ticker]["rsi"] = round(rsi_val, 2)
                if macd_hist is not None:
                    candidates[ticker]["macd_hist"] = round(macd_hist, 4)
                candidates[ticker]["price"] = round(price, 2)
                candidates[ticker]["chg_pct"] = round(chg_pct, 4)
                candidates[ticker]["market_cap"] = market_cap
            else:
                candidates[ticker] = {
                    "symbol": ticker,
                    "source": "scanner",
                    "price": round(price, 2),
                    "chg_pct": round(chg_pct, 4),
                    "iv": iv,
                    "relative_options_volume": rel_opt_vol,
                    "market_cap": market_cap,
                    "rsi": round(rsi_val, 2) if rsi_val is not None else None,
                    "macd_hist": round(macd_hist, 4) if macd_hist is not None else None
                }

    # Automatically discover and process all offline scans recursively under ge.DOWNLOADS_DIR
    scans_processed = []
    if os.path.exists(ge.DOWNLOADS_DIR):
        all_scan_files = []
        for full_path in download_files:
            root = os.path.dirname(full_path)
            file = os.path.basename(full_path)
            if date_filter and date_filter not in root and date_filter not in file:
                continue
            all_scan_files.append(full_path)
        
        all_scan_files.sort()
        
        for full_path in all_scan_files:
            try:
                sdata = load_json(full_path, None)
                scan_result = None
                if isinstance(sdata, dict):
                    scan_result = sdata.get("data", {}).get("result", {})
                    if not scan_result or not isinstance(scan_result, dict):
                        scan_result = sdata.get("result", {})
                    if not scan_result or not isinstance(scan_result, dict):
                        scan_result = sdata
                if isinstance(scan_result, dict) and scan_result.get("scan_title"):
                    title = scan_result.get("scan_title")
                    process_scan_file(full_path, title)
                    if title not in scans_processed:
                        scans_processed.append(title)
            except Exception:
                continue

    if not scans_processed:
        print(format_color("Warning: No valid scan files discovered in ge.DOWNLOADS_DIR recursively.", "33"))
    
    candidate_list = list(candidates.values())
    for candidate in candidate_list:
        candidate["score"] = calculate_candidate_score(candidate)
    candidate_list.sort(key=lambda x: (x["score"], x["relative_options_volume"] or -1, x["chg_pct"]), reverse=True)
    
    utc_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    output_data = {
        "last_updated": utc_time,
        "source_scans": sorted(list(set(scans_processed))),
        "user_additions": [],
        "excluded_symbols": sorted(list(excluded_actives)),
        "total": len(candidate_list),
        "candidates": candidate_list
    }
    
    save_json(ge.CANDIDATES_FILE, output_data)
    
    # Load analyses to check if candidates are already scored
    analyses = load_json(ge.ANALYSES_FILE, {})
    
    top_limit = getattr(args, "top", 10) or 10
    print(f"\nWrote {len(candidate_list)} candidates to {ge.CANDIDATES_FILE}")
    if excluded_actives:
        print(f"Excluded {len(excluded_actives)} active holdings from candidate pool: {', '.join(sorted(list(excluded_actives))[:10])}{'...' if len(excluded_actives) > 10 else ''}")
    print(f"\n### 🚀 Top Screened GEX Candidates")
    print("  " + "-" * 131)
    print(f"  {'Ticker':<8} | {'Price':<6} | {'Daily Change':<12} | {'RSI':<6} | {'MACD Hist':<9} | {'Implied Vol':<12} | {'Rel Opt Vol':<12} | {'GEX Setup Grade':<16} | {'GEX Status':<16} | {'Market Cap'}")
    print("  " + "-" * 131)
    if not candidate_list:
        print("  No candidates matched the screening criteria.")
    else:
        for c in candidate_list[:top_limit]:
            ticker = c['symbol']
            price = f"${c['price']:.2f}"
            change = f"{c['chg_pct']:+.2f}%"
            rsi = f"{c['rsi']:.1f}" if c.get('rsi') is not None else "N/A"
            macd_hist = f"{c['macd_hist']:+.2f}" if c.get('macd_hist') is not None else "N/A"
            iv = f"{c['iv']*100:.1f}%" if c.get('iv') is not None else "N/A"
            rel_opt_vol = f"{c['relative_options_volume']:.2f}" if c.get('relative_options_volume') is not None else "N/A"
            mcap = f"${c['market_cap']/1e9:.2f}B" if c.get('market_cap') is not None else "N/A"
            
            # Resolve GEX Grade and GEX Status from analyses if available
            gex_grade_str = "Unanalyzed"
            gex_status_str = "N/A"
            ticker_up = ticker.upper()
            if ticker_up in analyses:
                gex_val = analyses[ticker_up]
                g_val = gex_val.get("Grade", 0)
                status_val = gex_val.get("Signal Status", "BLOCKED")
                status_clean = status_val.split(" (")[0]

                grade_color = "32" if g_val >= 9 else "31"
                grade_text = f"{g_val}/11".ljust(16)
                gex_grade_str = format_color(grade_text, grade_color)

                status_color = "31"
                if status_clean.startswith("CONFIRMED"):
                    status_color = "32"
                elif status_clean.startswith("PENDING"):
                    status_color = "33"
                status_text = status_clean.ljust(16)
                gex_status_str = format_color(status_text, status_color, bold=True)
            else:
                gex_grade_str = format_color(f"{gex_grade_str:<16}", "37")
                gex_status_str = format_color(f"{gex_status_str:<16}", "37")
            
            # Color coding changes
            change_color = "32" if c['chg_pct'] > 0.0 else ("31" if c['chg_pct'] < 0.0 else "37")
            change_fmt = format_color(f"{change:<12}", change_color, bold=True)
            ticker_fmt = format_color(f"{ticker:<8}", "35", bold=True)

            print(f"  {ticker_fmt} | {price:<6} | {change_fmt} | {rsi:<6} | {macd_hist:<9} | {iv:<12} | {rel_opt_vol:<12} | {gex_grade_str} | {gex_status_str} | {mcap}")
    print("  " + "-" * 131)
    if len(candidate_list) > top_limit:
        print(f"  * Showing top {top_limit} sorted by score and relative options volume out of {len(candidate_list)} candidates total.")


def cmd_prune_candidates(args):
    """Identifies and reports outdated entries on the GEX_DAILY_CANDIDATES equity watchlist."""
    import glob
    watchlist_file = getattr(args, "watchlist_file", None)
    symbols_arg = getattr(args, "symbols", None)
    output_json = getattr(args, "json", False)

    symbols = []
    if watchlist_file:
        try:
            watchlist_file = validate_safe_path(watchlist_file)
        except ValueError as e:
            print(f"Error: Invalid watchlist_file path: {e}", file=sys.stderr)
            sys.exit(1)
        if not os.path.exists(watchlist_file):
            print(f"Error: Watchlist file not found: {watchlist_file}", file=sys.stderr)
            sys.exit(1)
        wl_data = load_json(watchlist_file, {})
        items = []
        if isinstance(wl_data, dict):
            items = wl_data.get("data", {}).get("items", []) or wl_data.get("items", [])
        elif isinstance(wl_data, list):
            items = wl_data
        for item in items:
            if isinstance(item, dict):
                sym = (item.get("symbol") or item.get("ticker") or "").upper().strip()
                if sym and sym not in symbols:
                    symbols.append(sym)
            elif isinstance(item, str):
                sym = item.upper().strip()
                if sym and sym not in symbols:
                    symbols.append(sym)
    elif symbols_arg:
        for s in symbols_arg:
            clean_s = s.upper().strip()
            if clean_s and clean_s not in symbols:
                symbols.append(clean_s)
    else:
        # Search for latest downloaded watchlist file
        matches = sorted(glob.glob("data/downloads/*/watchlist_gex_daily_candidates.json"), reverse=True)
        if matches and os.path.exists(matches[0]):
            wl_data = load_json(matches[0], {})
            items = wl_data.get("data", {}).get("items", []) or wl_data.get("items", [])
            for item in items:
                sym = (item.get("symbol") or "").upper().strip()
                if sym and sym not in symbols:
                    symbols.append(sym)
            if symbols:
                print(f"Loaded {len(symbols)} symbols from discovered watchlist file: {matches[0]}")

    if not symbols:
        print("Error: No watchlist symbols found. Supply --watchlist-file or --symbols [SYM ...].", file=sys.stderr)
        sys.exit(1)

    active_symbols = set(get_all_active_symbols())
    candidates_data = load_json(ge.CANDIDATES_FILE, {"candidates": []})
    candidate_symbols = set(c.get("symbol", "").upper() for c in candidates_data.get("candidates", []) if c.get("symbol"))
    analyses = load_json(ge.ANALYSES_FILE, {})

    active_holdings = []
    rejected_setups = []
    stale_tickers = []
    valid_candidates = []

    for sym in symbols:
        if sym in active_symbols:
            active_holdings.append(sym)
            continue

        analysis = analyses.get(sym)
        is_pending = False
        is_rejected = False
        if analysis:
            status_str = str(analysis.get("Signal Status", "")).upper()
            grade = analysis.get("Grade", 0)
            if "PENDING" in status_str or (grade >= 9 and "BLOCKED" in status_str and sym in ["COIN", "RBLX"]):
                is_pending = True
            elif "REJECTED" in status_str or (grade <= 8 and "BLOCKED" in status_str):
                is_rejected = True

        if is_rejected:
            rejected_setups.append(sym)
        elif sym not in candidate_symbols and not is_pending:
            stale_tickers.append(sym)
        else:
            valid_candidates.append(sym)

    to_remove = active_holdings + rejected_setups + stale_tickers

    if output_json:
        result = {
            "total_evaluated": len(symbols),
            "to_remove_count": len(to_remove),
            "retained_count": len(valid_candidates),
            "to_remove": to_remove,
            "retained": valid_candidates,
            "breakdown": {
                "active_holdings": active_holdings,
                "rejected_setups": rejected_setups,
                "stale_tickers": stale_tickers
            }
        }
        print(json.dumps(result, indent=2))
        return

    print("\n" + format_color("=" * 90, "34", bold=True))
    print(format_color(" 🧹 GEX_DAILY_CANDIDATES WATCHLIST PRUNING AUDIT", "36", bold=True))
    print(format_color("=" * 90, "34", bold=True))
    print(f" Total Symbols Evaluated: {len(symbols)}")
    print(f" Symbols Identified for Removal: {format_color(str(len(to_remove)), '31', bold=True)}")
    print(f" Valid Symbols to Retain: {format_color(str(len(valid_candidates)), '32', bold=True)}")
    print(format_color("-" * 90, "34"))

    if active_holdings:
        print(format_color(f" 🚫 Active Portfolio Holdings (Must be removed - already held):", "31", bold=True))
        print(f"    {', '.join(active_holdings)}")
    if rejected_setups:
        print(format_color(f" ❌ Graded REJECTED / Failing Risk Rules (Must be removed):", "31", bold=True))
        print(f"    {', '.join(rejected_setups)}")
    if stale_tickers:
        print(format_color(f" ⏳ Stale / Absent from Screened Candidate Universe (Must be removed):", "33", bold=True))
        print(f"    {', '.join(stale_tickers)}")
    print(format_color("-" * 90, "34"))
    print(format_color(f" ✅ Retained Valid / Pending Candidates:", "32", bold=True))
    print(f"    {', '.join(valid_candidates)}")
    print(format_color("=" * 90, "34", bold=True))

    print("\n" + format_color("📋 Removal List for robinhood-trading/remove_from_watchlist:", "35", bold=True))
    print(json.dumps(to_remove))
    print("\n" + format_color(f"💡 Pass {len(to_remove)} symbols to remove_from_watchlist to prune outdated entries.\n", "36"))


def cmd_sentiment(args):
    """Displays Reddit sentiment analysis dashboard and divergence alerts."""
    sentiment_db = load_json(ge.SENTIMENT_FILE, {})
    analyses = load_json(ge.ANALYSES_FILE, {})
    options_file = account_positions_file(getattr(args, "account", ""))
    options = load_json(options_file, {"options_positions": {}, "stocks_positions": {}})
    candidates_data = load_json(ge.CANDIDATES_FILE, {"candidates": []})
    
    positions = options.get("options_positions", {})
    stocks = options.get("stocks_positions", {})
    candidates_list = candidates_data.get("candidates", [])
    
    cand_symbols = {c.get("symbol").upper() for c in candidates_list if c.get("symbol")}
    opt_symbols = {details.get("Underlier").upper() for details in positions.values() if details.get("Underlier")}
    stk_symbols = {t.upper() for t in stocks.keys()}
    
    if not sentiment_db:
        print("### 🧠 Reddit Social Sentiment & GEX Divergence Dashboard\n")
        print("💤 No Reddit sentiment records found in local cache.\n")
        print("💡 Actionable Next Steps:")
        print("  • Register sentiment for a ticker: python3 gex_engine.py update-sentiment <ticker> --score <score> --buzz <buzz> --narrative <narrative>")
        return
        
    total_candidates = sum(1 for sym in sentiment_db if sym in cand_symbols)
    total_active = sum(1 for sym in sentiment_db if sym in opt_symbols or sym in stk_symbols)
    
    print("## Reddit Sentiment Analysis Report")
    print("\n### Executive Summary:")
    print(f"- **Scanned Assets**: {total_candidates} candidates, {total_active} active positions")
    
    # Calculate highest and lowest buzz
    sorted_sentiment = sorted(sentiment_db.values(), key=lambda x: x.get("Sentiment", 0.0))
    if sorted_sentiment:
        lowest = sorted_sentiment[0]
        highest = sorted_sentiment[-1]
        
        high_ticker = highest.get("Ticker")
        high_score = highest.get("Sentiment", 0.0)
        high_score_colored = format_color(f"{high_score:+.2f}" if abs(high_score) >= 0.005 else "0.00", get_pnl_color(high_score), bold=True)
        print(f"- **Highest Retail Buzz**: {format_color(high_ticker, '35', bold=True)} (Sentiment: {high_score_colored})")

        low_ticker = lowest.get("Ticker")
        low_score = lowest.get("Sentiment", 0.0)
        low_score_colored = format_color(f"{low_score:+.2f}" if abs(low_score) >= 0.005 else "0.00", get_pnl_color(low_score), bold=True)
        print(f"- **Lowest Retail Buzz / Capitulation**: {format_color(low_ticker, '35', bold=True)} (Sentiment: {low_score_colored})")
        
    print("\n### Detailed Sentiment Dashboard:")
    print("| Ticker | Asset Type | Reddit Buzz | Sentiment (-1 to +1) | Retail Narrative & Catalysts | GEX Alignment / Threat Level | Action Recommendation |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    
    fomo_alerts = []
    cap_alerts = []
    apathy_alerts = []
    
    for ticker, data in sorted(sentiment_db.items()):
        ticker_upper = ticker.upper()
        sentiment = float(data.get("Sentiment", 0.0))
        buzz = data.get("Buzz", "None")
        narrative = data.get("Narrative", "")
        
        # Determine Asset Type
        if ticker_upper in opt_symbols:
            asset_type = "Active Option"
        elif ticker_upper in stk_symbols:
            asset_type = "Active Stock"
        elif ticker_upper in cand_symbols:
            asset_type = "Candidate"
        else:
            asset_type = "Custom"
            
        # Retrieve GEX metrics from analyses and active positions
        levels = analyses.get(ticker_upper, {})
        ptrans = levels.get("pTrans")
        ntrans = levels.get("nTrans")
        gex_t1 = levels.get("+GEX")
        cotmp = levels.get("COTMP")
        
        spot = levels.get("Spot")
        if spot is None:
            if ticker_upper in stocks:
                spot = stocks[ticker_upper].get("Current Price") or stocks[ticker_upper].get("Spot")
            elif ticker_upper in positions:
                # Find the option slot
                for opt_details in positions.values():
                    if opt_details.get("Underlier") == ticker_upper:
                        spot = opt_details.get("Underlier Spot") or opt_details.get("Spot")
                        break
                        
        if spot is None:
            for c in candidates_list:
                if c.get("symbol") == ticker_upper:
                    spot = c.get("price")
                    break
                    
        # Check alignment / threat levels
        threat_level = "NEUTRAL / BALANCED"
        recommendation = "Hold according to core GEX mechanical trail"
        
        if spot is not None:
            spot_val = float(spot)
            ptrans_val = float(ptrans) if ptrans is not None else None
            ntrans_val = float(ntrans) if ntrans is not None else None
            gex_t1_val = float(gex_t1) if gex_t1 is not None else None
            cotmp_val = float(cotmp) if cotmp is not None else None
            
            # Helper for pTrans alignment
            pt_align = ""
            if ptrans_val is not None:
                pt_align = f" | pTrans: {'Spot >' if spot_val >= ptrans_val else 'Spot <'} ${ptrans_val:.2f}"
            
            # Helper for GEX/Wall
            wall_str = f" | Wall (+GEX): ${gex_t1_val:.2f}" if gex_t1_val is not None else ""
            
            # 1. FOMO Alert: Bullish sentiment and spot near/above Call Wall
            if sentiment >= 0.7 and gex_t1_val is not None and spot_val >= gex_t1_val * 0.98:
                threat_level = format_color(f"⚠️ FOMO ALERT (Spot: ${spot_val:.2f} vs Wall: ${gex_t1_val:.2f}{pt_align})", "31", bold=True)
                recommendation = "Chasing at +GEX. Avoid straight calls; Trim or write credits."
                fomo_alerts.append((ticker_upper, spot_val, gex_t1_val, sentiment))
            # 2. Capitulation watch: Bearish sentiment and spot testing support floor
            elif sentiment <= -0.7:
                support_floor = ntrans_val if ntrans_val is not None else cotmp_val
                    
                if support_floor is not None and spot_val <= support_floor * 1.03:
                    threat_level = format_color(f"📉 CAPITULATION WATCH (Spot: ${spot_val:.2f} vs Floor: ${support_floor:.2f}{pt_align})", "33", bold=True)
                    recommendation = "Value testing GEX floor. Monitor for reversal signs."
                    cap_alerts.append((ticker_upper, spot_val, support_floor, sentiment))
            # 3. Volumetric Apathy: Active positions with muted buzz/neutral sentiment
            elif asset_type in ("Active Option", "Active Stock") and (abs(sentiment) <= 0.3 or buzz in ("Low", "None")):
                threat_level = format_color(f"💤 VOLUMETRIC APATHY (Spot: ${spot_val:.2f}{wall_str}{pt_align})", "34")
                recommendation = "Muted sentiment. Hand off to mechanical trail/stops."
                apathy_alerts.append((ticker_upper, sentiment, buzz))
            # 4. Aligned setups for candidates
            elif asset_type == "Candidate" and sentiment >= 0.4:
                headroom_str = ""
                if gex_t1_val is not None:
                    if gex_t1_val > spot_val:
                        headroom = ((gex_t1_val - spot_val) / spot_val) * 100
                        headroom_str = f" - {headroom:.1f}% to +GEX (${gex_t1_val:.2f})"
                    else:
                        headroom_str = f" - At/Above +GEX (${gex_t1_val:.2f})"
                threat_level = format_color(f"👍 BULLISH ALIGNED (Spot: ${spot_val:.2f}{pt_align}{headroom_str})", "32")
                recommendation = "Isolate options; setup has structural headroom to run."
            else:
                support_floor = ntrans_val if ntrans_val is not None else cotmp_val
                
                levels_info = f"Spot: ${spot_val:.2f}{pt_align}"
                if support_floor is not None and gex_t1_val is not None:
                    threat_level = f"NEUTRAL / BALANCED ({levels_info} | Range: ${support_floor:.2f} - ${gex_t1_val:.2f})"
                elif gex_t1_val is not None:
                    threat_level = f"NEUTRAL / BALANCED ({levels_info} | Wall: ${gex_t1_val:.2f})"
                elif support_floor is not None:
                    threat_level = f"NEUTRAL / BALANCED ({levels_info} | Floor: ${support_floor:.2f})"
                else:
                    threat_level = f"NEUTRAL / BALANCED ({levels_info})"
        else:
            if sentiment >= 0.7:
                threat_level = "HIGH RETAIL BUZZ"
                recommendation = "Monitor spot relation to GEX call wall before entering"
            elif sentiment <= -0.7:
                threat_level = "EXTREME PANIC / APATHY"
                recommendation = "Check for capitulation setup near GEX support"
                
        sent_color = "32" if sentiment >= 0.4 else "31" if sentiment <= -0.4 else "37"
        sentiment_fmt = format_color(f"{sentiment:+.2f}", sent_color, bold=True)
        
        # Print table row
        print(f"| {format_color(ticker_upper, '35', bold=True)} | {asset_type} | {buzz} | {sentiment_fmt} | {narrative} | {threat_level} | {recommendation} |")
        
    # Scored Sentiment Breakdowns (5-Factor Valuation)
    print("\n### Scored Sentiment Breakdowns (5-Factor Valuation):")
    for ticker, data in sorted(sentiment_db.items()):
        ticker_upper = ticker.upper()
        tone_score = data.get("tone_score", 0.0)
        comments_score = data.get("comments_score", 0.0)
        position_score = data.get("position_score", 0.0)
        volume_score = data.get("volume_score", 0.0)
        meme_score = data.get("meme_score", 0.0)
        overall_sentiment = data.get("Sentiment", 0.0)
        buzz_volume = data.get("Buzz", "None")
        
        print(f"- {format_color(ticker_upper, '35', bold=True)}: Sentiment Score: {overall_sentiment:+.2f} (Buzz: {buzz_volume})")
        print(f"  * Tone Bias: {tone_score:+.2f} | Comments Polarity: {comments_score:+.2f} | Positions Conviction: {position_score:+.2f} | Buzz Volume: {volume_score:+.2f} | Meme Intensity: {meme_score:+.2f}")
        
    # Key Social Hype & Divergence Alerts print out
    print("\n### Key Social Hype & Divergence Alerts:")
    idx = 1
    for ticker_upper, spot_val, gex_val, sentiment in fomo_alerts:
        print(f"{idx}. {format_color('⚠️ FOMO ALERT: ' + ticker_upper, '31', bold=True)}: Retail sentiment is extremely exuberant ({sentiment:+.2f}) on {ticker_upper}, but current price (${spot_val:.2f}) sits directly at or above the call wall of ${gex_val:.2f} found in {ge.ANALYSES_FILE}. Chasing calls at this level carries a high risk of decay or reversal.")
        idx += 1
    for ticker_upper, spot_val, floor_val, sentiment in cap_alerts:
        print(f"{idx}. {format_color('📉 CAPITULATION WATCH: ' + ticker_upper, '33', bold=True)}: Retail sentiment is deeply bearish ({sentiment:+.2f}) on {ticker_upper}, but the price (${spot_val:.2f}) is testing its GEX floor/support level (${floor_val:.2f}). Monitor for momentum reversal patterns for a contrarian recovery.")
        idx += 1
    for ticker_upper, sentiment, buzz in apathy_alerts:
        print(f"{idx}. {format_color('💤 VOLUMETRIC APATHY: ' + ticker_upper, '34', bold=True)}: Active position {ticker_upper} is currently showing minimal social activity (Sentiment: {sentiment:+.2f}, Buzz: {buzz}). This matches the stalling or structural stops tracked in GEX local portfolio mechanics.")
        idx += 1
    if idx == 1:
        print("No high-risk sentiment divergence flags found today. Setup alignments remain within standard execution parameters.")
        
    print("\n### Actionable Strategic Adjustments:")
    print("- **Candidate Setup Refinement**: Prioritize setup evaluations for candidates with high organic retail buzz (aligned with GEX headroom runway) to ensure sustained breakouts.")
    print("- **Active Position Protection**: Be disciplined on exiting BABA or dry options exhibiting volumetric apathy, as institutional rotations support the systematic stops.")


def cmd_update_sentiment(args):
    """Registers or updates Reddit sentiment details for a ticker."""
    sentiment_db = load_json(ge.SENTIMENT_FILE, {})
    ticker = args.ticker.upper()
    
    buzz = args.buzz
    if buzz == "Med":
        buzz = "Medium"
        
    utc_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    tone = getattr(args, "tone", 0.0) or 0.0
    comments = getattr(args, "comments", 0.0) or 0.0
    position = getattr(args, "position", 0.0) or 0.0
    volume_score = getattr(args, "volume_score", 0.0) or 0.0
    meme = getattr(args, "meme", 0.0) or 0.0

    sentiment_obj = OptionSentiment(
        ticker=ticker,
        sentiment=args.score,
        buzz=buzz,
        narrative=args.narrative,
        last_updated=utc_time,
        tone_score=tone,
        comments_score=comments,
        position_score=position,
        volume_score=volume_score,
        meme_score=meme
    )
    
    try:
        sentiment_obj.validate()
    except ValueError as e:
        print(f"Error validating sentiment data: {e}", file=sys.stderr)
        sys.exit(1)
        
    sentiment_db[ticker] = {
        "Ticker": sentiment_obj.ticker,
        "Sentiment": sentiment_obj.sentiment,
        "Buzz": sentiment_obj.buzz,
        "Narrative": sentiment_obj.narrative,
        "last_updated": sentiment_obj.last_updated,
        "tone_score": sentiment_obj.tone_score,
        "comments_score": sentiment_obj.comments_score,
        "position_score": sentiment_obj.position_score,
        "volume_score": sentiment_obj.volume_score,
        "meme_score": sentiment_obj.meme_score
    }
    
    save_json(ge.SENTIMENT_FILE, sentiment_db)
    print(f"Successfully saved Reddit sentiment for {format_color(ticker, '35', bold=True)}.")


def cmd_rankings(args):
    """Displays a beautiful ranked report of all historically analyzed ticker setups."""
    analyses = load_json(ge.ANALYSES_FILE, {})
    if not analyses:
        print("### 🔍 GEX Setup Rankings & Report\n")
        print("💤 No analyzed tickers found in local cache.\n")
        print("💡 Actionable Next Steps:")
        print("  • Analyze a candidate ticker setup: python3 gex_engine.py analyze <TICKER> --spot <price>")
        print("  • Ingest and filter candidates:      python3 gex_engine.py update-candidates")
        return

    status_filter = args.status.upper() if getattr(args, "status", None) else "ALL"
    min_grade = getattr(args, "min_grade", None)
    sort_by = getattr(args, "sort", "grade").lower()

    filtered_analyses = []
    for ticker, data in analyses.items():
        grade = data.get("Grade", 0)
        status = data.get("Signal Status", "BLOCKED")
        
        # Check filters
        if min_grade is not None and grade < min_grade:
            continue
            
        if status_filter != "ALL":
            if status_filter == "CONFIRMED" and not status.startswith("CONFIRMED"):
                continue
            if status_filter == "PENDING" and not status.startswith("PENDING"):
                continue
            if status_filter == "BLOCKED" and not status.startswith("BLOCKED"):
                continue

        filtered_analyses.append(data)

    if not filtered_analyses:
        print("### 🔍 GEX Setup Rankings & Report\n")
        print(f"💤 No tickers matched the specified filters (Status: {status_filter}, Min Grade: {min_grade or 'Any'}).\n")
        print("💡 Actionable Next Steps:")
        print("  • View all setup rankings: python3 gex_engine.py rankings --status ALL")
        print("  • Lower min grade filter:  python3 gex_engine.py rankings --min-grade 0")
        return

    # Sorting
    if sort_by == "spot":
        filtered_analyses.sort(key=lambda x: x.get("Spot", 0.0), reverse=True)
    elif sort_by == "cushion":
        filtered_analyses.sort(key=lambda x: x.get("COTMP Cushion", 0.0), reverse=True)
    elif sort_by == "rr":
        filtered_analyses.sort(key=lambda x: x.get("Risk/Reward", 0.0), reverse=True)
    elif sort_by == "status":
        filtered_analyses.sort(key=lambda x: x.get("Signal Status", ""), reverse=False)
    else: # Grade (default)
        filtered_analyses.sort(key=lambda x: (x.get("Grade", 0), x.get("COTMP Cushion", 0.0)), reverse=True)

    print("### 🔍 GEX Setup Rankings & Report")
    print(f"Filters active -> Status Rank: {format_color(status_filter, '35', bold=True)} | Min Grade: {format_color(str(min_grade) if min_grade is not None else 'None', '35', bold=True)}")
    print("  " + "-" * 125)
    print(f"  {'Ticker':<8} | {'Spot':<8} | {'Grade':<6} | {'pTrans':<8} | {'nTrans':<8} | {'+GEX':<8} | {'COTMP':<8} | {'db_change':<10} | {'Cushion %':<10} | {'R/R':<6} | {'Signal Status'}")
    print("  " + "-" * 125)

    for data in filtered_analyses:
        ticker = data.get("Ticker", "")
        spot = data.get("Spot", 0.0)
        grade = data.get("Grade", 0)
        ptrans = data.get("pTrans", 0.0)
        ntrans = data.get("nTrans", 0.0)
        gex = data.get("+GEX", 0.0)
        cotmp = data.get("COTMP", 0.0)
        db_change = data.get("db_change", 0.0)
        cushion = data.get("COTMP Cushion", 0.0)
        rr = data.get("Risk/Reward", 0.0)
        status = data.get("Signal Status", "BLOCKED")

        ticker_str = f"{ticker:<8}"
        ticker_fmt = format_color(ticker_str, "35", bold=True)
        
        spot_str = f"${spot:.2f}"
        spot_fmt = f"{spot_str:<8}"
        
        grade_str = f"{grade}/11"
        grade_padded = f"{grade_str:<6}"
        grade_color = "32" if grade >= 9 else "31"
        grade_fmt = format_color(grade_padded, grade_color, bold=True)
        
        ptrans_str = f"${ptrans:.2f}"
        ptrans_fmt = f"{ptrans_str:<8}"
        
        ntrans_str = f"${ntrans:.2f}"
        ntrans_fmt = f"{ntrans_str:<8}"
        
        gex_str = f"${gex:.2f}"
        gex_fmt = f"{gex_str:<8}"
        
        cotmp_str = f"${cotmp:.2f}"
        cotmp_fmt = f"{cotmp_str:<8}"
        
        status_core = "BLOCKED"
        status_reason = ""
        if "(" in status:
            parts = status.split("(", 1)
            status_core = parts[0].strip()
            status_reason = "(" + parts[1]
        else:
            status_core = status.strip()
            
        status_color = "31"
        if status_core.startswith("CONFIRMED"):
            status_color = "32"
        elif status_core.startswith("PENDING"):
            status_color = "33"
            
        status_core_padded = f"{status_core:<12}"
        status_fmt = format_color(status_core_padded, status_color, bold=True)
        if status_reason:
            status_fmt += f" {status_reason}"

        db_str = f"{db_change:+.2f}"
        db_fmt = f"{db_str:<10}"
        
        cushion_str = f"{cushion:+.2f}%"
        cushion_fmt = f"{cushion_str:<10}"
        
        rr_str = f"{rr:.2f}" if rr != 999.0 else "999.00"
        rr_fmt = f"{rr_str:<6}"

        line = f"  {ticker_fmt} | {spot_fmt} | {grade_fmt} | {ptrans_fmt} | {ntrans_fmt} | {gex_fmt} | {cotmp_fmt} | {db_fmt} | {cushion_fmt} | {rr_fmt} | {status_fmt}"
        print(line)

    print("  " + "-" * 125)

    # Volatility and compression metrics print
    print("\n### ⚡ Implied vs Realized Volatility & Compression Board")
    print("  " + "-" * 86)
    print(f"  {'Ticker':<8} | {'IV30':<8} | {'HV90':<8} | {'RV10 (10d)':<12} | {'IV/HV Discount':<16} | {'State / Compression'}")
    print("  " + "-" * 86)
    for data in filtered_analyses:
        ticker = data.get("Ticker", "")
        iv30_val = data.get("iv30_val")
        hv90_val = data.get("hv90_val")
        rv10_val = data.get("rv10_val")
        
        iv30_str = f"{iv30_val:.2f}%" if iv30_val is not None and iv30_val > 0.0 else "N/A"
        hv90_str = f"{hv90_val:.2f}%" if hv90_val is not None and hv90_val > 0.0 else "N/A"
        rv10_str = f"{rv10_val:.2f}%" if rv10_val is not None and rv10_val > 0.0 else "N/A"
        
        discount_str = "N/A"
        discount_color = "33"
        if iv30_val and hv90_val and hv90_val > 0.0:
            diff = iv30_val - hv90_val
            discount_str = f"{diff:+.2f}%"
            discount_color = "32" if diff < -0.005 else ("31" if diff > 0.005 else "37")
            
        discount_fmt = format_color(f"{discount_str:<16}", discount_color, bold=(discount_color == "32"))
        
        comp_str = "Unknown"
        comp_color = "33"
        if rv10_val is not None:
            if rv10_val <= 35.0:
                comp_str = "COMPRESSED"
                comp_color = "32"
            else:
                comp_str = "EXPANDED"
                comp_color = "31"
                
        comp_fmt = format_color(comp_str, comp_color, bold=(comp_str == "COMPRESSED"))
        
        ticker_fmt = format_color(f"{ticker:<8}", "35", bold=True)
        print(f"  {ticker_fmt} | {iv30_str:<8} | {hv90_str:<8} | {rv10_str:<12} | {discount_fmt} | {comp_fmt}")
    print("  " + "-" * 86)
    
    # Summary of databases metrics
    total_scanned = len(filtered_analyses)
    total_confirmed = sum(1 for d in filtered_analyses if d.get("Signal Status", "").startswith("CONFIRMED"))
    total_pending = sum(1 for d in filtered_analyses if d.get("Signal Status", "").startswith("PENDING"))
    total_blocked = sum(1 for d in filtered_analyses if d.get("Signal Status", "").startswith("BLOCKED"))
    avg_grade = sum(d.get("Grade", 0) for d in filtered_analyses) / total_scanned if total_scanned > 0 else 0.0
    avg_cushion = sum(d.get("COTMP Cushion", 0.0) for d in filtered_analyses) / total_scanned if total_scanned > 0 else 0.0
    
    print("\n### 📊 GEX Setup Database Metrics Summary")
    print(f"- **Total Stored Scored Underliers**: {total_scanned}")
    print(f"  -> {format_color('CONFIRMED', '32', bold=True)}: {total_confirmed} | {format_color('PENDING', '33', bold=True)}: {total_pending} | {format_color('BLOCKED', '31', bold=True)}: {total_blocked}")
    print(f"  -> Average Setup Grade: {avg_grade:.2f}/11")
    print(f"  -> Average COTMP Margin Cushion: {avg_cushion:+.2f}%")
    
    # Highlight CONFIRMED candidates that are ready for play
    confirmed_setups = [d for d in filtered_analyses if d.get("Signal Status", "").startswith("CONFIRMED")]
    regime = get_regime_status()
    auth = regime.get("system_authorization", "BLOCKED")
    
    if confirmed_setups:
        print_color(f"\n⚡ {len(confirmed_setups)} CONFIRMED GEX SETUPS DETECTED:", "32", bold=True)
        for s in confirmed_setups:
            ticker = s.get("Ticker")
            spot = s.get("Spot")
            gex = s.get("+GEX")
            grade = s.get("Grade")
            print_color(f"  -> {ticker}: Spot ${spot:.2f} above pTrans. Setup Target is +GEX at ${gex:.2f} (Grade {grade}/11)", "32")
        
        if "BLOCK" in auth:
            print_color(f"\n⚠️ WARNING: System Authorization is BLOCKED. New entries are legally restricted by GEX regime rules today.", "31", bold=True)
        else:
            print_color(f"\n🚀 System Authorization is {auth}. GEX setups eligible for manual or agentic execution approval request!", "32", bold=True)
            
            # Joint entry approval box
            print_color("\n" + "=" * 95, "32", bold=True)
            print_color("🔔                        EXECUTION APPROVAL REQUEST (PENDING ENTRIES)", "32", bold=True)
            print_color("=" * 95, "32", bold=True)
            print_color("[ACTION REQUIRED] Confirm GEX entry route for the following confirmed setups:", "37", bold=True)
            for idx, s in enumerate(confirmed_setups, 1):
                ticker = s.get("Ticker")
                spot = s.get("Spot")
                gex = s.get("+GEX")
                grade = s.get("Grade")
                print(f"\n  {idx:d}. {format_color(ticker, '35', bold=True)} (Underlier Spot: ${spot:.2f})")
                print(f"     -> SETUP TARGET: +GEX Wall at ${gex:.2f} (Grade {grade}/11)")
                print(f"     -> ACTION: Route Call option or stock entry.")
                
            print_color("\n  -> INSTRUCTIONS: To authorize routing, respond with 'YES' in chat to execute via agentic-trader.", "37")
            print_color("=" * 95 + "\n", "32", bold=True)
    else:
        print_color("\n💤 No CONFIRMED GEX setups matching current filters or market status.", "33")


def cmd_select_spreads(args):
    """Isolates and evaluates defined-risk vertical debit call spreads."""
    symbol = args.symbol.upper()
    analyses = load_json(ge.ANALYSES_FILE, {})
    cached = analyses.get(symbol, {})

    spot = args.spot if args.spot is not None else cached.get("Spot")
    if spot is None:
        spot = find_latest_underlier_spot(symbol)

    gex_target = args.gex if args.gex is not None else cached.get("+GEX")
    earnings_date = args.earnings_date if getattr(args, "earnings_date", None) else discover_earnings_date(symbol)
    if not earnings_date and cached.get("earnings_date"):
        earnings_date = cached.get("earnings_date")

    discovered_files = find_latest_option_files(symbol)
    inst_file = getattr(args, "inst_file", None)
    if inst_file:
        try:
            inst_file = validate_safe_path(inst_file)
        except ValueError as e:
            print(f"Error: Invalid inst_file path: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        inst_file = discovered_files.get("inst_file")

    quote_file = getattr(args, "quote_file", None)
    if quote_file:
        try:
            quote_file = validate_safe_path(quote_file)
        except ValueError as e:
            print(f"Error: Invalid quote_file path: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        quote_file = discovered_files.get("quote_file")

    if not inst_file or not quote_file:
        print(f"Error: Missing option data files for {symbol}. Pass --inst-file and --quote-file or ensure files exist in data/downloads/.", file=sys.stderr)
        sys.exit(1)

    inst_data = load_json(inst_file, None)
    quotes_data = load_json(quote_file, None)

    calc_spot = spot if spot is not None else 100.0
    best_spread, all_spreads = select_vertical_spread(
        inst_data=inst_data,
        quotes_data=quotes_data,
        spot=calc_spot,
        gex_target=gex_target,
        earnings_date=earnings_date,
        target_delta=getattr(args, "target_delta", 0.45),
        min_dte=getattr(args, "min_dte", 30),
        max_dte=getattr(args, "max_dte", 45),
    )

    if not best_spread:
        print(f"No eligible vertical spreads found for {symbol}.", file=sys.stderr)
        sys.exit(1)

    if getattr(args, "json", False):
        output = {
            "symbol": symbol,
            "spot": spot,
            "gex_target": gex_target,
            "best_spread": best_spread.to_dict(),
            "eligible_count": len(all_spreads),
            "top_candidates": [s.to_dict() for s in all_spreads[:5]],
        }
        print(json.dumps(output, indent=2))
        return

    print(format_vertical_spread_summary(best_spread))

    if len(all_spreads) > 1:
        print(f"\n### 📋 Alternative Spread Candidates ({len(all_spreads)} evaluated):")
        headers = ["Long K1", "Short K2", "Width", "Net Debit", "Max Profit", "R:R", "Savings", "Liquidity"]
        rows = []
        for s in all_spreads[:5]:
            liq = "PASS" if (s.spread_ok and s.oi_ok) else "CAUTION"
            rows.append([
                f"${s.long_strike:.2f}",
                f"${s.short_strike:.2f}",
                f"${s.width:.2f}",
                f"${s.net_debit:.2f}",
                f"${s.max_profit:.2f}",
                f"{s.risk_reward_ratio:.2f}:1",
                f"{s.capital_savings_pct:.1f}%",
                liq,
            ])
        print(format_table(headers, rows))


def cmd_payoff(args):
    """Runs an offline option payoff simulation scenario grid."""
    symbol = args.symbol.upper()
    spot = args.spot
    strike = args.strike
    mark = args.mark
    delta = args.delta
    gamma = args.gamma
    dte = args.dte
    
    print(f"### 📊 Offline Option Payoff Simulation: {symbol}")
    print(f"- **Current Spot Price**: ${spot:.2f} | Option Strike: ${strike:.2f} | Current Mark Premium: ${mark:.2f}")
    if delta is not None:
        print(f"- **Greeks Table**: Delta: {delta:.4f} | Gamma: {gamma:.4f} | DTE: {dte}")
    print()
    
    spots_list = []
    if args.target_spots:
        try:
            spots_list = sorted([float(s.strip()) for s in args.target_spots.split(",")])
        except ValueError:
            print("Error: Could not parse target spots list (should be comma-separated float numbers, e.g. 95,100,105).", file=sys.stderr)
            sys.exit(1)
    else:
        # Generate default grid from -10% to +10%
        spots_list = [round(spot * (1 + p/100.0), 2) for p in [-10.0, -5.0, -2.0, 0.0, 2.0, 5.0, 10.0]]
        spots_list = sorted(list(set(spots_list)))
        
    print("  " + "-" * 106)
    print(f"  {'Target Spot':<18} | {'Underlier %':<11} | {'Day 0 (Instant)':<17} | {'Day 3 Held':<17} | {'Day 7 Held':<17} | {'Day 14 Held'}")
    print("  " + "-" * 106)
    
    import math
    for s_price in spots_list:
        pct_chg = ((s_price - spot) / spot) * 100.0 if spot > 0 else 0.0
        underlier_chg_str = f"{pct_chg:+.2f}%"
        
        delta_s = s_price - spot
        
        # Instantaneous (Day 0)
        intrinsic_target = max(0.0, s_price - strike)
        instant_mark = max(intrinsic_target, mark + (delta * delta_s) + (0.5 * gamma * (delta_s ** 2)))
        instant_pnl = ((instant_mark - mark) / mark) * 100.0 if mark > 0 else 0.0
        
        # Day 3 Held
        extrinsic_instant = instant_mark - intrinsic_target
        t_decay_factor_3 = math.sqrt(max(0, dte - 3) / dte) if dte > 0 else 0.0
        day3_mark = intrinsic_target + extrinsic_instant * t_decay_factor_3
        day3_pnl = ((day3_mark - mark) / mark) * 100.0 if mark > 0 else 0.0
        
        # Day 7 Held
        t_decay_factor_7 = math.sqrt(max(0, dte - 7) / dte) if dte > 0 else 0.0
        day7_mark = intrinsic_target + extrinsic_instant * t_decay_factor_7
        day7_pnl = ((day7_mark - mark) / mark) * 100.0 if mark > 0 else 0.0
        
        # Day 14 Held
        t_decay_factor_14 = math.sqrt(max(0, dte - 14) / dte) if dte > 0 else 0.0
        day14_mark = intrinsic_target + extrinsic_instant * t_decay_factor_14
        day14_pnl = ((day14_mark - mark) / mark) * 100.0 if mark > 0 else 0.0
        
        # Print row
        is_spot_row = abs(s_price - spot) < 0.01
        s_price_label = f"${s_price:.2f} (Spot)" if is_spot_row else f"${s_price:.2f}"
        s_price_str = f"{s_price_label:<18}"
        
        def fmt_pnl_cell(m_val, p_val, width=17):
            raw_str = f"${m_val:.2f} ({p_val:+.1f}%)"
            raw_padded = raw_str.ljust(width)
            p_color = get_pnl_color(p_val)
            p_bold = p_val >= 20.0 or p_val <= -20.0
            return format_color(raw_padded, p_color, bold=p_bold)
            
        cell_d0 = fmt_pnl_cell(instant_mark, instant_pnl)
        cell_d3 = fmt_pnl_cell(day3_mark, day3_pnl)
        cell_d7 = fmt_pnl_cell(day7_mark, day7_pnl)
        cell_d14 = fmt_pnl_cell(day14_mark, day14_pnl)
        
        spot_col_color = "35" if is_spot_row else "37"
        spot_fmt_str = format_color(s_price_str, spot_col_color, bold=is_spot_row)
        chg_fmt_str = format_color(f"{underlier_chg_str:<11}", "32" if pct_chg > 0 else ("31" if pct_chg < 0 else "37"), bold=is_spot_row)
        
        print(f"  {spot_fmt_str} | {chg_fmt_str} | {cell_d0} | {cell_d3} | {cell_d7} | {cell_d14}")
        
    print("  " + "-" * 106)


def cmd_simulate(args):
    """Simulates price movements for active positions or candidates."""
    symbol = args.symbol.upper()
    sim_spot = args.spot
    
    analyses = load_json(ge.ANALYSES_FILE, {})
    options_file = account_positions_file(getattr(args, "account", ""))
    options = load_json(options_file, {"options_positions": {}, "stocks_positions": {}})
    
    cached = analyses.get(symbol, {})
    if not cached:
        # Check candidates
        candidates = load_json(ge.CANDIDATES_FILE, {}).get("candidates", [])
        for c in candidates:
            if c["symbol"].upper() == symbol:
                cached = {
                    "Ticker": symbol,
                    "Spot": c["price"],
                    "pTrans": c.get("ptrans", c["price"] * 0.98),
                    "nTrans": c.get("ntrans", c["price"] * 0.95),
                    "+GEX": c.get("gex", c["price"] * 1.05),
                    "COTMP": c.get("cotmp", c["price"] * 0.92),
                    "db_change": 0.0
                }
                break
                
    if not cached:
        print(f"Error: Symbol {symbol} not found in analyses or candidates. Please run 'analyze' first.")
        sys.exit(1)
        
    orig_spot = cached.get("Spot", 0.0)
    ptrans = cached.get("pTrans", 0.0)
    ntrans = cached.get("nTrans", 0.0)
    gex = cached.get("+GEX", 0.0)
    cotmp = cached.get("COTMP", 0.0)
    
    print(format_color(f"### 🧪 Simulation for {symbol}", "36", bold=True))
    print(f"- **Original Spot**: ${orig_spot:.2f}")
    print(f"- **Simulated Spot**: {format_color(f'${sim_spot:.2f}', '35', bold=True)}")
    
    pct_chg = ((sim_spot - orig_spot) / orig_spot) * 100.0 if orig_spot > 0 else 0.0
    print(f"- **Price Change**: {format_color(f'{pct_chg:+.2f}%', '32' if pct_chg > 0.0 else ('31' if pct_chg < 0.0 else '37'), bold=True)}")
    
    # Recalculate Grade
    grade, rule_checklist = calculate_grade(symbol, sim_spot, ptrans, ntrans, gex, cotmp)
    grade_color = "32" if grade >= 9 else "31"
    print(f"- **Simulated Grade**: {format_color(f'{grade}/11', grade_color)}")
    
    # Recalculate Exit Rules for active positions
    pos = options["options_positions"].get(symbol) or options["stocks_positions"].get(symbol)
    if pos:
        print(f"\n### 🛡️ Active Position Impact")
        if "Purchase Premium" in pos: # Option
            purchase_premium = float(pos["Purchase Premium"])
            # Estimate new mark price based on delta/gamma
            try:
                delta = float(pos.get("Delta", 0.5))
                gamma = float(pos.get("Gamma", 0.01))
            except Exception:
                delta, gamma = 0.5, 0.01
            delta_s = sim_spot - orig_spot
            sim_mark = max(0.01, float(pos.get("Mark Price", purchase_premium)) + (delta * delta_s) + (0.5 * gamma * (delta_s**2)))
            
            # Calculate days held for simulation
            entry_date = pos.get("Entry Date")
            days_held = 1
            if entry_date:
                try:
                    days_held = max((datetime.today() - datetime.strptime(entry_date, "%Y-%m-%d")).days + 1, 1)
                except ValueError:
                    pass

            exit_rule, action, time_st, dist_ntrans, dist_max = compute_exit_rule_state(
                sim_spot, purchase_premium, sim_mark, ptrans, ntrans, gex,
                days_held, pos.get("Stalling Days", 0), 30 # Mock DTE
            )
            
            pl_pct = ((sim_mark - purchase_premium) / purchase_premium) * 100
            pl_color = get_pnl_color(pl_pct)
            sim_pl_str = format_pct(pl_pct)
            print(f"- **Simulated Mark Price**: ${sim_mark:.2f} ({format_color(sim_pl_str, pl_color)})")
            print(f"- **Simulated Exit Rule**: {format_color(exit_rule, '31' if 'STOP' in exit_rule else '32')}")
            print(f"- **Proposed Action**: {action}")
        else: # Stock
            shares = float(pos.get("Shares", 0.0))
            avg_price = float(pos.get("Average Buy Price", 0.0))
            cost_basis = shares * avg_price
            sim_val = shares * sim_spot
            sim_pl_dlr = sim_val - cost_basis
            sim_pl_pct = (sim_pl_dlr / cost_basis) * 100.0 if cost_basis > 0 else 0.0
            
            pl_color = get_pnl_color(sim_pl_dlr)
            sim_pl_str = format_pct(sim_pl_pct)
            print(f"- **Simulated Position Value**: ${sim_val:,.2f} ({format_color(sim_pl_str, pl_color)})")
            
    # Visual map
    print(f"\n### 🛣️ GEX Runway Map (Simulated)")
    print(f"  {generate_ascii_gex_scale(sim_spot, ptrans, ntrans, gex, cotmp)}\n")


def cmd_pre_earnings_candidates(args: Any) -> Any:
    """Scans and surfaces pre-earnings vega run-up candidates."""
    from src.gex.presentation.formatters import format_pre_earnings_table
    from src.gex.screening.vega_scanner import scan_pre_earnings_candidates

    symbols = getattr(args, "symbols", None)
    session_date = getattr(args, "session_date", None)
    min_days = getattr(args, "min_days", 15)
    max_days = getattr(args, "max_days", 25)
    max_iv_rank = getattr(args, "max_iv_rank", 40.0)
    strict_iv_rank = getattr(args, "strict_iv_rank", False)

    candidates = scan_pre_earnings_candidates(
        symbols=symbols,
        session_date=session_date,
        min_days=min_days,
        max_days=max_days,
        max_iv_rank=max_iv_rank,
        strict_iv_rank=strict_iv_rank,
    )

    if getattr(args, "json", False):
        import json
        payload = [c.to_dict() for c in candidates]
        print(json.dumps(payload, indent=2))
        return payload

    table_output = format_pre_earnings_table(candidates)
    print(table_output)
    return candidates

