"""
CLI commands for portfolio tracking, position management, delta rolling, and macro hedging.
Provides handlers and subparser definitions for:
- portfolio
- add-position
- update-option
- close-position
- add-stock
- update-stock
- close-stock
- sync-positions
- evaluate-rolls
- hedge-plan
"""

import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.gex.core.config import (
    DEFAULT_EXIT_REASON,
    DEFAULT_SIZING_THRESHOLD,
    DEFAULT_DB_FILE,
    EXIT_REASON_CODES,
    mask_account,
    sanitize_account,
    validate_safe_path,
)
from src.gex.core.models import OptionPosition, StockPosition
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
)
from src.gex.risk.hedge import derive_macro_hedge_plan
from src.gex.risk.rolling import evaluate_portfolio_rolls
from src.gex.risk.stops import compute_exit_rule_state
from src.gex.storage.db import sync_closed_positions_to_db


import src.gex_engine as ge

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


def add_portfolio_parsers(subparsers: Any) -> None:
    """Registers portfolio command parsers."""
    from src.gex.cli.parser import parse_spot_overrides

    p_port = subparsers.add_parser("portfolio", help="Analyzes position exits, trailing stops, and sizing limits.")
    p_port.add_argument("--account", type=str, default="", help="Optional account number used to scope tagged positions and performance")
    p_port.add_argument("--net-liq", type=float, dest="net_liq", help="Estimated Portfolio Net Liq value for sizing checks")
    p_port.add_argument("--sizing-threshold", type=float, dest="sizing_threshold", default=DEFAULT_SIZING_THRESHOLD, help=f"Portfolio Net Liq threshold for strict percentage sizing (default: {DEFAULT_SIZING_THRESHOLD})")
    p_port.add_argument("--spot-overrides", type=parse_spot_overrides, dest="spot_overrides", help="Comma-separated ticker=price overrides, e.g. AAPL=290,BABA=81")

    # add-position subcommand
    p_add_pos = subparsers.add_parser("add-position", help="Register a option contract in tracking sheet.")
    p_add_pos.add_argument("option_id", type=str, help="Option contract ID")
    p_add_pos.add_argument("underlier", type=str, help="Stock ticker symbol")
    p_add_pos.add_argument("strike", type=float, help="Strike price of option")
    p_add_pos.add_argument("expiration", type=str, help="Expiration date (YYYY-MM-DD)")
    p_add_pos.add_argument("type", type=str, choices=["call", "put"], help="Option contract call/put type")
    p_add_pos.add_argument("purchase_premium", type=float, help="Initial premium paid for contract")
    p_add_pos.add_argument("--delta", type=float, default=0.5, help="Delta (e.g. 0.52)")
    p_add_pos.add_argument("--gamma", type=float, default=0.01, help="Gamma (e.g. 0.02)")
    p_add_pos.add_argument("--open-interest", type=int, default=1000, help="Total open interest")
    p_add_pos.add_argument("--imp-vol", type=float, default=0.35, help="Implied volatility (e.g. 0.42)")
    p_add_pos.add_argument("--sector", type=str, default="Technology/Beta", help="Target sector classification (e.g. Technology/Beta, Consumer Cyclical)")
    p_add_pos.add_argument("--account", type=str, default="", help="Account number used to scope the position cache")

    # update-option subcommand
    p_up_opt = subparsers.add_parser("update-option", help="Updates pricing metrics or momentum trackers for options tracking")
    p_up_opt.add_argument("option_id", type=str, help="Option ID or Ticker underlier name")
    p_up_opt.add_argument("--mark", type=float, help="New current Mark Price")
    p_up_opt.add_argument("--delta", type=float, help="New option Delta")
    p_up_opt.add_argument("--gamma", type=float, help="New option Gamma")
    p_up_opt.add_argument("--oi", type=int, help="New option Open Interest")
    p_up_opt.add_argument("--iv", type=float, help="New option Implied Vol")
    p_up_opt.add_argument("--stalling-days", type=int, help="Set stalling counter")
    p_up_opt.add_argument("--target-mode", type=str, choices=["T1", "T2"], help="Set target mode for trailing rules (T1, T2)")
    p_up_opt.add_argument("--t2-target", type=float, help="Set secondary structural T2 target price")
    p_up_opt.add_argument("--account", type=str, default="", help="Account number used to scope the position cache")

    # close-position subcommand
    p_close_pos = subparsers.add_parser("close-position", help="Close a tracked option position and archive realized P&L.")
    p_close_pos.add_argument("option_id", type=str, help="Option ID or Ticker underlier name")
    p_close_pos.add_argument("--close-premium", type=float, dest="close_premium", help="Exit premium received (defaults to last Mark Price)")
    p_close_pos.add_argument("--account", type=str, default="", help="Account number used to scope position caches")
    p_close_pos.add_argument("--reason", type=str.upper, choices=EXIT_REASON_CODES, default=DEFAULT_EXIT_REASON, help="Coded exit reason (Stop 1-5 hierarchy, TARGET, MANUAL, RECONCILED). Default: MANUAL")

    # add-stock subcommand
    p_add_stock = subparsers.add_parser("add-stock", help="Register a stock position in tracking sheet.")
    p_add_stock.add_argument("ticker", type=str, help="Stock ticker symbol")
    p_add_stock.add_argument("shares", type=float, help="Number of shares purchased")
    p_add_stock.add_argument("average_buy_price", type=float, help="Average cost paid per share")
    p_add_stock.add_argument("--sector", type=str, default="Equity", help="Target sector tag (default: Equity)")
    p_add_stock.add_argument("--trail-pct", type=float, help="Trailing stop percentage (e.g. 5.0 for 5%%)")
    p_add_stock.add_argument("--stop-pct", type=float, help="Hard stop loss percentage (e.g. 7.0 for 7%%)")
    p_add_stock.add_argument("--target-pct", type=float, help="Profit target percentage (e.g. 15.0 for 15%%)")
    p_add_stock.add_argument("--account", type=str, default="", help="Account number used to scope the position cache")

    # update-stock subcommand
    p_up_stock = subparsers.add_parser("update-stock", help="Update stock tracking metrics.")
    p_up_stock.add_argument("ticker", type=str, help="Stock ticker symbol")
    p_up_stock.add_argument("--price", type=float, help="New current stock price")
    p_up_stock.add_argument("--shares", type=float, help="New stock shares count")
    p_up_stock.add_argument("--sector", type=str, help="New stock sector tag")
    p_up_stock.add_argument("--trail-pct", type=float, help="Update trailing stop percentage")
    p_up_stock.add_argument("--stop-pct", type=float, help="Update stop loss percentage")
    p_up_stock.add_argument("--target-pct", type=float, help="Update profit target percentage")
    p_up_stock.add_argument("--highest-price", type=float, dest="highest_price", help="Override highest price tracked")
    p_up_stock.add_argument("--account", type=str, default="", help="Account number used to scope the position cache")

    # close-stock subcommand
    p_close_stock = subparsers.add_parser("close-stock", help="Close a tracked stock position and archive standard P&L.")
    p_close_stock.add_argument("ticker", type=str, help="Stock ticker symbol")
    p_close_stock.add_argument("--close-price", type=float, dest="close_price", help="Exit price received per share (defaults to last current price)")
    p_close_stock.add_argument("--account", type=str, default="", help="Account number used to scope position caches")
    p_close_stock.add_argument("--reason", type=str.upper, choices=EXIT_REASON_CODES, default=DEFAULT_EXIT_REASON, help="Coded exit reason (Stop 1-5 hierarchy, TARGET, MANUAL, RECONCILED). Default: MANUAL")

    # update-candidates subcommand

    p_sync_pos = subparsers.add_parser("sync-positions", help="Sync active options and equity positions from raw Robinhood downloads.")
    p_sync_pos.add_argument("--base-dir", type=str, default="", help="Directory containing raw positions files (e.g. data/downloads/YYYYMMDD)")
    p_sync_pos.add_argument("--account", type=str, default="", help="Optional account number to filter files")

    # rankings subcommand

    p_rolls = subparsers.add_parser("evaluate-rolls", help="Evaluates active options positions for dynamic delta rolling and profit ratchets.")
    p_rolls.add_argument("--account", type=str, default="", help="Account number used to scope position cache")
    p_rolls.add_argument("--threshold-delta", type=float, default=0.70, dest="threshold_delta", help="Minimum delta trigger for rolling (default: 0.70)")
    p_rolls.add_argument("--threshold-gain", type=float, default=50.0, dest="threshold_gain", help="Minimum profit %% trigger for rolling (default: 50.0%%)")
    p_rolls.add_argument("--json", action="store_true", help="Output machine-readable JSON format")

    # hedge-plan subcommand (Roadmap 5.3 Automated Beta-Weighted Macro Hedging Engine)
    p_hedge = subparsers.add_parser("hedge-plan", help="Derives an automated portfolio beta-weighted macro hedge plan.")
    p_hedge.add_argument("--account", type=str, default="", help="Account number used to scope position cache")
    p_hedge.add_argument("--net-liq", type=float, default=None, dest="net_liq", help="Portfolio Net Liquidation value in USD")
    p_hedge.add_argument("--target-coverage", type=float, default=None, dest="target_coverage", help="Target delta coverage ratio (0.0 to 1.0, e.g. 0.50 for 50%%)")
    p_hedge.add_argument("--instrument", type=str, default="AUTO", choices=["AUTO", "SPY", "QQQ"], help="Target index ETF for hedge spread (default: AUTO)")
    p_hedge.add_argument("--json", action="store_true", help="Output machine-readable JSON format")


    # workflow subcommand



