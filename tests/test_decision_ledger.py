#!/usr/bin/env python3
"""
Tests for Roadmap 5.6 — Approval Decision Ledger (GitHub issue #164).
Verifies masked-account storage, provenance tracking, validation rules,
audit metrics, and CLI commands.
"""

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import src.gex_engine as gex_engine  # noqa: E402
from src.gex.core.config import mask_account, DECISION_TYPES, DECISION_ANSWERS, DECISION_TEXT_MAX_LEN  # noqa: E402
from src.gex.storage.db import (  # noqa: E402
    init_db,
    record_decision,
    query_decisions,
    summarize_decisions,
)

ENGINE = "src.gex_engine"


class TestMaskAccount(unittest.TestCase):
    def test_mask_standard_account(self):
        self.assertEqual(mask_account("970049961"), "••••9961")
        self.assertEqual(mask_account("181909196378"), "••••6378")
        self.assertEqual(mask_account("5QR24141"), "••••4141")

    def test_mask_empty_and_none(self):
        self.assertEqual(mask_account(""), "")
        self.assertEqual(mask_account(None), "")

    def test_mask_already_masked_or_short(self):
        self.assertEqual(mask_account("••••9961"), "••••9961")
        self.assertEqual(mask_account("12"), "••••12")

    def test_mask_invalid_traversal(self):
        self.assertEqual(mask_account("../../../"), "")


