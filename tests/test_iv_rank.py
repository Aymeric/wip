"""
Unit tests for IV Rank, IV Percentile, and SQLite snapshot persistence.
Verifies Milestone 5.7 implementation.
"""

import math
import os
import sqlite3
import tempfile
import unittest

from src.gex.quant.indicators import (
    calculate_iv_rank,
    calculate_iv_percentile,
)
from src.gex.presentation.formatters import (
    format_iv_context,
)
from src.gex.core.models import (
    ScannerCandidate,
)
from src.gex.storage.db import (
    init_db,
    save_gex_snapshot,
    query_historical_ivs,
)


class TestIVRankAndPercentile(unittest.TestCase):
    """Tests for calculate_iv_rank and calculate_iv_percentile."""

    def test_iv_rank_basic(self):
        # 20 sessions between 20.0 and 40.0
        hist = [20.0 + i for i in range(21)]  # 20.0 to 40.0, 21 items
        # Min = 20.0, Max = 40.0
        # Current = 30.0 -> (30 - 20) / (40 - 20) * 100 = 50.0
        rank = calculate_iv_rank(30.0, hist)
        self.assertIsNotNone(rank)
        self.assertAlmostEqual(rank, 50.0, places=2)

    def test_iv_rank_bounds(self):
        hist = [20.0, 25.0, 30.0, 35.0, 40.0] * 5  # 25 items
        # At min
        self.assertAlmostEqual(calculate_iv_rank(20.0, hist), 0.0, places=2)
        # At max
        self.assertAlmostEqual(calculate_iv_rank(40.0, hist), 100.0, places=2)
        # Below historical min (e.g. 15.0) -> clamped to 0.0
        self.assertAlmostEqual(calculate_iv_rank(15.0, hist), 0.0, places=2)
        # Above historical max (e.g. 50.0) -> clamped to 100.0
        self.assertAlmostEqual(calculate_iv_rank(50.0, hist), 100.0, places=2)

    def test_iv_rank_identical_values(self):
        # All historical values equal
        hist = [30.0] * 25
        rank = calculate_iv_rank(30.0, hist)
        self.assertIsNotNone(rank)
        self.assertAlmostEqual(rank, 50.0, places=2)

    def test_iv_rank_insufficient_sample(self):
        # Fewer than min_lookback (default 20)
        hist = [25.0, 30.0, 35.0]
        self.assertIsNone(calculate_iv_rank(30.0, hist))
        self.assertIsNone(calculate_iv_rank(30.0, hist, min_lookback=20))
        # Custom min_lookback
        self.assertIsNotNone(calculate_iv_rank(30.0, hist, min_lookback=3))

    def test_iv_rank_invalid_inputs(self):
        hist = [20.0 + i for i in range(25)]
        self.assertIsNone(calculate_iv_rank(None, hist))
        self.assertIsNone(calculate_iv_rank(-5.0, hist))
        self.assertIsNone(calculate_iv_rank(0.0, hist))
        self.assertIsNone(calculate_iv_rank(float("nan"), hist))
        self.assertIsNone(calculate_iv_rank(float("inf"), hist))

    def test_iv_rank_filters_bad_history(self):
        # 15 valid + 10 invalid = 25 items, but only 15 valid -> should return None
        hist = [25.0] * 15 + [None, -1.0, 0.0, float("nan")] * 2
        self.assertIsNone(calculate_iv_rank(25.0, hist, min_lookback=20))

    def test_iv_percentile_basic(self):
        # 25 observations from 10 to 34
        hist = [float(10 + i) for i in range(25)]  # 10.0 to 34.0
        # Current = 20.0 -> values strictly below 20.0: 10, 11, 12, 13, 14, 15, 16, 17, 18, 19 (10 values)
        # Percentile: (10 / 25) * 100 = 40.0%
        pct = calculate_iv_percentile(20.0, hist)
        self.assertIsNotNone(pct)
        self.assertAlmostEqual(pct, 40.0, places=2)

    def test_iv_percentile_bounds(self):
        hist = [float(10 + i) for i in range(25)]
        # Below all values -> 0.0%
        self.assertAlmostEqual(calculate_iv_percentile(5.0, hist), 0.0, places=2)
        # Above all values -> 100.0%
        self.assertAlmostEqual(calculate_iv_percentile(50.0, hist), 100.0, places=2)

    def test_iv_percentile_insufficient_sample(self):
        hist = [25.0, 30.0]
        self.assertIsNone(calculate_iv_percentile(28.0, hist))

    def test_iv_percentile_invalid_inputs(self):
        hist = [float(20 + i) for i in range(25)]
        self.assertIsNone(calculate_iv_percentile(None, hist))
        self.assertIsNone(calculate_iv_percentile(-1.0, hist))
        self.assertIsNone(calculate_iv_percentile(0.0, hist))
        self.assertIsNone(calculate_iv_percentile(float("nan"), hist))


