"""
Unit tests for Milestone 5.10: Alert Hysteresis & Notification Rate-Limiting Engine.
Tests stateful alert tracking, hysteresis deadband re-arming, cooldown suppression,
sliding-window webhook rate limiting, daily digests, and persistence.
"""

import os
import tempfile
import unittest

from src.gex.screening.monitor import (
    AlertState,
    AlertStateManager,
    PositionBreachAlert,
    format_alert_digest,
    run_monitor_pass,
)


class TestAlertHysteresisAndRateLimiting(unittest.TestCase):
    def setUp(self):
        self.stop1_alert = PositionBreachAlert(
            symbol="AAPL",
            position_id="opt_aapl_1",
            position_type="option",
            breach_type="STOP1_NTRANS",
            spot=99.0,
            threshold=100.0,
            message="Spot below nTrans",
            action="Exit",
            account="TEST_ACC",
        )
        self.gex_target_alert = PositionBreachAlert(
            symbol="AAPL",
            position_id="opt_aapl_1",
            position_type="option",
            breach_type="PROFIT_TARGET_GEX",
            spot=110.5,
            threshold=110.0,
            message="Spot met +GEX",
            action="Take Profit",
            account="TEST_ACC",
        )

    def test_alert_state_serialization(self):
        """Verifies AlertState serialization and deserialization round-trip."""
        state = AlertState(
            account="TEST_ACC",
            position_id="opt_123",
            breach_type="STOP1_NTRANS",
            symbol="AAPL",
            last_dispatched_at=1000.0,
            last_dispatched_spot=98.5,
            alert_count_today=2,
            is_armed=False,
            session_date="2026-11-13",
        )
        d = state.to_dict()
        reconstructed = AlertState.from_dict(d)
        self.assertEqual(reconstructed.account, "TEST_ACC")
        self.assertEqual(reconstructed.position_id, "opt_123")
        self.assertEqual(reconstructed.last_dispatched_spot, 98.5)
        self.assertFalse(reconstructed.is_armed)
        self.assertEqual(reconstructed.alert_count_today, 2)

    def test_downside_breach_hysteresis_rearming(self):
        """Spot below nTrans fires and disarms. Spot hovering in deadband does not rearm; clearing deadband rearms."""
        mgr = AlertStateManager(cooldown_seconds=600.0, deadband_pct=0.0025)  # 0.25% deadband
        t0 = 1000.0

        # 1. Initial breach should dispatch
        should_send, reason = mgr.should_dispatch(self.stop1_alert, current_time=t0)
        self.assertTrue(should_send)
        self.assertEqual(reason, "OK")

        # Record dispatch
        mgr.record_dispatch(self.stop1_alert, current_time=t0)

        # 2. Immediate subsequent check while disarmed is suppressed
        should_send, reason = mgr.should_dispatch(self.stop1_alert, current_time=t0 + 10.0)
        self.assertFalse(should_send)
        self.assertIn("DISARMED_HYSTERESIS", reason)

        # 3. Spot price hovers back up to $100.10 (threshold is $100.00; deadband requires $100.25)
        analyses = {"AAPL": {"nTrans": 100.0, "pTrans": 105.0, "+GEX": 110.0}}
        mgr.update_spot_and_rearm("AAPL", 100.10, analyses)
        key = ("TEST_ACC", "opt_aapl_1", "STOP1_NTRANS")
        self.assertFalse(mgr.states[key].is_armed, "Should not re-arm when spot is inside deadband")

        # 4. Spot price clears deadband at $100.30 (>= 100.25) -> trigger re-arms
        mgr.update_spot_and_rearm("AAPL", 100.30, analyses)
        self.assertTrue(mgr.states[key].is_armed, "Should re-arm when spot exceeds threshold + deadband")

        # 5. After re-arming, if cooldown has NOT elapsed, cooldown suppresses
        should_send, reason = mgr.should_dispatch(self.stop1_alert, current_time=t0 + 300.0)
        self.assertFalse(should_send)
        self.assertIn("COOLDOWN_ACTIVE", reason)

        # 6. After cooldown (t0 + 601s), dispatch is approved
        should_send, reason = mgr.should_dispatch(self.stop1_alert, current_time=t0 + 601.0)
        self.assertTrue(should_send)
        self.assertEqual(reason, "OK")

    def test_upside_target_hysteresis_rearming(self):
        """Profit target fires and disarms. Re-arms only after pullback below threshold * (1 - deadband)."""
        mgr = AlertStateManager(cooldown_seconds=300.0, deadband_pct=0.005)  # 0.50% deadband ($110 * 0.995 = $109.45)
        t0 = 2000.0

        should_send, _ = mgr.should_dispatch(self.gex_target_alert, current_time=t0)
        self.assertTrue(should_send)
        mgr.record_dispatch(self.gex_target_alert, current_time=t0)

        # Pullback to $109.80 is not enough (needs <= 109.45)
        analyses = {"AAPL": {"+GEX": 110.0, "nTrans": 95.0}}
        mgr.update_spot_and_rearm("AAPL", 109.80, analyses)
        key = ("TEST_ACC", "opt_aapl_1", "PROFIT_TARGET_GEX")
        self.assertFalse(mgr.states[key].is_armed)

        # Pullback to $109.30 clears deadband -> re-arms
        mgr.update_spot_and_rearm("AAPL", 109.30, analyses)
        self.assertTrue(mgr.states[key].is_armed)

    def test_global_webhook_burst_rate_limiting(self):
        """Sliding-window rate limiter prevents bursting more than max_burst alerts in burst_window_seconds."""
        mgr = AlertStateManager(max_burst=3, burst_window_seconds=60.0, cooldown_seconds=0.0)
        t0 = 5000.0

        for i in range(3):
            alert_i = PositionBreachAlert(
                symbol=f"SYM{i}",
                position_id=f"pos_{i}",
                position_type="option",
                breach_type="STOP1_NTRANS",
                spot=90.0,
                threshold=100.0,
                message="Breach",
                action="Exit",
                account="ACC",
            )
            should_send, reason = mgr.should_dispatch(alert_i, current_time=t0 + i)
            self.assertTrue(should_send)
            mgr.record_dispatch(alert_i, current_time=t0 + i)

        # 4th alert within 60s window must be rate-limited
        alert_4 = PositionBreachAlert(
            symbol="SYM_BURST",
            position_id="pos_4",
            position_type="option",
            breach_type="STOP1_NTRANS",
            spot=90.0,
            threshold=100.0,
            message="Breach",
            action="Exit",
            account="ACC",
        )
        should_send, reason = mgr.should_dispatch(alert_4, current_time=t0 + 10.0)
        self.assertFalse(should_send)
        self.assertIn("RATE_LIMITED", reason)

        # Advancing time past the 60s window allows dispatch again
        should_send, reason = mgr.should_dispatch(alert_4, current_time=t0 + 65.0)
        self.assertTrue(should_send)

    def test_catastrophic_emergency_bypass(self):
        """STOP5_CATASTROPHIC is treated as emergency and bypasses hysteresis disarming."""
        mgr = AlertStateManager()
        stop5_alert = PositionBreachAlert(
            symbol="AAPL",
            position_id="opt_aapl_1",
            position_type="option",
            breach_type="STOP5_CATASTROPHIC",
            spot=90.0,
            threshold=-50.0,
            message="Loss -55%",
            action="Emergency Exit",
            account="TEST_ACC",
        )
        should_send, reason = mgr.should_dispatch(stop5_alert, current_time=100.0)
        self.assertTrue(should_send)
        self.assertEqual(reason, "EMERGENCY_CATASTROPHIC")

    def test_state_persistence_and_daily_digest(self):
        """Tests atomic state persistence to file and daily digest formatting."""
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
            temp_file = f.name

        try:
            mgr = AlertStateManager(state_file=temp_file)
            mgr.record_dispatch(self.stop1_alert, current_time=12345.0)

            # Check file was saved
            self.assertTrue(os.path.exists(temp_file))

            # New instance loads file
            mgr_loaded = AlertStateManager(state_file=temp_file)
            digest = mgr_loaded.get_daily_digest()
            self.assertEqual(digest["total_dispatched_today"], 1)
            self.assertEqual(len(digest["active_alerts"]), 1)
            self.assertEqual(digest["active_alerts"][0]["symbol"], "AAPL")

            # Formatted digest output
            formatted = format_alert_digest(digest)
            self.assertIn("Intraday Alert Digest", formatted)
            self.assertIn("AAPL", formatted)
            self.assertIn("STOP1_NTRANS", formatted)
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def test_run_monitor_pass_integration_with_state_manager(self):
        """run_monitor_pass seamlessly integrates with AlertStateManager."""
        dispatched = []
        def mock_dispatch(t, m):
            dispatched.append(t)
            return True

        positions_sample = {
            "options_positions": {
                "opt_1": {"Underlier": "AAPL", "Purchase Premium": 5.0, "Mark Price": 4.0}
            }
        }
        analyses_sample = {"AAPL": {"nTrans": 100.0, "pTrans": 105.0, "+GEX": 110.0}}

        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
            temp_pos_file = f.name

        try:
            alert_mgr = AlertStateManager(cooldown_seconds=100.0, deadband_pct=0.0025)

            # Pass 1: Spot $95 breaches nTrans $100 -> dispatches 1 alert
            res1 = run_monitor_pass(
                account="TEST",
                alert=True,
                alert_cache=alert_mgr,
                spot_fetcher=lambda s: 95.0,
                dispatch_fn=mock_dispatch,
                positions_loader=lambda p: positions_sample,
                analyses_loader=lambda: analyses_sample,
                account_files_discoverer=lambda acc: [(acc, temp_pos_file)],
            )
            self.assertEqual(res1["breaches_count"], 1)
            self.assertEqual(res1["dispatched_alerts_count"], 1)
            self.assertEqual(len(dispatched), 1)
            self.assertIn("digest", res1)

            # Pass 2: Spot still $95 -> hysteresis suppresses
            res2 = run_monitor_pass(
                account="TEST",
                alert=True,
                alert_cache=alert_mgr,
                spot_fetcher=lambda s: 95.0,
                dispatch_fn=mock_dispatch,
                positions_loader=lambda p: positions_sample,
                analyses_loader=lambda: analyses_sample,
                account_files_discoverer=lambda acc: [(acc, temp_pos_file)],
            )
            self.assertEqual(res2["breaches_count"], 1)
            self.assertEqual(res2["dispatched_alerts_count"], 0)
            self.assertEqual(len(dispatched), 1)
        finally:
            if os.path.exists(temp_pos_file):
                os.remove(temp_pos_file)


if __name__ == "__main__":
    unittest.main()
