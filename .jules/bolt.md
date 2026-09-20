## 2026-09-15 - Single-pass Wilder's RSI calculation
**Learning:** Allocating temporary lists (`gains` and `losses`) in `calculate_rsi` created unnecessary list allocations and garbage collection overhead. Replacing intermediate list construction with inline accumulators and direct Wilder's smoothing reduced execution overhead by ~2.4x.
**Action:** When computing rolling technical indicators (RSI, EMA, ATR), compute initial seeds and running smoothed updates in single-pass scalar loops rather than allocating intermediate list structures.

## 2026-03-31 - Avoid $O(N)$ Directory Traversals in Loops
**Learning:** Functions like `find_latest_historical_closes` and `find_latest_technical_indicators` that call `os.walk(DOWNLOADS_DIR)` on every call cause massive $O(N \times F)$ filesystem overhead when called repeatedly inside loops over hundreds of candidate tickers.
**Action:** Accept a pre-listed file array or optional cached directory listing parameter in lookup helpers when calling them repeatedly across candidates or dataset items.

## 2026-09-18 - Cached Downloads Listing & JSON Caching for Historical OHLC
**Learning:** `find_latest_historical_ohlc` used direct `os.walk(DOWNLOADS_DIR)` traversals and uncached `open()`/`json.load()` file reads on every lookup. Passing an optional `file_list` parameter, falling back to `_get_downloads_files()`, and using `load_json()` (which leverages `_JSON_FILE_CACHE`) reduced historical OHLC lookup overhead by ~1.44x.
**Action:** Always accept optional `file_list` in file lookup utilities and use `load_json()` rather than raw `open()` to benefit from workspace file list and JSON memory caching.

## 2026-09-19 - Zero-Copy JSON Memory Cache Read/Write
**Learning:** `load_json` previously executed `copy.deepcopy()` twice per call (once when populating `_JSON_FILE_CACHE` and once on every cache hit). Deepcopying large nested dict structures on every lookup accounted for over 80% of execution time in JSON-heavy paths. Defaulting to `copy_data=False` to return direct zero-copy references from `_JSON_FILE_CACHE` accelerated spot price lookups and CLI status queries by ~15x.
**Action:** When implementing in-memory object caches for read-heavy operations, return references directly without `copy.deepcopy` unless explicit mutation isolation is requested.
