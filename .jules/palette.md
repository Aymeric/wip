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
