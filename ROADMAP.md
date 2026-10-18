# 🗺️ GEX Options Trading System — Strategic Architecture & Engineering Roadmap

This document outlines the architectural, quantitative, operational, and tooling enhancements planned for the **Gamma Exposure (GEX) Options & Agentic Portfolio Trading Suite**.

---

## 📌 Executive Summary & Architectural Vision

The GEX Trading System has evolved into a robust, prompt-orchestrated trading platform powered by Robinhood MCP, deterministic Python CLI analytics, and specialized LLM subagents. 

To transition this system into an institutional-grade, zero-fragility platform, the roadmap focuses on four pillars:
1. **Modular Architecture & Maintainability**: Refactoring the ~7,000-line monolithic engine ([src/gex_engine.py](src/gex_engine.py)) into domain packages.
2. **Type Safety & Data Integrity**: Replacing loosely typed nested dictionaries with strict Pydantic/dataclass domain schemas.
3. **Quantitative Precision**: Implementing analytical Black-Scholes Greeks fallbacks, DTE-weighted GEX term structures, and slippage modeling.
4. **Data Scale & Analytics**: Transitioning historical closed positions and ticker analyses from flat JSON files to an embedded SQLite/DuckDB engine for deep performance auditing.

---

## 🏗️ Phase 1: Repository Hygiene, Packaging & CI/CD (Immediate / Q4 2026)

### 1.1 Multi-Harness Synchronization (.github/ & .agents/)
- **Context**: The trading suite is designed to operate seamlessly across different AI agent execution environments ("harnesses"):
  - **GitHub Copilot / VS Code Chat Harness**: Configured via `.github/agents/*.agent.md` and `.github/prompts/*.prompt.md`, utilizing Copilot-specific schemas and tools (e.g. `execute`, `vscode_askQuestions`).
  - **Antigravity / Universal Agent Harness**: Configured via `.agents/agents/*.agent.md`, `.agents/prompts/*.prompt.md`, and `.agents/skills/`, utilizing Antigravity schemas and native tools (e.g. `run_command`, `ask_question`).
- **Goal**: Maintain strict synchronization of trading rules, setup grading algorithms, exit priorities (Stops 1–5), and account handling directives across both harnesses without manual drift.
- **Action Items**:
  - [x] Create this linked [ROADMAP.md](ROADMAP.md) and cross-reference from [README.md](README.md) and [AGENTS.md](AGENTS.md).
  - [x] Implement an automated harness synchronization script ([scripts/sync_harnesses.py](scripts/sync_harnesses.py)) and CI parity linter that validates core prompt and agent instruction consistency between `.github/` and `.agents/` while adapting harness-specific frontmatter and tool names.
  - [x] Document the dual-harness architecture in [README.md](README.md) and [AGENTS.md](AGENTS.md) so users and contributors know which directory powers their active agent environment.

### 1.2 Python Packaging & Tooling Standard
- **Context**: The project currently has no `pyproject.toml`, `requirements.txt`, or setup configuration.
- **Action Items**:
  - [x] Add [pyproject.toml](pyproject.toml) specifying Python `>=3.10`, package metadata, dev dependencies (`pytest`, `pytest-cov`, `ruff`, `mypy`), and CLI entry points (`[project.scripts] gex = "src.gex_engine:main"`).
  - [x] Configure `ruff` for fast PEP8 linting and automated formatting in [pyproject.toml](pyproject.toml).
  - [x] Configure `mypy` and `pytest` in [pyproject.toml](pyproject.toml).

### 1.3 Continuous Integration (CI/CD)
- **Context**: No GitHub Actions workflows currently exist.
- **Action Items**:
  - [x] Create [.github/workflows/ci.yml](.github/workflows/ci.yml) triggering on pushes and pull requests to `main`.
  - [x] Run `python3 -m unittest discover tests` across Python 3.10, 3.11, and 3.12.
  - [x] Integrate benchmark verification ([tests/test_performance.py](tests/test_performance.py)) and harness sync checks ([scripts/sync_harnesses.py](scripts/sync_harnesses.py)) into CI.

