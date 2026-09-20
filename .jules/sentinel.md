## 2026-09-20 - Enforce Strict Account Scoping in Performance Cache Resolution
**Vulnerability:** `account_performance_file()` previously fell back to the unscoped global default performance cache (`PERFORMANCE_FILE`) when an invalid or non-alphanumeric account parameter (e.g., `"!!!"`) was provided, whereas `account_positions_file()` and `account_closed_positions_file()` raised `ValueError`.
**Learning:** Inconsistent sanitization error handling allowed invalid account specifiers to silently target and contaminate global default application state instead of failing fast.
**Prevention:** Always enforce identical input validation and fail-secure behavior (`ValueError`) across all account-scoped cache path helpers.
