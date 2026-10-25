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

## 2026-10-05 - Single-Pass Scalar Search Loops for Option Level Extraction
**Learning:** `derive_gex_profile` used intermediate list comprehensions (`at_below_spot_puts`, `below_ptrans_puts`, `at_above_spot_calls`), lambda tuple key extractions in `max()`, and set union allocations (`set(...) | set(...)`) to calculate pTrans, nTrans, +GEX, and nearest strike levels. Replacing list allocations and lambda functions with single-pass scalar search loops yielded a ~1.16x execution speedup.
**Action:** In option chain level derivation functions, find extremum strike levels using single-pass iterative searches with scalar comparison tuples `(oi, strike)` rather than constructing intermediate list comprehensions and passing lambda keys to `max()`.

## 2026-10-06 - Single-Pass `date.fromisoformat` for Monthly Realized P&L Calculations
**Learning:** `get_monthly_realized_pnl` ran duplicate iteration passes over trade history and called slow `datetime.strptime` on every trade timestamp to find the reference date and filter 30-day gains. Replacing `datetime.strptime` with `date.fromisoformat` and tracking the latest trade date inline during a single tuple-parsing pass yielded a ~12.4x execution speedup.
**Action:** When computing windowed aggregate stats over timestamped trade records, parse ISO date strings once with `date.fromisoformat` and track extremum dates inline in a single iteration pass.

## 2026-10-10 - Precomputed Expiration DTE Weights & Sorted Tuple Zero-Crossing Iteration
**Learning:** `derive_gex_profile` executed `date.fromisoformat`, `date.today()`, `max()`, and `math.sqrt()` inside the option quotes loop for every contract, incurring hundreds of thousands of redundant function calls per execution. Precalculating `dte_val` and `dte_weight` per expiration date when building `inst_map` prior to quote iteration eliminated over 2.5 million function calls per 1000 runs. Furthermore, sorting `(strike, gex)` tuples once in `find_flip_strikes` eliminated repeated dictionary key lookups inside zero-crossing loops, yielding an overall ~2.2x speedup in `derive_gex_profile`.
**Action:** When iterating over contract quotes or multi-instrument feeds, hoist date parsing and time-decay/weight computations to the instrument level or cache them by expiration date to avoid redundant system calls in inner loops.

## 2026-10-14 - Pre-filtered Target Strikes & Pre-computed Sort Keys in Option Selection
**Learning:** `select_best_option` previously sorted all candidate expiration dates with `list.sort()`, evaluated `strike >= gex_target` after performing dictionary quote parsing, and sorted eligible contracts using a lambda function that repeatedly evaluated dict keys (`x['tier']`, `x['delta']`, etc.). Using `min()` to select target expirations, checking `strike >= gex_target` before quote lookup, and pre-computing sort key tuples during list construction yielded a ~1.11x speedup in `select_best_option`.
**Action:** In multi-criteria selection pipelines, filter out-of-bounds candidates before quote dictionary lookups and pre-compute sort key tuples during dictionary construction to avoid lambda attribute access overhead.

## 2026-10-21 - Precomputed Scaling Constant & Numerically Stable Two-Pass Variance
**Learning:** `calculate_annualized_vol` recomputed `math.sqrt(252) * 100.0` on every invocation. Hoisting `math.sqrt(252) * 100.0` into a module-level constant (`_SQRT_252_X_100`) while preserving numerically stable two-pass scalar variance calculation (`diff = x - mean_ret; sum_sq_diff += diff * diff`) avoided redundant constant math and function call overhead without risking catastrophic floating-point cancellation.
**Action:** When performing windowed statistical return calculations, hoist invariant scaling constants out of function execution scope while preserving numerically stable two-pass variance formulas.

## 2026-10-28 - Deferred Grouping Rounding & Local Date Parsing Caching in Journal Aggregation
**Learning:** `calculate_trade_journal` executed `dict.setdefault()` and inner `round()` calls on every trade record and re-parsed duplicate ISO date strings. Introducing a local `date_cache` dictionary and accumulating raw floating-point P&L in group buckets before applying a single deferred `round(..., 2)` pass over bucket values yielded a ~2.0x execution speedup (~0.388 ms/call to ~0.191 ms/call).
**Action:** In data aggregation pipelines over grouped dictionaries, accumulate raw floating-point values during record iteration and defer rounding formatting to a single post-processing loop over grouped bucket values.

## 2026-11-04 - Eliminate `abs()` and `max()` Overhead via Inline Scalar Conditionals in True Range
**Learning:** `calculate_atr` called `abs()` twice per bar to compute price differences `abs(h - c_prev)` and `abs(l - c_prev)` before performing multi-variable comparison checks. Since `True Range = max(h, c_prev) - min(l, c_prev)`, replacing `abs()` and `max()` function calls with inline scalar conditional branches (`if c_prev > h: tr = c_prev - l; elif c_prev < l: tr = h - c_prev; else: tr = h - l`) eliminated CPython built-in function call overhead entirely, yielding a ~1.89x execution speedup (0.1042 ms/call to 0.0551 ms/call).
**Action:** In high-frequency price loop calculations (such as ATR or range volatility), eliminate `abs()` and `max()` built-in function calls by using mathematically equivalent inline scalar conditional branches.

## 2026-11-04 - Fast String Type Check & Direct Dict Access in Option Contract Selection
**Learning:** `select_best_option` called `str(opt_type).lower()` on every instrument, used `dict.setdefault()` during expiration grouping, and performed `.get("quote", q_item)` fallback lookups across all quote payloads. Checking equality against `"call"` and `"CALL"` before converting strings, using direct dict key checks, and optimizing inner quote extraction eliminated hundreds of thousands of redundant function calls, improving `select_best_option` performance from ~1.01 ms/call to ~0.88 ms/call (~1.14x speedup).
**Action:** In dictionary parsing loops, check exact expected string literals before invoking `.lower()`, and use direct key membership checks or single lookups rather than chaining `.get()` with fallback defaults.

## 2026-11-05 - Optimistic Direct Key Subscripting & C-Level Sorting in GEX Profile Derivation
**Learning:** `derive_gex_profile` executed millions of dictionary `.get()` method lookups per run (`q.get("open_interest")`, `q.get("gamma")`, `strike_put_oi.get(...)`), while `find_flip_strikes` constructed temporary tuples `[(float(k), float(v)) ...]` and sorted them using a Python lambda key (`sort(key=lambda x: x[0])`). Using `try...except KeyError` optimistic key subscripting for standard quote payloads, replacing double `.get()` lookups with `if strike in strike_put_oi:` membership checks, and applying direct C-level Timsort (`items.sort()`) reduced execution time from ~1.52 ms/call to ~1.38 ms/call (~1.10x overall speedup).
**Action:** In high-volume quote processing pipelines, use optimistic direct key indexing with fallback error handling instead of repeated `.get()` calls, and sort pre-constructed 2-tuples directly without passing Python lambda key functions.
