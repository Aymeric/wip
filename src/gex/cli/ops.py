"""
CLI commands for operations, system workflow state, monitoring, snapshotting, and backtesting.
Provides handlers and subparser definitions for:
- workflow
- snapshot
- update-workflow
- audit-all
- monitor
- backtest
- cleanup-downloads
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.gex.backtest import (
    BacktestConfig,
    calculate_backtest_metrics,
    calculate_simulated_entry_fill,
    calculate_simulated_exit_fill,
    simulate_backtest,
)
from src.gex.core.config import (
    sanitize_account,
    validate_safe_path,
)
from src.gex.presentation.ascii_art import format_color
from src.gex.presentation.formatters import (
    format_backtest_regime_breakdown,
    format_backtest_summary,
    format_backtest_trade_log,
    format_pnl,
)
from src.gex.risk.stops import compute_exit_rule_state
from src.gex.screening.monitor import (
    AlertState,
    AlertStateManager,
    PositionBreachAlert,
    evaluate_holding_breaches,
    format_alert_digest,
    monitor_daemon,
    run_monitor_pass,
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


def add_ops_parsers(subparsers: Any) -> None:
    """Registers operations command parsers."""
    p_audit_all = subparsers.add_parser("audit-all", help="Headless pre-market audit across accounts with regime checks, stop evaluation, and optional alerting.")
    p_audit_all.add_argument("--account", type=str, default="", help="Optional specific account number to audit (audits all accounts if omitted)")
    p_audit_all.add_argument("--net-liq", type=float, default=None, help="Estimated Net Liquidation Value for portfolio sizing evaluation")
    p_audit_all.add_argument("--json", action="store_true", help="Output machine-readable JSON summary instead of markdown")
    p_audit_all.add_argument("--alert", action="store_true", help="Dispatch system notification webhooks/desktop alerts if any stop breaches are detected")

    # monitor subcommand (Roadmap 5.4 Intraday GEX Level Breach Monitor & Alert Daemon)
    p_monitor = subparsers.add_parser("monitor", help="Intraday GEX level breach monitor daemon and real-time alert engine.")
    p_monitor.add_argument("--account", type=str, default="", help="Optional account number used to scope active holdings (monitors all accounts if omitted)")
    p_monitor.add_argument("--interval", type=int, default=60, help="Polling interval in seconds between monitoring passes (default: 60)")
    p_monitor.add_argument("--alert", action="store_true", help="Dispatch system notification webhooks/desktop alerts upon level breaches")
    p_monitor.add_argument("--once", action="store_true", help="Execute a single monitoring pass and exit")
    p_monitor.add_argument("--json", action="store_true", help="Output machine-readable JSON format")
    p_monitor.add_argument("--cooldown", type=int, default=1800, help="Per-holding alert cooldown in seconds (default: 1800s / 30m)")
    p_monitor.add_argument("--deadband", type=float, default=0.25, help="Hysteresis deadband percentage before re-arming triggers (default: 0.25%%)")
    p_monitor.add_argument("--digest", action="store_true", help="Print consolidated daily alert digest summary")

    # record-decision subcommand (Roadmap 5.6 Approval Decision Ledger)

    p_workflow = subparsers.add_parser("workflow", help="Aggregates all JSON state into a high-level system summary.")
    p_workflow.add_argument("--account", type=str, default="", help="Optional account number used to scope position and performance caches")

    # snapshot subcommand
    p_snapshot = subparsers.add_parser("snapshot", help="Exports all cached system state as machine-readable JSON.")
    p_snapshot.add_argument("--account", type=str, default="", help="Optional account number used to scope position and performance caches")
    p_snapshot.add_argument("--output", type=str, help="Write the snapshot to a JSON file instead of stdout")

    # update-workflow subcommand
    p_up_flow = subparsers.add_parser("update-workflow", help="Update the session workflow state.")
    p_up_flow.add_argument("--phase", type=str, help="Set current phase (e.g. 'Phase I: Audit')")
    p_up_flow.add_argument("--agent", type=str, help="Subagent name that just completed")
    p_up_flow.add_argument("--status", type=str, choices=["SUCCESS", "FAILED", "PARTIAL", "BLOCKED"], help="Status of the subagent")
    p_up_flow.add_argument("--note", type=str, help="Add a manual progress note")

    # select-spreads subcommand (Milestone 6.1)

    # backtest subcommand (Milestone 5.1)
    p_backtest = subparsers.add_parser("backtest", help="Simulates historical options replay across cached data downloads.")
    p_backtest.add_argument("--start", type=str, help="Start date for simulation window (YYYY-MM-DD or YYYYMMDD)")
    p_backtest.add_argument("--end", type=str, help="End date for simulation window (YYYY-MM-DD or YYYYMMDD)")
    p_backtest.add_argument("--capital", type=float, default=100000.0, help="Initial virtual capital (default: 100,000.0)")
    p_backtest.add_argument("--max-positions", type=int, default=5, help="Maximum concurrent open positions (default: 5)")
    p_backtest.add_argument("--position-size-pct", type=float, default=0.05, help="Single-leg position allocation limit (default: 0.05 = 5%%)")
    p_backtest.add_argument("--target-delta", type=float, default=0.45, help="Target option delta (default: 0.45)")
    p_backtest.add_argument("--min-dte", type=int, default=30, help="Minimum target DTE (default: 30)")
    p_backtest.add_argument("--max-dte", type=int, default=45, help="Maximum target DTE (default: 45)")
    p_backtest.add_argument("--target-mode", type=str, default="T1", choices=["T1", "T2"], help="Exit target mode: T1 (+GEX touch) or T2 (Lock & Ride)")
    p_backtest.add_argument("--downloads-dir", type=str, help="Custom historical downloads directory")
    p_backtest.add_argument("--json", action="store_true", help="Output results as JSON")


    # cleanup-downloads subcommand
    p_clean = subparsers.add_parser("cleanup-downloads", help="Remove dated download folders older than N days and stale tmp folders.")
    p_clean.add_argument("--days", type=int, default=7, help="Remove dated download folders older than N days (default: 7)")




def cmd_workflow(args):
    """Aggregates all JSON state into a high-level system summary."""
    cleanup_downloads()
    regime = get_regime_status()
    auth = regime.get("system_authorization", "BLOCKED")
    state = load_json(ge.WORKFLOW_STATE_FILE, {"current_phase": "Phase 0: Initialization", "subagents": {}, "notes": []})
    
    print(format_color(f"\n--- 🛰️ SYSTEM WORKFLOW STATUS ---", "36", bold=True))
    print(f"Current Phase: {format_color(state['current_phase'], '33', bold=True)}")
    
    # 1. Regime Status
    auth_color = "32" if "OK" in auth else "31"
    print(f"\n[PHASE I] System Authorization: {format_color(auth, auth_color, bold=True)}")
    print(f"  - Bull:Bear Ratio: {regime.get('bull_bear_ratio')} ({regime.get('bull_count')}B : {regime.get('bear_count')}R)")
    print(f"  - VIX Delta Gate: {regime.get('vix_delta_gate')} (Spot: {regime.get('vix_spot')})")
    print(f"  - Basket Gate: {regime.get('basket_gate')} (SPY: {regime.get('spy_pct'):+.2f}%, QQQ: {regime.get('qqq_pct'):+.2f}%)")

    # 2. Portfolio Status
    options_file = account_positions_file(getattr(args, "account", ""))
    pos_data = load_json(options_file, {"options_positions": {}, "stocks_positions": {}})
    active_opts = pos_data.get("options_positions", {})
    active_stocks = pos_data.get("stocks_positions", {})
    print(f"\n[PHASE I] Active Portfolio: {len(active_opts)} Options | {len(active_stocks)} Stocks")
    
    # 3. Discovery Status
    cand_data = load_json(ge.CANDIDATES_FILE, {"candidates": []})
    candidates = cand_data.get("candidates", [])
    print(f"\n[PHASE II] Discovery: {len(candidates)} Candidate Tickers")
    
    # 4. Grading Status
    analyses = load_json(ge.ANALYSES_FILE, {})
    confirmed = [sym for sym, d in analyses.items() if d.get("Signal Status", "").startswith("CONFIRMED")]
    pending = [sym for sym, d in analyses.items() if d.get("Signal Status", "").startswith("PENDING")]
    print(f"\n[PHASE III] Setup Grading: {len(confirmed)} CONFIRMED | {len(pending)} PENDING")
    
    if confirmed:
        print(f"  - Confirmed: {', '.join(confirmed)}")

    # 5. Agent Status
    if state["subagents"]:
        print(f"\n[PHASE LOG] Subagent Executions:")
        for agent, info in state["subagents"].items():
            s_color = "32" if info["status"] == "SUCCESS" else ("31" if info["status"] == "FAILED" else "33")
            print(f"  - {agent:<25}: {format_color(info['status'], s_color)}")
    
    print(f"\n{format_color('--- END STATUS ---', '36')}\n")


def cmd_snapshot(args):
    """Exports the current cached system state as JSON for automation."""
    account = getattr(args, "account", "")
    snapshot = build_system_snapshot(account)
    output_path = getattr(args, "output", None)
    if output_path:
        try:
            output_path = validate_safe_path(output_path)
        except ValueError as e:
            print(f"Error: Invalid output path: {e}", file=sys.stderr)
            sys.exit(1)
        save_json(output_path, snapshot)
        print(f"System snapshot saved to {output_path}")
    else:
        print(json.dumps(snapshot, indent=2, sort_keys=True))


def cmd_update_workflow(args):
    """Updates the workflow state file with current phase and subagent status."""
    state = normalize_workflow_state(load_json(ge.WORKFLOW_STATE_FILE, {}))
    
    if args.phase:
        state["current_phase"] = args.phase
    if args.agent and args.status:
        state["subagents"][args.agent] = {
            "status": args.status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    if args.note:
        state["notes"].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content": args.note
        })
        state["notes"] = state["notes"][-10:]
        
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    save_json(ge.WORKFLOW_STATE_FILE, state)
    print(f"Workflow state updated: {state['current_phase']}")


def cmd_audit_all(args):
    """Headless pre-market audit mode. Audits active positions across accounts, evaluates Stops 1-5, and dispatches alerts."""
    raw_account = getattr(args, "account", "")
    target_account = sanitize_account(raw_account) if raw_account else ""
    is_json = getattr(args, "json", False)
    should_alert = getattr(args, "alert", False)
    net_liq = getattr(args, "net_liq", None)
    if net_liq is None:
        net_liq = 50000.0

    # 1. Discover target account active position files
    files_to_audit = []
    if target_account:
        pos_file = account_positions_file(target_account)
        files_to_audit.append((target_account, pos_file))
    else:
        # Scan data/ directory for active_positions*.json
        if os.path.exists(ge.DATA_DIR):
            for fname in sorted(os.listdir(ge.DATA_DIR)):
                if fname.startswith("active_positions") and fname.endswith(".json"):
                    fpath = os.path.join(ge.DATA_DIR, fname)
                    m = re.match(r"active_positions_([A-Za-z0-9_-]+)\.json", fname)
                    acc = m.group(1) if m else "default"
                    files_to_audit.append((acc, fpath))
        if not files_to_audit:
            files_to_audit.append(("default", ge.OPTIONS_FILE))

    # 2. Market Regime & Macro
    regime_data = load_json(ge.REGIME_FILE, {})
    regime_auth = regime_data.get("system_authorization", "UNKNOWN")
    bb_ratio = float(regime_data.get("bull_bear_ratio", 0.0) or 0.0)
    vix_delta = regime_data.get("vix_delta_gate", "UNKNOWN")

    # 3. Load Analyses
    analyses = load_json(ge.ANALYSES_FILE, {})

    # 4. Audit accounts
    accounts_audit = {}
    all_pending_exits = []
    total_positions_count = 0
    total_portfolio_cost_basis = 0.0
    total_portfolio_current_value = 0.0

    for acc, pos_file in files_to_audit:
        pos_data = load_json(pos_file, {"options_positions": {}, "stocks_positions": {}})
        options = pos_data.get("options_positions", {})
        stocks = pos_data.get("stocks_positions", {})

        opt_items = []
        stock_items = []

        # Audit Options
        for opt_id, details in options.items():
            ticker = details.get("Underlier", "")
            strike = details.get("Strike")
            exp = details.get("Expiration")
            opt_type = details.get("Type", "call").lower()
            purchase_px = float(details.get("Purchase Premium", 1.0) or 1.0)
            mark_px = float(details.get("Mark Price", purchase_px) or purchase_px)
            cost_basis = details.get("Asset Cost Basis") or (purchase_px * 100.0)

            contracts = 1.0
            if "Quantity" in details:
                try:
                    contracts = float(details["Quantity"])
                except (ValueError, TypeError):
                    contracts = 1.0
            elif purchase_px > 0:
                contracts = round(cost_basis / (purchase_px * 100.0), 2)
                if contracts <= 0:
                    contracts = 1.0

            cur_val = mark_px * 100.0 * contracts
            pnl_dlr = (mark_px - purchase_px) * 100.0 * contracts
            pnl_pct = ((mark_px - purchase_px) / purchase_px) * 100.0 if purchase_px else 0.0

            levels = analyses.get(ticker, {})
            ptrans = levels.get("pTrans")
            ntrans = levels.get("nTrans")
            gex_t1 = levels.get("+GEX")
            spot = levels.get("Spot") or details.get("Underlier Spot") or (float(strike) if strike else 100.0)

            entry_date = details.get("Entry Date")
            days_held = 1
            if entry_date:
                try:
                    days_held = max((datetime.today() - datetime.strptime(entry_date, "%Y-%m-%d")).days + 1, 1)
                except ValueError:
                    pass

            dte = None
            if exp:
                try:
                    dte = (datetime.strptime(exp, "%Y-%m-%d") - datetime.today()).days
                except ValueError:
                    pass

            stalling = details.get("Stalling Days", 0)
            target_mode = details.get("Target Mode", "T1")
            t2_target = details.get("T2 Target")
            if t2_target is not None:
                try:
                    t2_target = float(t2_target)
                except (ValueError, TypeError):
                    t2_target = None

            rule_state, _, _, _, _ = compute_exit_rule_state(
                spot, purchase_px, mark_px, ptrans, ntrans, gex_t1, days_held, stalling, dte,
                target_mode=target_mode, t2_target=t2_target
            )

            is_exit = any(k in rule_state for k in ("STOP", "EXIT", "BREACH", "GATE_FAIL"))
            item_summary = {
                "account": acc,
                "asset_cls": "Option",
                "ticker": ticker,
                "id": opt_id,
                "strike": strike,
                "type": opt_type,
                "expiration": exp,
                "dte": dte,
                "spot": spot,
                "cost_basis": cost_basis,
                "current_val": cur_val,
                "pnl_dollar": pnl_dlr,
                "pnl_pct": pnl_pct,
                "rule_state": rule_state,
                "is_pending_exit": is_exit,
            }
            opt_items.append(item_summary)
            if is_exit:
                all_pending_exits.append(item_summary)
            total_positions_count += 1
            total_portfolio_cost_basis += cost_basis
            total_portfolio_current_value += cur_val

        # Audit Stocks
        for ticker, details in stocks.items():
            shares = float(details.get("Shares", 0.0) or 0.0)
            avg_px = float(details.get("Average Buy Price", 0.0) or 0.0)
            cur_px = float(details.get("Current Price", avg_px) or avg_px)
            cost_basis = shares * avg_px
            cur_val = shares * cur_px
            pnl_dlr = cur_val - cost_basis
            pnl_pct = (pnl_dlr / cost_basis) * 100.0 if cost_basis > 0 else 0.0

            levels = analyses.get(ticker, {})
            ntrans = levels.get("nTrans")
            rule_state = "HOLD"
            if ntrans is not None and cur_px < ntrans:
                rule_state = "STOP 1 (BREACH)"
            if pnl_pct <= -50.0:
                rule_state = "STOP 5 (CATASTROPHIC)"

            is_exit = any(k in rule_state for k in ("STOP", "EXIT", "BREACH"))
            item_summary = {
                "account": acc,
                "asset_cls": "Stock",
                "ticker": ticker,
                "shares": shares,
                "spot": cur_px,
                "cost_basis": cost_basis,
                "current_val": cur_val,
                "pnl_dollar": pnl_dlr,
                "pnl_pct": pnl_pct,
                "rule_state": rule_state,
                "is_pending_exit": is_exit,
            }
            stock_items.append(item_summary)
            if is_exit:
                all_pending_exits.append(item_summary)
            total_positions_count += 1
            total_portfolio_cost_basis += cost_basis
            total_portfolio_current_value += cur_val

        accounts_audit[acc] = {
            "options": opt_items,
            "stocks": stock_items,
            "total_account_positions": len(opt_items) + len(stock_items),
        }

    total_unrealized_pnl = total_portfolio_current_value - total_portfolio_cost_basis
    total_unrealized_pct = (total_unrealized_pnl / total_portfolio_cost_basis * 100.0) if total_portfolio_cost_basis > 0 else 0.0

    # 5. Dispatch Alert if requested
    alert_dispatched = False
    if should_alert and all_pending_exits:
        alert_body = f"GEX Risk Stop Alert: {len(all_pending_exits)} exit(s) triggered across {len(accounts_audit)} account(s)!"
        dispatch_system_alert(title="GEX Pre-Market Risk Audit", message=alert_body)
        alert_dispatched = True

    # 6. Output format
    if is_json:
        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "regime": {
                "authorization": regime_auth,
                "bull_bear_ratio": bb_ratio,
                "vix_delta_gate": vix_delta,
            },
            "summary": {
                "accounts_count": len(accounts_audit),
                "total_positions": total_positions_count,
                "total_cost_basis": round(total_portfolio_cost_basis, 2),
                "total_current_value": round(total_portfolio_current_value, 2),
                "total_unrealized_pnl": round(total_unrealized_pnl, 2),
                "total_unrealized_pct": round(total_unrealized_pct, 2),
                "pending_exits_count": len(all_pending_exits),
                "alert_dispatched": alert_dispatched,
            },
            "pending_exits": all_pending_exits,
            "accounts": accounts_audit,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    # Render Markdown
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    auth_color = "32" if regime_auth in ("AUTHORIZED", "GO") else "31"
    print(format_color(f"# 🌅 Pre-Market Portfolio & GEX Risk Audit Brief ({now_str})", "36", bold=True))
    print(f"\n**Market Regime Authorization:** " + format_color(f"{regime_auth}", auth_color, bold=True)
          + f" (Bull/Bear: {bb_ratio:.2f}, VIX Delta: {vix_delta})")
    print(f"**Total Tracked Accounts:** {len(accounts_audit)} | **Open Positions:** {total_positions_count}")
    print(f"**Portfolio Valuation:** ${total_portfolio_current_value:,.2f} | **Unrealized P&L:** ${total_unrealized_pnl:+,.2f} ({total_unrealized_pct:+.2f}%)\n")

    print(format_color("## ⚠️ Action Items & Pending Exits", "33", bold=True))
    if all_pending_exits:
        for exit_item in all_pending_exits:
            acc_str = f"[{exit_item['account']}]" if exit_item['account'] != 'default' else ""
            print(f"  • {acc_str} " + format_color(f"{exit_item['ticker']} {exit_item['asset_cls']}", "35", bold=True)
                  + f": " + format_color(f"{exit_item['rule_state']}", "31", bold=True)
                  + f" (Spot: ${exit_item['spot']:.2f}, P&L: ${exit_item['pnl_dollar']:+,.2f} / {exit_item['pnl_pct']:+.1f}%)")
    else:
        print(format_color("  ✅ All positions within normal risk tolerance. No exit stops triggered.", "32", bold=True))

    print("\n" + format_color("## 📊 Position Breakdown by Account", "36", bold=True))
    for acc, acc_data in accounts_audit.items():
        acc_label = f"Account {acc}" if acc != "default" else "Default Account"
        print(f"\n### {acc_label} ({acc_data['total_account_positions']} positions)")
        if not acc_data["options"] and not acc_data["stocks"]:
            print("  💤 No open positions.")
            continue
        print("  " + "-" * 80)
        print(f"  {'Ticker':<6} | {'Class':<7} | {'Spot':<8} | {'Cost Basis':<11} | {'Cur Value':<11} | {'P&L ($)':<12} | {'State'}")
        print("  " + "-" * 80)
        for p in acc_data["options"] + acc_data["stocks"]:
            pnl_s = format_pnl(pnl_dlr=p["pnl_dollar"], bold=True, width=12)
            state_c = "31" if p["is_pending_exit"] else "32" if "PROFIT" in p["rule_state"] or "T1" in p["rule_state"] else "37"
            state_s = format_color(f"{p['rule_state']}", state_c, bold=p["is_pending_exit"])
            print(f"  {p['ticker']:<6} | {p['asset_cls']:<7} | ${p['spot']:<7.2f} | ${p['cost_basis']:<10.2f} | ${p['current_val']:<10.2f} | {pnl_s} | {state_s}")
        print("  " + "-" * 80)


def cmd_monitor(args):
    """Run intraday GEX level breach monitor daemon or single pass."""
    raw_account = getattr(args, "account", "")
    target_account = sanitize_account(raw_account) if raw_account else ""
    interval = getattr(args, "interval", 60)
    should_alert = getattr(args, "alert", False)
    is_once = getattr(args, "once", False)
    is_json = getattr(args, "json", False)
    cooldown = getattr(args, "cooldown", 1800)
    deadband = getattr(args, "deadband", 0.25)
    show_digest = getattr(args, "digest", False)

    if is_once:
        alert_mgr = AlertStateManager(
            cooldown_seconds=float(cooldown),
            deadband_pct=float(deadband) / 100.0,
        )
        result = run_monitor_pass(account=target_account, alert=should_alert, alert_cache=alert_mgr)
        if is_json:
            print(json.dumps(result, indent=2))
        else:
            ts = result.get("timestamp", "")
            breaches = result.get("breaches", [])
            checked = result.get("total_positions_checked", 0)
            accs = ", ".join(result.get("accounts_checked", [])) or "None"
            print(format_color(f"🛰️ GEX Level Breach Monitor (Single Pass: {ts})", "36", bold=True))
            print(f"Checked accounts: {accs} | Total positions: {checked} | Cooldown: {cooldown}s | Deadband: {deadband:.2f}%")
            if breaches:
                print(format_color(f"\n⚠️ {len(breaches)} LEVEL BREACH(ES) DETECTED:", "31", bold=True))
                for b in breaches:
                    acc_label = b.get("masked_account") or b.get("account") or "Account"
                    print(
                        f"  - [{acc_label}] {b.get('symbol')} ({b.get('position_type')}): "
                        f"{b.get('breach_type')} (Spot ${b.get('spot', 0.0):.2f} vs Level ${b.get('threshold', 0.0):.2f}) -> {b.get('action')}"
                    )
            else:
                print(format_color("\n✅ All holdings within structural runway bounds.", "32", bold=True))

            if show_digest:
                digest = result.get("digest")
                if digest:
                    print("\n" + format_alert_digest(digest))
    else:
        monitor_daemon(
            interval=interval,
            account=target_account,
            alert=should_alert,
            cooldown=cooldown,
            deadband=deadband,
            show_digest=show_digest,
        )


def cmd_backtest(args):
    """Executes historical options replay and systematic backtesting."""
    start_date = getattr(args, "start", None)
    end_date = getattr(args, "end", None)
    initial_capital = getattr(args, "capital", 100000.0) or 100000.0
    max_positions = getattr(args, "max_positions", 5) or 5
    position_size_pct = getattr(args, "position_size_pct", 0.05) or 0.05
    target_delta = getattr(args, "target_delta", 0.45) or 0.45
    min_dte = getattr(args, "min_dte", 30) or 30
    max_dte = getattr(args, "max_dte", 45) or 45
    target_mode = getattr(args, "target_mode", "T1") or "T1"
    downloads_dir = getattr(args, "downloads_dir", None) or ge.DOWNLOADS_DIR

    config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        position_size_pct=position_size_pct,
        max_active_positions=max_positions,
        target_delta=target_delta,
        min_dte=min_dte,
        max_dte=max_dte,
        target_mode=target_mode,
    )

    result = simulate_backtest(config=config, downloads_dir=downloads_dir)

    if getattr(args, "json", False):
        print(json.dumps(result.to_dict(), indent=2))
        return

    print()
    print(format_backtest_summary(result))
    print()
    print(format_backtest_regime_breakdown(result))
    print()
    print(format_backtest_trade_log(result))
    print()


def cmd_cleanup_downloads(args):
    """CLI wrapper for download-folder cleanup."""
    cleanup_downloads(args.days)
