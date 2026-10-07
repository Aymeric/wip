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

    def test_benchmark_discover_earnings_date(self):
        symbols = ['SHOP', 'OKLO', 'AVGO', 'TSLA', 'MARA', 'ASAN', 'BNTX', 'CRWD', 'TEAM', 'ACVA', 'KNSA', 'LASR', 'SUPN', 'NBIS', 'AAPL', 'MSFT', 'GOOG']
        iterations = 500
        total_calls = len(symbols) * iterations

        start_time = time.perf_counter()
        for _ in range(iterations):
            for sym in symbols:
                _ = gex_engine.discover_earnings_date(sym)
        elapsed = time.perf_counter() - start_time

        print(f"\n[BENCHMARK] Executed {total_calls} calls to discover_earnings_date in {elapsed:.4f} seconds ({elapsed/total_calls*1000:.4f} ms/call)")

    def test_benchmark_get_monthly_realized_pnl(self):
        pnl_data = {
            'trades': [
                {'timestamp': f'2026-0{i % 9 + 1}-{i % 28 + 1:02d}T10:00:00Z', 'realized_gain': 100.0}
                for i in range(1000)
            ]
        }
        import tempfile, json
        with tempfile.NamedTemporaryFile('w', delete=False, suffix='.json') as f:
            json.dump(pnl_data, f)
            tmp_path = f.name

        iterations = 500
        start_time = time.perf_counter()
        for _ in range(iterations):
            _ = gex_engine.get_monthly_realized_pnl(50000.0, pnl_file=tmp_path)
        elapsed = time.perf_counter() - start_time

        os.remove(tmp_path)
        print(f"\n[BENCHMARK] Executed {iterations} calls to get_monthly_realized_pnl in {elapsed:.4f} seconds ({elapsed/iterations*1000:.4f} ms/call)")

    def test_benchmark_select_best_option(self):
        expirations = ['2026-04-17', '2026-05-15', '2026-06-19', '2026-07-17']
        inst_data = [
            {
                'id': f'opt_{i}',
                'strike_price': str(100.0 + (i % 30) * 0.5),
                'type': 'call' if i % 2 == 0 else 'put',
                'expiration_date': expirations[i % len(expirations)],
                'chain_symbol': 'TEST'
            } for i in range(500)
        ]
        quotes_data = [
            {
                'instrument_id': f'opt_{i}',
                'bid_price': '1.50',
                'ask_price': '1.60',
                'open_interest': 1000,
                'volume': 500,
                'delta': '0.45',
                'gamma': '0.05',
                'implied_volatility': '0.30'
            } for i in range(500)
        ]
        iterations = 1000

        start_time = time.perf_counter()
        for _ in range(iterations):
            _ = gex_engine.select_best_option(inst_data, quotes_data, 100.0, 110.0, today_override='2026-03-31', earnings_date='2026-04-20')
        elapsed = time.perf_counter() - start_time

        print(f"\n[BENCHMARK] Executed {iterations} calls to select_best_option in {elapsed:.4f} seconds ({elapsed/iterations*1000:.4f} ms/call)")

if __name__ == "__main__":
    unittest.main()