def cmd_portfolio(args):
    """Tracks position exits, risk sizing weights, and portfolio metrics."""
    options_file = account_positions_file(getattr(args, "account", ""))
    options = load_json(options_file, {"options_positions": {}, "stocks_positions": {}})
    analyses = load_json(ge.ANALYSES_FILE, {})
    account = getattr(args, "account", "")
    
    positions = options.get("options_positions", {})
    stocks = options.get("stocks_positions", {})

    if account:
        positions = {
            position_id: details
            for position_id, details in positions.items()
            if not details.get("Account") or details.get("Account") == account
        }
        stocks = {
            ticker: details
            for ticker, details in stocks.items()
            if not details.get("Account") or details.get("Account") == account
        }
    
    pending_exits = []
    
    if not positions and not stocks:
        print("### 🛡️ Active Portfolio Tracker & Exits (Current Positions)\n")
        print_color("💤 No open portfolio positions found in local cache.", "33")
        print("\n💡 Actionable Next Steps:")
        print("  • Add an option position: python3 gex_engine.py add-position <option_id> <ticker> <strike> <expiration> <type> <purchase_premium>")
        print("  • Add a stock position:  python3 gex_engine.py add-stock <ticker> <shares> <average_buy_price>")
        print("  • Sync positions:        python3 gex_engine.py sync-positions")
        return
        
    print("### 🛡️ Active Portfolio Tracker & Exits (Current Positions)")
    
    net_liq = args.net_liq if args.net_liq is not None else 50000.0 # Default total workspace valuation estimate
    table_rows = []
    
    total_net_delta_shares = 0.0
    total_net_delta_exposure_dlr = 0.0
    total_beta_weighted_delta_exposure_dlr = 0.0
    
    # 1. Option Pre-calculations
    for opt_id, details in positions.items():
        ticker = details.get("Underlier", "")
        purchase_premium = float(details.get("Purchase Premium", 1.0))
        mark_price = float(details.get("Mark Price", 1.0))
        strike = details.get("Strike")
        expiration = details.get("Expiration")
        
        # Derivation of contracts count for scaling
        cost_basis = details.get("Asset Cost Basis") or (purchase_premium * 100.0)
        contracts_count = 1.0
        if "Quantity" in details:
            try:
                contracts_count = float(details["Quantity"])
            except (ValueError, TypeError):
                pass
        elif purchase_premium > 0:
            contracts_count = round(cost_basis / (purchase_premium * 100.0), 2)
            if contracts_count <= 0:
                contracts_count = 1.0

        # Calculate P&L
        pl_dollar = (mark_price - purchase_premium) * 100 * contracts_count
        pl_pct = ((mark_price - purchase_premium) / purchase_premium) * 100 if purchase_premium else 0.0
        
        # Fetch levels from analyses if available
        levels = analyses.get(ticker, {})
        ptrans = levels.get("pTrans")
        ntrans = levels.get("nTrans")
        gex_t1 = levels.get("+GEX")
        spot = args.spot_overrides.get(ticker) if args.spot_overrides else None
        if spot is None:
            spot = levels.get("Spot")
        if spot is None:
            spot = details.get("Underlier Spot") or details.get("Spot")
        if spot is None:
            spot = float(strike) if strike else 100.0
            
        # Entry date calculation
        entry_date = details.get("Entry Date")
        days_held = 1
        if entry_date:
            try:
                days_held = max((datetime.today() - datetime.strptime(entry_date, "%Y-%m-%d")).days + 1, 1)
            except ValueError:
                pass
                
        # DTE
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
                
        exit_rule_state, _, _, _, _ = compute_exit_rule_state(
            spot, purchase_premium, mark_price, ptrans, ntrans, gex_t1, days_held, stalling_counter, dte,
            target_mode=target_mode, t2_target=t2_target
        )
        
        current_value = mark_price * 100.0 * contracts_count
        sizing_risk_weight = (cost_basis / net_liq) * 100
        
        table_rows.append({
            "ticker": ticker,
            "asset_cls": "Option",
            "spot": spot,
            "cost_basis": cost_basis,
            "current_value": current_value,
            "pnl_dlr": pl_dollar,
            "pnl_pct": pl_pct,
            "weight": sizing_risk_weight,
            "rule_state": exit_rule_state,
            "sector": details.get("Beta Sector Tag", "Equity")
        })

        # Delta calculations
        try:
            delta_val = float(details.get("Delta") or 0.5)
        except Exception:
            delta_val = 0.5
            
        opt_type = details.get("Type", "call").lower()
        if opt_type == "put" and delta_val > 0:
            delta_val = -delta_val
        elif opt_type == "call" and delta_val < 0:
            delta_val = -delta_val
                
        delta_shares = delta_val * 100.0 * contracts_count
        delta_exposure = delta_shares * spot
        total_net_delta_shares += delta_shares
        total_net_delta_exposure_dlr += delta_exposure
        
        # Beta-Weighted calculations for option
        opt_sector = details.get("Beta Sector Tag", "Equity")
        opt_beta = get_beta_factor(opt_sector)
        total_beta_weighted_delta_exposure_dlr += delta_exposure * opt_beta
        
    # 2. Stock Pre-calculations
    for ticker, details in stocks.items():
        shares = float(details.get("Shares", 0.0))
        avg_price = float(details.get("Average Buy Price", 0.0))
        
        levels = analyses.get(ticker, {})
        ptrans = levels.get("pTrans")
        ntrans = levels.get("nTrans")
        gex_t1 = levels.get("+GEX")
        
        spot = args.spot_overrides.get(ticker) if args.spot_overrides else None
        if spot is None:
            spot = levels.get("Spot")
        if spot is None:
            spot = details.get("Current Price") or details.get("Spot")
        if spot is None:
            spot = avg_price
            
        cost_basis = shares * avg_price
        curr_val = shares * spot
        pl_dollar = curr_val - cost_basis
        pl_pct = (pl_dollar / cost_basis) * 100.0 if cost_basis > 0 else 0.0
        
        exit_rule_state = "HOLD"
        if ntrans:
            if spot < ntrans:
                exit_rule_state = "STOP TRIGGERED (Structural)"
        if exit_rule_state == "HOLD":
            if gex_t1 and spot >= gex_t1:
                exit_rule_state = "PROFIT TAKE"
            elif ptrans and spot < ptrans:
                exit_rule_state = "WATCH"
                
        sizing_risk_weight = (cost_basis / net_liq) * 100
        
        table_rows.append({
            "ticker": ticker,
            "asset_cls": "Stock",
            "spot": spot,
            "cost_basis": cost_basis,
            "current_value": curr_val,
            "pnl_dlr": pl_dollar,
            "pnl_pct": pl_pct,
            "weight": sizing_risk_weight,
            "rule_state": exit_rule_state,
            "sector": details.get("Beta Sector Tag", "Equity")
        })

        # Delta calculations for stocks (1 share = 1.0 delta)
        total_net_delta_shares += shares
        total_net_delta_exposure_dlr += shares * spot
        
        # Beta-Weighted calculations for stock
        stk_sector = details.get("Beta Sector Tag", "Equity")
        stk_beta = get_beta_factor(stk_sector)
        total_beta_weighted_delta_exposure_dlr += (shares * spot) * stk_beta

    print("\n### 📊 Portfolio Allocation & Performance Matrix")
    print("  " + "-" * 114)
    print(f"  {'Ticker':<6} | {'Class':<6} | {'Spot':<8} | {'Cost Basis':<10} | {'Current Val':<11} | {'Unrealized P&L':<20} | {'Weight':<6} | {'Rule State':<26}")
    print("  " + "-" * 114)
    
    for r in table_rows:
        tk_str = f"{r['ticker']:<6}"
        tk_fmt = format_color(tk_str, "35", bold=True)
        
        cls_fmt = f"{r['asset_cls']:<6}"
        
        spot_str = f"${r['spot']:,.2f}"
        spot_fmt = f"{spot_str:<8}"

        cb_str = f"${r['cost_basis']:,.2f}"
        cb_fmt = f"{cb_str:<10}"

        cv_str = f"${r['current_value']:,.2f}"
        cv_fmt = f"{cv_str:<11}"
        
        pnl_dlr = r['pnl_dlr']
        pnl_pct = r['pnl_pct']
        pnl_fmt = format_pnl(pnl_dlr, pnl_pct, bold=True, width=20)
        
        weight_fmt = f"{r['weight']:5.2f}%"
        
        # Color coding rule states in table with explicit non-TTY status indicators
        r_state = r['rule_state']
        if "STOP" in r_state or "EXPIRED" in r_state:
            r_color, r_bold = "31", True
            clean_state = r_state.replace("STOP TRIGGERED ", "").replace("EXPIRED ", "")
            r_state_short = f"[STOP] {clean_state}"
        elif "PROFIT" in r_state or "MET" in r_state:
            r_color, r_bold = "32", True
            clean_state = r_state.replace("PROFIT TAKE ", "")
            r_state_short = f"[TAKE] {clean_state}"
        elif "WATCH" in r_state:
            r_color, r_bold = "33", False
            r_state_short = f"[WARN] {r_state}"
        else:
            r_color, r_bold = "32", False
            r_state_short = f"[HOLD] {r_state}" if r_state != "HOLD" else "[HOLD] Normal Posture"
        
        if len(r_state_short) > 26:
            r_state_short = r_state_short[:23] + "..."
        r_fmt = format_color(f"{r_state_short:<26}", r_color, bold=r_bold)
        
        print(f"  {tk_fmt} | {cls_fmt} | {spot_fmt} | {cb_fmt} | {cv_fmt} | {pnl_fmt} | {weight_fmt} | {r_fmt}")
        
    print("  " + "-" * 114)
    
    tech_exposure = 0.0
    total_cost_basis = 0.0
    total_current_value = 0.0
    
    if positions:
        print("\n### 🛡️ Active Options Positions (GEX Tracked)")
    for opt_id, details in positions.items():
        ticker = details.get("Underlier")
        purchase_premium = float(details.get("Purchase Premium", 1.0))
        mark_price = float(details.get("Mark Price", 1.0))
        strike = details.get("Strike")
        expiration = details.get("Expiration")
        opt_type = details.get("Type")
        
        cost_basis = details.get("Asset Cost Basis") or (purchase_premium * 100.0)
        contracts_count = 1.0
        if "Quantity" in details:
            try:
                contracts_count = float(details["Quantity"])
            except (ValueError, TypeError):
                pass
        elif purchase_premium > 0:
            contracts_count = round(cost_basis / (purchase_premium * 100.0), 2)
            if contracts_count <= 0:
                contracts_count = 1.0

        # Calculate P&L
        pl_dollar = (mark_price - purchase_premium) * 100 * contracts_count
        pl_pct = ((mark_price - purchase_premium) / purchase_premium) * 100
        
        # Fetch levels from analyses if available
        levels = analyses.get(ticker, {})
        ptrans = levels.get("pTrans")
        ntrans = levels.get("nTrans")
        gex_t1 = levels.get("+GEX")
        cotmp = levels.get("COTMP")
        spot = args.spot_overrides.get(ticker) if args.spot_overrides else None
        if spot is None:
            spot = levels.get("Spot")
        if spot is None:
            spot = details.get("Underlier Spot") or details.get("Spot")
            
        if spot is None:
            # Fallback mock spot to keep calculations running
            spot = float(strike) if strike else 100.0
            
        # Determine tracking days (derived from Entry Date)
        entry_date = details.get("Entry Date")
        days_held = 1
        if entry_date:
            try:
                days_held = max((datetime.today() - datetime.strptime(entry_date, "%Y-%m-%d")).days + 1, 1)
            except ValueError:
                pass

        # Days to expiration
        dte = None
        if expiration:
            try:
                dte = (datetime.strptime(expiration, "%Y-%m-%d") - datetime.today()).days
            except ValueError:
                pass
        
        # Calculate stops
        stalling_counter = details.get("Stalling Days", 0)
        target_mode = details.get("Target Mode", "T1")
        t2_target = details.get("T2 Target")
        if t2_target is not None:
            try:
                t2_target = float(t2_target)
            except (ValueError, TypeError):
                t2_target = None
                
        exit_rule_state, proposed_action, time_status, distance_ntrans, distance_max_stop = compute_exit_rule_state(
            spot, purchase_premium, mark_price, ptrans, ntrans, gex_t1, days_held, stalling_counter, dte,
            target_mode=target_mode, t2_target=t2_target
        )
            
        # Update metrics in position state
        details["Current Value"] = mark_price * 100 * contracts_count
        details["P&L ($)"] = round(pl_dollar, 2)
        details["P&L (%)"] = round(pl_pct, 2)
        sizing_risk_weight = (cost_basis / net_liq) * 100
        details["Sizing Risk Weight (%)"] = round(sizing_risk_weight, 2)
        
        details_sector_tag = details.get("Beta Sector Tag", "Equity")
        if "Technology" in details_sector_tag or "Beta" in details_sector_tag:
            tech_exposure += sizing_risk_weight
            
        # Format strings with CLI colors
        pl_color = get_pnl_color(pl_pct)
        status_colors = {
            "HOLD": ("32", False),
            "WATCH": ("33", False),
            "PROFIT TAKE (T1 TARGET MET)": ("32", True),
            "PROFIT TAKE (T2 TARGET MET)": ("32", True),
            "UNDERLIER TARGET MET (Option in Loss)": ("31", True),
            "STOP TRIGGERED (Structural Stop: Spot < nTrans)": ("31", True),
            "STOP TRIGGERED (Max Asset Stop: -10% option loss below pTrans)": ("31", True),
            "STOP TRIGGERED (Time Stop: <50% progress by Day 7)": ("31", True),
            "STOP TRIGGERED (Stalling Stop: <10% daily progress for 3 consecutive days)": ("31", True),
            "STOP TRIGGERED (Trailed Stop: Option at or below entry premium)": ("31", True),
            "EXPIRED (Contract past expiration)": ("31", True),
        }
        color_code, bold = status_colors.get(exit_rule_state, ("31", True))
        exit_rule_fmt = format_color(exit_rule_state, color_code, bold=bold)
        
        # Print position
        print(f"- **{format_color(ticker, '35', bold=True)}**: Current Spot {format_color(f'${spot:.2f} (Spot)', '36')} vs Avg Buy Premium {format_color(f'${purchase_premium:.2f}', '33')} / Mark {format_color(f'${mark_price:.2f}', '33')} (Gain/Loss: {format_color(f'{pl_pct:+.2f}%', pl_color, bold=True)})")
        print(f"  - **Exits Rule State**: [{exit_rule_fmt}]")
        print(f"  - **Target Mode**: [{target_mode}]{' (Target Strike: $' + f'{t2_target:.2f}' + ')' if t2_target else ''}")
        print(f"  - **Distance to Structural Stop (nTrans at ${ntrans if ntrans else 0.0:.2f})**: {distance_ntrans}")
        print(f"  - **Distance to Max Asset Stop**: {distance_max_stop}")
        dte_str = f", DTE: {dte}" if dte is not None else ""
        time_limit_str = "N/A (LEAP)" if (dte is not None and dte > 90) else "7"
        print(f"  - **Time / Momentum Tracking**: Day [{days_held}] of {time_limit_str} (Status: [{time_status}]{dte_str})")
        print(f"  - **Proposed Action**: [{format_color(proposed_action, color_code, bold=bold)}]")
        if ptrans is not None or ntrans is not None or gex_t1 is not None or cotmp is not None:
            scale_str = generate_ascii_gex_scale(spot, ptrans, ntrans, gex_t1, cotmp)
            print(f"  - **GEX Runway Map**: {scale_str}")
        
        # Accumulate pending exits for options
        if "STOP" in exit_rule_state or "PROFIT" in exit_rule_state or "EXPIRED" in exit_rule_state or "Exit" in proposed_action or "MET" in exit_rule_state:
            pending_exits.append({
                "ticker": ticker,
                "asset_cls": "Option",
                "desc": f"{opt_type.upper()} Strike ${strike} Exp {expiration}",
                "rule_state": exit_rule_state,
                "proposed_action": proposed_action,
                "current_price": mark_price,
                "pnl_pct": pl_pct,
                "pnl_dlr": pl_dollar
            })
            
        # Accumulate aggregate metrics
        total_cost_basis += details.get("Asset Cost Basis") or (purchase_premium * 100.0)
        total_current_value += details.get("Current Value") or (mark_price * 100.0)

    if stocks:
        print("\n### 📈 Active Stock Positions")
    for ticker, details in stocks.items():
        shares = float(details.get("Shares", 0.0))
        avg_price = float(details.get("Average Buy Price", 0.0))
        
        levels = analyses.get(ticker, {})
        ptrans = levels.get("pTrans")
        ntrans = levels.get("nTrans")
        gex_t1 = levels.get("+GEX")
        cotmp = levels.get("COTMP")
        
        spot = args.spot_overrides.get(ticker) if args.spot_overrides else None
        if spot is None:
            spot = levels.get("Spot")
        if spot is None:
            spot = details.get("Current Price") or details.get("Spot")
        if spot is None:
            spot = avg_price
            
        cost_basis = shares * avg_price
        curr_val = shares * spot
        pl_dollar = curr_val - cost_basis
        pl_pct = (pl_dollar / cost_basis) * 100.0 if cost_basis > 0 else 0.0
        
        # Determine exit rule states for stocks
        exit_rule_state = "HOLD"
        proposed_action = "No Action"
        
        # Update/get Highest Price
        highest_price = details.get("Highest Price")
        if highest_price is None:
            highest_price = details.get("Average Buy Price", spot)
        highest_price = max(highest_price, spot)
        details["Highest Price"] = highest_price
        
        # 1. Structural Stop
        distance_ntrans = "N/A"
        if ntrans:
            dist = ((spot - ntrans) / ntrans) * 100
            distance_ntrans = f"{dist:+.2f}%"
            if spot < ntrans:
                exit_rule_state = "STOP TRIGGERED (Structural Stop: Spot < nTrans)"
                proposed_action = "Immediate Exit (Structural Stop)"
                
        # 2. Trailing Stop Pct
        if exit_rule_state == "HOLD":
            trail_pct = details.get("Trailing Stop Pct")
            if trail_pct is not None:
                trail_price = highest_price * (1.0 - trail_pct / 100.0)
                if spot < trail_price:
                    exit_rule_state = f"STOP TRIGGERED (Trailing Stop: Spot < Highest Price - {trail_pct}%)"
                    proposed_action = f"Immediate Exit (Trailing Stop Triggered: spot ${spot:.2f} < stop price ${trail_price:.2f})"
                    
        # 3. Stop Loss Pct
        if exit_rule_state == "HOLD":
            stop_pct = details.get("Stop Loss Pct")
            if stop_pct is not None:
                stop_price = avg_price * (1.0 - stop_pct / 100.0)
                if spot < stop_price:
                    exit_rule_state = f"STOP TRIGGERED (Stop Loss: Spot < Avg Buy Price - {stop_pct}%)"
                    proposed_action = f"Immediate Exit (Stop Loss Triggered: spot ${spot:.2f} < stop price ${stop_price:.2f})"
                    
        # 4. Profit Target Pct
        if exit_rule_state == "HOLD":
            target_pct = details.get("Profit Target Pct")
            if target_pct is not None:
                target_price = avg_price * (1.0 + target_pct / 100.0)
                if spot >= target_price:
                    exit_rule_state = f"PROFIT TAKE (Profit Target: Spot >= Avg Buy Price + {target_pct}%)"
                    proposed_action = f"Exit position or scale out at profit target (spot ${spot:.2f} >= target price ${target_price:.2f})"
                    
        # 5. Standard GEX exits fallback
        if exit_rule_state == "HOLD":
            if gex_t1 and spot >= gex_t1:
                exit_rule_state = "PROFIT TAKE (T1 TARGET MET)"
                proposed_action = "Exit position or scale out at +GEX target to lock in gains"
            elif ptrans and spot < ptrans:
                exit_rule_state = "WATCH"
                proposed_action = "Hold existing, but add NOTHING"
                
        details["Current Price"] = spot
        details["Current Value"] = curr_val
        details["P&L ($)"] = round(pl_dollar, 2)
        details["P&L (%)"] = round(pl_pct, 2)
        sizing_risk_weight = (cost_basis / net_liq) * 100
        details["Sizing Risk Weight (%)"] = round(sizing_risk_weight, 2)
        
        details_sector_tag = details.get("Beta Sector Tag", "Equity")
        if "Technology" in details_sector_tag or "Beta" in details_sector_tag:
            tech_exposure += sizing_risk_weight
            
        pl_color = get_pnl_color(pl_pct)
        color_code, bold = ("32", False)
        if "STOP" in exit_rule_state or "EXPIRED" in exit_rule_state:
            color_code, bold = "31", True
        elif "PROFIT" in exit_rule_state or "MET" in exit_rule_state:
            color_code, bold = "32", True
        elif "WATCH" in exit_rule_state:
            color_code, bold = "33", False
        exit_rule_fmt = format_color(exit_rule_state, color_code, bold=bold)
        
        print(f"- **{format_color(ticker, '35', bold=True)}**: Current Spot {format_color(f'${spot:.2f} (Spot)', '36')} vs Avg Buy Price {format_color(f'${avg_price:.2f}', '33')} (Shares: {shares:,.2f} | Gain/Loss: {format_color(f'{pl_pct:+.2f}%', pl_color, bold=True)} / {format_color(f'${pl_dollar:+.2f}', pl_color, bold=True)})")
        print(f"  - **Exits Rule State**: [{exit_rule_fmt}]")
        print(f"  - **Distance to GEX nTrans Stop (nTrans at ${ntrans if ntrans else 0.0:.2f})**: {distance_ntrans}")
        
        # Print configured trailing/stop/profit parameters
        extra_rules = []
        if details.get("Trailing Stop Pct") is not None:
            t_pct = details["Trailing Stop Pct"]
            trail_price = highest_price * (1.0 - t_pct / 100.0)
            extra_rules.append(f"Highest: ${highest_price:.2f}, Trail Stop: ${trail_price:.2f} (-{t_pct}%)")
        if details.get("Stop Loss Pct") is not None:
            s_pct = details["Stop Loss Pct"]
            stop_price = avg_price * (1.0 - s_pct / 100.0)
            extra_rules.append(f"Hard Stop: ${stop_price:.2f} (-{s_pct}%)")
        if details.get("Profit Target Pct") is not None:
            p_pct = details["Profit Target Pct"]
            target_price = avg_price * (1.0 + p_pct / 100.0)
            extra_rules.append(f"Profit Target: ${target_price:.2f} (+{p_pct}%)")
        if extra_rules:
            print(f"  - **Systematic Rules**: {', '.join(extra_rules)}")
            
        print(f"  - **Proposed Action**: [{format_color(proposed_action, color_code, bold=bold)}]")
        if ptrans is not None or ntrans is not None or gex_t1 is not None or cotmp is not None:
            scale_str = generate_ascii_gex_scale(spot, ptrans, ntrans, gex_t1, cotmp)
            print(f"  - **GEX Runway Map**: {scale_str}")
        
        # Accumulate pending exits for stocks
        if "STOP" in exit_rule_state or "PROFIT" in exit_rule_state or "Exit" in proposed_action or "MET" in exit_rule_state:
            pending_exits.append({
                "ticker": ticker,
                "asset_cls": "Stock",
                "desc": f"{shares:,.2f} shares",
                "rule_state": exit_rule_state,
                "proposed_action": proposed_action,
                "current_price": spot,
                "pnl_pct": pl_pct,
                "pnl_dlr": pl_dollar
            })
            
        total_cost_basis += cost_basis
        total_current_value += curr_val
        
    # Aggregate Portfolio Metrics
    unrealized_pl_dlr = total_current_value - total_cost_basis
    unrealized_pl_pct = (unrealized_pl_dlr / total_cost_basis) * 100.0 if total_cost_basis > 0 else 0.0
    options_exposure_pct = (total_current_value / net_liq) * 100.0
    cash_buffer = net_liq - total_current_value
    cash_buffer_pct = (cash_buffer / net_liq) * 100.0
    
    pl_color = get_pnl_color(unrealized_pl_dlr)
    cash_buffer_status = format_color("PASS", "32", bold=True) if cash_buffer_pct >= 20.0 else format_color("WARNING (Low liquid buffer <20%)", "31", bold=True)
    
    # 3. Trailing 30-Day Realized Drawdown Gate
    performance_file = account_performance_file(account) if account else None
    monthly_pnl_dlr, monthly_pnl_pct, drawdown_gate_status, monthly_cnt = get_monthly_realized_pnl(
        net_liq,
        monthly_file=performance_file,
    )
    
    print("\n### 📈 Aggregate Portfolio Summary")
    print(f"- **Total Portfolio Net Liquidation (Net Liq)**: ${net_liq:,.2f}")
    print(f"- **Total Positions Cost Basis**: ${total_cost_basis:,.2f}")
    print(f"- **Total Positions Market Value**: ${total_current_value:,.2f} ({options_exposure_pct:.2f}% allocation)")
    print(f"- **Total Unrealized P&L**: {format_pnl(unrealized_pl_dlr, unrealized_pl_pct, bold=True)}")
    
    # Cumulative portfolio delta exposure
    delta_shares_color = get_pnl_color(total_net_delta_shares)
    delta_exposure_color = get_pnl_color(total_net_delta_exposure_dlr)
    ds_fmt = format_color(f"{total_net_delta_shares:+,.2f} shares" if abs(total_net_delta_shares) >= 0.005 else "0.00 shares", delta_shares_color, bold=True)
    de_fmt = format_pnl(pnl_dlr=total_net_delta_exposure_dlr, bold=True)
    print(f"- **Cumulative Portfolio Net Delta**: {ds_fmt} (Delta-Equivalent directional Exposure: {de_fmt})")
    
    # Beta-Weighted Delta calculations
    regime = get_regime_status()
    spy_price = 550.0
    etf_details = regime.get("etf_details", {})
    if "SPY" in etf_details:
        val = etf_details["SPY"].get("Price", 0.0)
        if val > 0:
            spy_price = val
            
    beta_weighted_delta_shares = total_beta_weighted_delta_exposure_dlr / spy_price if spy_price > 0 else 0.0
    beta_shares_color = get_pnl_color(beta_weighted_delta_shares)
    beta_exposure_color = get_pnl_color(total_beta_weighted_delta_exposure_dlr)
    bds_fmt = format_color(f"{beta_weighted_delta_shares:+,.2f} SPY-equiv shares" if abs(beta_weighted_delta_shares) >= 0.005 else "0.00 SPY-equiv shares", beta_shares_color, bold=True)
    bde_fmt = format_pnl(pnl_dlr=total_beta_weighted_delta_exposure_dlr, bold=True)
    print(f"- **Beta-Weighted directional Delta (SPY)**: {bds_fmt} (Beta-Equivalent directional Exposure: {bde_fmt} at SPY ${spy_price:.2f})")
    
    # Live Brokerage 30-day realized statistics
    m_pnl_color = get_pnl_color(monthly_pnl_dlr)
    gate_color = "32" if drawdown_gate_status == "PASS" else "31"
    gate_fmt = format_color(drawdown_gate_status, gate_color, bold=True)
    print(f"- **Trailing 30-Day Realized P&L**: {format_color(f'${monthly_pnl_dlr:+,.2f}', m_pnl_color, bold=True)} ({format_color(f'{monthly_pnl_pct:+.2f}%', m_pnl_color, bold=True)}) over {monthly_cnt} closed trades")
    print(f"- **Monthly Drawdown Gate**: {gate_fmt} " + (f"({format_color('BREACH ACTIVE: Prohibiting new entries', '31', bold=True)})" if drawdown_gate_status == "FAIL" else "(Drawdown within safe parameters)"))
    print(f"- **Cash Buffer / Liquid Reserves**: ${cash_buffer:,.2f} ({cash_buffer_pct:.2f}% of Net Liq) | Status: {cash_buffer_status}")
    
    closed_file = account_closed_positions_file(getattr(args, "account", ""))
    closed_data = load_json(closed_file, {})
    closed_options = closed_data.get("closed_options", options.get("closed_options", []))
    closed_stocks = closed_data.get("closed_stocks", options.get("closed_stocks", []))
    if closed_options or closed_stocks:
        print("\n### 📊 Realized Performance Stats")
        
        # Options specific stats
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
            
        # Stocks specific stats
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
            
        # Unified combined stats
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
        
    # Sector Allocation Matrix
    sector_sums = {}
    for r in table_rows:
        sec = r.get("sector", "Equity")
        sector_sums[sec] = sector_sums.get(sec, 0.0) + r["cost_basis"]
        
    print("\n### ⚖️ Portfolio Sector Risk Allocation")
    print("  " + "-" * 55)
    print(f"  {'Sector Tag':<28} | {'Cost Basis':<12} | {'Weight %'}")
    print("  " + "-" * 55)
    for sec, sec_cb in sorted(sector_sums.items(), key=lambda x: x[1], reverse=True):
        sec_weight = (sec_cb / net_liq) * 100.0
        sec_weight_fmt = f"{sec_weight:5.2f}%"
        sec_color = "32"
        if ("Technology" in sec or "Beta" in sec) and sec_weight > 15.0:
            sec_color = "31" # Over Tech limit!
        sec_weight_fmt = format_color(sec_weight_fmt, sec_color, bold=(sec_color == "31"))
        print(f"  {sec:<28} | ${sec_cb:<11,.2f} | {sec_weight_fmt}")
    print("  " + "-" * 55)

    print("\n### 📏 Sizing Constraints Checklist")
    # Sizing constraints check
    sizing_threshold = getattr(args, "sizing_threshold", None)
    if sizing_threshold is None:
        sizing_threshold = DEFAULT_SIZING_THRESHOLD
        
    is_micro_account = net_liq < sizing_threshold

    if is_micro_account:
        print(f"- **Single-Leg Sizing Limit (<= 3.0% of Net Liq)**: "
              f"{format_color('EXEMPT', '33', bold=True)} (Net Liq ${net_liq:,.2f} < ${sizing_threshold:,.0f} threshold; 1-contract minimum sizing applies)")
        print(f"- **Sector Sizing Cap (Tech/Beta <= 15.0% of Net Liq)**: "
              f"{format_color('EXEMPT', '33', bold=True)} (Net Liq ${net_liq:,.2f} < ${sizing_threshold:,.0f} threshold; Tech exposure: {tech_exposure:.2f}%)")
    else:
        over_allocated = []
        for opt_id, details in positions.items():
            risk_weight = details.get("Sizing Risk Weight (%)", 0.0)
            tk = details.get("Underlier")
            if risk_weight > 3.0:
                over_allocated.append(f"{tk} ({risk_weight:.2f}% > 3.0%)")
                
        single_leg_ok = len(over_allocated) == 0
        single_leg_fmt = format_color("PASS", "32", bold=True) if single_leg_ok else format_color(f"FAIL ({', '.join(over_allocated)})", "31", bold=True)
        print(f"- **Single-Leg Sizing Limit (<= 3.0% of Net Liq)**: {single_leg_fmt}")
        
        sector_cap_ok = tech_exposure <= 15.0
        sector_cap_fmt = format_color("PASS", "32", bold=True) if sector_cap_ok else format_color("FAIL", "31", bold=True)
        print(f"- **Sector Sizing Cap (Tech/Beta <= 15.0% of Net Liq)**: "
              f"{sector_cap_fmt} (Tech Sizing exposure: {format_color(f'{tech_exposure:.2f}%', '32' if sector_cap_ok else '31')})")
    
    # Sizing warnings for high concentration (exceeding 15% of net liq)
    high_concentration = []
    for opt_id, details in positions.items():
        curr_val = details.get("Current Value")
        if curr_val is None:
            curr_val = float(details.get("Mark Price", 1.0)) * 100.0
        curr_weight = (curr_val / net_liq) * 100.0
        if curr_weight >= 15.0:
            high_concentration.append(f"{details.get('Underlier')} ({curr_weight:.2f}%)")
            
    for ticker, details in stocks.items():
        curr_val = details.get("Current Value")
        if curr_val is None:
            shares = float(details.get("Shares", 0.0))
            spot = float(details.get("Current Price", 0.0))
            if spot <= 0.0:
                spot = float(details.get("Average Buy Price", 0.0))
            curr_val = shares * spot
        curr_weight = (curr_val / net_liq) * 100.0
        if curr_weight >= 15.0:
            high_concentration.append(f"{ticker} ({curr_weight:.2f}%)")
    
    if is_micro_account:
        if high_concentration:
            print(format_color(f"\nℹ️ Micro-Account Allocation Note: {', '.join(high_concentration)} exceed 15% Net Liq due to single-contract sizing on sub-${sizing_threshold:,.0f} portfolio.", "33"))
    else:
        if high_concentration:
            print_color(f"\n⚠️ HIGH CONCENTRATION ALERT: {', '.join(high_concentration)} exceed 15-20% portfolio Net Liquidation threshold.", "31", bold=True)
            print_color("⚠️ RECOMMENDED ACTION: Trim or reduce position exposure to maintain aggregate capital health.", "31", bold=False)
            
        if not sector_cap_ok:
            print_color(f"\n⚠️ SECTOR EXPOSURE ALERT: High-beta tech/beta exposure exceeds 15.0% ({tech_exposure:.2f}%).", "33", bold=True)
    # Collect unique active underliers and scan for technical alerts
    unique_tickers = sorted(list(set(
        [details.get("Underlier", "") for details in positions.values() if details.get("Underlier")] +
        [ticker for ticker in stocks.keys() if ticker]
    )))
    
    technical_alerts = []
    download_files = _get_downloads_files(ge.DOWNLOADS_DIR) if os.path.exists(ge.DOWNLOADS_DIR) else []
    for tkr in unique_tickers:
        closes, highs, lows, opens = find_latest_historical_ohlc(tkr, file_list=download_files)
        if closes:
            res = check_technical_alerts(closes, highs, lows)
            if res.get("alerts"):
                for alert in res["alerts"]:
                    alert_desc = alert.replace("_", " ")
                    color = "33"
                    if "OVERSOLD" in alert or "BULLISH" in alert or "LOWER_TOUCH" in alert:
                        color = "32"
                    elif "OVERBOUGHT" in alert or "BEARISH" in alert or "UPPER_TOUCH" in alert:
                        color = "31"
                    
                    val_str = ""
                    if "RSI" in alert: val_str = f" (RSI: {res['rsi']:.1f})"
                    elif "MACD" in alert: val_str = f" (Hist: {res['macd_hist']:+.4f})"
                    elif "BB" in alert: val_str = f" (Spot: ${closes[-1]:.2f})"
                    
                    technical_alerts.append(f"  - {format_color(tkr, '35', bold=True)}: {format_color(alert_desc + val_str, color, bold=True)}")
                    
    print("\n### 📈 Active Positions Technical Alerts")
    if technical_alerts:
        for ta in technical_alerts:
            print(ta)
    else:
        print("  No active technical alerts.")

    # Save the updated indicators
    options["options_positions"] = positions
    options["stocks_positions"] = stocks
    save_json(options_file, options)
    
    # Render Execution Approval Requests for systematic exits
    if pending_exits:
        print_color("\n" + "=" * 95, "31", bold=True)
        print_color("🔔                        EXECUTION APPROVAL REQUEST (PENDING EXITS)", "31", bold=True)
        print_color("=" * 95, "31", bold=True)
        print_color("[ACTION REQUIRED] Confirm systematic GEX order routing for the following exits:", "37", bold=True)
        for idx, item in enumerate(pending_exits, 1):
            pnl_formatted = format_pnl(pnl_dlr=item["pnl_dlr"], pnl_pct=item["pnl_pct"], bold=True)
            print(f"\n  {idx:d}. {format_color(item['ticker'], '35', bold=True)} ({item['asset_cls']}: {item['desc']})")
            print(f"     -> TRIGGER: {format_color(item['rule_state'], '31', bold=True)}")
            print(f"     -> ACTION: {format_color(item['proposed_action'], '33', bold=True)}")
            print(f"     -> CURRENT MARK / PRICE: ${item['current_price']:.2f} (Unrealized P&L: {pnl_formatted})")
            
        print_color("\n  -> INSTRUCTIONS: To authorize, respond with 'YES' in chat to execute via agentic-trader.", "37")
        print_color("=" * 95 + "\n", "31", bold=True)


