"""
Unit tests for the extracted GEX CLI package (src/gex/cli/).
Validates subparser registration, command handlers mapping, converters,
backward compatibility re-exports from gex_engine, and dispatch routing.
"""

import argparse
import unittest
from unittest.mock import MagicMock, patch

import gex_engine
from src.gex.cli import (
    COMMAND_HANDLERS,
    build_parser,
    dispatch_command,
    get_command_handlers,
    parse_effective_session_date,
    parse_spot_overrides,
    str2bool,
)
import src.gex.cli as cli


ALL_34_COMMANDS = [
    # Regime (2)
    "status",
    "update-regime",
    # Portfolio (10)
    "portfolio",
    "add-position",
    "update-option",
    "close-position",
    "add-stock",
    "update-stock",
    "close-stock",
    "sync-positions",
    "evaluate-rolls",
    "hedge-plan",
    # Screening (11)
    "analyze",
    "update-candidates",
    "prune-candidates",
    "sentiment",
    "update-sentiment",
    "rankings",
    "select-spreads",
    "payoff",
    "simulate",
    "pre-earnings-candidates",
    # Journal (6)
    "update-performance",
    "closed",
    "journal",
    "sync-pnl",
    "record-decision",
    "decisions",
    # Ops (7)
    "workflow",
    "snapshot",
    "update-workflow",
    "audit-all",
    "monitor",
    "backtest",
    "cleanup-downloads",
]

ALL_34_HANDLERS = [
    # Regime
    "cmd_status",
    "cmd_update_regime",
    # Portfolio
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
    # Screening
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
    # Journal
    "cmd_update_performance",
    "cmd_closed",
    "cmd_journal",
    "cmd_sync_pnl",
    "cmd_record_decision",
    "cmd_decisions",
    # Ops
    "cmd_workflow",
    "cmd_snapshot",
    "cmd_update_workflow",
    "cmd_audit_all",
    "cmd_monitor",
    "cmd_backtest",
    "cmd_cleanup_downloads",
]


