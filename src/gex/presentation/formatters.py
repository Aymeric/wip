"""
Formatting helpers and markdown report generators for the GEX Trading System.
Provides consistent currency, percentage, and tabular block formatting.
"""

from typing import Any, Dict, List, Optional


def format_currency(value: Optional[float], default: str = "$0.00") -> str:
    """Formats numeric value as currency."""
    if value is None:
        return default
    if abs(value) < 0.005:
        return "$0.00"
    if value < 0:
        return f"-${abs(value):,.2f}"
    return f"${value:,.2f}"


def format_pct(value: Optional[float], default: str = "+0.00%", include_sign: bool = True) -> str:
    """Formats float value as percentage."""
    if value is None:
        return default
    if abs(value) < 0.005:
        return "+0.00%" if include_sign else "0.00%"
    sign = "+" if include_sign and value > 0 else ""
    return f"{sign}{value:.2f}%"


def get_pnl_color(value: Optional[float]) -> str:
    """
    Returns ANSI color code for 3-state financial metrics:
    Positive (> 0.005) -> '32' (Green)
    Negative (< -0.005) -> '31' (Red)
    Zero / Neutral -> '37' (Dim/Neutral)
    """
    if value is None or abs(value) < 0.005:
        return "37"
    return "32" if value > 0 else "31"


def format_pnl(
    pnl_dlr: Optional[float] = None,
    pnl_pct: Optional[float] = None,
    bold: bool = True,
    width: Optional[int] = None,
) -> str:
    """Formats financial P&L values with 3-state color semantics (Green/Red/Neutral) and optional pre-color width padding."""
    val_for_color = pnl_dlr if pnl_dlr is not None else pnl_pct
    color = get_pnl_color(val_for_color)

    parts = []
    if pnl_dlr is not None:
        if abs(pnl_dlr) < 0.005:
            dlr_str = "$0.00"
        elif pnl_dlr > 0:
            dlr_str = f"+${pnl_dlr:,.2f}"
        else:
            dlr_str = f"-${abs(pnl_dlr):,.2f}"
        parts.append(dlr_str)

    if pnl_pct is not None:
        if abs(pnl_pct) < 0.005:
            pct_str = "0.00%"
        elif pnl_pct > 0:
            pct_str = f"+{pnl_pct:.2f}%"
        else:
            pct_str = f"{pnl_pct:.2f}%"
        if pnl_dlr is not None:
            parts.append(f"({pct_str})")
        else:
            parts.append(pct_str)

    res = " ".join(parts)
    if width is not None:
        res = f"{res:<{width}}"
    from src.gex.presentation.ascii_art import format_color
    return format_color(res, color, bold=bold)


def format_table(headers: List[str], rows: List[List[Any]], empty_message: str = "No data available") -> str:
    """Formats simple tabular text rows with aligned column widths."""
    if not headers:
        return ""
    if not rows:
        col_widths = [len(h) for h in headers]
        table_width = sum(col_widths) + 3 * (len(headers) - 1)
        if len(empty_message) > table_width:
            col_widths[-1] += len(empty_message) - table_width
        header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
        separator_line = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
        return "\n".join([header_line, separator_line, empty_message])

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