def cmd_add_pos(args):
    """Add new options position manually."""
    options_file = account_positions_file(getattr(args, "account", ""))
    options = load_json(options_file, {"options_positions": {}})
    positions = options.get("options_positions", {})
    
    if args.option_id in positions:
        print(f"Error: Option ID {args.option_id} already exists in portfolio. Use update-option to modify it.", file=sys.stderr)
        sys.exit(1)
        
    try:
        datetime.strptime(args.expiration, "%Y-%m-%d")
    except ValueError:
        print(f"Error: Expiration '{args.expiration}' must be a valid date in YYYY-MM-DD format.", file=sys.stderr)
        sys.exit(1)

    try:
        opt_pos = OptionPosition(
            option_id=args.option_id,
            underlier=args.underlier,
            strike=args.strike,
            expiration=args.expiration,
            type=args.type,
            purchase_premium=args.purchase_premium,
            mark_price=args.purchase_premium,
            days_held=1,
            stalling_days=0,
            delta=args.delta,
            gamma=args.gamma,
            open_interest=args.open_interest,
            imp_vol=args.imp_vol,
            beta_sector_tag=args.sector
        )
        opt_pos.validate()
    except ValueError as e:
        print(f"Error validating option position parameters: {e}", file=sys.stderr)
        sys.exit(1)
    
    positions[args.option_id] = {
        "Option ID": args.option_id,
        "Underlier": args.underlier.upper(),
        "Strike": f"{args.strike:.2f}",
        "Expiration": args.expiration,
        "Type": args.type.lower(),
        "Purchase Premium": args.purchase_premium,
        "Delta": str(args.delta),
        "Gamma": str(args.gamma),
        "Mark Price": args.purchase_premium,
        "Open Interest": args.open_interest,
        "ImpVol": str(args.imp_vol),
        "Asset Cost Basis": args.purchase_premium * 100,
        "Current Value": args.purchase_premium * 100,
        "P&L (%)": 0.0,
        "P&L ($)": 0.0,
        "Sizing Risk Weight (%)": 0.0,
        "Beta Sector Tag": args.sector,
        "Entry Date": datetime.today().strftime('%Y-%m-%d'),
        "Stalling Days": 0,
        "Target Mode": "T1",
        "T2 Target": None
    }
    
    options["options_positions"] = positions
    save_json(options_file, options)
    print(f"Successfully added options position for {args.underlier.upper()} in {options_file}.")


