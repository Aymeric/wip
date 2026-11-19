"""
CLI commands for market regime checks and status reporting.
Provides handlers and subparser definitions for:
- status: Analyze broader Daily Regime Gates and authorization.
- update-regime: Recompute Daily Regime Gates from raw market inputs.
"""

import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.gex.core.config import (
    validate_safe_path,
)
from src.gex.presentation.ascii_art import format_color, print_color
from src.gex.presentation.formatters import format_pct, format_pnl, get_pnl_color
from src.gex.risk.stops import compute_exit_rule_state


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


def add_regime_parsers(subparsers: Any) -> None:
    """Registers regime command parsers."""
    from src.gex.cli.parser import str2bool

    p_status = subparsers.add_parser("status", help="Analyze broader Daily Regime Gates and authorization.")
    p_status.add_argument("--net-liq", type=float, dest="net_liq", help="Estimated Portfolio Net Liq value for sizing & drawdown checks")
    p_status.add_argument("--account", type=str, default="", help="Optional account number used to scope position and performance caches")

    # update-regime subcommand
    p_regime = subparsers.add_parser("update-regime", help="Recompute Daily Regime Gates from raw market inputs.")
    p_regime.add_argument("--spy", type=float, help="SPY session change percent (e.g. 0.62)")
    p_regime.add_argument("--qqq", type=float, help="QQQ session change percent (e.g. 1.10)")
    p_regime.add_argument("--bulls", type=int, help="Count of bullish (green) symbols in the sector ETF list")
    p_regime.add_argument("--bears", type=int, help="Count of bearish (red) symbols in the sector ETF list")
    p_regime.add_argument("--vix-bearish", type=str2bool, dest="vix_bearish", help="Dealer VIX positioning is bearish/short vol (True/False)")
    p_regime.add_argument("--vix-spot", type=float, dest="vix_spot", help="Current VIX spot level")
    p_regime.add_argument("--hyg", type=float, help="HYG credit high-yield bond daily change percent (e.g. -0.35)")
    p_regime.add_argument("--etf-file", type=str, help="ETF Quotes JSON file to calculate regime gates automatically")

    # update-performance subcommand



