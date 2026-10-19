"""
Formatting helpers and markdown report generators for the GEX Trading System.
Provides consistent currency, percentage, and tabular block formatting.
"""

from typing import Any, Dict, List, Optional


def format_currency(value: Optional[float], default: str = "$0.00") -> str:
    """Formats numeric value as currency."""
    if value is None:
        return default
    return f"${value:,.2f}"


def format_pct(value: Optional[float], default: str = "+0.00%", include_sign: bool = True) -> str:
    """Formats float value as percentage."""
    if value is None:
        return default
    sign = "+" if include_sign and value > 0 else ""
    return f"{sign}{value:.2f}%"


def format_table(headers: List[str], rows: List[List[Any]]) -> str:
    """Formats simple tabular text rows with aligned column widths."""
    if not headers:
        return ""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(val)))

    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    separator_line = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
    row_lines = [
        " | ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row))
        for row in rows
    ]
    return "\n".join([header_line, separator_line] + row_lines)
