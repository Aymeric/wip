"""
CLI commands for trade journal auditing, P&L synchronization, decision provenance, and performance tracking.
Provides handlers and subparser definitions for:
- closed
- journal
- sync-pnl
- update-performance
- record-decision
- decisions
"""

import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.gex.core.config import (
    DECISION_ANSWERS,
    DECISION_TYPES,
    DEFAULT_DB_FILE,
    EXIT_REASON_CODES,
    RECONCILED_EXIT_REASON,
    mask_account,
    sanitize_account,
    validate_safe_path,
)
from src.gex.presentation.ascii_art import format_color, print_color
from src.gex.presentation.formatters import (
    format_currency,
    format_pct,
    format_pnl,
    format_table,
    get_pnl_color,
)
from src.gex.storage.db import (
    query_decisions,
    query_trade_metrics,
    record_decision,
    summarize_decisions,
    sync_closed_positions_to_db,
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


def add_journal_parsers(subparsers: Any) -> None:
    """Registers journal command parsers."""
    p_performance = subparsers.add_parser("update-performance", help="Compute account-scoped realized P&L and drawdown metrics.")
    p_performance.add_argument("--account", type=str, required=True, help="Account number for the performance cache")
    p_performance.add_argument("--net-liq", type=float, dest="net_liq", required=True, help="Live account Net Liq value")
    p_performance.add_argument("--monthly-file", type=str, help="Validated account-scoped realized P&L JSON file")
    p_performance.add_argument("--pnl-file", type=str, help="Validated account-scoped trade history JSON file")

    # analyze subcommand

    p_sync_pnl = subparsers.add_parser("sync-pnl", help="Sync trade history to detect closed positions and move them to closed_positions.json.")
    p_sync_pnl.add_argument("--pnl-file", type=str, default="", help="Path to raw Robinhood P&L trade history JSON file")
    p_sync_pnl.add_argument("--account", type=str, default="", help="Optional account number to filter files")

    # sync-positions subcommand

    p_closed = subparsers.add_parser("closed", help="Displays a beautiful execution history of all closed options and stocks positions.")
    p_closed.add_argument("--account", type=str, default="", help="Account number used to scope the closed-position cache")

    # journal subcommand
    p_journal = subparsers.add_parser("journal", help="Calculates machine-readable closed-trade performance and rule attribution metrics.")
    p_journal.add_argument("--account", type=str, default="", help="Account number used to scope position and performance caches")
    p_journal.add_argument("--db", action="store_true", help="Output SQLite database performance metrics instead of JSON cache metrics")
    p_journal.add_argument("--sync-db", action="store_true", help="Synchronize all closed positions into the SQLite database first")

    # audit-all subcommand (Phase 4.3 Pre-Market Execution & Morning Audit)

    p_rec_dec = subparsers.add_parser("record-decision", help="Record human-in-the-loop trade approval or exit decision.")
    p_rec_dec.add_argument("--account", type=str, required=True, help="Account number used to scope decision provenance")
    p_rec_dec.add_argument("--type", type=str.upper, choices=DECISION_TYPES, required=True, help="Decision type (ENTRY or EXIT)")
    p_rec_dec.add_argument("--symbol", type=str, required=True, help="Underlier ticker symbol (e.g. AAPL)")
    p_rec_dec.add_argument("--recommendation", type=str, required=True, help="Proposed action summary or trade specification")
    p_rec_dec.add_argument("--answer", type=str.upper, choices=DECISION_ANSWERS, required=True, help="Human response (APPROVED, DECLINED, SKIPPED, AMBIGUOUS)")
    p_rec_dec.add_argument("--contract", type=str, help="Option contract description or strike/expiry")
    p_rec_dec.add_argument("--grade", type=str.upper, choices=["CONFIRMED", "PENDING", "REJECTED"], help="Setup grade for entry decisions")
    p_rec_dec.add_argument("--regime", type=str, help="Market regime state at decision time (e.g. 'ALL TRACKS OK')")
    p_rec_dec.add_argument("--gates-passed", type=int, dest="gates_passed", help="Number of regime gates passed (0-3)")
    p_rec_dec.add_argument("--trigger", type=str.upper, choices=EXIT_REASON_CODES, help="Triggering stop code for EXIT decisions (e.g. STOP1, STOP5, TARGET)")
    p_rec_dec.add_argument("--order-ref", type=str, dest="order_ref", help="Broker order reference UUID if approved and executed")
    p_rec_dec.add_argument("--notes", type=str, help="Additional context or notes for the decision")
    p_rec_dec.add_argument("--db-path", type=str, dest="db_path", help="Custom SQLite database file path")

    # decisions subcommand (Roadmap 5.6 Approval Decision Ledger)
    p_dec = subparsers.add_parser("decisions", help="Display recorded trade approval decisions and rule-adherence metrics.")
    p_dec.add_argument("--account", type=str, default="", help="Account number used to filter decision ledger")
    p_dec.add_argument("--limit", type=int, default=50, help="Maximum number of decisions to return (default: 50)")
    p_dec.add_argument("--json", action="store_true", help="Output machine-readable JSON format")
    p_dec.add_argument("--db-path", type=str, dest="db_path", help="Custom SQLite database file path")

    # evaluate-rolls subcommand (Roadmap 5.2 Dynamic Delta Rolling & Profit Optimization)



def cmd_update_performance(args):
    """Computes and persists realized drawdown for one account."""
    if args.net_liq is None or args.net_liq <= 0:
        print("Error: --net-liq must be a positive account net liquidation value.", file=sys.stderr)
        sys.exit(1)

    monthly_file = getattr(args, "monthly_file", None)
    if monthly_file:
        try:
            monthly_file = validate_safe_path(monthly_file)
        except ValueError as e:
            print(f"Error: Invalid monthly_file path: {e}", file=sys.stderr)
            sys.exit(1)

    pnl_file = getattr(args, "pnl_file", None)
    if pnl_file:
        try:
            pnl_file = validate_safe_path(pnl_file)
        except ValueError as e:
            print(f"Error: Invalid pnl_file path: {e}", file=sys.stderr)
            sys.exit(1)

    monthly_pnl_dlr, monthly_pnl_pct, drawdown_gate_status, monthly_cnt = get_monthly_realized_pnl(
        args.net_liq,
        monthly_file=monthly_file,
        pnl_file=pnl_file,
    )
    performance_path = account_performance_file(args.account)
    performance_data = {
        "account": args.account,
        "monthly_pnl_dlr": monthly_pnl_dlr,
        "monthly_pnl_pct": monthly_pnl_pct,
        "drawdown_gate_status": drawdown_gate_status,
        "monthly_cnt": monthly_cnt,
        "last_updated": datetime.today().strftime('%Y-%m-%d')
    }
    save_json(performance_path, performance_data)
    print(f"Account performance metrics saved to {performance_path}.")


def cmd_closed(args):
    """Displays a beautiful detailed report of all closed / archived positions."""
    closed_file = account_closed_positions_file(getattr(args, "account", ""))
    closed_data = load_json(closed_file, {"closed_options": [], "closed_stocks": []})
    
    closed_options = closed_data.get("closed_options", [])
    closed_stocks = closed_data.get("closed_stocks", [])
    
    if not closed_options and not closed_stocks:
        print("### 📊 GEX Closed Positions History\n")
        print("💤 No closed positions found in local cache.\n")
        print("💡 Actionable Next Steps:")
        print("  • Sync trade history to archive closed trades: python3 gex_engine.py sync-pnl [--pnl-file <path>]")
        print("  • Close an active option position:            python3 gex_engine.py close-position <option_id_or_ticker> --close-premium <price>")
        print("  • Close an active stock position:             python3 gex_engine.py close-stock <ticker> --close-price <price>")
        return
        
    print("### 📊 GEX Closed Positions History")
    print("  " + "-" * 103)
    print(f"  {'Ticker':<6} | {'Class':<7} | {'Entry Date':<11} | {'Close Date':<11} | {'Days':<4} | {'Cost Basis':<11} | {'Realized P&L ($)':<16} | {'Realized P&L (%)'}")
    print("  " + "-" * 103)
    
    def format_row(item, asset_cls):
        ticker = item.get("Ticker") or item.get("Underlier", "Unknown").upper()
        ticker_fmt = format_color(f"{ticker:<6}", "35", bold=True)
        cls_fmt = f"{asset_cls:<7}"
        entry_date = item.get("Entry Date", "N/A")
        close_date = item.get("Close Date", "N/A")
        
        # Calculate days held
        days = "N/A"
        if entry_date != "N/A" and close_date != "N/A":
            try:
                days = (datetime.strptime(close_date, "%Y-%m-%d") - datetime.strptime(entry_date, "%Y-%m-%d")).days + 1
            except Exception:
                pass
            
        days_str = f"{days:<4}"
        
        cost_basis = item.get("Asset Cost Basis")
        if cost_basis is None:
            if asset_cls == "Option":
                try:
                    cost_basis = float(item.get("Purchase Premium", 1.0)) * 100.0
                except Exception:
                    cost_basis = 0.0
            else:
                try:
                    cost_basis = float(item.get("Shares", 0.0)) * float(item.get("Average Buy Price", 0.0))
                except Exception:
                    cost_basis = 0.0
        cb_str = f"${cost_basis:,.2f}" if cost_basis is not None else f"${0.0:,.2f}"
        cb_fmt = f"{cb_str:<11}"
        
        pnl_dlr = item.get("Realized P&L ($)", 0.0)
        pnl_pct = item.get("Realized P&L (%)", 0.0)
        
        pnl_dlr_fmt = format_pnl(pnl_dlr=pnl_dlr, bold=True, width=16)
        pnl_pct_fmt = format_pnl(pnl_pct=pnl_pct, bold=True, width=16)
        
        print(f"  {ticker_fmt} | {cls_fmt} | {entry_date:<11} | {close_date:<11} | {days_str} | {cb_fmt} | {pnl_dlr_fmt} | {pnl_pct_fmt}")

    for opt in closed_options:
        format_row(opt, "Option")
    for stk in closed_stocks:
        format_row(stk, "Stock")
        
    print("  " + "-" * 103)
    
    # Print summarized stats
    if closed_options:
        total_closed_opt = len(closed_options)
        profitable_closed_opt = sum(1 for p in closed_options if p.get("Realized P&L ($)", 0.0) > 0.0)
        win_rate_opt = (profitable_closed_opt / total_closed_opt) * 100.0 if total_closed_opt > 0 else 0.0
        total_realized_opt = sum(p.get("Realized P&L ($)", 0.0) for p in closed_options)
        gross_p_opt = sum(p.get("Realized P&L ($)", 0.0) for p in closed_options if p.get("Realized P&L ($)", 0.0) > 0.0)
        gross_l_opt = abs(sum(p.get("Realized P&L ($)", 0.0) for p in closed_options if p.get("Realized P&L ($)", 0.0) < 0.0))
        pf_opt = f"{gross_p_opt / gross_l_opt:.2f}" if gross_l_opt > 0 else f"{gross_p_opt:.2f}" if gross_p_opt > 0 else "N/A"
        
        unprofitable_closed_opt = total_closed_opt - profitable_closed_opt
        avg_win_opt = gross_p_opt / profitable_closed_opt if profitable_closed_opt > 0 else 0.0
        avg_loss_opt = gross_l_opt / unprofitable_closed_opt if unprofitable_closed_opt > 0 else 0.0
        r_ratio_opt = avg_win_opt / avg_loss_opt if avg_loss_opt > 0 else 0.0
        expectancy_opt = total_realized_opt / total_closed_opt if total_closed_opt > 0 else 0.0
        
        avg_win_str = f"${avg_win_opt:,.2f}"
        avg_loss_str = f"${avg_loss_opt:,.2f}"
        win_loss_fmt = f"{avg_win_str} / {avg_loss_str} (Ratio: {r_ratio_opt:.2f})"
        expectancy_fmt = format_pnl(pnl_dlr=expectancy_opt, bold=True)
        
        print(f"- **Options Stats** ({total_closed_opt} trades): Realized Win Rate {win_rate_opt:.1f}% ({profitable_closed_opt}/{total_closed_opt} profitable) | Total Realized P&L: {format_pnl(pnl_dlr=total_realized_opt, bold=True)} | PF: {pf_opt}")
        print(f"  -> Avg Win/Loss: {win_loss_fmt} | Expectancy: {expectancy_fmt} per trade")
        
    if closed_stocks:
        total_closed_stk = len(closed_stocks)
        profitable_closed_stk = sum(1 for s in closed_stocks if s.get("Realized P&L ($)", 0.0) > 0.0)
        win_rate_stk = (profitable_closed_stk / total_closed_stk) * 100.0 if total_closed_stk > 0 else 0.0
        total_realized_stk = sum(s.get("Realized P&L ($)", 0.0) for s in closed_stocks)
        gross_p_stk = sum(s.get("Realized P&L ($)", 0.0) for s in closed_stocks if s.get("Realized P&L ($)", 0.0) > 0.0)
        gross_l_stk = abs(sum(s.get("Realized P&L ($)", 0.0) for s in closed_stocks if s.get("Realized P&L ($)", 0.0) < 0.0))
        pf_stk = f"{gross_p_stk / gross_l_stk:.2f}" if gross_l_stk > 0 else f"{gross_p_stk:.2f}" if gross_p_stk > 0 else "N/A"
        
        unprofitable_closed_stk = total_closed_stk - profitable_closed_stk
        avg_win_stk = gross_p_stk / profitable_closed_stk if profitable_closed_stk > 0 else 0.0
        avg_loss_stk = gross_l_stk / unprofitable_closed_stk if unprofitable_closed_stk > 0 else 0.0
        r_ratio_stk = avg_win_stk / avg_loss_stk if avg_loss_stk > 0 else 0.0
        expectancy_stk = total_realized_stk / total_closed_stk if total_closed_stk > 0 else 0.0
        
        avg_win_str = f"${avg_win_stk:,.2f}"
        avg_loss_str = f"${avg_loss_stk:,.2f}"
        win_loss_fmt = f"{avg_win_str} / {avg_loss_str} (Ratio: {r_ratio_stk:.2f})"
        expectancy_fmt = format_pnl(pnl_dlr=expectancy_stk, bold=True)
        
        print(f"- **Stocks Stats** ({total_closed_stk} trades): Realized Win Rate {win_rate_stk:.1f}% ({profitable_closed_stk}/{total_closed_stk} profitable) | Total Realized P&L: {format_pnl(pnl_dlr=total_realized_stk, bold=True)} | PF: {pf_stk}")
        print(f"  -> Avg Win/Loss: {win_loss_fmt} | Expectancy: {expectancy_fmt} per trade")
        
    if closed_options and closed_stocks:
        all_closed = closed_options + closed_stocks
        total_closed_all = len(all_closed)
        profitable_closed_all = sum(1 for p in all_closed if p.get("Realized P&L ($)", 0.0) > 0.0)
        win_rate_all = (profitable_closed_all / total_closed_all) * 100.0 if total_closed_all > 0 else 0.0
        total_realized_all = sum(p.get("Realized P&L ($)", 0.0) for p in all_closed)
        gross_p_all = sum(p.get("Realized P&L ($)", 0.0) for p in all_closed if p.get("Realized P&L ($)", 0.0) > 0.0)
        gross_l_all = abs(sum(p.get("Realized P&L ($)", 0.0) for p in all_closed if p.get("Realized P&L ($)", 0.0) < 0.0))
        pf_all = f"{gross_p_all / gross_l_all:.2f}" if gross_l_all > 0 else f"{gross_p_all:.2f}" if gross_p_all > 0 else "N/A"
        
        unprofitable_closed_all = total_closed_all - profitable_closed_all
        avg_win_all = gross_p_all / profitable_closed_all if profitable_closed_all > 0 else 0.0
        avg_loss_all = gross_l_all / unprofitable_closed_all if unprofitable_closed_all > 0 else 0.0
        r_ratio_all = avg_win_all / avg_loss_all if avg_loss_all > 0 else 0.0
        expectancy_all = total_realized_all / total_closed_all if total_closed_all > 0 else 0.0
        
        avg_win_str = f"${avg_win_all:,.2f}"
        avg_loss_str = f"${avg_loss_all:,.2f}"
        win_loss_fmt = f"{avg_win_str} / {avg_loss_str} (Ratio: {r_ratio_all:.2f})"
        expectancy_fmt = format_pnl(pnl_dlr=expectancy_all, bold=True)
        
        print(f"- **Total Combined Realized P&L**: {format_pnl(pnl_dlr=total_realized_all, bold=True)} | Win Rate {win_rate_all:.1f}% | Combined PF: {pf_all}")
        print(f"  -> Avg Win/Loss: {win_loss_fmt} | Expectancy: {expectancy_fmt} per trade")


def cmd_journal(args):
    """Display machine-readable closed-trade performance metrics."""
    account = getattr(args, "account", "")
    use_db = getattr(args, "db", False)
    sync_db = getattr(args, "sync_db", False)
    closed_file = account_closed_positions_file(account)
    closed_data = load_json(closed_file, {"closed_options": [], "closed_stocks": []})

    if sync_db:
        synced = sync_closed_positions_to_db(closed_data, account=account)
        print(f"Synchronized {synced} trade(s) to SQLite database.", file=sys.stderr)

    if use_db:
        db_metrics = query_trade_metrics(account=account)
        print(json.dumps(db_metrics, indent=2, sort_keys=True))
        return

    performance_file = account_performance_file(account) if account else ge.PERFORMANCE_FILE
    performance_data = load_json(performance_file, {})
    print(json.dumps(calculate_trade_journal(closed_data, performance_data), indent=2, sort_keys=True))


def cmd_sync_pnl(args):
    """Syncs P&L trade history from retrieved file to detect closed positions, and moves closed positions to closed_positions.json."""
    pnl_file = getattr(args, "pnl_file", "")
    if pnl_file:
        try:
            pnl_file = validate_safe_path(pnl_file)
        except ValueError as e:
            print(f"Error: Invalid pnl_file path: {e}", file=sys.stderr)
            sys.exit(1)
    raw_account = getattr(args, "account", "")
    account = sanitize_account(raw_account) if raw_account else ""
    options_file = account_positions_file(account)
    if not pnl_file or not os.path.exists(pnl_file):
        # Scan ge.DOWNLOADS_DIR and sort lexicographically to find the latest trade history file
        pnl_candidates = []
        if os.path.exists(ge.DOWNLOADS_DIR):
            for filepath, file_upper in _get_downloads_files(ge.DOWNLOADS_DIR):
                if account:
                    if file_upper in (f"PNL_TRADE_HISTORY_{account.upper()}_RAW.JSON", f"PNL_TRADE_HISTORY_{account.upper()}.JSON"):
                        pnl_candidates.append(filepath)
                else:
                    if file_upper in ("PNL_TRADE_HISTORY.JSON", "PNL_TRADE_HISTORY_RAW.JSON"):
                        pnl_candidates.append(filepath)
        if pnl_candidates:
            pnl_candidates.sort()
            pnl_file = pnl_candidates[-1]
        else:
            target_name = f"pnl_trade_history_{account}.json" if account else "pnl_trade_history.json"
            print(f"Error: P&L trade history file {args.pnl_file or target_name} not found in {ge.DOWNLOADS_DIR}.", file=sys.stderr)
            sys.exit(1)

    print(f"Loading P&L trade history from: {pnl_file}")
    pnl_data = load_json(pnl_file, {})
    trades = pnl_data.get("data", {}).get("trades", [])
    if not trades:
        trades = pnl_data.get("trades", [])
        
    print(f"Found {len(trades)} trades in trade history.")

    # Load active options and stocks
    options = load_json(options_file, {"options_positions": {}, "stocks_positions": {}})
    positions = options.get("options_positions", {})
    stocks = options.get("stocks_positions", {})

    # Define the separate closed positions file path
    closed_file = account_closed_positions_file(account)
    closed_data = load_json(closed_file, {"closed_options": [], "closed_stocks": []})

    # For safety/migration: if active_positions.json has existing closed items, migrate them!
    migrated_opt = 0
    migrated_stk = 0
    if "closed_options" in options:
        existing_closed_options = options.pop("closed_options")
        for item in existing_closed_options:
            if item not in closed_data["closed_options"]:
                closed_data["closed_options"].append(item)
                migrated_opt += 1
    if "closed_stocks" in options:
        existing_closed_stocks = options.pop("closed_stocks")
        for item in existing_closed_stocks:
            if item not in closed_data["closed_stocks"]:
                closed_data["closed_stocks"].append(item)
                migrated_stk += 1

    if migrated_opt or migrated_stk:
        print(f"Migrated {migrated_opt} options and {migrated_stk} stocks from {options_file} to {closed_file}.")

    newly_closed_stocks = 0
    newly_closed_options = 0

    # Sort trades chronologically to process them in order of occurrence
    sorted_trades = []
    for t in trades:
        ts = t.get("timestamp", "")
        sorted_trades.append((ts, t))
    sorted_trades.sort(key=lambda x: x[0])

    def trade_quantity(trade: Dict[str, Any]) -> Optional[float]:
        """Return a positive realized quantity, or None when the broker omitted it."""
        raw_quantity = trade.get("quantity", trade.get("Quantity"))
        if raw_quantity is None:
            return None
        try:
            quantity = abs(float(raw_quantity))
        except (TypeError, ValueError):
            return None
        return quantity if quantity > 0 else None

    def matching_realized_trades(ticker: str, entry_date: Optional[str], required_quantity: float) -> Optional[List[Tuple[str, Dict[str, Any]]]]:
        """Find enough post-entry realized quantity to close one active position."""
        matches: List[Tuple[str, Dict[str, Any]]] = []
        realized_quantity = 0.0
        for ts, trade in sorted_trades:
            if trade.get("symbol", "").upper() != ticker.upper():
                continue
            if entry_date and ts < entry_date:
                continue
            quantity = trade_quantity(trade)
            if quantity is None:
                continue
            matches.append((ts, trade))
            realized_quantity += quantity
            if realized_quantity + 1e-9 >= required_quantity:
                return matches
        return None

    # 1. Detect Closed Stocks. A realized event can represent a partial close;
    # never archive an active lot until its realized quantity covers the lot.
    stocks_to_remove = []
    for ticker, details in stocks.items():
        entry_date_str = details.get("Entry Date")
        shares = float(details.get("Shares", 0.0))
        matches = matching_realized_trades(ticker, entry_date_str, shares)
        if not matches:
            continue

        ts, t = matches[-1]
        avg_price = float(details.get("Average Buy Price", 0.0))
        try:
            close_price = float(t.get("price", avg_price))
        except (ValueError, TypeError):
            close_price = avg_price
        realized_dollar = sum(float(item.get("realized_gain", 0.0)) for _, item in matches)

        cost_basis = shares * avg_price
        realized_pct = (realized_dollar / cost_basis) * 100.0 if cost_basis > 0 else 0.0
        details["Close Price"] = close_price
        details["Close Date"] = ts[:10] if ts else datetime.today().strftime('%Y-%m-%d')
        details["Realized P&L ($)"] = round(realized_dollar, 2)
        details["Realized P&L (%)"] = round(realized_pct, 2)
        details["Close Reason"] = RECONCILED_EXIT_REASON
        details["Close Note"] = "Detected closed via trade history quantity reconciliation"
        if account:
            details["Account"] = account

        closed_data.setdefault("closed_stocks", []).append(details)
        stocks_to_remove.append(ticker)
        newly_closed_stocks += 1

        pnl_str = format_pnl(realized_dollar, realized_pct, bold=True)
        print(f"Detected Closed Stock {format_color(ticker, '35', bold=True)}: Realized P&L {pnl_str}")

    for ticker in stocks_to_remove:
        stocks.pop(ticker)

    # 2. Detect Closed Options
    options_to_remove = []
    for opt_id, details in positions.items():
        underlier = details.get("Underlier", "").upper()
        entry_date_str = details.get("Entry Date")
        quantity = float(details.get("Quantity", details.get("quantity", 1.0)))
        matches = matching_realized_trades(underlier, entry_date_str, quantity)
        if not matches:
            continue

        ts, t = matches[-1]
        purchase_premium = float(details.get("Purchase Premium", 1.0))
        try:
            close_premium = float(t.get("price", purchase_premium))
        except (ValueError, TypeError):
            close_premium = purchase_premium
        realized_dollar = sum(float(item.get("realized_gain", 0.0)) for _, item in matches)

        realized_pct = ((close_premium - purchase_premium) / purchase_premium) * 100.0 if purchase_premium else 0.0
        if realized_dollar and not realized_pct:
            realized_pct = (realized_dollar / (purchase_premium * 100.0)) * 100.0

        details["Close Premium"] = close_premium
        details["Close Date"] = ts[:10] if ts else datetime.today().strftime('%Y-%m-%d')
        details["Realized P&L ($)"] = round(realized_dollar, 2)
        details["Realized P&L (%)"] = round(realized_pct, 2)
        details["Close Reason"] = RECONCILED_EXIT_REASON
        details["Close Note"] = "Detected closed via trade history quantity reconciliation"
        if account:
            details["Account"] = account

        closed_data.setdefault("closed_options", []).append(details)
        options_to_remove.append(opt_id)
        newly_closed_options += 1

        pnl_str = format_pnl(realized_dollar, realized_pct, bold=True)
        print(f"Detected Closed Option {format_color(underlier, '35', bold=True)} {details.get('Strike')} {details.get('Type')}: Realized P&L {pnl_str}")

    for opt_id in options_to_remove:
        positions.pop(opt_id)

    # Save active and closed files
    options["stocks_positions"] = stocks
    options["options_positions"] = positions
    save_json(options_file, options)
    save_json(closed_file, closed_data)
    try:
        synced = sync_closed_positions_to_db(closed_data, account=account)
        if synced:
            print(f"Synchronized {synced} closed trade(s) to SQLite database.")
    except Exception as e:
        print(f"Notice: SQLite trade sync skipped: {e}", file=sys.stderr)

    print(f"Sync complete. Newly closed: {newly_closed_stocks} stocks, {newly_closed_options} options.")

    print(f"Closed positions saved to {closed_file}. Active positions saved to {options_file}.")


def cmd_record_decision(args):
    """Records an execution approval decision into the SQLite audit ledger."""
    db_path = getattr(args, "db_path", None)
    account = getattr(args, "account", "")
    if not account:
        print("Error: --account is required to record a decision.", file=sys.stderr)
        sys.exit(1)

    try:
        decision_id = record_decision(
            decision_type=args.type,
            symbol=args.symbol,
            recommendation=args.recommendation,
            human_answer=args.answer,
            account=account,
            contract=getattr(args, "contract", None),
            grade=getattr(args, "grade", None),
            regime_authorization=getattr(args, "regime", None),
            gates_passed=getattr(args, "gates_passed", None),
            trigger_code=getattr(args, "trigger", None),
            order_ref=getattr(args, "order_ref", None),
            notes=getattr(args, "notes", None),
            db_path=db_path,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    masked = mask_account(account)
    ans_color = "32" if args.answer == "APPROVED" else ("31" if args.answer == "DECLINED" else "33")
    ans_formatted = format_color(args.answer, ans_color, bold=True)
    print(f"Recorded decision #{decision_id} ({args.type} {args.symbol.upper()} -> {ans_formatted}) for {masked}")


def cmd_decisions(args):
    """Displays recorded human approval decisions and rule-adherence metrics."""
    account = getattr(args, "account", "")
    db_path = getattr(args, "db_path", None)
    limit = getattr(args, "limit", 50)
    as_json = getattr(args, "json", False)

    decisions = query_decisions(account=account, limit=limit, db_path=db_path)
    summary = summarize_decisions(account=account, db_path=db_path)

    if as_json:
        print(json.dumps({"summary": summary, "decisions": decisions}, indent=2, sort_keys=True))
        return

    masked = mask_account(account) if account else "ALL ACCOUNTS"
    print(f"\n### 📋 Execution Approval Decision Ledger ({masked})")

    headers = ["ID", "Recorded At", "Account", "Type", "Symbol", "Grade/Trigger", "Answer", "Order Ref"]
    rows = []
    for d in decisions:
        d_type = d.get("decision_type", "")
        gt = d.get("trigger_code") if d_type == "EXIT" else (d.get("grade") or "-")
        ans = d.get("human_answer", "")
        ans_color = "32" if ans == "APPROVED" else ("31" if ans == "DECLINED" else "33")
        ans_str = format_color(ans, ans_color, bold=(ans in ("APPROVED", "DECLINED")))

        rec_at = (d.get("recorded_at") or "")[:19].replace("T", " ")

        rows.append([
            str(d.get("id")),
            rec_at,
            d.get("account_mask") or "-",
            d_type,
            d.get("symbol", ""),
            gt or "-",
            ans_str,
            d.get("order_ref") or "-",
        ])

    alignments = ["right", "left", "left", "left", "left", "left", "left", "left"]
    print(format_table(headers, rows, empty_message="No decisions recorded in ledger.", alignments=alignments))
    print()

    total = summary["total_decisions"]
    by_type = summary["by_type"]
    by_ans = summary["by_answer"]
    app_rate = summary["approval_rate_pct"]
    conflicts = summary["rule_conflicts_count"]

    print(f"  Total Decisions: {total} (Entries: {by_type.get('ENTRY', 0)}, Exits: {by_type.get('EXIT', 0)})")
    print(f"  Outcomes: Approved: {by_ans.get('APPROVED', 0)} | Declined: {by_ans.get('DECLINED', 0)} | Skipped: {by_ans.get('SKIPPED', 0)} | Ambiguous: {by_ans.get('AMBIGUOUS', 0)}")
    print(f"  Approval Rate: {app_rate:.1f}%")

    if conflicts > 0:
        conf_str = format_color(f"{conflicts} rule conflict(s) detected!", "31", bold=True)
        print(f"  ⚠️  Audit Warning: {conf_str}")
        for c in summary["rule_conflicts"]:
            print(f"      - Decision #{c['id']} ({c['type']} {c['symbol']}): {c['reason']}")
    else:
        ok_str = format_color("0 rule conflicts (100% mechanical adherence)", "32")
        print(f"  Audit Status: {ok_str}")
    print()