def cmd_update_regime(args):
    """Recomputes the Daily Regime Gates from raw market inputs and persists them."""
    cached_regime = load_json(ge.REGIME_FILE, {})
    
    spy_val = args.spy
    qqq_val = args.qqq
    bulls_val = args.bulls
    bears_val = args.bears
    vix_bearish_val = args.vix_bearish
    vix_spot_val = args.vix_spot
    hyg_val = getattr(args, "hyg", None)
    
    etf_file = getattr(args, "etf_file", None)
    if etf_file:
        try:
            etf_file = validate_safe_path(etf_file)
            args.etf_file = etf_file
        except ValueError as e:
            print(f"Error: Invalid etf_file path: {e}", file=sys.stderr)
            sys.exit(1)
    if not etf_file and spy_val is None:
        # Try to auto-discover latest ETF quotes file
        etf_candidates = []
        if os.path.exists(ge.DOWNLOADS_DIR):
            for filepath, file_upper in _get_downloads_files(ge.DOWNLOADS_DIR):
                if file_upper == "ETF_QUOTES.JSON":
                    etf_candidates.append(filepath)
        if etf_candidates:
            etf_candidates.sort()
            etf_file = etf_candidates[-1]
            args.etf_file = etf_file
            print(f"Auto-discovered latest ETF quotes file: {etf_file}")
            
    if hasattr(args, "etf_file") and args.etf_file:
        try:
            etf_data = load_json(args.etf_file, {})
            results = []
            if isinstance(etf_data, dict):
                results = etf_data.get("data", {}).get("results", [])
                if not results:
                    results = etf_data.get("results", [])
                if not results:
                    results = etf_data.get("data", [])
            elif isinstance(etf_data, list):
                results = etf_data
                
            reference_etfs = {
                "SPY", "QQQ", "IWM", "DIA", 
                "XLK", "XLF", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLRE", "XLE", "XLC", "HYG"
            }
            
            spy_pct = 0.0
            qqq_pct = 0.0
            bull_count = 0
            bear_count = 0
            found_symbols = {}
            detailed_etfs = {}
            
            for item in results:
                if not isinstance(item, dict):
                    continue
                q = item.get("quote", item)
                if not isinstance(q, dict):
                    continue
                symbol = q.get("symbol")
                if not symbol:
                    continue
                sym_upper = symbol.upper()
                if sym_upper in reference_etfs:
                    # Resolve price choosing non-reg or reg based on timestamps
                    nonreg_t = q.get("venue_last_non_reg_trade_time") or ""
                    reg_t = q.get("venue_last_trade_time") or ""
                    
                    price = 0.0
                    if nonreg_t > reg_t and q.get("last_non_reg_trade_price") is not None:
                        try:
                            price = float(q["last_non_reg_trade_price"])
                        except ValueError:
                            pass
                    if price <= 0.0 and q.get("last_trade_price") is not None:
                        try:
                            price = float(q["last_trade_price"])
                        except ValueError:
                            pass
                            
                    prev_close = 0.0
                    if q.get("adjusted_previous_close") is not None:
                        try:
                            prev_close = float(q["adjusted_previous_close"])
                        except ValueError:
                            pass
                            
                    chg_pct = 0.0
                    if price > 0.0 and prev_close > 0.0:
                        chg_pct = ((price - prev_close) / prev_close) * 100.0
                        found_symbols[sym_upper] = chg_pct
                        
                    classification = classify_etf(sym_upper, chg_pct)
                            
                    etf_segment_names = {
                        "SPY": "S&P 500 Broad Market",
                        "QQQ": "Nasdaq 100 Growth Index",
                        "IWM": "Russell 2000 Small Caps",
                        "DIA": "Dow Jones Industrials Value",
                        "XLK": "Technology",
                        "XLF": "Financials",
                        "XLV": "Health Care",
                        "XLY": "Consumer Discretionary",
                        "XLP": "Consumer Staples",
                        "XLI": "Industrials",
                        "XLU": "Utilities",
                        "XLB": "Materials",
                        "XLRE": "Real Estate",
                        "XLE": "Energy",
                        "XLC": "Communication Services",
                        "HYG": "High Yield Corporate Bond ETF"
                    }
                    
                    detailed_etfs[sym_upper] = {
                        "Ticker": sym_upper,
                        "ETF Segment / Sector Name": etf_segment_names.get(sym_upper, "Unknown Sector"),
                        "Price": round(price, 2) if price > 0.0 else round(prev_close, 2),
                        "Daily Change %": round(chg_pct, 4),
                        "Classification": classification
                    }
                        
            # Calculate SPY, QQQ changes
            spy_pct = found_symbols.get("SPY", 0.0)
            qqq_pct = found_symbols.get("QQQ", 0.0)
            
            # Count bulls and bears
            for sym, chg in found_symbols.items():
                if sym == "HYG":
                    continue
                if chg > 0.1:
                    bull_count += 1
                elif chg < -0.1:
                    bear_count += 1
                    
            spy_val = spy_pct
            qqq_val = qqq_pct
            bulls_val = bull_count
            bears_val = bear_count
            
            if "HYG" in found_symbols:
                hyg_val = found_symbols["HYG"]
            
            print(format_color(f"📊 Auto-derived regime metrics from {args.etf_file}:", "32", bold=True))
            print(f"  -> SPY Change: {spy_pct:+.2f}%, QQQ Change: {qqq_pct:+.2f}%")
            if "HYG" in found_symbols:
                print(f"  -> HYG Credit Change: {found_symbols['HYG']:+.2f}%")
            print(f"  -> Bulls: {bull_count}, Bears: {bear_count} (out of {len(found_symbols) - (1 if 'HYG' in found_symbols else 0)} tracked reference ETFs)")
            
            # If VXX or UVXY are in findings, we can use their signs as a fallback VIX Delta gate proxy
            if vix_bearish_val is None:
                for item in results:
                    q = item.get("quote", item) if isinstance(item, dict) else {}
                    if not isinstance(q, dict): continue
                    s = q.get("symbol", "").upper()
                    if s in ("VXX", "UVXY"):
                        nonreg_t = q.get("venue_last_non_reg_trade_time") or ""
                        reg_t = q.get("venue_last_trade_time") or ""
                        p = 0.0
                        if nonreg_t > reg_t and q.get("last_non_reg_trade_price") is not None:
                            p = float(q["last_non_reg_trade_price"]) or 0.0
                        if p <= 0.0 and q.get("last_trade_price") is not None:
                            p = float(q["last_trade_price"]) or 0.0
                        pc = float(q.get("adjusted_previous_close") or 0.0)
                        if p > 0.0 and pc > 0.0:
                            proxy_chg = ((p - pc) / pc) * 100.0
                            vix_bearish_val = proxy_chg < 0.0
                            print(f"  -> Derived VIX bearish from proxy {s} (% change: {proxy_chg:+.2f}%): {vix_bearish_val}")
                            break
                if vix_bearish_val is None:
                    # Fallback default if not derivable from file
                    vix_bearish_val = False
                    print("  -> VIX Bearish could not be resolved from proxy underliers in ETF file. Defaulting to False (Conservative).")
                            
        except Exception as e:
            print(f"Error parsing ETF quotes file: {e}", file=sys.stderr)
            
    if spy_val is None or qqq_val is None or bulls_val is None or bears_val is None or vix_bearish_val is None:
        print("Error: Missing required metrics for Daily Regime check. Pass them via --spy, --qqq, --bulls, --bears, --vix-bearish, or use --etf-file.", file=sys.stderr)
        sys.exit(1)
        
    basket_gate, bull_bear_ratio, bull_bear_gate, vix_delta_gate, system_auth, gates_passed = compute_regime_gates(
        spy_val, qqq_val, bulls_val, bears_val, vix_bearish_val
    )
    
    etf_details = cached_regime.get("etf_details", {})
    if hasattr(args, "etf_file") and args.etf_file and "found_symbols" in locals():
        etf_details = detailed_etfs
    else:
        # Fallback construct basic etf_details objects on manual arguments update
        etf_segment_names = {
            "SPY": "S&P 500 Broad Market",
            "QQQ": "Nasdaq 100 Growth Index",
            "HYG": "High Yield Corporate Bond ETF"
        }
        for sym, val in [("SPY", spy_val), ("QQQ", qqq_val), ("HYG", hyg_val)]:
            if val is not None:
                chg_pct = float(val)
                classification = classify_etf(sym, chg_pct)
                etf_details[sym] = {
                    "Ticker": sym,
                    "ETF Segment / Sector Name": etf_segment_names.get(sym, "Unknown Sector"),
                    "Price": 0.0,
                    "Daily Change %": round(chg_pct, 4),
                    "Classification": classification
                }

    regime_data = {
        "basket_gate": basket_gate,
        "bull_bear_gate": bull_bear_gate,
        "vix_spot": round(vix_spot_val, 2) if vix_spot_val is not None else cached_regime.get("vix_spot", 0.0),
        "vix_bearish": vix_bearish_val,
        "vix_delta_gate": vix_delta_gate,
        "system_authorization": system_auth,
        "gates_passed": gates_passed,
        "etf_details": etf_details,
        "last_updated": datetime.today().strftime('%Y-%m-%d')
    }
    
    save_json(ge.REGIME_FILE, regime_data)
    print(f"Regime gates recomputed and saved to {ge.REGIME_FILE} ({gates_passed}/3 gates passed).")
    print("Account drawdown was not evaluated; run update-performance for each selected account.\n")
    cmd_status(args)


