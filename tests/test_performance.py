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

    def test_benchmark_calculate_annualized_vol(self):
        returns_list = [0.01 * (i % 5 - 2) for i in range(250)]
        iterations = 50000

        start_time = time.perf_counter()
        for _ in range(iterations):
            _ = gex_engine.calculate_annualized_vol(returns_list)
        elapsed = time.perf_counter() - start_time

        print(f"\n[BENCHMARK] Executed {iterations} calls to calculate_annualized_vol in {elapsed:.4f} seconds ({elapsed/iterations*1000:.4f} ms/call)")

    def test_benchmark_calculate_candidate_score(self):
        candidate = {
            'relative_options_volume': 15.0,
            'chg_pct': 3.5,
            'iv': 0.8,
            'rsi': 65.0,
            'macd_hist': 0.12
        }
        iterations = 100000

        start_time = time.perf_counter()
        for _ in range(iterations):
            _ = gex_engine.calculate_candidate_score(candidate)
        elapsed = time.perf_counter() - start_time

        print(f"\n[BENCHMARK] Executed {iterations} calls to calculate_candidate_score in {elapsed:.4f} seconds ({elapsed/iterations*1000:.4f} ms/call)")

    def test_benchmark_calculate_trade_journal(self):
        closed_data = {
            'closed_options': [
                {'Realized P&L ($)': '150.50', 'Entry Date': '2026-01-01', 'Close Date': '2026-01-10', 'Close Reason': 'TARGET', 'Target Mode': 'SWING'}
                for _ in range(50)
            ],
            'closed_stocks': [
                {'Realized P&L ($)': '-50.25', 'Entry Date': '2026-01-05', 'Close Date': '2026-01-12', 'Close Reason': 'STOP', 'Target Mode': 'DAY'}
                for _ in range(50)
            ]
        }
        iterations = 5000

        start_time = time.perf_counter()
        for _ in range(iterations):
            _ = gex_engine.calculate_trade_journal(closed_data)
        elapsed = time.perf_counter() - start_time

        print(f"\n[BENCHMARK] Executed {iterations} calls to calculate_trade_journal in {elapsed:.4f} seconds ({elapsed/iterations*1000:.4f} ms/call)")

if __name__ == "__main__":
    unittest.main()