def cmd_add_stock_pos(args):
    """Add new stock position manually."""
    options_file = account_positions_file(getattr(args, "account", ""))
    options = load_json(options_file, {"options_positions": {}, "stocks_positions": {}})
    stocks = options.setdefault("stocks_positions", {})
    ticker = args.ticker.upper()
    
    if ticker in stocks:
        print(f"Error: Stock Ticker {ticker} already exists in portfolio. Use update-stock to modify it.", file=sys.stderr)
        sys.exit(1)

    try:
        stock_pos = StockPosition(
            ticker=ticker,
            shares=args.shares,
            average_buy_price=args.average_buy_price,
            current_price=args.average_buy_price,
            beta_sector_tag=args.sector,
            trailing_stop_pct=getattr(args, "trail_pct", None),
            stop_loss_pct=getattr(args, "stop_pct", None),
            profit_target_pct=getattr(args, "target_pct", None)
        )
        stock_pos.validate()
    except ValueError as e:
        print(f"Error validating stock position parameters: {e}", file=sys.stderr)
        sys.exit(1)
        
    stocks[ticker] = {
        "Ticker": ticker,
        "Shares": args.shares,
        "Average Buy Price": args.average_buy_price,
        "Current Price": args.average_buy_price,
        "Highest Price": args.average_buy_price,
        "Trailing Stop Pct": getattr(args, "trail_pct", None),
        "Stop Loss Pct": getattr(args, "stop_pct", None),
        "Profit Target Pct": getattr(args, "target_pct", None),
        "Beta Sector Tag": args.sector,
        "Entry Date": datetime.today().strftime('%Y-%m-%d'),
        "Asset Cost Basis": args.shares * args.average_buy_price,
        "Current Value": args.shares * args.average_buy_price,
        "P&L (%)": 0.0,
        "P&L ($)": 0.0,
        "Sizing Risk Weight (%)": 0.0
    }
    
    options["stocks_positions"] = stocks
    save_json(options_file, options)
    print(f"Successfully added stock position for {ticker} in {options_file}.")


