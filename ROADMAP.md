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

### 2.2 Strict Domain Modeling (Pydantic / Typed Dataclasses)
- **Status**: ✅ **Implemented foundational models** in [src/gex/core/models.py](src/gex/core/models.py) (`OptionQuote`, `GexProfile`, `ScannerCandidate`, `RegimeStatus`).
- **Next**: Add schema-validation adapters at the ingestion boundary when reading Robinhood API payloads and JSON cache files.

### 2.3 Modular Test Suite
- **Status**: ✅ **Implemented roadmap unit test module** in [tests/test_quant_roadmap.py](tests/test_quant_roadmap.py).
- **Next**: Progressively partition the 5,019-line [tests/test_gex_engine.py](tests/test_gex_engine.py) into `tests/unit/` and `tests/integration/`.

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
- **Problem**: Order simulation and backtesting assume mid-price fills, overstating win rates and profit factors.
- **Solution**:
  - Model realistic execution friction: penalize entry fills by $25\%\text{--}50\%$ of the bid-ask spread.
  - Reject candidate contracts whose bid-ask spread exceeds $10\%$ of contract value.

### 3.4 Multi-Account In-Memory Cache Isolation
- **Context**: [AGENTS.md](AGENTS.md) mandates strict account partitioning (`--account ACCOUNT_NUMBER`).
- **Action Items**:
  - Namespace in-memory cache dictionaries by account ID to guarantee zero state bleeding when multiple accounts are evaluated in a single session.

---

## 💾 Phase 4: Persistence, Analytics & Operational Automation (Long-term / Q3 2027)

### 4.1 Embedded Database Engine (SQLite / DuckDB)
- **Context**: Flat JSON files (`data/ticker_analyses.json` >120 KB, `data/candidate_stocks.json` >57 KB, `data/closed_positions_*.json`) grow unboundedly and must be fully parsed on every CLI call.
- **Solution**:
  - Retain lightweight JSON for active session state (`workflow_state.json`, `regime.json`).
  - Migrate closed trades, daily scanner outputs, and historical GEX levels to an embedded **SQLite** (or DuckDB) database:
    - `trades`: Historical fills, hold duration, entry/exit GEX levels, slippage, realized P&L.
    - `gex_snapshots`: Daily pTrans, nTrans, and GEX wall readings per underlier.
  - Enable instant, complex queries for the `TradeJournalAnalyst` (win rate by sector, performance vs holding period, maximum adverse excursion / MAE).

### 4.2 Automated Notification Webhooks
- **Problem**: Stop-loss warnings and execution approval requests only render to standard output.
- **Solution**:
  - Add optional webhook alerting (Discord, Slack, Telegram, or native macOS notifications via `osascript`).
  - Send alerts immediately when:
    - Stop 1–5 triggers on any open position.
    - Daily Market Regime flips (e.g. from `ALL TRACKS OK` to `DEFENSIVE / RESTRICTED`).

### 4.3 Headless Pre-Market Audit Mode
- **Action Items**:
  - Provide a standalone CLI mode (`gex audit-all`) suitable for cron or scheduled tasks before the market open.
  - Automatically fetch futures (/ES, /NQ), evaluate broad regime breadth, sync portfolio stops, and output an executive markdown morning brief.

---

## 📊 Summary Roadmap Matrix

| Milestone | Phase | Priority | Primary Impact | Dependencies |
| :--- | :---: | :---: | :--- | :--- |
| **Multi-Harness Synchronization** | Phase 1 | 🔴 High | Keeps .github/ and .agents/ prompts/agents in sync across harnesses | None |
| **Packaging & CI/CD** | Phase 1 | 🔴 High | Automated linting, test execution, regression guards | None |
| **Modular Package Refactoring** | Phase 2 | 🟡 Medium | High maintainability, clean domain separation | Phase 1 |
| **Pydantic / Typed Domain Models** | Phase 2 | 🟡 Medium | Robust data integrity, compile-time/runtime validation | Phase 2 |
| **Black-Scholes Gamma Fallback** | Phase 3 | 🟡 Medium | Resilient GEX derivation on illiquid option chains | Phase 2 |
| **DTE-Weighted GEX Modeling** | Phase 3 | 🟢 Low | More realistic dealer gamma pressure assessment | Phase 3 |
| **SQLite Trade Journal Persistence** | Phase 4 | 🟢 Low | Scalable historical queries, advanced journal metrics | Phase 2 |
| **Notification Webhooks** | Phase 4 | 🟢 Low | Proactive alerts for stop breaches & regime changes | Phase 2 |

---

*Document maintained collaboratively by human traders and the GEX Agent Workspace.*
