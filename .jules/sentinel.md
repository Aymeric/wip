## 2026-09-22 - Auxiliary file reading functions must route through load_json to guarantee path traversal checks
**Vulnerability:** Additional helper functions and subcommands (`cmd_analyze`, `get_monthly_realized_pnl`, `discover_earnings_date`, `persist_new_scans`) opened files using raw `open()` and `json.load()`, bypassing `load_json()` path traversal checks.
**Learning:** Raw `open()` calls in auxiliary file reading routines bypass path traversal protection unless systematically converted to use `load_json()`.
**Prevention:** Always use `load_json()` for all JSON file read operations across all subcommands and helper routines to enforce `validate_safe_path()`.

## 2026-09-21 - CLI subcommands must route file reading through load_json to enforce path traversal validation
**Vulnerability:** Several CLI subcommands (`prune-candidates`, `update-candidates`, `update-regime`) used raw `open()` and `json.load()` directly on user-controlled input paths, bypassing `load_json()` and `validate_safe_path()` path traversal checks.
**Learning:** Having a safe helper function like `load_json()` is ineffective if subcommand handlers open raw files directly without routing through the helper.
**Prevention:** Always use `load_json()` for reading JSON files across all CLI subcommands to guarantee `validate_safe_path()` validation is applied.

## 2026-09-20 - File read helpers must enforce path traversal validation alongside write helpers
**Vulnerability:** `load_json` omitted calling `validate_safe_path()` on input file paths while `save_json()` enforced it, leaving JSON file reading vulnerable to path traversal outside repository and temp directories.
**Learning:** Helper functions performing file I/O operations must symmetrically validate input paths against allowed root directories for both reads and writes.
**Prevention:** Always call `validate_safe_path()` at the top of file loading/reading utilities and include module root directory in allowed roots to prevent path traversal and false positives.

## 2026-09-19 - Account scoping functions must strictly validate input to avoid silent fallback to global cache
**Vulnerability:** Inconsistent account parameter sanitization in `account_performance_file()` caused non-alphanumeric account inputs to silently fall back to default global `data/performance.json` instead of raising `ValueError`.
**Learning:** Functions that scope cache paths by account parameters must consistently reject invalid account identifiers rather than defaulting to shared global files.
**Prevention:** Always raise `ValueError` on empty normalized account strings when an account parameter was explicitly provided.