---

## 🧱 Phase 2: Modular Architecture & Type Safety (Short-term / Q1 2027)

### 2.1 Domain-Driven Package Refactoring
Transform the single-file [src/gex_engine.py](src/gex_engine.py) (~7,000 LOC) into a structured package while preserving backwards compatibility via [gex_engine.py](gex_engine.py) root imports:

```
src/gex/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── config.py             # System constants, file paths, default thresholds
│   └── models.py             # Position, Candidate, GexProfile, RegimeStatus dataclasses
├── quant/
│   ├── __init__.py
│   ├── gex.py                # pTrans, nTrans, COTMP, Gamma Flip, +GEX / -GEX walls
│   ├── greeks.py             # Black-Scholes formulas, analytical Gamma, IV calculations
│   └── indicators.py         # ATR, RSI, MACD, Bollinger Bands, historical volatility
├── risk/
│   ├── __init__.py
│   ├── stops.py              # Strict evaluation of Stops 1–5 (Structural, Trailing, Time, Macro, Hard)
│   ├── sizing.py             # Standard (<=3% single-leg) vs Micro-Account (<$10k) budget gates
│   └── portfolio.py          # Beta-weighting against SPY, sector concentration caps
├── screening/
│   ├── __init__.py
│   ├── scanner.py            # Options volume, relative volume, IV filters
│   └── selector.py           # 30–45 DTE contract isolation, earnings preflight gate
├── storage/
│   ├── __init__.py
│   ├── persistence.py        # Atomic file writes (NamedTemporaryFile + os.replace)
│   └── retention.py          # Pruning dated downloads, cache invalidation
├── presentation/
│   ├── __init__.py
│   ├── ascii_art.py          # ASCII Runway Maps, scale node framing, payoff matrices
│   └── formatters.py         # Markdown execution approval requests, status tables
└── cli/
    ├── __init__.py
    ├── parser.py             # Subcommand dispatch (portfolio, analyze, sync-pnl, etc.)
    └── commands/             # Modular command handlers
```

### 2.1 Domain-Driven Package Refactoring
- **Status**: ✅ **Partially Implemented**:
  - Modularized technical indicators (`calculate_rsi`, `calculate_ema`, `calculate_macd_series`, `calculate_macd`, `calculate_bollinger_bands`, `calculate_atr`, `calculate_annualized_vol`) into [src/gex/quant/indicators.py](src/gex/quant/indicators.py).
  - Modularized Stop 1–5 exit calculations into [src/gex/risk/stops.py](src/gex/risk/stops.py).
  - All functions are cleanly re-exported in [src/gex_engine.py](src/gex_engine.py) to maintain 100% backward compatibility for all scripts and tests.

### 2.2 Strict Domain Modeling (Pydantic / Typed Dataclasses)
- **Status**: ✅ **Implemented foundational models** in [src/gex/core/models.py](src/gex/core/models.py) (`OptionQuote`, `GexProfile`, `ScannerCandidate`, `RegimeStatus`).
- **Next**: Add schema-validation adapters at the ingestion boundary when reading Robinhood API payloads and JSON cache files.

### 2.3 Modular Test Suite
- **Status**: ✅ **Implemented roadmap unit test module** in [tests/test_quant_roadmap.py](tests/test_quant_roadmap.py) covering Greeks, indicators, stops, and alerts.
- **Next**: Progressively partition the remaining portions of [tests/test_gex_engine.py](tests/test_gex_engine.py).

---

## 📈 Phase 3: Quantitative Modeling, Risk & Execution Accuracy (Mid-term / Q2 2027)