def cmd_status(args):
    """View the current Daily Regime Gates."""
    # 📅 Cache Freshness validation preflight health check
    today_local = datetime.today().strftime('%Y-%m-%d')
    today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    account = getattr(args, "account", "")
    options_file = account_positions_file(account)
    performance_file = account_performance_file(account)
    
    files_to_check = {
        "Daily Regime": (ge.REGIME_FILE, "run 'update-regime' subcommand"),
        "Portfolio Performance": (performance_file, "run 'update-regime' or 'risk' subcommand"),
        "Candidates List": (ge.CANDIDATES_FILE, "run 'update-candidates' subcommand"),
        "Active Options": (options_file, "update options manually or via sync"),
        "Ticker Analyses": (ge.ANALYSES_FILE, "run the full current-session ticker refresh workflow")
    }
    
    print("### 📅 Cache Freshness Report")
    for label, (filepath, action) in files_to_check.items():
        if not os.path.exists(filepath):
            print(f"- **{label}**: {format_color('MISSING', '31', bold=True)} -> *Action: {action}*")
        elif label == "Ticker Analyses":
            freshness = get_ticker_analysis_freshness(account, (today_local, today_utc))
            current_count = len(freshness["current"])
            stale_count = len(freshness["stale"])
            missing_count = len(freshness["missing"])
            if current_count and not stale_count and not missing_count:
                status = format_color(f"FRESH ({current_count} current-session)", "32")
            else:
                status = format_color(
                    f"STALE ({current_count} current, {stale_count} historical-stale, {missing_count} missing)",
                    "33",
                )
            print(f"- **{label}**: {status} -> *Action: {action}*")
        else:
            file_date = ""
            try:
                content = load_json(filepath, {})
                if isinstance(content, dict):
                    if "last_updated" in content:
                        val = content["last_updated"]
                        if "T" in val:
                            file_date = val.split("T")[0]
                        else:
                            file_date = val
                    elif "analyzed_date" in content:
                        file_date = content.get("analyzed_date", "")
            except Exception:
                pass
            
            if not file_date:
                try:
                    mtime = os.path.getmtime(filepath)
                    file_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
                except Exception:
                    file_date = "UNKNOWN"
            
            if file_date in (today_local, today_utc):
                print(f"- **{label}**: {format_color(f'FRESH ({file_date})', '32')}")
            else:
                print(f"- **{label}**: {format_color(f'STALE ({file_date})', '33')} -> *Action: {action}*")
    print()

    regime = get_regime_status()
    
    print("### 📊 GEX Regime Check")
    
    # Let's apply neat styling / colors for CLI output readability
    bgate_status = format_color(regime['basket_gate'], "32" if regime['basket_gate'] == "PASS" else "31", bold=True)
    bbgate_status = format_color(regime['bull_bear_gate'], "32" if regime['bull_bear_gate'] == "PASS" else "31", bold=True)
    vixgate_status = format_color(regime['vix_delta_gate'], "32" if regime['vix_delta_gate'] == "PASS" else "31", bold=True)
    
    spy_pct_str = f"{regime['spy_pct']:+.2f}%"
    qqq_pct_str = f"{regime['qqq_pct']:+.2f}%"
    spy_color = "32" if regime['spy_pct'] >= 0.5 else ("31" if regime['spy_pct'] < 0 else "33")
    qqq_color = "32" if regime['qqq_pct'] >= 0.5 else ("31" if regime['qqq_pct'] < 0 else "33")
    spy_color_str = format_color(spy_pct_str, spy_color)
    qqq_color_str = format_color(qqq_pct_str, qqq_color)
    
    ratio_str = f"{regime['bull_bear_ratio']:.2f}:1"
    ratio_color = "32" if regime['bull_bear_ratio'] >= 3.0 else "31"
    ratio_color_str = format_color(ratio_str, ratio_color)
    
    system_auth_str = regime['system_authorization']
    if "BLOCK" in system_auth_str:
        system_auth_str = format_color(system_auth_str, "31", bold=True)
    else:
        system_auth_str = format_color(system_auth_str, "32", bold=True)
        
    print(f"- **Basket Gate**: {bgate_status} (SPY: {spy_color_str}, QQQ: {qqq_color_str})")
    
    etf_details = regime.get("etf_details", {})
    bullish_etfs = [sym for sym, det in etf_details.items() if sym != "HYG" and det.get("Classification") == "BULLISH"]
    bearish_etfs = [sym for sym, det in etf_details.items() if sym != "HYG" and det.get("Classification") == "BEARISH"]
    bull_str = ", ".join(sorted(bullish_etfs)) if bullish_etfs else "None"
    bear_str = ", ".join(sorted(bearish_etfs)) if bearish_etfs else "None"
    print(f"- **Bull:Bear Gate**: {bbgate_status} (Ratio: {ratio_color_str}, Bulls: {regime['bull_count']} [{bull_str}], Bears: {regime['bear_count']} [{bear_str}] from {ge.REGIME_FILE} Cache)")
    
    print(f"- **VIX Delta Gate**: {vixgate_status} (VIX Spot: {regime['vix_spot']:.2f})")
    
    # 30-Day Drawdown Gate Check
    perf = get_performance_status()
    drawdown_gate_status = perf.get("drawdown_gate_status", "PASS")
    monthly_pnl_dlr = perf.get("monthly_pnl_dlr", 0.0)
    monthly_pnl_pct = perf.get("monthly_pnl_pct", 0.0)
    monthly_cnt = perf.get("monthly_cnt", 0)
    
    drawdown_color = "32" if drawdown_gate_status == "PASS" else "31"
    drawdown_fmt = format_color(drawdown_gate_status, drawdown_color, bold=True)
    m_pnl_fmt = format_pnl(monthly_pnl_dlr, monthly_pnl_pct, bold=True)
    print(f"- **Account Drawdown Gate**: {drawdown_fmt} (30-Day Realized: {m_pnl_fmt} over {monthly_cnt} closed trades)")
    
    print(f"- **System Authorization**: {system_auth_str}")
    
    hyg_pct = regime.get("hyg_pct")
    if hyg_pct is not None:
        hyg_color = "31" if hyg_pct <= -0.3 else ("32" if hyg_pct > 0 else "33")
        hyg_pct_str = format_color(f"{hyg_pct:+.2f}%", hyg_color)
        print(f"- **HYG Credit Overlay**: {hyg_pct_str}")
        
        equities_bullish = regime["spy_pct"] > 0.0 or regime["qqq_pct"] > 0.0
        if hyg_pct < -0.3 and equities_bullish:
            print_color("\n⚠️ CREDIT DIVERGENCE DETECTED: HYG daily change of < -0.30% while equities are positive.", "33", bold=True)
            print_color("⚠️ RISK MITIGATION TRIGGERED: Reduce position sizing on new options entries by 50%.", "33", bold=True)
            
    # Sector Momentum Rotation Summary
    if etf_details:
        spy_change = etf_details.get("SPY", {}).get("Daily Change %")
        if spy_change is None:
            spy_change = regime.get("spy_pct", 0.0)
            
        leaders_tuples = []
        laggers_tuples = []
        for sym, det in etf_details.items():
            if sym in ("SPY", "HYG"):
                continue
            chg = det.get("Daily Change %", 0.0)
            segment_name = det.get("ETF Segment / Sector Name", sym)
            clean_name = segment_name.split(" / ")[-1].split(" ETF")[0]
            if chg > spy_change:
                leaders_tuples.append((chg, sym, clean_name))
            else:
                laggers_tuples.append((chg, sym, clean_name))
                
        leaders_tuples.sort(reverse=True)
        laggers_tuples.sort()
        
        leaders_str = ", ".join(f"{format_color(sym, '35', bold=True)} ({chg:+.2f}%)" for chg, sym, name in leaders_tuples) or "None"
        laggers_str = ", ".join(f"{format_color(sym, '35', bold=True)} ({chg:+.2f}%)" for chg, sym, name in laggers_tuples) or "None"
        
        print("\n### 🔄 Sector Momentum & Rotation")
        spy_color = get_pnl_color(spy_change)
        spy_chg_str = format_pct(spy_change)
        print(f"- **Benchmark SPY Change**: {format_color(spy_chg_str, spy_color, bold=True)}")
        print(f"- **Leading Sectors (Outperforming SPY)**: {leaders_str}")
        print(f"- **Lagging Sectors (Underperforming SPY)**: {laggers_str}")
            
    if etf_details:
        print("\n### 📈 Sector & Broad Market ETF Breadth Board")
        print("  " + "-" * 75)
        print(f"  {'Ticker':<8} | {'ETF Segment / Sector Name':<32} | {'Daily Change':<12} | {'Classification':<12}")
        print("  " + "-" * 75)
        # Sort by classification (BULLISH, FLAT, BEARISH) then daily change %
        def sort_key(x):
            c_val = 0
            if x.get("Classification") == "BULLISH":
                c_val = 2
            elif x.get("Classification") == "FLAT":
                c_val = 1
            else:
                c_val = 0
            return (c_val, float(x.get("Daily Change %", 0.0)))
        sorted_etfs = sorted(etf_details.values(), key=sort_key, reverse=True)
        for det in sorted_etfs:
            ticker = det.get("Ticker", "")
            name = det.get("ETF Segment / Sector Name", "")
            chg = float(det.get("Daily Change %", 0.0))
            classification = det.get("Classification", "FLAT")
            
            # Formats with color
            chg_color = "32" if chg > 0.05 else ("31" if chg < -0.05 else "33")
            class_color = "32" if classification == "BULLISH" else ("31" if classification == "BEARISH" else "33")
            
            chg_str = f"{chg:+.2f}%"
            chg_fmt = format_color(f"{chg_str:<12}", chg_color, bold=True)
            class_fmt = format_color(f"{classification:<12}", class_color, bold=True)
            ticker_fmt = format_color(f"{ticker:<8}", "35", bold=True)
            print(f"  {ticker_fmt} | {name:<32} | {chg_fmt} | {class_fmt}")
        print("  " + "-" * 75)

    # Simple alert or summary
    if regime['system_authorization'] == "BLOCKED":
        print_color("\n🛑 SYSTEM STATUS: BLOCKED. No new entries authorized today.", "31", bold=True)
    else:
        print_color(f"\n✅ SYSTEM STATUS: AUTHORIZED ({regime['system_authorization']}). New trade entries are permitted.", "32", bold=True)

    # 🔔 Central Command alerts summary
    account = getattr(args, "account", "")
    options_file = account_positions_file(account)
    options = load_json(options_file, {"options_positions": {}, "stocks_positions": {}})
    analyses = load_json(ge.ANALYSES_FILE, {})
    positions = options.get("options_positions", {})
    stocks = options.get("stocks_positions", {})
    
    perf = get_performance_status(account)
    
    pending_exits = []
    
    # Check options exits
    for opt_id, details in positions.items():
        ticker = details.get("Underlier", "")
        purchase_premium = float(details.get("Purchase Premium", 1.0))
        mark_price = float(details.get("Mark Price", 1.0))
        strike = details.get("Strike")
        expiration = details.get("Expiration")
        
        levels = analyses.get(ticker, {})
        ptrans = levels.get("pTrans")
        ntrans = levels.get("nTrans")
        gex_t1 = levels.get("+GEX")
        spot = levels.get("Spot")
        if spot is None:
            spot = details.get("Underlier Spot") or details.get("Spot")
        if spot is None:
            spot = float(strike) if strike else 100.0
            
        entry_date = details.get("Entry Date")
        days_held = 1
        if entry_date:
            try:
                days_held = max((datetime.today() - datetime.strptime(entry_date, "%Y-%m-%d")).days + 1, 1)
            except ValueError:
                pass
                
        dte = None
        if expiration:
            try:
                dte = (datetime.strptime(expiration, "%Y-%m-%d") - datetime.today()).days
            except ValueError:
                pass
                
        stalling_counter = details.get("Stalling Days", 0)
        target_mode = details.get("Target Mode", "T1")
        t2_target = details.get("T2 Target")
        if t2_target is not None:
            try:
                t2_target = float(t2_target)
            except (ValueError, TypeError):
                t2_target = None
                
        exit_rule_state, proposed_action, _, _, _ = compute_exit_rule_state(
            spot, purchase_premium, mark_price, ptrans, ntrans, gex_t1, days_held, stalling_counter, dte,
            target_mode=target_mode, t2_target=t2_target
        )
        
        if "STOP" in exit_rule_state or "PROFIT" in exit_rule_state or "EXPIRED" in exit_rule_state or "Exit" in proposed_action or "MET" in exit_rule_state:
            pending_exits.append(f"{ticker} (Option: {exit_rule_state})")
            
    # Check stock exits
    for ticker, details in stocks.items():
        shares = float(details.get("Shares", 0.0))
        avg_price = float(details.get("Average Buy Price", 0.0))
        
        levels = analyses.get(ticker, {})
        ptrans = levels.get("pTrans")
        ntrans = levels.get("nTrans")
        gex_t1 = levels.get("+GEX")
        
        spot = levels.get("Spot")
        if spot is None:
            spot = details.get("Current Price") or details.get("Spot")
        if spot is None:
            spot = avg_price
            
        exit_rule_state = "HOLD"
        if ntrans and spot < ntrans:
            exit_rule_state = "STOP TRIGGERED (Structural Stop)"
        elif gex_t1 and spot >= gex_t1:
            exit_rule_state = "PROFIT TAKE (T1 TARGET MET)"
            
        if "STOP" in exit_rule_state or "PROFIT" in exit_rule_state:
            pending_exits.append(f"{ticker} (Stock: {exit_rule_state})")
            
    # Check confirmed setups
    confirmed_setups = []
    for tkr, data in sorted(analyses.items()):
        if data.get("Signal Status", "").startswith("CONFIRMED"):
            confirmed_setups.append(f"{tkr} (Grade {data.get('Grade')}/11, Spot: ${data.get('Spot')})")
            
    if pending_exits or confirmed_setups:
        print("\n### 🔔 Central Command Actionable Alerts Summary")
        if pending_exits:
            print_color(f"  ⚠️ {len(pending_exits)} TRIGGERED SYSTEMATIC EXITS DETECTED:", "31", bold=True)
            for pe in pending_exits:
                print(f"    - {pe}")
        if confirmed_setups:
            if "BLOCK" in regime['system_authorization']:
                print_color(f"  💤 {len(confirmed_setups)} CONFIRMED SETUPS (Entries currently BLOCKED by daily regime):", "33")
            else:
                print_color(f"  🚀 {len(confirmed_setups)} CONFIRMED SETUPS READY FOR ENTRY:", "32", bold=True)
            for cs in confirmed_setups:
                print(f"    - {cs}")
    else:
        print_color("\n💤 No active portfolio exits or confirmed setups ready for execution today.", "33")