def cmd_update_stock_pos(args):
    """Update stock position shares or price."""
    options_file = account_positions_file(getattr(args, "account", ""))
    options = load_json(options_file, {"options_positions": {}, "stocks_positions": {}})
    stocks = options.get("stocks_positions", {})
    ticker = args.ticker.upper()
    
    if ticker not in stocks:
        print(f"Error: Stock position for {ticker} not found in portfolio.", file=sys.stderr)
        sys.exit(1)
        
    target_stock = stocks[ticker]
    if args.price is not None:
        target_stock["Current Price"] = args.price
        # Update Highest Price automatically when price increases
        highest_price = target_stock.get("Highest Price")
        if highest_price is None:
            highest_price = target_stock.get("Average Buy Price", args.price)
        target_stock["Highest Price"] = max(highest_price, args.price)
        
    if args.shares is not None:
        target_stock["Shares"] = args.shares
        target_stock["Asset Cost Basis"] = args.shares * target_stock.get("Average Buy Price", 0.0)
    if args.sector is not None:
        target_stock["Beta Sector Tag"] = args.sector
    if getattr(args, "trail_pct", None) is not None:
        target_stock["Trailing Stop Pct"] = args.trail_pct
    if getattr(args, "stop_pct", None) is not None:
        target_stock["Stop Loss Pct"] = args.stop_pct
    if getattr(args, "target_pct", None) is not None:
        target_stock["Profit Target Pct"] = args.target_pct
    if getattr(args, "highest_price", None) is not None:
        target_stock["Highest Price"] = args.highest_price

    # Validate updated stock position parameters
    try:
        stock_pos = StockPosition(
            ticker=ticker,
            shares=float(target_stock.get("Shares", 1.0)),
            average_buy_price=float(target_stock.get("Average Buy Price", 1.0)),
            current_price=float(target_stock.get("Current Price", 0.0)),
            beta_sector_tag=target_stock.get("Beta Sector Tag", "Equity"),
            entry_date=target_stock.get("Entry Date"),
            highest_price=float(target_stock["Highest Price"]) if target_stock.get("Highest Price") is not None else None,
            trailing_stop_pct=float(target_stock["Trailing Stop Pct"]) if target_stock.get("Trailing Stop Pct") is not None else None,
            stop_loss_pct=float(target_stock["Stop Loss Pct"]) if target_stock.get("Stop Loss Pct") is not None else None,
            profit_target_pct=float(target_stock["Profit Target Pct"]) if target_stock.get("Profit Target Pct") is not None else None,
        )
        stock_pos.validate()
    except ValueError as e:
        print(f"Error validating stock position parameters: {e}", file=sys.stderr)
        sys.exit(1)
        
    # Save the updated stocks dict back using stocks_positions
    options["stocks_positions"] = stocks
    save_json(options_file, options)
    print(f"Successfully updated metrics for stock {ticker} in {options_file}.")


def cmd_close_stock_pos(args):
    """Close a stock position and archive standard P&L."""
    options_file = account_positions_file(getattr(args, "account", ""))
    options = load_json(options_file, {"options_positions": {}, "stocks_positions": {}})
    stocks = options.get("stocks_positions", {})
    ticker = args.ticker.upper()
    
    if ticker not in stocks:
        print(f"Error: Stock position for {ticker} not found in portfolio.", file=sys.stderr)
        sys.exit(1)
        
    closed_file = account_closed_positions_file(getattr(args, "account", ""))
    closed_data = load_json(closed_file, {"closed_options": [], "closed_stocks": []})
    closed = closed_data.setdefault("closed_stocks", [])
    
    # Extract any existing legacy closed_stocks from active_positions.json and merge
    if "closed_stocks" in options:
        legacy_closed = options.pop("closed_stocks", [])
        for item in legacy_closed:
            if item not in closed:
                closed.append(item)
                
    details = stocks.pop(ticker)
    
    shares = float(details.get("Shares", 0.0))
    avg_price = float(details.get("Average Buy Price", 0.0))
    close_price = args.close_price if args.close_price is not None else float(details.get("Current Price", avg_price))
    
    cost_basis = shares * avg_price
    current_val = shares * close_price
    realized_dollar = current_val - cost_basis
    realized_pct = (realized_dollar / cost_basis) * 100.0 if cost_basis > 0 else 0.0
    
    details["Close Price"] = close_price
    details["Close Date"] = datetime.today().strftime('%Y-%m-%d')
    details["Realized P&L ($)"] = round(realized_dollar, 2)
    details["Realized P&L (%)"] = round(realized_pct, 2)
    details["Close Reason"] = getattr(args, "reason", None) or DEFAULT_EXIT_REASON
    closed.append(details)
    
    pnl_str = format_pnl(realized_dollar, realized_pct, bold=True)
    print(f"Closed stock position for {ticker} [{details['Close Reason']}]: Realized P&L {pnl_str}")
          
    options["stocks_positions"] = stocks
    save_json(options_file, options)
    save_json(closed_file, closed_data)
    try:
        synced = sync_closed_positions_to_db(closed_data, account=getattr(args, "account", ""))
        if synced:
            print(f"Synchronized {synced} closed trade(s) to SQLite database.")
    except Exception as e:
        print(f"Notice: SQLite trade sync skipped: {e}", file=sys.stderr)
    print(f"Archived stock position for {ticker} to closed_stocks in {closed_file}.")


