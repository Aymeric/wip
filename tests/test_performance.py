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

    def test_benchmark_candidate_indicator_lookups(self):
        symbols = ['SHOP', 'OKLO', 'AVGO', 'TSLA', 'MARA', 'ASAN', 'BNTX', 'CRWD', 'TEAM', 'ACVA', 'KNSA', 'LASR', 'SUPN', 'NBIS', 'AAPL', 'MSFT', 'GOOG']
        raw_files = gex_engine.list_download_files(gex_engine.DOWNLOADS_DIR)
        file_tuples = [(f, f.rsplit('/', 1)[-1].rsplit('\\', 1)[-1].upper()) for f in raw_files]
        iterations = 20
        total_lookups = len(symbols) * iterations * 2

        start_time = time.perf_counter()
        for _ in range(iterations):
            for sym in symbols:
                _ = gex_engine.find_latest_historical_closes(sym, file_list=file_tuples)
                _ = gex_engine.find_latest_technical_indicators(sym, file_list=file_tuples)
        elapsed = time.perf_counter() - start_time

        print(f"\n[BENCHMARK] Executed {total_lookups} candidate indicator lookups in {elapsed:.4f} seconds ({elapsed/total_lookups*1000:.4f} ms/lookup)")

if __name__ == "__main__":
    unittest.main()
