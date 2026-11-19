"""
CLI package for the GEX Options Trading System.
Provides modular domain-driven subcommands, parser builders, and command dispatchers.
"""

from src.gex.cli.parser import (
    COMMAND_HANDLERS,
    build_parser,
    dispatch_command,
    get_command_handlers,
    parse_effective_session_date,
    parse_spot_overrides,
    str2bool,
)
from src.gex.cli.regime import (
    add_regime_parsers,
    cmd_status,
    cmd_update_regime,
)
from src.gex.cli.portfolio import (
    add_portfolio_parsers,
    cmd_add_pos,
    cmd_add_stock_pos,
    cmd_close_pos,
    cmd_close_stock_pos,
    cmd_evaluate_rolls,
    cmd_hedge_plan,
    cmd_portfolio,
    cmd_sync_positions,
    cmd_update_opt,
    cmd_update_stock_pos,
)
from src.gex.cli.screening import (
    add_screening_parsers,
    cmd_analyze,
    cmd_payoff,
    cmd_prune_candidates,
    cmd_rankings,
    cmd_select_spreads,
    cmd_sentiment,
    cmd_simulate,
    cmd_pre_earnings_candidates,
    cmd_update_candidates,
    cmd_update_sentiment,
)
from src.gex.cli.journal import (
    add_journal_parsers,
    cmd_closed,
    cmd_decisions,
    cmd_journal,
    cmd_record_decision,
    cmd_sync_pnl,
    cmd_update_performance,
)
from src.gex.cli.ops import (
    add_ops_parsers,
    cmd_audit_all,
    cmd_backtest,
    cmd_cleanup_downloads,
    cmd_monitor,
    cmd_snapshot,
    cmd_update_workflow,
    cmd_workflow,
)

__all__ = [
    # Parser & Dispatcher
    "COMMAND_HANDLERS",
    "get_command_handlers",
    "build_parser",
    "dispatch_command",
    "str2bool",
    "parse_spot_overrides",
    "parse_effective_session_date",
    # Domain Parsers
    "add_regime_parsers",
    "add_portfolio_parsers",
    "add_screening_parsers",
    "add_journal_parsers",
    "add_ops_parsers",
    # Regime Commands
    "cmd_status",
    "cmd_update_regime",
    # Portfolio Commands
    "cmd_portfolio",
    "cmd_add_pos",
    "cmd_update_opt",
    "cmd_close_pos",
    "cmd_add_stock_pos",
    "cmd_update_stock_pos",
    "cmd_close_stock_pos",
    "cmd_sync_positions",
    "cmd_evaluate_rolls",
    "cmd_hedge_plan",
    # Screening Commands
    "cmd_analyze",
    "cmd_update_candidates",
    "cmd_prune_candidates",
    "cmd_sentiment",
    "cmd_update_sentiment",
    "cmd_rankings",
    "cmd_select_spreads",
    "cmd_payoff",
    "cmd_simulate",
    "cmd_pre_earnings_candidates",
    # Journal Commands
    "cmd_update_performance",
    "cmd_closed",
    "cmd_journal",
    "cmd_sync_pnl",
    "cmd_record_decision",
    "cmd_decisions",
    # Ops Commands
    "cmd_workflow",
    "cmd_snapshot",
    "cmd_update_workflow",
    "cmd_audit_all",
    "cmd_monitor",
    "cmd_backtest",
    "cmd_cleanup_downloads",
]
