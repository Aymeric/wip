import time
import unittest
import os
import sys

# Ensure src/ is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
import gex_engine

class TestPerformanceBenchmark(unittest.TestCase):
    def test_benchmark_find_latest_underlier_spot(self):
        symbols = ['SHOP', 'OKLO', 'AVGO', 'TSLA', 'MARA', 'ASAN', 'BNTX', 'CRWD', 'TEAM', 'ACVA', 'KNSA', 'LASR', 'SUPN', 'NBIS', 'AAPL', 'MSFT', 'GOOG']
        iterations = 30
        total_calls = len(symbols) * iterations

        start_time = time.perf_counter()
        for _ in range(iterations):
            for sym in symbols:
                _ = gex_engine.find_latest_underlier_spot(sym)
        elapsed = time.perf_counter() - start_time

        print(f"\n[BENCHMARK] Executed {total_calls} calls to find_latest_underlier_spot in {elapsed:.4f} seconds ({elapsed/total_calls*1000:.4f} ms/call)")

    def test_benchmark_calculate_atr(self):
        highs = [100.0 + i * 0.5 for i in range(300)]
        lows = [98.0 + i * 0.5 for i in range(300)]
        closes = [99.0 + i * 0.5 for i in range(300)]
        iterations = 10000

        start_time = time.perf_counter()
        for _ in range(iterations):
            _ = gex_engine.calculate_atr(highs, lows, closes, period=14)
        elapsed = time.perf_counter() - start_time

        print(f"\n[BENCHMARK] Executed {iterations} calls to calculate_atr in {elapsed:.4f} seconds ({elapsed/iterations*1000:.4f} ms/call)")

    def test_benchmark_calculate_bollinger_bands(self):
        closes = [100.0 + (i % 7) * 0.5 - (i % 3) * 0.2 for i in range(250)]
        iterations = 50000

        start_time = time.perf_counter()
        for _ in range(iterations):
            _ = gex_engine.calculate_bollinger_bands(closes, period=20, num_std=2.0)
        elapsed = time.perf_counter() - start_time

        print(f"\n[BENCHMARK] Executed {iterations} calls to calculate_bollinger_bands in {elapsed:.4f} seconds ({elapsed/iterations*1000:.4f} ms/call)")

if __name__ == "__main__":
    unittest.main()
