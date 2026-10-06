## 2026-09-15 - Single-pass Wilder's RSI calculation
**Learning:** Allocating temporary lists (`gains` and `losses`) in `calculate_rsi` created unnecessary list allocations and garbage collection overhead. Replacing intermediate list construction with inline accumulators and direct Wilder's smoothing reduced execution overhead by ~2.4x.
**Action:** When computing rolling technical indicators (RSI, EMA, ATR), compute initial seeds and running smoothed updates in single-pass scalar loops rather than allocating intermediate list structures.

## 2026-03-31 - Avoid $O(N)$ Directory Traversals in Loops
**Learning:** Functions like `find_latest_historical_closes` and `find_latest_technical_indicators` that call `os.walk(DOWNLOADS_DIR)` on every call cause massive $O(N \times F)$ filesystem overhead when called repeatedly inside loops over hundreds of candidate tickers.
**Action:** Accept a pre-listed file array or optional cached directory listing parameter in lookup helpers when calling them repeatedly across candidates or dataset items.

## 2026-09-18 - Cached Downloads Listing & JSON Caching for Historical OHLC
**Learning:** `find_latest_historical_ohlc` used direct `os.walk(DOWNLOADS_DIR)` traversals and uncached `open()`/`json.load()` file reads on every lookup. Passing an optional `file_list` parameter, falling back to `_get_downloads_files()`, and using `load_json()` (which leverages `_JSON_FILE_CACHE`) reduced historical OHLC lookup overhead by ~1.44x.
**Action:** Always accept optional `file_list` in file lookup utilities and use `load_json()` rather than raw `open()` to benefit from workspace file list and JSON memory caching.

## 2026-09-19 - Fast Recursive JSON Cloning & Single-Pass Indicator Calculations
**Learning:** Standard library `copy.deepcopy` used in JSON cache lookups incurs massive Python runtime object introspection and memoization overhead. Replacing `copy.deepcopy` with a lightweight recursive dict/list cloner (`_clone_json`) yielded a ~2.4x speedup in `load_json`. Additionally, reusing computed MACD series in `check_technical_alerts` eliminated duplicate EMA calculations for a ~1.3x speedup.
**Action:** Use tailored recursive cloners for plain JSON structures rather than `copy.deepcopy`, and store freshly parsed `json.load()` objects directly into cache without deepcopying on cache miss.

## 2026-09-20 - Single-pass Wilder's ATR calculation
**Learning:** Allocating intermediate list structures (`true_ranges`), slicing (`true_ranges[:period]`), and repeated function call overhead of `max()` in `calculate_atr` caused significant execution latency. Replacing list construction and `max()` calls with inline comparisons and direct Wilder's smoothing yielded a ~2.8x execution speedup.
**Action:** In rolling technical indicator calculations (ATR, RSI, EMA), avoid intermediate array allocations and built-in function call overhead inside high-frequency price loops by using scalar running accumulators and inline comparisons.

## 2026-09-24 - Pre-indexed Basename Tuples in Directory Caches
**Learning:** Repeated calls to `os.path.basename(f).upper()` across cached directory lists in lookup functions (`find_latest_historical_closes`, `find_latest_underlier_spot`, `find_latest_technical_indicators`) created significant string manipulation and C-extension function call overhead. Storing pre-indexed `(filepath, filename_upper)` tuples directly in `_get_downloads_files()`'s `_DIR_FILES_CACHE` reduced string comp lookups by ~12x and boosted `find_latest_underlier_spot` execution speed by ~3.4x.
**Action:** When caching filesystem directory listings for repeated string pattern matching, pre-compute and store normalized filename metadata (e.g. `(path, basename_upper)`) directly in the cache structure.

## 2026-09-27 - Replace Generator Expressions with Scalar Loops in Window Statistics
**Learning:** Using Python generator expressions inside built-in aggregators like `sum((closes[i] - mean)**2 for ...)` incurs CPython generator frame allocation, iteration protocol, and opcode dispatch overhead per element. Replacing generator expressions with explicit scalar accumulator loops (`for i in range(...): diff = closes[i] - mean; sum_sq_diff += diff * diff`) in `calculate_bollinger_bands` yielded a ~1.8x execution speedup.
**Action:** In statistical and mathematical window calculations, prefer explicit scalar accumulation loops over generator expressions inside `sum()` to eliminate generator frame allocation overhead.