class TestDecisionLedgerStorage(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "trades.db")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_record_and_query_decision_round_trip(self):
        row_id = record_decision(
            decision_type="ENTRY",
            symbol="AAPL",
            recommendation="Buy 1x AAPL 230C @ 4.20",
            human_answer="APPROVED",
            account="970049961",
            contract="AAPL 2026-12-18 230C",
            grade="CONFIRMED",
            regime_authorization="ALL TRACKS OK",
            gates_passed=3,
            order_ref="ord-12345-uuid",
            notes="Setup passed 11 rules",
            db_path=self.db_path,
        )
        self.assertGreater(row_id, 0)

        # Query back
        records = query_decisions(account="970049961", db_path=self.db_path)
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["id"], row_id)
        self.assertEqual(rec["account_mask"], "••••9961")
        self.assertEqual(rec["decision_type"], "ENTRY")
        self.assertEqual(rec["symbol"], "AAPL")
        self.assertEqual(rec["grade"], "CONFIRMED")
        self.assertEqual(rec["gates_passed"], 3)
        self.assertEqual(rec["human_answer"], "APPROVED")
        self.assertEqual(rec["order_ref"], "ord-12345-uuid")

        # Verify raw SQLite content has zero instances of unmasked raw account
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute("SELECT * FROM decisions WHERE id = ?", (row_id,)).fetchone()
            for val in row:
                if isinstance(val, str):
                    self.assertNotIn("970049961", val)
        finally:
            conn.close()

    def test_free_text_account_redaction(self):
        raw_acc = "181909196378"
        row_id = record_decision(
            decision_type="EXIT",
            symbol="NVDA",
            recommendation=f"Close NVDA for account {raw_acc} due to stop breach",
            human_answer="APPROVED",
            account=raw_acc,
            trigger_code="STOP1",
            notes=f"Ref trade for {raw_acc}",
            db_path=self.db_path,
        )
        records = query_decisions(account=raw_acc, db_path=self.db_path)
        self.assertEqual(len(records), 1)
        self.assertNotIn(raw_acc, records[0]["recommendation"])
        self.assertIn("••••6378", records[0]["recommendation"])
        self.assertNotIn(raw_acc, records[0]["notes"])
        self.assertIn("••••6378", records[0]["notes"])

    def test_text_length_truncation(self):
        long_text = "X" * (DECISION_TEXT_MAX_LEN + 100)
        row_id = record_decision(
            decision_type="ENTRY",
            symbol="MSFT",
            recommendation=long_text,
            human_answer="DECLINED",
            account="970049961",
            notes=long_text,
            db_path=self.db_path,
        )
        records = query_decisions(account="970049961", db_path=self.db_path)
        self.assertEqual(len(records[0]["recommendation"]), DECISION_TEXT_MAX_LEN)
        self.assertEqual(len(records[0]["notes"]), DECISION_TEXT_MAX_LEN)

    def test_validation_errors(self):
        # Invalid type
        with self.assertRaises(ValueError) as cm:
            record_decision(
                decision_type="BOGUS",
                symbol="AAPL",
                recommendation="rec",
                human_answer="APPROVED",
                db_path=self.db_path,
            )
        self.assertIn("Invalid decision_type", str(cm.exception))

        # Invalid answer
        with self.assertRaises(ValueError) as cm:
            record_decision(
                decision_type="ENTRY",
                symbol="AAPL",
                recommendation="rec",
                human_answer="MAYBE",
                db_path=self.db_path,
            )
        self.assertIn("Invalid human_answer", str(cm.exception))

        # Order ref with DECLINED
        with self.assertRaises(ValueError) as cm:
            record_decision(
                decision_type="ENTRY",
                symbol="AAPL",
                recommendation="rec",
                human_answer="DECLINED",
                order_ref="ord-ref-123",
                db_path=self.db_path,
            )
        self.assertIn("order_ref can only be supplied when human_answer is 'APPROVED'", str(cm.exception))

        # EXIT without trigger_code
        with self.assertRaises(ValueError) as cm:
            record_decision(
                decision_type="EXIT",
                symbol="AAPL",
                recommendation="rec",
                human_answer="APPROVED",
                db_path=self.db_path,
            )
        self.assertIn("trigger_code is required for EXIT decisions", str(cm.exception))

        # Invalid trigger code
        with self.assertRaises(ValueError) as cm:
            record_decision(
                decision_type="EXIT",
                symbol="AAPL",
                recommendation="rec",
                human_answer="APPROVED",
                trigger_code="INVALID_STOP",
                db_path=self.db_path,
            )
        self.assertIn("Invalid trigger_code", str(cm.exception))

        # Invalid gates_passed
        with self.assertRaises(ValueError) as cm:
            record_decision(
                decision_type="ENTRY",
                symbol="AAPL",
                recommendation="rec",
                human_answer="APPROVED",
                gates_passed=4,
                db_path=self.db_path,
            )
        self.assertIn("Invalid gates_passed", str(cm.exception))

        # Empty symbol or recommendation
        with self.assertRaises(ValueError):
            record_decision(
                decision_type="ENTRY",
                symbol="",
                recommendation="rec",
                human_answer="APPROVED",
                db_path=self.db_path,
            )

        with self.assertRaises(ValueError):
            record_decision(
                decision_type="ENTRY",
                symbol="AAPL",
                recommendation="",
                human_answer="APPROVED",
                db_path=self.db_path,
            )

        # Invalid account identifiers
        with self.assertRaises(ValueError):
            record_decision(
                decision_type="ENTRY",
                symbol="AAPL",
                recommendation="rec",
                human_answer="APPROVED",
                account="../../../",
                db_path=self.db_path,
            )

        with self.assertRaises(ValueError):
            query_decisions(account="../../../", db_path=self.db_path)

        with self.assertRaises(ValueError):
            summarize_decisions(account="../../../", db_path=self.db_path)

    def test_summarize_decisions_and_rule_conflicts(self):
        # 1. Approved confirmed entry (No conflict)
        record_decision(
            decision_type="ENTRY", symbol="AAPL", recommendation="rec1",
            human_answer="APPROVED", grade="CONFIRMED", account="970049961", db_path=self.db_path
        )
        # 2. Approved PENDING entry (Rule conflict)
        record_decision(
            decision_type="ENTRY", symbol="NVDA", recommendation="rec2",
            human_answer="APPROVED", grade="PENDING", account="970049961", db_path=self.db_path
        )
        # 3. Declined STOP1 exit (Rule conflict: mandatory stop declined)
        record_decision(
            decision_type="EXIT", symbol="TSLA", recommendation="rec3",
            human_answer="DECLINED", trigger_code="STOP1", account="970049961", db_path=self.db_path
        )
        # 4. Approved STOP5 exit (No conflict)
        record_decision(
            decision_type="EXIT", symbol="AMD", recommendation="rec4",
            human_answer="APPROVED", trigger_code="STOP5", account="970049961", db_path=self.db_path
        )
        # 5. Declined STOP2 trailing giveback (No conflict: discretionary trail)
        record_decision(
            decision_type="EXIT", symbol="GOOGL", recommendation="rec5",
            human_answer="DECLINED", trigger_code="STOP2", account="970049961", db_path=self.db_path
        )

        summary = summarize_decisions(account="970049961", db_path=self.db_path)
        self.assertEqual(summary["total_decisions"], 5)
        self.assertEqual(summary["by_type"]["ENTRY"], 2)
        self.assertEqual(summary["by_type"]["EXIT"], 3)
        self.assertEqual(summary["by_answer"]["APPROVED"], 3)
        self.assertEqual(summary["by_answer"]["DECLINED"], 2)
        self.assertEqual(summary["approval_rate_pct"], 60.0)

        self.assertEqual(summary["rule_conflicts_count"], 2)
        conflict_symbols = [c["symbol"] for c in summary["rule_conflicts"]]
        self.assertIn("NVDA", conflict_symbols)
        self.assertIn("TSLA", conflict_symbols)