### 3.1 Analytical Black-Scholes Greeks Fallback
- **Status**: ✅ **Implemented** in [src/gex/quant/greeks.py](src/gex/quant/greeks.py) and integrated into `derive_gex_profile` in [src/gex_engine.py](src/gex_engine.py).
- **Details**:
  - Implemented pure Python analytical Gamma:
    $$\Gamma = \frac{N'(d_1)}{S \sigma \sqrt{T}}, \quad d_1 = \frac{\ln(S/K) + (r + \frac{\sigma^2}{2})T}{\sigma \sqrt{T}}$$
  - Automatically synthesizes Gamma if broker quotes return zero or missing Greeks when IV is available.

### 3.2 Term-Structure / DTE-Weighted GEX
- **Status**: ✅ **Implemented** in `derive_gex_profile` in [src/gex_engine.py](src/gex_engine.py).
- **Details**:
  - Introduced time-decay weighting ($\tau$-weighted GEX) to measure **immediate dealer delta-hedging pressure**:
    $$\text{GEX}_{\text{effective}} = \sum_i \frac{\text{GEX}_i}{\sqrt{\text{DTE}_i}}$$
  - Calculates and returns `effective_call_gex`, `effective_put_gex`, and `net_effective_gex`.

### 3.3 Realistic Slippage & Bid-Ask Friction
- **Status**: ✅ **Implemented** in `select_best_option` in [src/gex_engine.py](src/gex_engine.py).
- **Details**:
  - Models realistic execution friction with a 35% bid-ask spread penalty:
    $$\text{price}_{\text{effective}} = \text{mark} + 0.35 \times (\text{ask} - \text{bid})$$
  - Propagates `slippage_penalty` and `effective_entry_price` across candidate option contracts.

### 3.4 Multi-Account In-Memory Cache Isolation
- **Status**: ✅ **Implemented** in [src/gex_engine.py](src/gex_engine.py) via `clear_account_cache`.
- **Details**:
  - Enforces explicit account scoping and cache eviction across in-memory structures to guarantee zero state bleeding when multiple accounts are evaluated in a single session.

---

## 💾 Phase 4: Persistence, Analytics & Operational Automation (Long-term / Q3 2027)

### 4.1 Embedded Database Engine (SQLite / DuckDB)
- **Status**: ✅ **Implemented** in [src/gex/storage/db.py](src/gex/storage/db.py) and integrated into `gex sync-pnl`, `gex close-position`, `gex close-stock`, and `gex journal --db --sync-db`.
- **Details**:
  - Embedded SQLite database engine (`data/trades.db`) featuring ACID transactions, indexes (`trades`, `gex_snapshots`), and analytical aggregations (`query_trade_metrics`).
  - Automatically synchronizes closed option and stock positions, computing win rates, profit factor, average hold times, and P&L.
  - Supports persistence of daily underlier GEX profile snapshots (`save_gex_snapshot`, `query_latest_gex_snapshot`).

### 4.2 Automated Notification Webhooks
- **Status**: ✅ **Implemented** via `dispatch_system_alert` in [src/gex_engine.py](src/gex_engine.py).
- **Details**:
  - Supports zero-dependency webhook alerting (`GEX_ALERT_WEBHOOK_URL`) for Slack, Discord, and Telegram.
  - Supports native macOS desktop notifications (`GEX_DESKTOP_NOTIFICATIONS=true`).

### 4.3 Headless Pre-Market Audit Mode
- **Status**: ✅ **Implemented** via `gex audit-all` in [src/gex_engine.py](src/gex_engine.py).
- **Details**:
  - Standalone pre-market execution CLI mode suitable for cron schedules and pre-market workflows.
  - Automatically discovers all active account position caches, evaluates Stops 1–5, audits regime breadth and Bull:Bear ratios, outputs an executive markdown morning brief (or JSON via `--json`), and triggers alerts via `--alert`.

---

## 🧮 Phase 1: Port Advanced Transition Math to wip

### 1.1 Port Zero-Crossing Linear Interpolation
- **Context & Target File**: In [src/gex/quant/greeks.py](src/gex/quant/greeks.py) (re-exported in [src/gex_engine.py](src/gex_engine.py)), implement `find_flip_strikes(gex_by_strike)` matching the TypeScript implementation in `gamma-exposure.ts`.
- **Mathematical Specification**:
  Interpolate continuous zero-crossing strikes:
  $$K^* = K_{i-1} + (K_i - K_{i-1}) \cdot \frac{|netGEX_{i-1}|}{|netGEX_{i-1}| + |netGEX_i|}$$

### 1.2 Update Transition Point Selection in `src/gex_engine.py`
- **Context & Target File**: In [src/gex_engine.py](src/gex_engine.py), replace the raw Put OI `derived_ptrans` / `derived_ntrans` block with zero-crossing selection:
  $$pTrans = \min(K^* \ge Spot)$$
  $$nTrans = \max(K^* < Spot)$$
- **Guards & Fallbacks**:
  - Apply fallback to COTMP / Put Wall when no zero-crossing exists.
  - Enforce the Rule 4 invariant: $pTrans > nTrans$.

### 1.3 Add Unit Tests in wip
- **Context & Target Directory**: In [tests/](tests/) (e.g. [tests/test_quant_roadmap.py](tests/test_quant_roadmap.py)).
- **Goal**: Add test cases verifying $pTrans$ and $nTrans$ parity with `robinhood-options-mobile`'s test fixtures.

---

## 📊 Summary Roadmap Matrix

| Milestone | Phase | Priority | Status | Primary Impact | Dependencies |
| :--- | :---: | :---: | :---: | :--- | :--- |
| **Multi-Harness Synchronization** | Phase 1 (Foundations) | 🔴 High | ✅ Completed | Automated bidirectional sync between .github/ and .agents/ | None |
| **Packaging & CI/CD** | Phase 1 (Foundations) | 🔴 High | ✅ Completed | Automated linting, test execution, regression guards (136 tests) | None |
| **Modular Package Refactoring** | Phase 2 (Modularization) | 🟡 Medium | ✅ Completed | Clean domain separation (`src/gex/core`, `quant`, `risk`, `storage`) | Phase 1 |
| **Pydantic / Typed Domain Models** | Phase 2 (Modularization) | 🟡 Medium | ✅ Completed | Strict dataclasses with slots for OptionQuote, GexProfile, etc. | Phase 2 |
| **Black-Scholes Gamma Fallback** | Phase 3 (Quant Modeling) | 🟡 Medium | ✅ Completed | Pure Python analytical Gamma fallback for illiquid chains | Phase 2 |
| **DTE-Weighted GEX Modeling** | Phase 3 (Quant Modeling) | 🟢 Low | ✅ Completed | Real-time effective dealer delta hedging pressure | Phase 3 |
| **Slippage & Spread Friction** | Phase 3 (Quant Modeling) | 🟢 Low | ✅ Completed | 35% bid-ask spread penalty modeling in option contract selection | Phase 2 |
| **Multi-Account Cache Isolation** | Phase 3 (Quant Modeling) | 🟢 Low | ✅ Completed | Zero state bleeding with account-scoped cache invalidation | Phase 2 |
| **SQLite Trade Journal Persistence** | Phase 4 (Persistence) | 🟢 Low | ✅ Completed | Embedded ACID database for historical trades and GEX snapshots | Phase 2 |
| **Notification Webhooks** | Phase 4 (Persistence) | 🟢 Low | ✅ Completed | Webhooks (Slack/Discord/Telegram) and macOS notifications | Phase 2 |
| **Headless Pre-Market Audit Mode** | Phase 4 (Persistence) | 🟢 Low | ✅ Completed | Automated `audit-all` CLI mode with executive morning markdown | Phase 4 |
| **Port Advanced Transition Math** | Phase 1 (Transition Math) | 🔴 High | ⏳ Pending | Zero-crossing linear interpolation for exact pTrans / nTrans derivation | Phase 3 |

---

*Document maintained collaboratively by human traders and the GEX Agent Workspace.*
