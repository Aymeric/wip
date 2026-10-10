## 2026-09-22 - Raw file move and removal helpers in scan persistence must apply validate_safe_path
**Vulnerability:** `persist_new_scans()` performed raw `os.path.isfile()`, `shutil.copy2()`, and `os.remove()` operations on temporary file paths without applying `validate_safe_path()`.
**Learning:** File utility functions that move or delete raw scan downloads must apply `validate_safe_path()` to both source and target paths before performing filesystem mutations.
**Prevention:** Always validate both input source paths and computed output paths using `validate_safe_path()` before invoking file copying, moving, or deletion utilities.

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