def cmd_update_opt(args):
    """Update options evaluation price/mark and momentum tracking."""
    options_file = account_positions_file(getattr(args, "account", ""))
    options = load_json(options_file, {"options_positions": {}})
    positions = options.get("options_positions", {})
    
    target_pos = None
    for opt_id, details in positions.items():
        if opt_id == args.option_id or details.get("Underlier") == args.option_id.upper():
            target_pos = details
            break
            
    if not target_pos:
        print(f"Error: Option position with ID or Ticker {args.option_id} not found in portfolio.", file=sys.stderr)
        sys.exit(1)
        
    if args.mark is not None:
        target_pos["Mark Price"] = args.mark
    if args.delta is not None:
        target_pos["Delta"] = str(args.delta)
    if args.gamma is not None:
        target_pos["Gamma"] = str(args.gamma)
    if args.oi is not None:
        target_pos["Open Interest"] = args.oi
    if args.iv is not None:
        target_pos["ImpVol"] = str(args.iv)
    if args.stalling_days is not None:
        target_pos["Stalling Days"] = args.stalling_days
    if getattr(args, "target_mode", None) is not None:
        target_pos["Target Mode"] = args.target_mode
    if getattr(args, "t2_target", None) is not None:
        target_pos["T2 Target"] = args.t2_target

    # Validate updated option position parameters
    try:
        opt_pos = OptionPosition(
            option_id=target_pos.get("Option ID", args.option_id),
            underlier=target_pos.get("Underlier", "UNKNOWN"),
            strike=float(target_pos.get("Strike", 1.0)),
            expiration=target_pos.get("Expiration", "1970-01-01"),
            type=target_pos.get("Type", "call"),
            purchase_premium=float(target_pos.get("Purchase Premium", 1.0)),
            mark_price=float(target_pos.get("Mark Price", 0.0)),
            days_held=int(target_pos.get("Days Held", 1)),
            stalling_days=int(target_pos.get("Stalling Days", 0)),
            target_mode=target_pos.get("Target Mode", "T1"),
            t2_target=float(target_pos["T2 Target"]) if target_pos.get("T2 Target") is not None else None,
            beta_sector_tag=target_pos.get("Beta Sector Tag", "Technology/Beta"),
            entry_date=target_pos.get("Entry Date")
        )
        opt_pos.validate()
    except ValueError as e:
        print(f"Error validating option position parameters: {e}", file=sys.stderr)
        sys.exit(1)
        
    save_json(options_file, options)
    print(f"Successfully updated metrics for option {args.option_id} in {options_file}.")


def cmd_close_pos(args):
    """Close a tracked options position and archive its realized P&L."""
    options_file = account_positions_file(getattr(args, "account", ""))
    options = load_json(options_file, {"options_positions": {}})
    positions = options.get("options_positions", {})
    
    matches = [
        opt_id for opt_id, details in positions.items()
        if opt_id == args.option_id or details.get("Underlier") == args.option_id.upper()
    ]
    if not matches:
        print(f"Error: Option position with ID or Ticker {args.option_id} not found in portfolio.", file=sys.stderr)
        sys.exit(1)
        
    closed_file = account_closed_positions_file(getattr(args, "account", ""))
    closed_data = load_json(closed_file, {"closed_options": [], "closed_stocks": []})
    closed = closed_data.setdefault("closed_options", [])
    
    # Extract any existing legacy closed_options from active_positions.json and merge
    if "closed_options" in options:
        legacy_closed = options.pop("closed_options", [])
        for item in legacy_closed:
            if item not in closed:
                closed.append(item)
                
    for opt_id in matches:
        details = positions.pop(opt_id)
        purchase_premium = float(details.get("Purchase Premium", 0.0))
        close_premium = args.close_premium if args.close_premium is not None else float(details.get("Mark Price", purchase_premium))
        realized_dollar = round((close_premium - purchase_premium) * 100, 2)
        realized_pct = round(((close_premium - purchase_premium) / purchase_premium) * 100, 2) if purchase_premium else 0.0
        
        details["Close Premium"] = close_premium
        details["Close Date"] = datetime.today().strftime('%Y-%m-%d')
        details["Realized P&L ($)"] = realized_dollar
        details["Realized P&L (%)"] = realized_pct
        details["Close Reason"] = getattr(args, "reason", None) or DEFAULT_EXIT_REASON
        closed.append(details)
        
        pnl_str = format_pnl(realized_dollar, realized_pct, bold=True)
        print(f"Closed {details.get('Underlier')} {details.get('Strike')} {details.get('Type')} ({opt_id}) [{details['Close Reason']}]: Realized P&L {pnl_str}")
        
    options["options_positions"] = positions
    save_json(options_file, options)
    save_json(closed_file, closed_data)
    try:
        synced = sync_closed_positions_to_db(closed_data, account=getattr(args, "account", ""))
        if synced:
            print(f"Synchronized {synced} closed trade(s) to SQLite database.")
    except Exception as e:
        print(f"Notice: SQLite trade sync skipped: {e}", file=sys.stderr)
    print(f"Archived {len(matches)} position(s) to closed_options in {closed_file}.")


