## 2026-03-31 - Path Traversal Prevention in Account-Scoped File Resolution
**Vulnerability:** Account parameters in `account_positions_file`, `account_closed_positions_file`, and `account_performance_file` stripped invalid characters but returned default files or allowed path manipulation when invalid path traversal characters were passed.
**Learning:** Sanitizing inputs by stripping unwanted characters can inadvertently mask malicious path traversal sequences or produce unexpected default fallbacks when all characters are stripped.
**Prevention:** Validate input strings against strict allowlists (e.g., `^[A-Za-z0-9_-]+$`) and verify resolved absolute file paths using `os.path.abspath` to ensure they remain contained within the intended directory (`data/`).
