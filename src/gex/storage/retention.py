"""
Retention policy enforcement and dated cache invalidation for the GEX Trading System.
Prunes dated raw Robinhood API downloads and cleans temporary scratch directories.
"""

import os
import re
import shutil
from datetime import datetime
from typing import Optional

from src.gex.core.config import DOWNLOADS_DIR, validate_safe_path


def cleanup_downloads(days: int = 7, downloads_dir: Optional[str] = None) -> int:
    """Removes dated download folders older than the retention period and stale tmp folders.

    Args:
        days: Retention horizon in days. Folders older than this are purged.
        downloads_dir: Directory to clean, defaults to DOWNLOADS_DIR.

    Returns:
        Number of purged directories.
    """
    target_dir = downloads_dir or DOWNLOADS_DIR
    try:
        target_dir = validate_safe_path(target_dir)
    except ValueError:
        return 0

    now = datetime.now()
    removed_count = 0

    if not os.path.exists(target_dir):
        print("No downloads directory found.")
        return 0

    for item in os.listdir(target_dir):
        item_path = os.path.join(target_dir, item)
        if os.path.isdir(item_path):
            # Check if directory name is a date YYYYMMDD
            if re.match(r"^\d{8}$", item):
                try:
                    dir_date = datetime.strptime(item, "%Y%m%d")
                    age_days = (now - dir_date).days
                    if age_days > days:
                        print(f"Removing stale download folder: {item} ({age_days} days old)")
                        shutil.rmtree(item_path)
                        removed_count += 1
                except Exception:
                    pass
            elif item == "tmp":
                try:
                    mtime = os.path.getmtime(item_path)
                    if (now - datetime.fromtimestamp(mtime)).days >= 1:
                        print(f"Removing stale tmp folder: {item}")
                        shutil.rmtree(item_path)
                        removed_count += 1
                except Exception:
                    pass

    return removed_count
