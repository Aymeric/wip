"""
Configuration, path resolution, and system constants for the GEX Trading System.
Provides deterministic directory paths, account-scoped file resolution,
security path traversal guards, and screener baseline thresholds.
"""

import os
import re
import tempfile
from typing import List, Optional


# Resolve repository root independent of caller working directory
REPOSITORY_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA_DIR = os.path.join(REPOSITORY_ROOT, "data")
REGIME_FILE = os.path.join(REPOSITORY_ROOT, "data", "regime.json")
ANALYSES_FILE = os.path.join(REPOSITORY_ROOT, "data", "ticker_analyses.json")
OPTIONS_FILE = os.path.join(REPOSITORY_ROOT, "data", "active_positions.json")
CANDIDATES_FILE = os.path.join(REPOSITORY_ROOT, "data", "candidate_stocks.json")
PERFORMANCE_FILE = os.path.join(REPOSITORY_ROOT, "data", "performance.json")
DOWNLOADS_DIR = os.path.join(REPOSITORY_ROOT, "data", "downloads")
SENTIMENT_FILE = os.path.join(REPOSITORY_ROOT, "data", "reddit_sentiment.json")
WORKFLOW_STATE_FILE = os.path.join(REPOSITORY_ROOT, "data", "workflow_state.json")
DEFAULT_DB_FILE = os.path.join(REPOSITORY_ROOT, "data", "trades.db")
DEFAULT_SIZING_THRESHOLD = 10000.0  # Portfolio Net Liq threshold for strict percentage sizing

# Standard Mechanical Screener Baseline Filter Constants
MIN_PRICE = 5.0
MAX_PRICE = 1000.0
MIN_VOLUME = 200000
MIN_CHG_PCT = 0.3
MIN_MARKET_CAP = 1000000000


def validate_safe_path(filepath: str, allowed_roots: Optional[List[str]] = None) -> str:
    """Ensure filepath resolves strictly within allowed roots (defaults to REPOSITORY_ROOT and temp dir)."""
    if allowed_roots is None:
        allowed_roots = [REPOSITORY_ROOT, tempfile.gettempdir()]

    if not os.path.isabs(filepath):
        abs_target = os.path.abspath(os.path.join(REPOSITORY_ROOT, filepath))
    else:
        abs_target = os.path.abspath(filepath)

    for root in allowed_roots:
        if not root:
            continue
        abs_root = os.path.abspath(root)
        try:
            if os.path.commonpath([abs_root, abs_target]) == abs_root:
                return abs_target
        except ValueError:
            continue

    raise ValueError(f"Path traversal detected: '{filepath}' is outside allowed directories")


def sanitize_account(account: str = "") -> str:
    """Sanitize account identifier string to prevent path traversal or invalid file paths."""
    if not account:
        return ""
    normalized_account = re.sub(r"[^A-Za-z0-9_-]", "", str(account))
    if not re.search(r"[A-Za-z0-9]", normalized_account):
        raise ValueError("account must contain at least one alphanumeric character")
    return normalized_account


def account_performance_file(account: str = "") -> str:
    """Return the account-scoped performance cache path."""
    normalized_account = sanitize_account(account)
    if not normalized_account:
        return PERFORMANCE_FILE
    return os.path.join(REPOSITORY_ROOT, "data", f"performance_{normalized_account}.json")


def account_positions_file(account: str = "") -> str:
    """Return the active-position cache path, scoped when an account is supplied."""
    normalized_account = sanitize_account(account)
    if not normalized_account:
        return OPTIONS_FILE
    return os.path.join(REPOSITORY_ROOT, "data", f"active_positions_{normalized_account}.json")


def account_closed_positions_file(account: str = "") -> str:
    """Return the closed-position cache path, scoped when an account is supplied."""
    normalized_account = sanitize_account(account)
    if not normalized_account:
        return os.path.join(os.path.dirname(OPTIONS_FILE), "closed_positions.json")
    return os.path.join(REPOSITORY_ROOT, "data", f"closed_positions_{normalized_account}.json")