class TestFormatIVContext(unittest.TestCase):
    """Tests for format_iv_context presentation helper."""

    def test_format_complete(self):
        res = format_iv_context(35.2, 42.5, 55.0, history_len=252)
        self.assertEqual(res, "IV: 35.2% | IV Rank: 42.5 | IV Percentile: 55.0% (N=252 sessions)")

    def test_format_insufficient_sample(self):
        res = format_iv_context(35.2, None, None, history_len=5)
        self.assertEqual(res, "IV: 35.2% | IV Rank: UNKNOWN (N=5 < 20 sessions) | IV Percentile: UNKNOWN")

    def test_format_none_current(self):
        res = format_iv_context(None, None, None, history_len=0)
        self.assertEqual(res, "IV: N/A | IV Rank: N/A | IV Percentile: N/A")


class TestScannerCandidateIVFields(unittest.TestCase):
    """Tests ScannerCandidate dataclass with new IV rank/percentile attributes."""

    def test_defaults(self):
        cand = ScannerCandidate(symbol="AAPL", price=150.0, chg_pct=1.5)
        self.assertIsNone(cand.iv_rank)
        self.assertIsNone(cand.iv_percentile)

    def test_from_dict(self):
        data = {
            "symbol": "NVDA",
            "price": 120.0,
            "chg_pct": 2.5,
            "iv": 45.0,
            "iv_rank": 62.3,
            "iv_percentile": 71.0,
        }
        cand = ScannerCandidate.from_dict(data)
        self.assertEqual(cand.symbol, "NVDA")
        self.assertEqual(cand.iv_rank, 62.3)
        self.assertEqual(cand.iv_percentile, 71.0)


class TestDatabaseIVSnapshots(unittest.TestCase):
    """Tests SQLite persistence of daily IV snapshots and historical retrieval."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test_gex.db")

    def tearDown(self):
        if os.path.exists(self.tmp_dir):
            import shutil
            shutil.rmtree(self.tmp_dir)

    def test_save_and_query_historical_ivs(self):
        init_db(self.db_path)

        # Save multiple snapshots for AAPL across different dates
        dates_and_ivs = [
            ("2026-01-01", 25.5),
            ("2026-01-02", 26.0),
            ("2026-01-03", 24.8),
            ("2026-01-04", 28.2),
        ]
        for s_date, iv in dates_and_ivs:
            save_gex_snapshot(
                symbol="AAPL",
                spot=150.0,
                ptrans=148.0,
                ntrans=145.0,
                gex=155.0,
                cotmp=146.0,
                iv=iv,
                session_date=s_date,
                db_path=self.db_path,
            )

        # Query back
        ivs = query_historical_ivs("AAPL", lookback_days=30, db_path=self.db_path)
        self.assertEqual(len(ivs), 4)
        self.assertEqual(ivs, [25.5, 26.0, 24.8, 28.2])

    def test_migration_from_legacy_db(self):
        # Create legacy table without `iv` column
        conn = sqlite3.connect(self.db_path)
        with conn:
            conn.execute("""
                CREATE TABLE gex_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    session_date TEXT NOT NULL,
                    spot REAL NOT NULL,
                    ptrans REAL,
                    ntrans REAL,
                    call_wall REAL,
                    put_wall REAL,
                    total_call_gex REAL,
                    total_put_gex REAL,
                    net_gex REAL,
                    UNIQUE(symbol, session_date)
                )
            """)
            conn.execute("""
                INSERT INTO gex_snapshots (symbol, session_date, spot, ptrans, ntrans, call_wall, put_wall, net_gex)
                VALUES ('MSFT', '2026-01-01', 400.0, 395.0, 390.0, 410.0, 392.0, 1000.0)
            """)
        conn.close()

        # Run init_db which must automatically run migration ALTER TABLE ADD COLUMN iv REAL
        init_db(self.db_path)

        # Insert new snapshot with iv
        save_gex_snapshot(
            symbol="MSFT",
            spot=405.0,
            ptrans=400.0,
            ntrans=395.0,
            gex=415.0,
            cotmp=398.0,
            iv=32.5,
            session_date="2026-01-02",
            db_path=self.db_path,
        )

        ivs = query_historical_ivs("MSFT", lookback_days=30, db_path=self.db_path)
        self.assertEqual(len(ivs), 1)
        self.assertEqual(ivs[0], 32.5)


if __name__ == "__main__":
    unittest.main()
