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
