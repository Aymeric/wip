# Changelog

All notable changes to the **Gamma Exposure (GEX) Options & Agentic Portfolio Trading Suite** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
