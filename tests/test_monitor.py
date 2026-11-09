import io
import json
import os
import sys
import tempfile
import unittest

# Ensure src/ is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
import gex_engine
from src.gex.screening.monitor import (
    PositionBreachAlert,
    evaluate_holding_breaches,
    run_monitor_pass,
    monitor_daemon,
)


class TestIntradayLevelBreachMonitor(unittest.TestCase):
    def setUp(self):
        self.analyses_sample = {
            "AAPL": {
                "Ticker": "AAPL",
                "Spot": 200.0,
                "pTrans": 195.0,
                "nTrans": 190.0,
                "+GEX": 210.0,
                "t2_target": 220.0,
            },
            "NVDA": {
                "Ticker": "NVDA",
                "Spot": 130.0,
                "pTrans": 125.0,
                "nTrans": 120.0,
                "+GEX": 140.0,
            },
        }

    def test_evaluate_holding_breaches_stop1(self):
        """Spot below nTrans triggers STOP1_NTRANS breach alert."""
        positions = {
            "options_positions": {
                "opt_aapl": {
                    "Underlier": "AAPL",
                    "Purchase Premium": 5.0,
                    "Mark Price": 4.5,
                }
            }
        }
        # Spot is $185.0, below nTrans ($190.0)
        alerts = evaluate_holding_breaches(
            positions,
            self.analyses_sample,
            spot_fetcher=lambda s: 185.0 if s == "AAPL" else 100.0,
            account="TEST_ACC_1",
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].breach_type, "STOP1_NTRANS")
        self.assertEqual(alerts[0].symbol, "AAPL")
        self.assertEqual(alerts[0].threshold, 190.0)
        self.assertIn("Immediate Exit", alerts[0].action)

    def test_evaluate_holding_breaches_profit_target(self):
        """Spot at or above +GEX triggers PROFIT_TARGET_GEX breach alert."""
        positions = {
            "options_positions": {
                "opt_aapl": {
                    "Underlier": "AAPL",
                    "Purchase Premium": 5.0,
                    "Mark Price": 8.0,
                }
            }
        }
        # Spot is $212.0, above +GEX ($210.0)
        alerts = evaluate_holding_breaches(
            positions,
            self.analyses_sample,
            spot_fetcher=lambda s: 212.0 if s == "AAPL" else 100.0,
            account="TEST_ACC_1",
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].breach_type, "PROFIT_TARGET_GEX")
        self.assertEqual(alerts[0].symbol, "AAPL")
        self.assertEqual(alerts[0].threshold, 210.0)
        self.assertIn("T1 Profit", alerts[0].action)

    def test_evaluate_holding_breaches_t2_target(self):
        """Position in T2 mode reaching T2 target triggers T2_TARGET breach alert."""
        positions = {
            "options_positions": {
                "opt_aapl": {
                    "Underlier": "AAPL",
                    "Purchase Premium": 5.0,
                    "Mark Price": 12.0,
                    "Target Mode": "T2",
                }
            }
        }
        # Spot is $225.0, above t2_target ($220.0)
        alerts = evaluate_holding_breaches(
            positions,
            self.analyses_sample,
            spot_fetcher=lambda s: 225.0 if s == "AAPL" else 100.0,
            account="TEST_ACC_1",
        )
        types = [a.breach_type for a in alerts]
        self.assertIn("T2_TARGET", types)
        self.assertIn("PROFIT_TARGET_GEX", types)

    def test_evaluate_holding_breaches_stop2_max_asset(self):
        """Spot below pTrans with option loss <= -10% triggers STOP2_MAX_ASSET."""
        positions = {
            "options_positions": {
                "opt_aapl": {
                    "Underlier": "AAPL",
                    "Purchase Premium": 10.0,
                    "Mark Price": 8.5,  # -15% loss
                }
            }
        }
        # Spot is $193.0, below pTrans ($195.0) but above nTrans ($190.0)
        alerts = evaluate_holding_breaches(
            positions,
            self.analyses_sample,
            spot_fetcher=lambda s: 193.0 if s == "AAPL" else 100.0,
            account="TEST_ACC_1",
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].breach_type, "STOP2_MAX_ASSET")

    def test_evaluate_holding_breaches_stop5_catastrophic(self):
        """Option loss <= -50% triggers STOP5_CATASTROPHIC hard stop."""
        positions = {
            "options_positions": {
                "opt_aapl": {
                    "Underlier": "AAPL",
                    "Purchase Premium": 10.0,
                    "Mark Price": 4.0,  # -60% loss
                }
            }
        }
        # Spot is $200.0 (safe spot level)
        alerts = evaluate_holding_breaches(
            positions,
            self.analyses_sample,
            spot_fetcher=lambda s: 200.0 if s == "AAPL" else 100.0,
            account="TEST_ACC_1",
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].breach_type, "STOP5_CATASTROPHIC")

    def test_evaluate_holding_breaches_hold(self):
        """Holding within normal runway bounds triggers zero breach alerts."""
        positions = {
            "options_positions": {
                "opt_aapl": {
                    "Underlier": "AAPL",
                    "Purchase Premium": 5.0,
                    "Mark Price": 5.5,
                }
            }
        }
        # Spot is $202.0 (between pTrans $195 and +GEX $210, small gain)
        alerts = evaluate_holding_breaches(
            positions,
            self.analyses_sample,
            spot_fetcher=lambda s: 202.0 if s == "AAPL" else 100.0,
            account="TEST_ACC_1",
        )
        self.assertEqual(len(alerts), 0)

    def test_evaluate_holding_breaches_stock(self):
        """Stock holdings trigger STOP1_NTRANS and STOP5_CATASTROPHIC accurately."""
        positions = {
            "stocks_positions": {
                "NVDA": {
                    "Shares": 10.0,
                    "Average Buy Price": 125.0,
                }
            }
        }
        # NVDA spot $115.0 below nTrans $120.0
        alerts = evaluate_holding_breaches(
            positions,
            self.analyses_sample,
            spot_fetcher=lambda s: 115.0 if s == "NVDA" else 100.0,
            account="TEST_ACC_1",
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].breach_type, "STOP1_NTRANS")
        self.assertEqual(alerts[0].position_type, "stock")

    def test_run_monitor_pass_alerting_and_deduplication(self):
        """run_monitor_pass dispatches alerts on initial breach and deduplicates subsequent passes."""
        dispatched = []
        def mock_dispatch(title, message):
            dispatched.append((title, message))
            return True

        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
            json.dump({
                "options_positions": {
                    "opt_1": {"Underlier": "AAPL", "Purchase Premium": 5.0, "Mark Price": 4.0}
                }
            }, f)
            temp_pos_file = f.name

        def read_pos(path):
            with open(path, "r", encoding="utf-8") as fp:
                return json.load(fp)

        try:
            alert_cache = set()
            # Pass 1: Spot is $180.0 (breach nTrans $190)
            res1 = run_monitor_pass(
                account="TEST_DEDUP",
                alert=True,
                alert_cache=alert_cache,
                spot_fetcher=lambda s: 180.0,
                dispatch_fn=mock_dispatch,
                positions_loader=read_pos,
                analyses_loader=lambda: self.analyses_sample,
                account_files_discoverer=lambda acc: [(acc, temp_pos_file)],
            )
            self.assertEqual(res1["breaches_count"], 1)
            self.assertEqual(res1["dispatched_alerts_count"], 1)
            self.assertEqual(len(dispatched), 1)

            # Pass 2: Same breach condition -> alert_cache deduplicates, 0 new dispatches
            res2 = run_monitor_pass(
                account="TEST_DEDUP",
                alert=True,
                alert_cache=alert_cache,
                spot_fetcher=lambda s: 180.0,
                dispatch_fn=mock_dispatch,
                positions_loader=read_pos,
                analyses_loader=lambda: self.analyses_sample,
                account_files_discoverer=lambda acc: [(acc, temp_pos_file)],
            )
            self.assertEqual(res2["breaches_count"], 1)
            self.assertEqual(res2["dispatched_alerts_count"], 0)
            self.assertEqual(len(dispatched), 1)
        finally:
            if os.path.exists(temp_pos_file):
                os.remove(temp_pos_file)

    def test_monitor_daemon_max_iterations(self):
        """monitor_daemon terminates gracefully after max_iterations with output logging."""
        out = io.StringIO()
        monitor_daemon(
            interval=1,
            account="TEST_DAEMON",
            alert=False,
            max_iterations=1,
            spot_fetcher=lambda s: 200.0,
            output_stream=out,
        )
        output = out.getvalue()
        self.assertIn("GEX Level Breach Monitor active", output)
        self.assertIn("Checked", output)

    def test_monitor_cli_once_json(self):
        """CLI command 'monitor --once --json' executes cleanly and returns valid JSON."""
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            # We call cmd_monitor directly with mock args
            class MockArgs:
                command = "monitor"
                account = ""
                interval = 60
                alert = False
                once = True
                json = True
            gex_engine.cmd_monitor(MockArgs())
            output = sys.stdout.getvalue()
            data = json.loads(output)
            self.assertIn("timestamp", data)
            self.assertIn("total_positions_checked", data)
            self.assertIn("breaches", data)
        finally:
            sys.stdout = old_stdout


if __name__ == "__main__":
    unittest.main()
