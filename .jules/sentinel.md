## 2026-09-25 - All CLI subcommand file output and input parameters must enforce validate_safe_path before writing or processing
**Vulnerability:** Subcommands `cmd_snapshot` (`--output`) and `cmd_analyze` (`--inst-file`/`--quote-file`/`--hist-file`) as well as helper `_get_downloads_files` processed user-supplied output/input paths without `validate_safe_path()` checks, causing delayed or bypassed path traversal validation and misleading success outputs.
**Learning:** Delegating path traversal checks solely to atomic save/load utilities can cause subcommands to output success messages or proceed with execution even after file persistence fails due to path validation errors.
**Prevention:** Always perform `validate_safe_path()` checks at subcommand parameter extraction prior to executing file reads, writes, or printing execution status.

## 2026-09-24 - CLI subcommands must validate user-supplied file path parameters with validate_safe_path before os.path.exists checks
**Vulnerability:** Subcommands `cmd_sync_pnl` (`--pnl-file`), `cmd_prune_candidates` (`--watchlist-file`), `cmd_update_regime` (`--etf-file`), and `cmd_update_performance` (`--monthly-file`/`--pnl-file`) checked `os.path.exists()` on raw user-supplied input paths before calling `validate_safe_path()`, permitting file existence probing and delayed validation.
**Learning:** Checking file existence with `os.path.exists()` on raw user inputs before path traversal validation leaks file existence on arbitrary filesystem paths outside allowed roots.
**Prevention:** Always validate user-supplied file path arguments with `validate_safe_path()` immediately at the start of subcommand handlers before invoking `os.path.exists()` or other file operations.

## 2026-09-23 - Directory cleanup utilities must enforce path traversal validation before checking or deleting directories
**Vulnerability:** `cleanup_downloads()` accepted an unvalidated `downloads_dir` parameter directly into `os.path.exists()`, `os.listdir()`, and `shutil.rmtree()`, permitting directory deletion and traversal outside allowed root directories.
**Learning:** Directory deletion and retention utilities accepting directory parameters must validate input paths against allowed root directories before checking existence or purging directories.
**Prevention:** Always wrap input paths in `validate_safe_path()` before performing directory traversal or recursive deletion operations.

## 2026-09-22 - Subcommand base directories and directory listing functions must validate input paths with validate_safe_path
**Vulnerability:** `cmd_sync_positions` (`--base-dir`) and `list_download_files()` (`downloads_dir`) accepted user-controlled directory paths directly into `os.path.exists()`, `os.listdir()`, and `os.walk()` without calling `validate_safe_path()`, permitting directory traversal outside allowed root directories.
**Learning:** Directory listing utilities and CLI subcommands taking directory path parameters must validate input paths against allowed roots before performing filesystem traversal operations.
**Prevention:** Always call `validate_safe_path()` on user-supplied directory paths before inspecting or listing directory contents.

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