class TestDecisionLedgerCli(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "trades.db")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_cli_record_decision_and_table_display(self):
        # Record via CLI handler
        args_rec = SimpleNamespace(
            account="970049961",
            type="ENTRY",
            symbol="AAPL",
            recommendation="Buy 1x AAPL 230C",
            answer="APPROVED",
            contract="AAPL 2026-12-18 230C",
            grade="CONFIRMED",
            regime="ALL TRACKS OK",
            gates_passed=3,
            trigger=None,
            order_ref="ord-abc",
            notes="Passed setup rules",
            db_path=self.db_path,
        )
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            gex_engine.cmd_record_decision(args_rec)
            self.assertIn("Recorded decision #1", mock_stdout.getvalue())
            self.assertIn("••••9961", mock_stdout.getvalue())

        # View via decisions table
        args_view = SimpleNamespace(
            account="970049961",
            limit=50,
            json=False,
            db_path=self.db_path,
        )
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            gex_engine.cmd_decisions(args_view)
            output = mock_stdout.getvalue()
            self.assertIn("Execution Approval Decision Ledger", output)
            self.assertIn("••••9961", output)
            self.assertIn("AAPL", output)
            self.assertIn("APPROVED", output)
            self.assertIn("Total Decisions: 1", output)

    def test_cli_decisions_json_output(self):
        args_rec = SimpleNamespace(
            account="970049961",
            type="EXIT",
            symbol="MSFT",
            recommendation="Close MSFT on nTrans breach",
            answer="APPROVED",
            contract=None,
            grade=None,
            regime=None,
            gates_passed=None,
            trigger="STOP1",
            order_ref=None,
            notes=None,
            db_path=self.db_path,
        )
        gex_engine.cmd_record_decision(args_rec)

        args_json = SimpleNamespace(
            account="970049961",
            limit=50,
            json=True,
            db_path=self.db_path,
        )
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            gex_engine.cmd_decisions(args_json)
            import json
            data = json.loads(mock_stdout.getvalue())
            self.assertIn("summary", data)
            self.assertIn("decisions", data)
            self.assertEqual(len(data["decisions"]), 1)
            self.assertEqual(data["decisions"][0]["trigger_code"], "STOP1")
            self.assertEqual(data["summary"]["approval_rate_pct"], 100.0)

    def test_cli_record_decision_missing_account(self):
        args = SimpleNamespace(
            account="",
            type="ENTRY",
            symbol="AAPL",
            recommendation="rec",
            answer="APPROVED",
            db_path=self.db_path,
        )
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with self.assertRaises(SystemExit) as cm:
                gex_engine.cmd_record_decision(args)
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("--account is required", mock_stderr.getvalue())

    def test_argparse_parsing_case_normalization(self):
        captured = {}
        with patch.object(
            sys, "argv",
            [
                "gex_engine.py", "record-decision",
                "--account", "970049961",
                "--type", "entry",
                "--symbol", "aapl",
                "--recommendation", "test rec",
                "--answer", "approved",
                "--grade", "confirmed",
                "--db-path", self.db_path,
            ]
        ), patch(f"{ENGINE}.cmd_record_decision", side_effect=lambda a: captured.update(vars(a))):
            gex_engine.main()

        self.assertEqual(captured["type"], "ENTRY")
        self.assertEqual(captured["answer"], "APPROVED")
        self.assertEqual(captured["grade"], "CONFIRMED")


if __name__ == "__main__":
    unittest.main()
