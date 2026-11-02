#!/usr/bin/env python3
"""
Tests for Roadmap 5.5 — Stop-Coded Exit Attribution (GitHub issue #163).
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
from src.gex.core.config import EXIT_REASON_CODES  # noqa: E402
from src.gex.storage.db import sync_closed_positions_to_db  # noqa: E402

ENGINE = "src.gex_engine"


class TestExitReasonCli(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.active_file = os.path.join(self.temp_dir, "active_positions_TEST.json")
        self.closed_file = os.path.join(self.temp_dir, "closed_positions_TEST.json")
        gex_engine.save_json(self.active_file, {
            "options_positions": {
                "opt_1": {"Underlier": "AAPL", "Strike": 150.0, "Type": "call",
                          "Purchase Premium": 2.0, "Mark Price": 1.0},
            },
            "stocks_positions": {
                "MSFT": {"Shares": 10, "Average Buy Price": 400.0, "Current Price": 440.0},
            },
        })

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def _patches(self):
        return (
            patch(f"{ENGINE}.account_positions_file", return_value=self.active_file),
            patch(f"{ENGINE}.account_closed_positions_file", return_value=self.closed_file),
            patch(f"{ENGINE}.sync_closed_positions_to_db", return_value=1),
            patch("sys.stdout", new_callable=StringIO),
        )

    def test_close_option_persists_stop_code(self):
        p1, p2, p3, p4 = self._patches()
        with p1, p2, p3, p4 as out:
            gex_engine.cmd_close_pos(SimpleNamespace(option_id="opt_1", close_premium=1.0,
                                                     account="TEST", reason="STOP1"))
            self.assertIn("[STOP1]", out.getvalue())
        closed = gex_engine.load_json(self.closed_file, {})["closed_options"]
        self.assertEqual(closed[0]["Close Reason"], "STOP1")

    def test_close_stock_persists_target_code(self):
        p1, p2, p3, p4 = self._patches()
        with p1, p2, p3, p4:
            gex_engine.cmd_close_stock_pos(SimpleNamespace(ticker="msft", close_price=None,
                                                           account="TEST", reason="TARGET"))
        closed = gex_engine.load_json(self.closed_file, {})["closed_stocks"]
        self.assertEqual(closed[0]["Close Reason"], "TARGET")

    def test_missing_reason_defaults_to_manual(self):
        p1, p2, p3, p4 = self._patches()
        with p1, p2, p3, p4:
            gex_engine.cmd_close_pos(SimpleNamespace(option_id="AAPL", close_premium=None, account="TEST"))
        closed = gex_engine.load_json(self.closed_file, {})["closed_options"]
        self.assertEqual(closed[0]["Close Reason"], "MANUAL")

    def test_argparse_normalizes_and_validates_reason(self):
        captured = {}
        with patch.object(sys, "argv", ["gex_engine.py", "close-position", "opt_1", "--reason", "stop3"]), \
             patch(f"{ENGINE}.cmd_close_pos", side_effect=lambda a: captured.setdefault("reason", a.reason)):
            gex_engine.main()
        self.assertEqual(captured["reason"], "STOP3")

        with patch.object(sys, "argv", ["gex_engine.py", "close-stock", "MSFT", "--reason", "BOGUS"]), \
             patch("sys.stderr", new_callable=StringIO):
            with self.assertRaises(SystemExit) as cm:
                gex_engine.main()
            self.assertEqual(cm.exception.code, 2)

    def test_reason_codes_cover_stop_hierarchy(self):
        for code in ("STOP1", "STOP2", "STOP3", "STOP4", "STOP5", "TARGET", "MANUAL", "RECONCILED"):
            self.assertIn(code, EXIT_REASON_CODES)


class TestExitReasonPersistenceAndJournal(unittest.TestCase):
    def test_sqlite_exit_reason_persisted(self):
        temp_dir = tempfile.mkdtemp()
        try:
            db_path = os.path.join(temp_dir, "trades.db")
            closed = {
                "closed_options": [{
                    "Option ID": "opt_1", "Underlier": "AAPL", "Strike": 150.0, "Type": "call",
                    "Expiration": "2026-12-18", "Purchase Premium": 2.0, "Close Premium": 1.0,
                    "Realized P&L ($)": -100.0, "Realized P&L (%)": -50.0,
                    "Entry Date": "2026-10-01", "Close Date": "2026-10-10", "Close Reason": "STOP5",
                }],
                "closed_stocks": [],
            }
            self.assertEqual(sync_closed_positions_to_db(closed, account="TEST", db_path=db_path), 1)
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute("SELECT exit_reason FROM trades").fetchone()
            finally:
                conn.close()
            self.assertEqual(row[0], "STOP5")
        finally:
            shutil.rmtree(temp_dir)

    def test_journal_per_reason_win_rate_and_expectancy(self):
        closed = {
            "closed_options": [
                {"Realized P&L ($)": 200.0, "Close Reason": "TARGET"},
                {"Realized P&L ($)": 100.0, "Close Reason": "TARGET"},
                {"Realized P&L ($)": -80.0, "Close Reason": "STOP1"},
                {"Realized P&L ($)": 40.0, "Close Reason": "STOP1"},
            ],
            "closed_stocks": [],
        }
        report = gex_engine.calculate_trade_journal(closed)
        target = report["close_reasons"]["TARGET"]
        stop1 = report["close_reasons"]["STOP1"]
        self.assertEqual(target["count"], 2)
        self.assertEqual(target["win_rate_pct"], 100.0)
        self.assertEqual(target["expectancy_per_trade"], 150.0)
        self.assertEqual(stop1["win_rate_pct"], 50.0)
        self.assertEqual(stop1["expectancy_per_trade"], -20.0)
        self.assertEqual(stop1["pnl"], -40.0)


if __name__ == "__main__":
    unittest.main()
