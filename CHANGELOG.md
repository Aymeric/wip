# Changelog

All notable changes to the **Gamma Exposure (GEX) Options & Agentic Portfolio Trading Suite** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [5.11.0] - 2026-11-18

### 🚀 Advanced Strategy Engineering & Multi-Leg Architecture
- **Pre-Earnings Vega Run-Up Harvester (Milestone 5.11)**: Engineered options scanner and setup grading for pre-earnings implied volatility expansion, evaluating underliers 15–25 DTE prior to earnings announcements with IV Rank $\le 40\%$, and enforcing strict 14-day mandatory exits prior to earnings (Rule 7) (`gex pre-earnings-candidates`) ([#197](https://github.com/Aymeric/wip/issues/197)).
- **Historical Options Replay & Backtesting Engine**: Added simulation harness with realistic bid/ask slippage modeling, regime-gated entries, and multi-day portfolio equity tracking (`gex backtest`) ([#193](https://github.com/Aymeric/wip/issues/193)).
- **Defined-Risk Vertical Spreads**: Implemented long call debit vertical spreads pegged to dealer +GEX call walls, payoff diagrams, and multi-leg simulation (`gex select-spreads`, `gex payoff`, `gex simulate`) ([#196](https://github.com/Aymeric/wip/issues/196)).
- **Second-Order Dealer Exposure Modeling (Vanna & Charm)**: Analytical derivation of Vanna ($\partial \Delta / \partial \sigma$) and Charm ($-\partial \Delta / \partial t$) dealer positioning profiles across option chains to project volatility-crush and weekend decay flows ([#194](https://github.com/Aymeric/wip/issues/194)).
- **IV Rank & IV Percentile Context**: Added relative implied volatility ranking context with automated SQLite volatility snapshot persistence (`gex snapshot`) ([#165](https://github.com/Aymeric/wip/issues/165)).
- **Beta-Weighted Macro Hedging Engine**: Automated portfolio hedge sizing allocating inverse/index contracts (SPY/QQQ) on defensive regime transitions (Roadmap 5.3; `gex hedge-plan`).
- **Dynamic Delta Rolling Engine**: Systematic roll-up and roll-out rules for deep-ITM winning contracts ($\Delta \ge 0.70$) to lock in capital gains (`gex evaluate-rolls`).
- **Intraday GEX Level Breach Monitor Daemon**: Real-time intraday monitoring daemon evaluating Stop 1 and profit target breaches with stateful cooldowns and deadbands (`gex monitor`).
- **Alert Hysteresis & Rate Limiting**: Added stateful alert dispatch suppression with minimum 15-minute cooldowns and threshold deadbands to eliminate notification noise ([#195](https://github.com/Aymeric/wip/issues/195)).
- **Stop-Coded Exit Attribution**: Recorded explicit stop-loss triggers (Stops 1–5, Target, Manual, Expiration) on trade exit records for quantitative attribution ([#163](https://github.com/Aymeric/wip/issues/163)).
- **Approval Decision Ledger**: Implemented durable SQLite audit ledger tracking trade confirmations, declines, and overrides with masked-account provenance (`gex record-decision`, `gex decisions`) ([#164](https://github.com/Aymeric/wip/issues/164)).

### 🏗️ Architecture & CLI Refactoring
- **Modular CLI Command Extraction**: Extracted 34 CLI subcommands from monolithic `gex_engine.py` into dedicated domain modules in `src/gex/cli/` (`regime`, `portfolio`, `screening`, `journal`, `ops`, `parser`, `proxy`) ([#166](https://github.com/Aymeric/wip/issues/166)).
- **Direct CLI `--version` Support**: Exposed root `--version` argument on `gex_engine.py` tied to package metadata.
- **Autonomous Watchlist Hygiene**: Enacted non-financial candidate tracking exemption allowing background automations to synchronize and prune watchlists without user interaction interruption.

### 🛡️ Security Hardening
- **Path Traversal Containment**: Hardened `validate_safe_path` with symlink traversal breakout protection and precomputed root prefix checks ([#176](https://github.com/Aymeric/wip/pull/176), [#180](https://github.com/Aymeric/wip/pull/180)).
- **Account Parameter Sanitization**: Strictly validated and sanitized account parameters across SQLite decision and trade journal operations ([#181](https://github.com/Aymeric/wip/pull/181), [#187](https://github.com/Aymeric/wip/pull/187)).
- **Desktop Alert Escaping**: Escaped backslashes and quotes in macOS AppleScript notification dispatch ([#156](https://github.com/Aymeric/wip/pull/156)).
- **File Access Hardening**: Fixed path traversal vulnerabilities across mtime calculation and scan download utilities ([#147](https://github.com/Aymeric/wip/pull/147)).

### ⚡ Performance & Optimization (Bolt)
- **Table Formatting**: Consolidated visible length calculation and inlined cell padding for single-pass table rendering ([#173](https://github.com/Aymeric/wip/pull/173), [#182](https://github.com/Aymeric/wip/pull/182)).
- **Technical Indicator Speedups**: Optimized Wilder's ATR calculation with running accumulators ([#175](https://github.com/Aymeric/wip/pull/175)), scalar reciprocal periods in RSI ([#168](https://github.com/Aymeric/wip/pull/168)), and vectorized Bollinger Band evaluation ([#186](https://github.com/Aymeric/wip/pull/186)).
- **Option Contract Selection**: Optimized contract filtering with direct set indexing and pre-filtered quotes lookups ([#144](https://github.com/Aymeric/wip/pull/144), [#160](https://github.com/Aymeric/wip/pull/160)).
- **SQLite Batch Operations**: Implemented batched transactions and single-connection upserts in closed position persistence ([#167](https://github.com/Aymeric/wip/pull/167)).
- **Black-Scholes & GEX Profile Speedups**: Vectorized d1/d2 computation and unrolled candidate scoring evaluations ([#153](https://github.com/Aymeric/wip/pull/153), [#157](https://github.com/Aymeric/wip/pull/157)).

### 🎨 User Experience & Formatting (Palette)
- **3-State Color Semantics**: Introduced neutral color styling for volatility discounts and payoff table cells ([#185](https://github.com/Aymeric/wip/pull/185)).
- **Table Formatting & Alignment**: Added per-column text alignment and aligned borders in closed positions and audit tables ([#154](https://github.com/Aymeric/wip/pull/154), [#158](https://github.com/Aymeric/wip/pull/158), [#184](https://github.com/Aymeric/wip/pull/184)).

### 🤖 Tooling & Agent Workflow
- **Multi-Harness Synchronization**: Enforced prompt and agent manifest parity between `.agents/` and `.github/` with CI checking.
- **Static Analysis Gate**: Integrated `ruff` and `mypy` static typing and linting checks into GitHub Actions CI matrix ([#162](https://github.com/Aymeric/wip/issues/162)).
- **Project Version Maintenance**: Enforced project version metadata synchronization across `src/gex/__init__.py` and `pyproject.toml` in `roadmap-implementation` and `roadmap-release` workflows with dedicated unit test verification (`tests/test_version.py`).

---

## [1.1.0] - 2026-10-26

### 🚀 Features & Architecture
- **Domain-Driven Package Refactoring**: Replaced monolithic script architecture with a structured Python package in `src/gex/` organized into cohesive domain modules:
  - `src/gex/core`: Centralized configuration, paths, and immutable dataclass models (`OptionPosition`, `StockPosition`, `RegimeGates`, `GexProfile`, `ClosedTradeRecord`).
  - `src/gex/quant`: Quantitative engines for Black-Scholes pricing, analytical Greeks (delta, gamma, theta, vega), historical volatility, ATR, Bollinger Bands, and dealer GEX profile derivation.
  - `src/gex/risk`: Stop loss 1–5 hierarchy, micro-account 1-contract sizing rules, and portfolio buying power budget management.
  - `src/gex/screening`: Volatility and options volume scanner parser, 5-factor scoring, and optimal 30–45 DTE option contract selector.
  - `src/gex/storage`: Robust persistence engine with atomic writes, cache management, retention pruning, and SQLite trade history persistence.
  - `src/gex/presentation`: ANSI color formatters, financial string formatters, and ASCII GEX runway scale generation.
- **Zero-Crossing Linear Interpolation**: Derived exact sub-strike dealer gamma flip transitions ($pTrans$ and $nTrans$) using linear interpolation across zero-crossings.
- **SQLite Database Persistence**: Added ACID-compliant SQLite storage (`gex_trading.db`) with automatic schema migration and transaction history tracking.
- **Pre-Market Headless Audit**: Added `python3 src/gex_engine.py audit-all` command generating consolidated morning markdown reports across active accounts.
- **Notification Dispatch System**: Added webhook dispatch for Slack, Discord, Telegram, and macOS native desktop notifications on critical exit signals.

### 🛡️ Security Hardening
- **SSRF Scheme Validation**: Enforced strict `http` and `https` URL scheme validation in webhook alerting to prevent SSRF and `file://` local file inclusion ([#138](https://github.com/Aymeric/wip/pull/138)).
- **Path Traversal Protection**: Enforced path containment validation across all CLI file inputs, database paths, and download helpers ([#142](https://github.com/Aymeric/wip/pull/142), [#136](https://github.com/Aymeric/wip/pull/136), [#131](https://github.com/Aymeric/wip/pull/131), [#127](https://github.com/Aymeric/wip/pull/127), [#121](https://github.com/Aymeric/wip/pull/121)).

### ⚡ Performance & Optimization
- **GEX Profile Derivation**: Optimized zero-crossing strike discovery and precomputed DTE time-decay weights ([#140](https://github.com/Aymeric/wip/pull/140), [#122](https://github.com/Aymeric/wip/pull/122)).
- **Cache Lookup Speed**: Replaced deep copy cloning with optimized structure cloning in high-frequency cache reads ([#141](https://github.com/Aymeric/wip/pull/141)).
- **Quant Calculation Micro-Optimizations**: Inlined scalar math in ATR calculation ([#132](https://github.com/Aymeric/wip/pull/132)), annualized volatility scaling ([#128](https://github.com/Aymeric/wip/pull/128)), and trade journal aggregation ([#130](https://github.com/Aymeric/wip/pull/130)).
- **Option Contract Selection**: Optimized linear scan and strike validation in `select_best_option` ([#137](https://github.com/Aymeric/wip/pull/137), [#123](https://github.com/Aymeric/wip/pull/123)).

### 🎨 User Experience & Presentation
- **Neutral P&L Formatting**: Added 3-state color formatting with neutral grey styling for 0.0% breakeven price movements ([#139](https://github.com/Aymeric/wip/pull/139), [#124](https://github.com/Aymeric/wip/pull/124)).
- **Table Alignment & ANSI Safety**: Corrected string padding and column alignment across ANSI color codes in CLI tables ([#143](https://github.com/Aymeric/wip/pull/143)).
- **Single-Node ASCII Runway**: Added graceful single-spot fallback support for ASCII GEX scale visualizations ([#133](https://github.com/Aymeric/wip/pull/133)).
- **Empty States & Placeholders**: Added explicit empty state messages and dim formatting for unanalyzed placeholders ([#126](https://github.com/Aymeric/wip/pull/126), [#120](https://github.com/Aymeric/wip/pull/120), [#110](https://github.com/Aymeric/wip/pull/110)).
- **Financial Formatting**: Enhanced formatting for currency, percentages, and sign normalization ([#129](https://github.com/Aymeric/wip/pull/129)).

### 🤖 Agent Ecosystem & Automation
- **Multi-Harness Synchronization**: Introduced `scripts/sync_harnesses.py` to synchronize agent manifests, system prompts, and tool configurations across Copilot and Gemini harnesses with `--check` CI enforcement.
- **Workflow Skills**: Added standardized agent skills for `/roadmap-ideation`, `/roadmap-implementation`, and `/roadmap-release`.

---

## [1.0.0] - 2026-10-18

### 🚀 Initial Release
- Initial release of the Gamma Exposure (GEX) Options & Agentic Portfolio Trading Suite.
- Core CLI engine `gex_engine.py` for dealer gamma level calculation, market regime gates, and portfolio risk management.
- Integration with Robinhood MCP server for market data ingestion and order execution.
- 11-Rule GEX setup grading checklist.
