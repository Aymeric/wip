"""
Centralized argument parser construction and command dispatching for the GEX CLI.
Assembles subparsers across all 5 domain modules (regime, portfolio, screening, journal, ops)
and maps CLI command invocations to their respective handlers.
"""

import argparse
from datetime import datetime
from typing import Any, Dict, List, Optional


def str2bool(value: Any) -> bool:
    """Parses CLI boolean flags reliably (argparse type=bool treats 'False' as True)."""
    if isinstance(value, bool):
        return value
    if value.lower() in ("true", "t", "yes", "y", "1"):
        return True
    if value.lower() in ("false", "f", "no", "n", "0"):
        return False
    raise argparse.ArgumentTypeError(f"Boolean value expected, got '{value}'.")


def parse_effective_session_date(value: str) -> str:
    """Validate the market session date used for persisted ticker analyses."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(
            "effective session date must use YYYY-MM-DD"
        ) from exc


def parse_spot_overrides(values: Optional[List[str]]) -> Dict[str, float]:
    """Parses spot overrides in the format TICKER=PRICE, e.g. AAPL=290,BABA=81."""
    if not values:
        return {}
    overrides: Dict[str, float] = {}
    for entry in values:
        if not entry:
            continue
        parts = [p.strip() for p in entry.split(",") if p.strip()]
        for part in parts:
            if "=" not in part:
                raise argparse.ArgumentTypeError(
                    f"Invalid override format '{part}'. Expected TICKER=PRICE, e.g. AAPL=290"
                )
            sym, val = part.split("=", 1)
            sym = sym.strip().upper()
            try:
                price = float(val.strip())
            except ValueError as exc:
                raise argparse.ArgumentTypeError(
                    f"Invalid price value for {sym}: '{val.strip()}'. Must be a float."
                ) from exc
            overrides[sym] = price
    return overrides


def build_parser() -> argparse.ArgumentParser:
    """Assembles the unified command-line argument parser with all subcommands."""
    from src.gex import __version__

    parser = argparse.ArgumentParser(
        description="GEX Options Mechanical Engine - Rule validation CLI and storage keeper"
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    from src.gex.cli.regime import add_regime_parsers
    from src.gex.cli.portfolio import add_portfolio_parsers
    from src.gex.cli.screening import add_screening_parsers
    from src.gex.cli.journal import add_journal_parsers
    from src.gex.cli.ops import add_ops_parsers

    add_regime_parsers(subparsers)
    add_portfolio_parsers(subparsers)
    add_screening_parsers(subparsers)
    add_journal_parsers(subparsers)
    add_ops_parsers(subparsers)

    return parser


COMMAND_HANDLERS: Dict[str, Any] = {}


def get_command_handlers() -> Dict[str, Any]:
    """Returns the dictionary mapping subcommand names to handler functions."""
    global COMMAND_HANDLERS
    if not COMMAND_HANDLERS:
        from src.gex.cli.regime import cmd_status, cmd_update_regime
        from src.gex.cli.portfolio import (
            cmd_portfolio, cmd_add_pos, cmd_update_opt, cmd_close_pos,
            cmd_add_stock_pos, cmd_update_stock_pos, cmd_close_stock_pos,
            cmd_sync_positions, cmd_evaluate_rolls, cmd_hedge_plan,
        )
        from src.gex.cli.screening import (
            cmd_analyze, cmd_update_candidates, cmd_prune_candidates,
            cmd_sentiment, cmd_update_sentiment, cmd_rankings,
            cmd_select_spreads, cmd_payoff, cmd_simulate,
            cmd_pre_earnings_candidates,
        )
        from src.gex.cli.journal import (
            cmd_update_performance, cmd_closed, cmd_journal,
            cmd_sync_pnl, cmd_record_decision, cmd_decisions,
        )
        from src.gex.cli.ops import (
            cmd_workflow, cmd_snapshot, cmd_update_workflow,
            cmd_audit_all, cmd_monitor, cmd_backtest, cmd_cleanup_downloads,
        )

        COMMAND_HANDLERS = {
            "status": cmd_status,
            "update-regime": cmd_update_regime,
            "portfolio": cmd_portfolio,
            "add-position": cmd_add_pos,
            "update-option": cmd_update_opt,
            "close-position": cmd_close_pos,
            "add-stock": cmd_add_stock_pos,
            "update-stock": cmd_update_stock_pos,
            "close-stock": cmd_close_stock_pos,
            "sync-positions": cmd_sync_positions,
            "evaluate-rolls": cmd_evaluate_rolls,
            "hedge-plan": cmd_hedge_plan,
            "analyze": cmd_analyze,
            "update-candidates": cmd_update_candidates,
            "prune-candidates": cmd_prune_candidates,
            "sentiment": cmd_sentiment,
            "update-sentiment": cmd_update_sentiment,
            "rankings": cmd_rankings,
            "select-spreads": cmd_select_spreads,
            "payoff": cmd_payoff,
            "simulate": cmd_simulate,
            "pre-earnings-candidates": cmd_pre_earnings_candidates,
            "update-performance": cmd_update_performance,
            "closed": cmd_closed,
            "journal": cmd_journal,
            "sync-pnl": cmd_sync_pnl,
            "record-decision": cmd_record_decision,
            "decisions": cmd_decisions,
            "workflow": cmd_workflow,
            "snapshot": cmd_snapshot,
            "update-workflow": cmd_update_workflow,
            "audit-all": cmd_audit_all,
            "monitor": cmd_monitor,
            "backtest": cmd_backtest,
            "cleanup-downloads": cmd_cleanup_downloads,
        }
    return COMMAND_HANDLERS


def dispatch_command(args: argparse.Namespace) -> Any:
    """Routes a parsed command to its registered handler."""
    import sys
    import src.gex_engine as ge

    if not hasattr(args, "spot_overrides"):
        args.spot_overrides = {}

    cmd_attr_map = {
        "status": "cmd_status",
        "update-regime": "cmd_update_regime",
        "portfolio": "cmd_portfolio",
        "add-position": "cmd_add_pos",
        "update-option": "cmd_update_opt",
        "close-position": "cmd_close_pos",
        "add-stock": "cmd_add_stock_pos",
        "update-stock": "cmd_update_stock_pos",
        "close-stock": "cmd_close_stock_pos",
        "sync-positions": "cmd_sync_positions",
        "evaluate-rolls": "cmd_evaluate_rolls",
        "hedge-plan": "cmd_hedge_plan",
        "analyze": "cmd_analyze",
        "update-candidates": "cmd_update_candidates",
        "prune-candidates": "cmd_prune_candidates",
        "sentiment": "cmd_sentiment",
        "update-sentiment": "cmd_update_sentiment",
        "rankings": "cmd_rankings",
        "select-spreads": "cmd_select_spreads",
        "payoff": "cmd_payoff",
        "simulate": "cmd_simulate",
        "pre-earnings-candidates": "cmd_pre_earnings_candidates",
        "update-performance": "cmd_update_performance",
        "closed": "cmd_closed",
        "journal": "cmd_journal",
        "sync-pnl": "cmd_sync_pnl",
        "record-decision": "cmd_record_decision",
        "decisions": "cmd_decisions",
        "workflow": "cmd_workflow",
        "snapshot": "cmd_snapshot",
        "update-workflow": "cmd_update_workflow",
        "audit-all": "cmd_audit_all",
        "monitor": "cmd_monitor",
        "backtest": "cmd_backtest",
        "cleanup-downloads": "cmd_cleanup_downloads",
    }

    attr_name = cmd_attr_map.get(args.command)
    root_ge = sys.modules.get("gex_engine")
    if root_ge and attr_name and hasattr(root_ge, attr_name):
        root_handler = getattr(root_ge, attr_name)
        if hasattr(ge, attr_name) and root_handler is not getattr(ge, attr_name):
            return root_handler(args)

    if attr_name and hasattr(ge, attr_name):
        return getattr(ge, attr_name)(args)

    handlers = get_command_handlers()
    handler = handlers.get(args.command)
    if handler:
        return handler(args)
    raise ValueError(f"Unknown command: {args.command}")
