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

## 2026-11-05 - Empty Table Line Alignment for Long Messages
**Learning:** When formatting empty ASCII tables in CLI output, if the `empty_message` string is longer than the table headers, unadjusted column widths cause header and separator lines to be shorter than the message beneath them, creating visually truncated ASCII boundaries.
**Action:** Dynamically expand column width in `format_table` when `rows` is empty so that header and separator lines match or exceed the width of long `empty_message` strings.