## 2026-09-28 - Scalar Accumulation for Volatility and Candidate Scoring
**Learning:** `calculate_candidate_score` allocated temporary lists (`available`) and ran generator expression `sum()` calls, while `calculate_annualized_vol` ran generator expressions with exponentiation `** 2`. Replacing list allocations and generator `sum()` with scalar accumulation loops and direct multiplication (`diff * diff`) yielded ~3.0x and ~2.3x speedups respectively.
**Action:** In scoring and statistical return metrics, perform normalization and weight accumulation in a single inline loop rather than building intermediate lists or passing generator expressions to `sum()`.

## 2026-09-29 - ISO Date Parsing & Single-Pass Journal Aggregation
**Learning:** `calculate_trade_journal` used `datetime.strptime` for date string parsing and multi-pass list comprehensions to compute trade metrics across closed options/stocks. Replacing `datetime.strptime` with `date.fromisoformat` (~27x faster per date pair) and consolidating multi-pass filtering into a single scalar loop yielded a ~6.5x execution speedup.
**Action:** Prefer `date.fromisoformat` over `datetime.strptime` for ISO formatted date strings (`YYYY-MM-DD`), and accumulate grouped statistics in a single iteration pass rather than making repeated list comprehension passes over dataset items.

## 2026-09-30 - Direct Scalar EMA Accumulation for Point MACD Estimates
**Learning:** `calculate_macd` previously called `calculate_macd_series` and `calculate_ema`, allocating full time-series lists (`macd_line` and `signal_line`) even though candidate screening and technical filtering only need the latest scalar MACD, Signal, and Histogram values. Computing fast/slow EMAs and the signal line EMA directly via scalar variables eliminated list allocations and provided a ~1.27x execution speedup.
**Action:** When computing point technical indicators for filtering or screening where only the latest value is needed, use scalar accumulators instead of allocating full time-series lists.

## 2026-10-01 - Early Filtering & Fast ISO Date Parsing in Option Selection
**Learning:** `select_best_option` created full dictionary objects for all option contract instruments (including puts and non-target option types) and used `datetime.strptime` for date string comparisons. Pre-filtering target call options during the initial instrument sweep to store minimal 2-tuples `(strike, exp_str)` and switching date parsing to `date.fromisoformat` yielded a ~1.4x execution speedup.
**Action:** In option chain analysis pipelines, pre-filter non-candidate instrument types during the first pass and use `date.fromisoformat` for ISO date strings (`YYYY-MM-DD`).

<<<<<<< Updated upstream
## 2026-10-05 - Single-Pass Scalar Search Loops for Option Level Extraction
**Learning:** `derive_gex_profile` used intermediate list comprehensions (`at_below_spot_puts`, `below_ptrans_puts`, `at_above_spot_calls`), lambda tuple key extractions in `max()`, and set union allocations (`set(...) | set(...)`) to calculate pTrans, nTrans, +GEX, and nearest strike levels. Replacing list allocations and lambda functions with single-pass scalar search loops yielded a ~1.16x execution speedup.
**Action:** In option chain level derivation functions, find extremum strike levels using single-pass iterative searches with scalar comparison tuples `(oi, strike)` rather than constructing intermediate list comprehensions and passing lambda keys to `max()`.
=======
## 2026-10-04 - Fast Option & Earnings File Discovery via Pre-Indexed Metadata & JSON Caching
**Learning:** `find_latest_option_files` and `discover_earnings_date` performed repeated un-cached `os.walk(DOWNLOADS_DIR)` traversals and raw `open()`/`json.load()` calls during ticker analysis. Accepting an optional `file_list` parameter, leveraging `_get_downloads_files()`'s pre-indexed upper-case metadata (`file_upper`), early exiting when all option files are found, and using `load_json()` memory caching yielded a ~5.7x speedup for option file discovery and ~5.0x speedup for earnings date discovery.
**Action:** In file discovery utilities, accept an optional `file_list` parameter, leverage pre-indexed upper-case tuple metadata for fast string matching, exit early once targets are found, and use `load_json()` for file reading.
>>>>>>> Stashed changes