class TestCliExtraction(unittest.TestCase):
    """Verifies complete extraction and parity of src/gex/cli/."""

    def test_build_parser_registers_all_34_subcommands(self):
        """Verify that build_parser() configures all 34 domain subcommands."""
        parser = build_parser()
        # Find the subparsers action
        subparsers_actions = [
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        ]
        self.assertEqual(len(subparsers_actions), 1)
        subparser_choices = set(subparsers_actions[0].choices.keys())

        self.assertEqual(len(ALL_34_COMMANDS), 35)
        for cmd in ALL_34_COMMANDS:
            self.assertIn(
                cmd,
                subparser_choices,
                f"Command '{cmd}' is missing from subparser choices",
            )

    def test_all_handlers_exported_from_cli_package(self):
        """Verify all 34 cmd_* handlers are accessible from src.gex.cli."""
        for handler_name in ALL_34_HANDLERS:
            self.assertTrue(
                hasattr(cli, handler_name),
                f"Handler '{handler_name}' not found in src.gex.cli",
            )
            handler = getattr(cli, handler_name)
            self.assertTrue(callable(handler))

    def test_all_handlers_reexported_from_gex_engine(self):
        """Verify 100% backward compatibility: gex_engine re-exports all 34 handlers."""
        for handler_name in ALL_34_HANDLERS:
            self.assertTrue(
                hasattr(gex_engine, handler_name),
                f"Handler '{handler_name}' not re-exported from gex_engine",
            )
            handler = getattr(gex_engine, handler_name)
            self.assertTrue(callable(handler))

    def test_command_handlers_map_integrity(self):
        """Verify get_command_handlers() returns all 35 registered commands."""
        handlers = get_command_handlers()
        self.assertEqual(len(handlers), 35)
        for cmd in ALL_34_COMMANDS:
            self.assertIn(cmd, handlers)
            self.assertTrue(callable(handlers[cmd]))

    def test_str2bool_conversions(self):
        """Verify str2bool converter parsing truthy, falsy, and invalid inputs."""
        for val in (True, "true", "True", "t", "yes", "Y", "1"):
            self.assertTrue(str2bool(val))

        for val in (False, "false", "False", "f", "no", "N", "0"):
            self.assertFalse(str2bool(val))

        for val in ("maybe", "unknown", "2", "-1"):
            with self.assertRaises(argparse.ArgumentTypeError):
                str2bool(val)

    def test_parse_effective_session_date(self):
        """Verify parse_effective_session_date parses YYYY-MM-DD or raises ArgumentTypeError."""
        self.assertEqual(parse_effective_session_date("2026-11-18"), "2026-11-18")
        self.assertEqual(parse_effective_session_date("2025-01-01"), "2025-01-01")

        for invalid in ("2026/11/18", "18-11-2026", "invalid-date", ""):
            with self.assertRaises(argparse.ArgumentTypeError):
                parse_effective_session_date(invalid)

    def test_parse_spot_overrides(self):
        """Verify spot overrides parsing from TICKER=PRICE syntax."""
        self.assertEqual(parse_spot_overrides(None), {})
        self.assertEqual(parse_spot_overrides([]), {})
        self.assertEqual(parse_spot_overrides([""]), {})

        parsed = parse_spot_overrides(["AAPL=150.5", "MSFT=400,GOOGL=175.25"])
        self.assertEqual(
            parsed,
            {"AAPL": 150.5, "MSFT": 400.0, "GOOGL": 175.25},
        )

        # Invalid formats
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_spot_overrides(["AAPL150"])

        with self.assertRaises(argparse.ArgumentTypeError):
            parse_spot_overrides(["AAPL=invalid_price"])

    def test_dispatch_command_routing(self):
        """Verify dispatch_command routes to the corresponding handler."""
        mock_handler = MagicMock(return_value="executed_ok")
        args = argparse.Namespace(command="status")

        with patch.object(gex_engine, "cmd_status", mock_handler):
            res = dispatch_command(args)
            self.assertEqual(res, "executed_ok")
            mock_handler.assert_called_once_with(args)

    def test_dispatch_command_unknown_raises_value_error(self):
        """Verify dispatch_command raises ValueError for an unregistered command."""
        args = argparse.Namespace(command="unregistered_subcommand_xyz")
        with self.assertRaises(ValueError):
            dispatch_command(args)

    def test_subparser_arguments_parsing(self):
        """Verify representative CLI argument parsing across different domains."""
        parser = build_parser()

        # Regime domain
        args = parser.parse_args(["status", "--account", "ACC123", "--net-liq", "50000.0"])
        self.assertEqual(args.command, "status")
        self.assertEqual(args.account, "ACC123")
        self.assertEqual(args.net_liq, 50000.0)

        # Portfolio domain
        args = parser.parse_args(["portfolio", "--account", "ACC123", "--net-liq", "25000.0"])
        self.assertEqual(args.command, "portfolio")
        self.assertEqual(args.account, "ACC123")
        self.assertEqual(args.net_liq, 25000.0)

        # Screening domain
        args = parser.parse_args(["analyze", "AAPL", "--effective-session-date", "2026-11-18"])
        self.assertEqual(args.command, "analyze")
        self.assertEqual(args.symbol, "AAPL")
        self.assertEqual(args.effective_session_date, "2026-11-18")

        # Journal domain
        args = parser.parse_args(["journal", "--account", "ACC456", "--sync-db"])
        self.assertEqual(args.command, "journal")
        self.assertEqual(args.account, "ACC456")
        self.assertTrue(args.sync_db)

        # Ops domain
        args = parser.parse_args(["update-workflow", "--phase", "Phase I: Audit"])
        self.assertEqual(args.command, "update-workflow")
        self.assertEqual(args.phase, "Phase I: Audit")


if __name__ == "__main__":
    unittest.main()
