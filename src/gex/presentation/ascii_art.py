"""
Presentation layer for terminal color formatting and ASCII GEX scale visualizations.
Renders linear runway maps of dealer positioning relative to current underlying spot.
"""

import sys
from typing import Optional


def print_color(text: str, color_code: str, bold: bool = False) -> None:
    """Prints text in ANSI color if the output is a tty."""
    if sys.stdout.isatty():
        prefix = f"\033[{1 if bold else 0};{color_code}m"
        suffix = "\033[0m"
        print(f"{prefix}{text}{suffix}")
    else:
        print(text)


def format_color(text: str, color_code: str, bold: bool = False) -> str:
    """Formats text with ANSI color codes if the output is a tty."""
    if sys.stdout.isatty():
        return f"\033[{1 if bold else 0};{color_code}m{text}\033[0m"
    return text


def generate_ascii_gex_scale(
    spot: Optional[float],
    ptrans: Optional[float] = None,
    ntrans: Optional[float] = None,
    gex: Optional[float] = None,
    cotmp: Optional[float] = None,
) -> str:
    """Constructs a visual linear ASCII representation of GEX levels and where SPOT resides."""
    levels_by_price = {}
    for price, label in [(cotmp, "COTMP"), (ntrans, "nTrans"), (ptrans, "pTrans"), (gex, "+GEX"), (spot, "SPOT")]:
        if price is None:
            continue
        p_round = round(price, 2)
        levels_by_price.setdefault(p_round, []).append(label)

    sorted_prices = sorted(levels_by_price.keys())

    runway_segments = []
    for i, price in enumerate(sorted_prices):
        labels = levels_by_price[price]
        label_strs = []
        for label in labels:
            if label == "SPOT":
                label_strs.append(format_color("SPOT (Current)", "35", bold=True))
            elif label == "+GEX":
                label_strs.append(format_color("+GEX (T1 Target)", "32", bold=True))
            elif label == "pTrans":
                label_strs.append(format_color("pTrans (Trigger)", "36", bold=True))
            elif label == "nTrans":
                label_strs.append(format_color("nTrans (Stop)", "31", bold=True))
            elif label == "COTMP":
                label_strs.append(format_color("COTMP (Support)", "31", bold=True))
            else:
                label_strs.append(label)

        label_block = " + ".join(label_strs)
        formatted_block = f"[{label_block}: ${price:.2f}]"

        runway_segments.append(formatted_block)

        if i < len(sorted_prices) - 1:
            next_price = sorted_prices[i + 1]
            delta = next_price - price
            pct_dist = (delta / price) * 100.0 if price > 0 else 0.0
            runway_segments.append(f" === {pct_dist:+.1f}% ===> ")

    return "".join(runway_segments)
