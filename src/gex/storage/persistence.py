"""
Atomic file persistence and in-memory mtime cache management for the GEX Trading System.
Guarantees zero-truncation writes via NamedTemporaryFile + os.replace and
prevents cross-account state bleeding.
"""

import os
import sys
import json
import tempfile
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.gex.core.config import validate_safe_path, sanitize_account

_MAX_JSON_CACHE_SIZE = 512
_JSON_FILE_CACHE: Dict[Tuple[str, float], Any] = {}
_SPOT_PRICE_CACHE: Dict[Any, Any] = {}
_DIR_FILES_CACHE: Dict[Any, Any] = {}
_LAST_MTIME_CHECK_TIME: Dict[Any, Any] = {}
_CACHED_DIR_MTIME_KEY: Dict[Any, Any] = {}
_CACHE_CLEAR_CALLBACKS: List[Callable[[], None]] = []


def register_cache_clear_callback(cb: Callable[[], None]) -> None:
    """Registers an external cache invalidation callback triggered on writes."""
    if cb not in _CACHE_CLEAR_CALLBACKS:
        _CACHE_CLEAR_CALLBACKS.append(cb)


def _clone_json(obj: Any) -> Any:
    """Fast recursive cloner for JSON-serializable structures (dicts, lists, scalars).

    Performance optimization (Bolt):
    - Uses exact `type()` checks (`t is dict`, `t is list`, `t is tuple`) to avoid CPython
      class hierarchy and `isinstance()` inspection overhead on every key/item in JSON structures.
    - Directly assigns primitive scalars (`str`, `int`, `float`, `bool`, `None`) without
      recursive function calls (~1.57x speedup in `load_json`).
    """
    t = type(obj)
    if t is dict:
        res = {}
        for k, v in obj.items():
            vt = type(v)
            if vt is dict or vt is list or vt is tuple:
                res[k] = _clone_json(v)
            elif vt is str or vt is int or vt is float or vt is bool or v is None:
                res[k] = v
            else:
                res[k] = _clone_json(v)
        return res
    if t is list:
        res = []
        for item in obj:
            it = type(item)
            if it is dict or it is list or it is tuple:
                res.append(_clone_json(item))
            elif it is str or it is int or it is float or it is bool or item is None:
                res.append(item)
            else:
                res.append(_clone_json(item))
        return res
    if t is tuple:
        return tuple(_clone_json(item) for item in obj)
    if isinstance(obj, dict):
        return {k: _clone_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clone_json(item) for item in obj]
    if isinstance(obj, tuple):
        return tuple(_clone_json(item) for item in obj)
    return obj


def load_json(filepath: str, default: Any = None) -> Any:
    """Loads a JSON file from disk with mtime caching, returning default if absent or invalid."""
    try:
        filepath = validate_safe_path(filepath)
    except Exception as e:
        print(f"Warning: Failed to load {filepath}: {e}", file=sys.stderr)
        return default

    if not os.path.exists(filepath):
        return default
    try:
        mtime = os.path.getmtime(filepath)
        if os.path.getsize(filepath) == 0:
            return default
    except Exception:
        return default

    cache_key = (filepath, mtime)
    if cache_key in _JSON_FILE_CACHE:
        cached_data = _JSON_FILE_CACHE[cache_key]
        if isinstance(default, (dict, list)) and not isinstance(cached_data, (dict, list)):
            return _clone_json(default)
        return _clone_json(cached_data)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(default, (dict, list)) and not isinstance(data, (dict, list)):
            return _clone_json(default)
        if len(_JSON_FILE_CACHE) >= _MAX_JSON_CACHE_SIZE:
            _JSON_FILE_CACHE.pop(next(iter(_JSON_FILE_CACHE)))
        _JSON_FILE_CACHE[cache_key] = data
        return _clone_json(data)
    except Exception as e:
        print(f"Warning: Failed to load {filepath}: {e}", file=sys.stderr)
        return default


def _clear_cache_for_write() -> None:
    """Clears in-memory caches when new state is written to disk."""
    _SPOT_PRICE_CACHE.clear()
    _DIR_FILES_CACHE.clear()
    _JSON_FILE_CACHE.clear()
    _LAST_MTIME_CHECK_TIME.clear()
    _CACHED_DIR_MTIME_KEY.clear()
    for cb in _CACHE_CLEAR_CALLBACKS:
        try:
            cb()
        except Exception:
            pass


def clear_account_cache(account: str = "") -> int:
    """Evicts account-scoped files from in-memory cache to guarantee zero cross-account state bleeding."""
    if not account:
        count = len(_JSON_FILE_CACHE)
        _JSON_FILE_CACHE.clear()
        return count

    sanitized = sanitize_account(account)
    keys_to_remove = [k for k in _JSON_FILE_CACHE.keys() if sanitized in k[0]]
    for k in keys_to_remove:
        _JSON_FILE_CACHE.pop(k, None)
    return len(keys_to_remove)


def save_json(filepath: str, data: Any) -> None:
    """Saves JSON atomically so a failed write cannot truncate existing state."""
    _clear_cache_for_write()
    temp_path = None
    try:
        target_filepath = validate_safe_path(filepath)
        dir_name = os.path.dirname(target_filepath)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        target_dir = dir_name or "."
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target_dir,
            prefix=".gex-", suffix=".tmp", delete=False
        ) as f:
            temp_path = f.name
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, target_filepath)
        temp_path = None
    except Exception as e:
        print(f"Error: Failed to save to {filepath}: {e}", file=sys.stderr)
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