def cmd_sync_positions(args):
    """Syncs active options and equity positions from raw Robinhood downloads to active_positions.json."""
    base_dir = args.base_dir
    raw_account = getattr(args, "account", "")
    account = sanitize_account(raw_account) if raw_account else ""
    options_file = account_positions_file(account)
    if base_dir:
        try:
            base_dir = validate_safe_path(base_dir)
        except ValueError as e:
            print(f"Error: Invalid base_dir: {e}", file=sys.stderr)
            sys.exit(1)
    if not base_dir or not os.path.exists(base_dir):
        # Scan ge.DOWNLOADS_DIR for latest directory with positions
        candidates = []
        if os.path.exists(ge.DOWNLOADS_DIR):
            try:
                entries = list(os.scandir(ge.DOWNLOADS_DIR))
            except OSError:
                entries = []

            def is_matching_pos_file(filename: str) -> bool:
                if not filename.endswith(".json"):
                    return False
                if account:
                    return filename.startswith(f"option_positions_{account}") or filename.startswith(f"equity_positions_{account}")
                return filename.startswith("option_positions") or filename.startswith("equity_positions")

            matching_root_files = [
                e.path for e in entries
                if e.is_file() and is_matching_pos_file(e.name)
            ]
            if matching_root_files:
                candidates.append((max(os.path.getmtime(p) for p in matching_root_files), ge.DOWNLOADS_DIR))

            for e in entries:
                if e.is_dir() and e.name != "downloads":
                    try:
                        sub_entries = list(os.scandir(e.path))
                    except OSError:
                        continue
                    matching_files = [
                        se.path for se in sub_entries
                        if se.is_file() and is_matching_pos_file(se.name)
                    ]
                    if matching_files:
                        candidates.append((max(os.path.getmtime(p) for p in matching_files), e.path))
        if candidates:
            # Folder names can lag the broker snapshot date, so select by file mtime.
            base_dir = max(candidates, key=lambda candidate: (candidate[0], candidate[1]))[1]
        else:
            print(f"Error: No positions files found for account '{account or 'any'}' in data/downloads/.", file=sys.stderr)
            sys.exit(1)

    print(f"Syncing active positions from: {base_dir}")
    
    # 1. Build Instrument Map for Options (Global scan with chronological precedence, favoring base_dir)
    inst_map = {}
    quote_map = {}
    print("Building global instrument/quote map from downloads...")
    if os.path.exists(ge.DOWNLOADS_DIR):
        # Sort folders chronologically so later dates overwrite earlier dates
        subdirs = sorted([d for d in os.listdir(ge.DOWNLOADS_DIR) if os.path.isdir(os.path.join(ge.DOWNLOADS_DIR, d))])
        all_dirs = [ge.DOWNLOADS_DIR] + [os.path.join(ge.DOWNLOADS_DIR, d) for d in subdirs]
        # Ensure base_dir has highest precedence by visiting it last
        if base_dir and base_dir in all_dirs:
            all_dirs.remove(base_dir)
            all_dirs.append(base_dir)
        elif base_dir:
            all_dirs.append(base_dir)

        for d_path in all_dirs:
            if not os.path.exists(d_path):
                continue
            for file in sorted(os.listdir(d_path)):
                if not file.endswith(".json"):
                    continue
                is_inst = "option_instruments" in file
                is_quote = "option_quotes" in file
                if not (is_inst or is_quote):
                    continue
                file_path = os.path.join(d_path, file)
                if not os.path.isfile(file_path):
                    continue

                if is_inst:
                    data = load_json(file_path, {})
                    instruments = (
                        data.get("data", {}).get("instruments", []) or
                        data.get("instruments", []) or
                        (data if isinstance(data, list) else [])
                    )
                    for inst in instruments:
                        if isinstance(inst, dict) and "id" in inst:
                            inst_map[inst["id"]] = {
                                "strike": float(inst.get("strike_price") or inst.get("strike") or 0.0),
                                "type": inst.get("type"),
                                "expiration": inst.get("expiration_date")
                            }
                elif is_quote:
                    data = load_json(file_path, {})
                    quotes = (
                        data.get("data", {}).get("results", []) or
                        data.get("results", []) or
                        data.get("option_quotes", []) or
                        data.get("data", []) or
                        (data if isinstance(data, list) else [])
                    )
                    for q_item in quotes:
                        q = q_item.get("quote", q_item) if isinstance(q_item, dict) else {}
                        opt_id = q.get("instrument_id") or q.get("id") or q.get("instrument")
                        if opt_id:
                            quote_map[opt_id] = q

    # 2. Load Existing Active Positions
    options = load_json(options_file, {"options_positions": {}, "stocks_positions": {}})
    active_opts = options.get("options_positions", {})
    active_stocks = options.get("stocks_positions", {})

    # 3. Sync Equities
    if account:
        equity_files = [f for f in os.listdir(base_dir) if f.startswith(f"equity_positions_{account}") and f.endswith(".json")]
    else:
        equity_files = [f for f in os.listdir(base_dir) if f.startswith("equity_positions") and f.endswith(".json")]
    
    if not equity_files:
        simple_name = f"equity_positions_{account}.json" if account else "equity_positions.json"
        if os.path.exists(os.path.join(base_dir, simple_name)):
            equity_files = [simple_name]
    
    new_stocks = 0
    updated_stocks = 0
    removed_stocks = 0
    seen_stock_tickers = set()
    
    for ef in equity_files:
        equity_path = os.path.join(base_dir, ef)
        equity_data = load_json(equity_path, {})
        
        if isinstance(equity_data, list):
            raw_stocks = equity_data
        else:
            raw_stocks = equity_data.get("data", {}).get("positions", []) or \
                         equity_data.get("positions", []) or \
                         equity_data.get("results", []) or []
        
        # Track which stocks are present in the raw data
        for rs in raw_stocks:
            ticker = rs.get("symbol", "").upper()
            if not ticker: continue
            seen_stock_tickers.add(ticker)
            
            shares = float(rs.get("quantity", 0.0))
            avg_price = float(rs.get("average_buy_price", 0.0))
            
            if shares <= 0:
                if ticker in active_stocks:
                    active_stocks.pop(ticker)
                    removed_stocks += 1
                continue
                
            if ticker in active_stocks:
                active_stocks[ticker]["Shares"] = shares
                active_stocks[ticker]["Average Buy Price"] = avg_price
                active_stocks[ticker]["Asset Cost Basis"] = shares * avg_price
                if account:
                    active_stocks[ticker]["Account"] = account
                updated_stocks += 1
            else:
                active_stocks[ticker] = {
                    "Ticker": ticker,
                    "Shares": shares,
                    "Average Buy Price": avg_price,
                    "Current Price": avg_price,
                    "Highest Price": avg_price,
                    "Beta Sector Tag": "Equity",
                    "Entry Date": datetime.today().strftime('%Y-%m-%d'),
                    "Asset Cost Basis": shares * avg_price,
                    "Current Value": shares * avg_price,
                    "P&L (%)": 0.0,
                    "P&L ($)": 0.0,
                    "Sizing Risk Weight (%)": 0.0
                }
                if account:
                    active_stocks[ticker]["Account"] = account
                new_stocks += 1

    # A closed equity position may disappear from the broker payload entirely,
    # so reconcile cached records against the complete snapshot, not only rows
    # with an explicit zero quantity.
    for ticker, details in list(active_stocks.items()):
        belongs_to_account = not account or details.get("Account") in (None, "", account)
        if belongs_to_account and ticker not in seen_stock_tickers:
            active_stocks.pop(ticker)
            removed_stocks += 1
        
    # 4. Sync Options
    if account:
        opt_files = [f for f in os.listdir(base_dir) if f.startswith(f"option_positions_{account}") and f.endswith(".json")]
    else:
        opt_files = [f for f in os.listdir(base_dir) if f.startswith("option_positions") and f.endswith(".json")]
        
    if not opt_files:
        simple_name = f"option_positions_{account}.json" if account else "option_positions.json"
        if os.path.exists(os.path.join(base_dir, simple_name)):
            opt_files = [simple_name]
    
    new_opts = 0
    updated_opts = 0
    removed_opts = 0
    seen_option_ids = set()
    for of in opt_files:
        opt_path = os.path.join(base_dir, of)
        opt_data = load_json(opt_path, {})
        
        if isinstance(opt_data, list):
            raw_opts = opt_data
        else:
            raw_opts = opt_data.get("data", {}).get("positions", []) or \
                       opt_data.get("positions", []) or \
                       opt_data.get("results", []) or []
            
        for ro in raw_opts:
            opt_id = ro.get("option_id")
            if not opt_id:
                continue
            seen_option_ids.add(opt_id)
                
            underlier = ro.get("chain_symbol", "").upper()
            qty = float(ro.get("quantity", 0.0))
            avg_price = float(ro.get("average_price", 0.0)) / 100.0
            ro_expiration = ro.get("expiration_date")
            ro_type = ro.get("type")
            
            if qty <= 0:
                if opt_id in active_opts:
                    active_opts.pop(opt_id)
                    removed_opts += 1
                continue
            
            inst = inst_map.get(opt_id, {})
            quote = quote_map.get(opt_id, {})
            
            strike = inst.get("strike")
            opt_type = inst.get("type") or ro_type
            expiration = inst.get("expiration") or ro_expiration
            
            mark = float(quote.get("mark_price") or quote.get("adjusted_mark_price") or avg_price)
            delta = float(quote.get("delta") or 0.0) if quote.get("delta") is not None else 0.0
            gamma = float(quote.get("gamma") or 0.0) if quote.get("gamma") is not None else 0.0
            oi = int(quote.get("open_interest") or 0) if quote.get("open_interest") is not None else 0
            iv = float(quote.get("implied_volatility") or 0.0) if quote.get("implied_volatility") is not None else 0.0

            pl_dollar = round((mark - avg_price) * 100.0 * qty, 2)
            pl_pct = round(((mark - avg_price) / avg_price) * 100.0, 2) if avg_price > 0 else 0.0

            if opt_id in active_opts:
                if strike:
                    active_opts[opt_id]["Strike"] = f"{strike:.2f}"
                if expiration:
                    active_opts[opt_id]["Expiration"] = expiration
                
                active_opts[opt_id]["Purchase Premium"] = avg_price
                active_opts[opt_id]["Mark Price"] = mark
                active_opts[opt_id]["Delta"] = str(delta)
                active_opts[opt_id]["Gamma"] = str(gamma)
                active_opts[opt_id]["Open Interest"] = oi
                active_opts[opt_id]["ImpVol"] = str(iv)
                active_opts[opt_id]["Asset Cost Basis"] = avg_price * 100.0 * qty
                active_opts[opt_id]["Current Value"] = mark * 100.0 * qty
                active_opts[opt_id]["P&L ($)"] = pl_dollar
                active_opts[opt_id]["P&L (%)"] = pl_pct
                if account:
                    active_opts[opt_id]["Account"] = account
                updated_opts += 1
            else:
                active_opts[opt_id] = {
                    "Option ID": opt_id,
                    "Underlier": underlier,
                    "Strike": f"{strike:.2f}" if strike else "0.00",
                    "Expiration": expiration or "1970-01-01",
                    "Type": opt_type or "call",
                    "Purchase Premium": avg_price,
                    "Delta": str(delta),
                    "Gamma": str(gamma),
                    "Mark Price": mark,
                    "Open Interest": oi,
                    "ImpVol": str(iv),
                    "Asset Cost Basis": avg_price * 100.0 * qty,
                    "Current Value": mark * 100.0 * qty,
                    "P&L (%)": pl_pct,
                    "P&L ($)": pl_dollar,
                    "Sizing Risk Weight (%)": 0.0,
                    "Beta Sector Tag": "Technology/Beta",
                    "Entry Date": datetime.today().strftime('%Y-%m-%d'),
                    "Stalling Days": 0,
                    "Target Mode": "T1",
                    "T2 Target": None
                }
                if account:
                    active_opts[opt_id]["Account"] = account
                new_opts += 1

    # Broker snapshots omit closed options instead of returning a zero-quantity
    # row, so remove cached options absent from the selected account snapshot.
    for opt_id, details in list(active_opts.items()):
        belongs_to_account = not account or details.get("Account") in (None, "", account)
        if belongs_to_account and opt_id not in seen_option_ids:
            active_opts.pop(opt_id)
            removed_opts += 1

    options["options_positions"] = active_opts
    options["stocks_positions"] = active_stocks
    save_json(options_file, options)
    
    print(f"Sync complete. Equities: {new_stocks} new, {updated_stocks} updated, {removed_stocks} removed.")
    print(f"Options: {new_opts} new, {updated_opts} updated, {removed_opts} removed.")
    print(f"Active positions updated in {options_file}.")


def cmd_evaluate_rolls(args):
    """Evaluates active options positions for systematic dynamic delta rolling and profit ratchets."""
    account = getattr(args, "account", "")
    threshold_delta = getattr(args, "threshold_delta", 0.70)
    if threshold_delta is None:
        threshold_delta = 0.70
    threshold_gain = getattr(args, "threshold_gain", 50.0)
    if threshold_gain is None:
        threshold_gain = 50.0
    as_json = getattr(args, "json", False)

    options_file = account_positions_file(account)
    options_data = load_json(options_file, {"options_positions": {}})
    active_opts = options_data.get("options_positions", {})

    spots: Dict[str, float] = {}
    analyses = load_json(ge.ANALYSES_FILE, {})
    for opt_id, details in active_opts.items():
        underlier = (details.get("Underlier") or details.get("underlier") or "").upper()
        if underlier and underlier not in spots:
            spot_found = find_latest_underlier_spot(underlier)
            if spot_found is None and underlier in analyses:
                spot_found = analyses[underlier].get("spot")
            if spot_found is None:
                spot_found = float(details.get("Underlier Spot") or details.get("Strike") or 100.0)
            spots[underlier] = float(spot_found)

    roll_summary = evaluate_portfolio_rolls(
        active_options=active_opts,
        spots=spots,
        threshold_delta=threshold_delta,
        threshold_gain=threshold_gain,
    )

    if as_json:
        clean_summary = {k: v for k, v in roll_summary.items() if k != "recommendation_objects"}
        print(json.dumps(clean_summary, indent=2, sort_keys=True))
        return

    masked_acc = mask_account(account) if account else "DEFAULT / ALL"
    print(f"\n### 🔄 Dynamic Delta Rolling & Profit Ratchet Audit ({masked_acc})")
    print(f"  - Sizing & Convexity Rules: Roll at Delta >= {threshold_delta:.2f} or ROI >= +{threshold_gain:.1f}%")
    print(f"  - Target Re-Centering: Delta 0.40 - 0.50 | 30 - 45 DTE | Net Cash Credit Extraction\n")

    recs = roll_summary.get("recommendation_objects", [])
    headers = [
        "Status", "Contract", "Spot", "Delta", "DTE", "P&L (%)",
        "Target Roll", "Target Mark", "Net Credit", "Extracted ($)", "Ratchet Floor"
    ]
    rows = []
    for r in recs:
        if r.eligible:
            status_str = format_color("ROLL NOW", "32", bold=True)
        elif r.ratchet_stop_floor_pct is not None:
            status_str = format_color("RATCHET", "33", bold=True)
        else:
            status_str = format_color("HOLD", "37")

        delta_str = f"{r.delta:.2f}" if r.delta is not None else "N/A"
        if r.delta is not None and abs(r.delta) >= threshold_delta:
            delta_str = format_color(delta_str, "31", bold=True)

        pnl_pct_str = format_pnl(r.unrealized_pnl_dollar, r.unrealized_pnl_pct)

        target_str = f"${r.target_strike:.2f} ({r.target_dte}d)" if r.target_strike else "N/A"
        target_mark_str = f"${r.target_mark:.2f}" if r.target_mark else "N/A"

        credit_str = f"+${r.estimated_net_credit:.2f}" if r.estimated_net_credit and r.estimated_net_credit > 0 else f"${r.estimated_net_credit:.2f}" if r.estimated_net_credit else "N/A"
        if r.estimated_net_credit and r.estimated_net_credit > 0:
            credit_str = format_color(credit_str, "32", bold=True)

        extracted_str = f"+${r.capital_extracted:,.2f}" if r.capital_extracted and r.capital_extracted > 0 else f"${r.capital_extracted:,.2f}" if r.capital_extracted else "$0.00"
        if r.capital_extracted and r.capital_extracted > 0:
            extracted_str = format_color(extracted_str, "32", bold=True)

        ratchet_str = f"{r.ratchet_stop_floor_pct:+.1f}% min" if r.ratchet_stop_floor_pct is not None else "-"
        if r.ratchet_stop_floor_pct is not None:
            ratchet_str = format_color(ratchet_str, "36", bold=True)

        spot_val = spots.get(r.underlier, r.strike)

        rows.append([
            status_str,
            f"{r.underlier} ${r.strike:.1f}C",
            f"${spot_val:.2f}",
            delta_str,
            f"{r.dte}d",
            pnl_pct_str,
            target_str,
            target_mark_str,
            credit_str,
            extracted_str,
            ratchet_str,
        ])

    alignments = ["left", "left", "right", "right", "right", "right", "left", "right", "right", "right", "right"]
    print(format_table(headers, rows, empty_message="No active options positions found in account portfolio.", alignments=alignments))
    print()

    tot = roll_summary["total_positions"]
    elig = roll_summary["eligible_roll_count"]
    cap = roll_summary["total_extractable_capital"]

    print(f"  Summary: {tot} Position(s) Evaluated | {elig} Eligible Roll Candidate(s)")
    if elig > 0:
        cap_fmt = format_color(f"+${cap:,.2f}", "32", bold=True)
        print(f"  💰 Total Extractable Cash Capital: {cap_fmt}")
        print("\n  Detailed Roll Triggers:")
        for r in recs:
            if r.eligible:
                print(f"  -> {format_color(r.contract_desc, '36', bold=True)}:")
                for t in r.triggers:
                    print(f"     * {t}")
                print(f"     * Roll Action: Close current at ${r.mark_price:.2f}, Open target ${r.target_strike:.2f} ({r.target_dte} DTE, Delta {r.target_delta:.2f}) at ${r.target_mark:.2f}")
                print(f"     * Capital Extraction: +${r.capital_extracted:,.2f} cash credit, Risk Reduction: {r.capital_at_risk_reduction_pct:.1f}%")
                if r.ratchet_stop_floor_pct is not None:
                    print(f"     * Profit Ratchet: Minimum gain stop floor locked at {r.ratchet_stop_floor_pct:+.1f}%")
    else:
        print("  All active positions maintain optimal delta (<0.70) and positive runway convexity.")
    print()


