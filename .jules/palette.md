# Palette UX Journal

## 2026-09-18 - CLI Terminal Visual Alignment
**Learning:** In terminal CLI ASCII diagrams and tables, inconsistent node delimiters (e.g., mixing bracketed `[LABEL: $PRICE]` nodes with unbracketed `*LABEL*($PRICE)` nodes) degrade visual scanning and readability.
**Action:** Always maintain uniform boundary framing (brackets, spacing, alignment) across all nodes in linear ASCII scales and ensure table footers do not leak loop-residual variable formatting.

## 2026-09-18 - Non-TTY / Screen Reader CLI Table Row Markers
**Learning:** In CLI terminal simulation matrices and data tables, relying solely on ANSI color codes to highlight baseline rows (e.g. current spot price) fails in non-TTY environments, pipe operations, or for screen reader users.
**Action:** Always complement color styling with explicit inline text labels (such as `(Spot)`) in table columns to ensure accessibility across all output environments.

## 2026-10-03 - Plain Text Role Symmetry in Terminal ASCII Scales
**Learning:** In ASCII linear diagrams, mixing a plain key label (e.g. `SPOT`) alongside descriptive role-tagged labels (e.g. `+GEX (T1 Target)`) creates visual asymmetry and ambiguity. Additionally, using plain ASCII text role tags (such as `SPOT (Current)`) instead of multi-byte Unicode emojis avoids column alignment distortions across varied terminal emulators.
**Action:** Maintain consistent plain-text role descriptor suffixes across all scale nodes in ASCII visualizations.

## 2026-10-14 - Dim Styling for Unanalyzed Placeholders in CLI Tables
**Learning:** In CLI terminal tables mixing active status badges with placeholder/unanalyzed values, leaving placeholders uncolored causes them to take on default foreground brightness, competing visually with highlighted status indicators.
**Action:** Always format unanalyzed or placeholder text entries with a dim/muted color (e.g. ANSI 37) so that actionable status indicators pop out clearly.

## 2026-10-24 - CLI Terminal Table Empty States
**Learning:** Rendering CLI tables with zero rows as back-to-back header and footer separators without explicit messaging appears broken and ambiguous to users and screen readers.
**Action:** Always handle empty row collections in table formatters and loops with explicit empty state notices (e.g. "No data available" or "No candidates matched the screening criteria") between table headers/footers.

## 2026-11-08 - Neutral Color Semantics for Zero Price Movement
**Learning:** In financial CLI tables and simulation outputs, binary color evaluation (`chg > 0` -> green, else -> red) incorrectly colors flat 0.00% daily price changes as losses (red) or gains (green), creating false alarm states for users scanning table rows.
**Action:** Always evaluate price movement across three distinct states (positive -> green 32, negative -> red 31, zero -> neutral/dim 37) to prevent misleading visual signals.

## 2026-11-05 - Empty Table Line Alignment for Long Messages
**Learning:** When formatting empty ASCII tables in CLI output, if the `empty_message` string is longer than the table headers, unadjusted column widths cause header and separator lines to be shorter than the message beneath them, creating visually truncated ASCII boundaries.
**Action:** Dynamically expand column width in `format_table` when `rows` is empty so that header and separator lines match or exceed the width of long `empty_message` strings.

## 2026-11-20 - Pre-Color String Width Padding in ANSI CLI Tables
**Learning:** Applying fixed-width string formatting (e.g. `f"{text:<16}"`) on strings that already contain ANSI escape codes causes Python's `len()` to count non-printable control characters, inflating string length and misaligning CLI table columns.
**Action:** Always apply width padding to raw uncolored strings before wrapping them with ANSI escape sequences in table formatters.

## 2026-11-20 - ANSI Escape Code Alignment in CLI Tables
**Learning:** In CLI tables containing ANSI color-formatted cells (such as colored P&L values or ticker badges), standard string length calculation `len()` counts non-printable escape bytes, causing column widths and pipe delimiters (`|`) to visually misalign across rows.
**Action:** Always compute string widths and cell padding using ANSI-stripped visible length (`_visible_len`) in CLI table formatters so column boundaries remain pixel/character-aligned regardless of color styling.

## 2026-11-22 - Consistent Pre-Color Padding in Audit Output
**Learning:** In pre-market account audit tables (`cmd_audit_all`), applying manual ANSI formatting with fixed format widths like `pnl_s:<21` inflates column width in non-TTY environments and misaligns column pipes (`|`) with header lines (`P&L ($)` at 12 characters).
**Action:** Always leverage `format_pnl(..., width=N)` which formats and pads the raw string prior to ANSI code encapsulation, and synchronize horizontal boundary separator lengths with total header line width.

## 2026-11-25 - Trailing Delimiter Alignment in Historical Closed Trade Tables
**Learning:** In terminal CLI historical tables like `cmd_closed`, omitting width padding on the final column (`pnl_pct_fmt`) while using a fixed-width header (`Realized P&L (%)` at 16 chars) causes row endpoints and horizontal boundary separators to visually mismatch header bounds.
**Action:** Always pass `width=N` to the trailing column formatter (e.g. `format_pnl(pnl_pct=..., width=16)`) and calibrate separator dash lengths to match total header visible width.