def cmd_hedge_plan(args):
    """Derives an automated portfolio beta-weighted macro hedge plan."""
    account = getattr(args, "account", "")
    target_coverage = getattr(args, "target_coverage", None)
    instrument_choice = getattr(args, "instrument", "AUTO") or "AUTO"
    as_json = getattr(args, "json", False)

    options_file = account_positions_file(account)
    options_data = load_json(options_file, {"options_positions": {}, "stocks_positions": {}})
    positions = options_data.get("options_positions", {})
    stocks = options_data.get("stocks_positions", {})

    if account:
        positions = {
            pid: det for pid, det in positions.items()
            if not det.get("Account") or det.get("Account") == account
        }
        stocks = {
            tick: det for tick, det in stocks.items()
            if not det.get("Account") or det.get("Account") == account
        }

    # Net liq resolution
    net_liq = getattr(args, "net_liq", None)
    if net_liq is None:
        perf = get_performance_status(account)
        cached_net_liq = perf.get("net_liq")
        if cached_net_liq and float(cached_net_liq) > 0:
            net_liq = float(cached_net_liq)
        elif account and "9961" in account:
            net_liq = 8500.0  # micro-account default
        else:
            net_liq = 50000.0  # standard default

    cash_buying_power = getattr(args, "cash_buying_power", None)
    if cash_buying_power is None:
        cash_buying_power = net_liq * 0.40  # estimate available cash

    # Retrieve regime and reference ETF prices
    regime = get_regime_status()
    etf_details = regime.get("etf_details", {})
    spy_price = 550.0
    if "SPY" in etf_details:
        val = etf_details["SPY"].get("Price", 0.0)
        if val > 0:
            spy_price = val
    if spy_price == 550.0:
        spot_spy = find_latest_underlier_spot("SPY")
        if spot_spy:
            spy_price = float(spot_spy)

    qqq_price = 480.0
    if "QQQ" in etf_details:
        val = etf_details["QQQ"].get("Price", 0.0)
        if val > 0:
            qqq_price = val
    if qqq_price == 480.0:
        spot_qqq = find_latest_underlier_spot("QQQ")
        if spot_qqq:
            qqq_price = float(spot_qqq)

    # Spot overrides if any from analyses
    spot_overrides: Dict[str, float] = {}
    analyses = load_json(ge.ANALYSES_FILE, {})
    for opt_id, details in positions.items():
        sym = (details.get("Underlier") or "").upper()
        if sym and sym not in spot_overrides:
            sp = find_latest_underlier_spot(sym)
            if sp is not None:
                spot_overrides[sym] = float(sp)
            elif sym in analyses and analyses[sym].get("spot"):
                spot_overrides[sym] = float(analyses[sym]["spot"])

    for tick in stocks.keys():
        sym = tick.upper()
        if sym and sym not in spot_overrides:
            sp = find_latest_underlier_spot(sym)
            if sp is not None:
                spot_overrides[sym] = float(sp)
            elif sym in analyses and analyses[sym].get("spot"):
                spot_overrides[sym] = float(analyses[sym]["spot"])

    hedge_plan = derive_macro_hedge_plan(
        account=account,
        net_liq=net_liq,
        cash_buying_power=cash_buying_power,
        regime=regime,
        options_positions=positions,
        stocks_positions=stocks,
        spy_price=spy_price,
        qqq_price=qqq_price,
        target_coverage=target_coverage,
        instrument_choice=instrument_choice,
        spot_overrides=spot_overrides,
    )

    if as_json:
        print(json.dumps(hedge_plan.to_dict(), indent=2, sort_keys=True))
        return

    masked_acc = mask_account(account) if account else "DEFAULT / ALL"
    print(f"\n### 🛡️ Portfolio Beta-Weighted Macro Hedge Plan ({masked_acc})")
    print(f"  - Portfolio Net Liq: ${hedge_plan.net_liq:,.2f} | Available Cash BP: ${hedge_plan.cash_buying_power:,.2f}")
    print(f"  - Reference Index Spot: SPY ${hedge_plan.spy_price:.2f} | QQQ ${qqq_price:.2f}")
    print(f"  - Market Regime Status: {hedge_plan.regime_status} ({hedge_plan.gates_passed}/3 Gates Passed)\n")

    if not hedge_plan.positions:
        print_color("💤 No open portfolio positions found to evaluate for macro hedging.", "33")
        return

    print("#### 📊 Component Holdings Delta Exposure Matrix")
    headers = ["Symbol", "Asset", "Qty", "Spot", "Raw Delta", "Delta Shs", "Beta", "BW Exp ($)", "SPY Equiv"]
    rows = []
    for p in hedge_plan.positions:
        rows.append([
            p.symbol,
            p.asset_type,
            f"{p.quantity:g}",
            f"${p.spot:,.2f}",
            f"{p.raw_delta:+.2f}",
            f"{p.delta_shares:+,.1f}",
            f"{p.beta:.2f}",
            f"${p.beta_weighted_dollar_exposure:+,.2f}",
            f"{p.spy_equivalent_delta_shares:+,.1f}",
        ])
    alignments = ["left", "left", "right", "right", "right", "right", "right", "right", "right"]
    print(format_table(headers, rows, empty_message="No positions.", alignments=alignments))
    print()

    print(f"  - Total Beta-Weighted Dollar Delta: {format_pnl(pnl_dlr=hedge_plan.total_beta_weighted_dollar_delta, bold=True)}")
    spy_color = "32" if hedge_plan.spy_equivalent_delta_shares > 0 else "31"
    print(f"  - Total SPY-Equivalent Directional Delta: {format_color(f'{hedge_plan.spy_equivalent_delta_shares:+,.2f} shares', spy_color, bold=True)}")
    print(f"  - Tech / Growth Beta Concentration: {hedge_plan.tech_exposure_pct:.1f}%\n")

    print("#### 🚦 Macro Regime Gate & Hedge Authorization")
    status_color = "32" if hedge_plan.hedge_status == "NO_HEDGE_NEEDED" else "33" if hedge_plan.hedge_status == "DEFENSIVE_HEDGE" else "31"
    status_fmt = format_color(hedge_plan.hedge_status, status_color, bold=True)
    cov_fmt = format_color(f"{hedge_plan.target_coverage_pct * 100:.1f}%", "36", bold=True)
    print(f"  - Hedge Recommendation Status: {status_fmt}")
    print(f"  - Prescribed Coverage Ratio: {cov_fmt} of Net Positive Delta")

    if hedge_plan.hedge_required and hedge_plan.target_contracts > 0:
        inst = hedge_plan.recommended_instrument
        print(f"\n#### 🎯 Structured Index Hedge: {inst} Bear Put Debit Spread")
        print(f"  - Expiration: ~{hedge_plan.target_dte} DTE Monthly Cycle")
        print(f"  - Long Put Strike: ${hedge_plan.long_put_strike:.2f} (~ -0.35 Delta, OTM Cushion)")
        print(f"  - Short Put Strike: ${hedge_plan.short_put_strike:.2f} (~ -0.15 Delta, Spread Width: ${hedge_plan.spread_width:.2f})")
        print(f"  - Recommended Allocation: {format_color(f'{hedge_plan.target_contracts} contract(s)', '33', bold=True)}")
        print(f"  - Estimated Spread Debit: ${hedge_plan.estimated_spread_debit:.2f}/sh (${hedge_plan.estimated_spread_debit * 100:,.2f}/contract)")
        outlay_pct = (hedge_plan.total_estimated_cost / hedge_plan.net_liq) * 100.0 if hedge_plan.net_liq > 0 else 0.0
        print(f"  - Total Capital Outlay: ${hedge_plan.total_estimated_cost:,.2f} ({outlay_pct:.2f}% of Net Liq)")
        print(f"  - Max Downside Protection P&L: {format_color(f'+${hedge_plan.max_protection_pnl:,.2f}', '32', bold=True)}")
        print(f"  - Post-Hedge Net Directional Delta: {format_color(f'{hedge_plan.post_hedge_net_delta_shares:+,.2f} {inst}-equiv shares', '36', bold=True)}")
    elif hedge_plan.hedge_required and hedge_plan.target_contracts == 0:
        print_color("\n⚠️ HEDGE ALLOCATION DEFERRED: Capital constrained or insufficient delta threshold.", "33")
    else:
        print_color("\n✅ UNHEDGED SWING CLEARANCE: Daily Regime Gates fully authorized (ALL TRACKS OK). No macro hedge required.", "32", bold=True)

    if hedge_plan.notes:
        print("\n💡 Sizing & Account Notes:")
        for note in hedge_plan.notes:
            print(f"  • {note}")

    if hedge_plan.hedge_rules:
        print("\n📜 Operational Hedge Rules:")
        for r in hedge_plan.hedge_rules:
            print(f"  • {r}")
    print()
