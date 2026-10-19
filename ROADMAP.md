# 🗺️ GEX Options Trading System — Strategic Architecture & Engineering Roadmap

This document outlines the architectural, quantitative, operational, and tooling roadmap for the **Gamma Exposure (GEX) Options & Agentic Portfolio Trading Suite**.

---

## 📌 Executive Summary & Architectural Vision

The GEX Trading System is an institutional-grade, rules-based options swing trading platform engineered around dealer gamma positioning, volatility regimes, and liquidity dynamics.

The system's engineering lifecycle is organized into structured phases:
1. **Phase 1: Repository Hygiene, Packaging & CI/CD** (Foundations & Multi-Harness Sync).
2. **Phase 2: Modular Architecture & Type Safety** (Domain Packages, Typed Dataclasses & Boundary Adapters).
3. **Phase 3: Quantitative Modeling, Risk & Execution Accuracy** (Zero-Crossing Interpolation, Analytical Greeks, Slippage).
4. **Phase 4: Persistence, Analytics & Operational Automation** (Embedded SQLite, Audit Mode, Alert Webhooks).
5. **Phase 5: Advanced Strategy Engineering & Backtesting** (Historical Playback, Dynamic Rolling, Automated Hedging).

---

## 🏗️ Phase 1: Repository Hygiene, Packaging & CI/CD

### 1.1 Multi-Harness Synchronization (.github/ & .agents/)
- **Context**: The trading suite operates seamlessly across distinct AI agent execution environments ("harnesses"):
  - **GitHub Copilot / VS Code Chat Harness**: Configured via `.github/agents/*.agent.md` and `.github/prompts/*.prompt.md`.
  - **Antigravity / Universal Agent Harness**: Configured via `.agents/agents/*.agent.md`, `.agents/prompts/*.prompt.md`, and `.agents/skills/`.
- **Status**: ✅ **Implemented**:
  - [x] Automated harness synchronization script ([scripts/sync_harnesses.py](scripts/sync_harnesses.py)) and CI parity linter that validates core prompt and agent instruction consistency between `.github/` and `.agents/`.
  - [x] Documented dual-harness architecture in [README.md](README.md) and [AGENTS.md](AGENTS.md).

### 1.2 Python Packaging & Tooling Standard
- **Status**: ✅ **Implemented**:
  - [x] Added [pyproject.toml](pyproject.toml) specifying Python `>=3.10`, package metadata, dev dependencies (`pytest`, `pytest-cov`, `ruff`, `mypy`), and CLI entry points (`[project.scripts] gex = "src.gex_engine:main"`).
  - [x] Configured `ruff`, `mypy`, and `pytest` in [pyproject.toml](pyproject.toml).

### 1.3 Continuous Integration (CI/CD)
- **Status**: ✅ **Implemented**:
  - [x] Created [.github/workflows/ci.yml](.github/workflows/ci.yml) running test matrices across Python 3.10, 3.11, and 3.12.
  - [x] Integrated benchmark verification ([tests/test_performance.py](tests/test_performance.py)) and harness sync checks ([scripts/sync_harnesses.py](scripts/sync_harnesses.py)).

---

## 🧱 Phase 2: Modular Architecture & Type Safety

### 2.1 Domain-Driven Package Refactoring
Transform the monolithic engine ([src/gex_engine.py](src/gex_engine.py)) into clean domain packages while preserving backwards compatibility via root re-exports:

```
src/gex/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── config.py             # System paths, baseline thresholds, account path resolvers
│   └── models.py             # Strongly typed dataclasses with validation & ingestion adapters
├── quant/
│   ├── __init__.py
│   ├── gex.py                # GEX profile derivation, quote matrix parsing, COTMP
│   ├── greeks.py             # Black-Scholes formulas, analytical Gamma, zero-crossing interpolation
│   └── indicators.py         # ATR, RSI, MACD, Bollinger Bands, historical volatility
├── risk/
│   ├── __init__.py
│   ├── stops.py              # Strict evaluation of Stops 1–5 (Structural, Trailing, Time, Macro, Hard)
│   ├── sizing.py             # Standard (<=3% single-leg) vs Micro-Account (<$10k) budget gates
│   └── portfolio.py          # Beta-weighting against SPY, sector concentration caps
├── screening/
│   ├── __init__.py
│   ├── scanner.py            # Options volume, relative volume, IV and candidate score models
│   └── selector.py           # 30–45 DTE contract isolation, earnings preflight gate, slippage penalty
├── storage/
│   ├── __init__.py
│   ├── persistence.py        # Atomic writes (NamedTemporaryFile + os.replace), mtime cache, eviction
│   ├── retention.py          # Pruning dated downloads, cache invalidation
│   └── db.py                 # Embedded SQLite trade journal & snapshot persistence
└── presentation/
    ├── __init__.py
    ├── ascii_art.py          # ASCII Runway Maps, scale node framing, ANSI color styling
    └── formatters.py         # Tabular data formatters, markdown reporting, currency/pct formatting
```

- **Status**: ✅ **Implemented**:
  - [x] Modularized `core/` ([src/gex/core/config.py](src/gex/core/config.py), [src/gex/core/models.py](src/gex/core/models.py)).
  - [x] Modularized `quant/` ([src/gex/quant/indicators.py](src/gex/quant/indicators.py), [src/gex/quant/greeks.py](src/gex/quant/greeks.py), [src/gex/quant/gex.py](src/gex/quant/gex.py)).
  - [x] Modularized `risk/` ([src/gex/risk/stops.py](src/gex/risk/stops.py), [src/gex/risk/sizing.py](src/gex/risk/sizing.py)).
  - [x] Modularized `screening/` ([src/gex/screening/scanner.py](src/gex/screening/scanner.py), [src/gex/screening/selector.py](src/gex/screening/selector.py)).
  - [x] Modularized `storage/` ([src/gex/storage/persistence.py](src/gex/storage/persistence.py), [src/gex/storage/retention.py](src/gex/storage/retention.py), [src/gex/storage/db.py](src/gex/storage/db.py)).
  - [x] Modularized `presentation/` ([src/gex/presentation/ascii_art.py](src/gex/presentation/ascii_art.py), [src/gex/presentation/formatters.py](src/gex/presentation/formatters.py)).
  - [x] 100% backward compatibility maintained via root imports in [src/gex_engine.py](src/gex_engine.py).

### 2.2 Strict Domain Modeling & Boundary Adapters
- **Status**: ✅ **Implemented**:
  - [x] Strongly typed dataclasses in [src/gex/core/models.py](src/gex/core/models.py): `OptionQuote`, `GexProfile`, `ScannerCandidate`, `RegimeGates`, `RegimeStatus`, `OptionPosition`, `StockPosition`, `OptionSentiment`, `Position`, `TradeRecord`.
  - [x] Boundary ingestion adapters:
    - `OptionQuote.from_robinhood(quote_data, instrument_data)`: Standardizes broker payloads and nested Greeks.
    - `ScannerCandidate.from_dict(data)`: Parses raw screener results.
    - `OptionPosition.from_dict(data)` & `StockPosition.from_dict(data)`: Handles snake_case and UI-spaced keys with field validation.
    - `OptionSentiment.from_dict(data)`: Validates 5-factor mathematical consistency.
    - `RegimeGates.from_dict(data)`: Validates macro gate states.
    - `GexProfile.from_dict(data)` & `GexProfile.to_dict()`: Seamless bidirectional serialization with `derive_gex_profile`.

### 2.3 Modular Test Suite
- **Status**: ✅ **Implemented**:
  - [x] Dedicated domain test suite in [tests/test_quant_roadmap.py](tests/test_quant_roadmap.py) (`TestRoadmapImplementations`, `TestPhase2ModularArchitecture`) with 146 unit tests passing across all packages.

---

## 📈 Phase 3: Quantitative Modeling, Risk & Execution Accuracy

### 3.1 Continuous Zero-Crossing Linear Interpolation
- **Status**: ✅ **Implemented** in [src/gex/quant/greeks.py](src/gex/quant/greeks.py).
- **Details**:
  - Mathematical linear interpolation of continuous zero-crossing strikes:
    $$K^* = K_{i-1} + (K_i - K_{i-1}) \cdot \frac{|netGEX_{i-1}|}{|netGEX_{i-1}| + |netGEX_i|}$$
  - Dynamic transition point selection:
    $$pTrans = \min(K^* \ge Spot), \quad nTrans = \max(K^* < Spot)$$
  - Deterministic fallback to COTMP / Put Wall when no zero-crossing exists.
  - Strict Rule 4 invariant enforcement: $pTrans > nTrans$.

### 3.2 Analytical Black-Scholes Greeks Fallback
- **Status**: ✅ **Implemented** in [src/gex/quant/greeks.py](src/gex/quant/greeks.py) and integrated into `derive_gex_profile`.
- **Details**:
  - Pure Python analytical Gamma formula:
    $$\Gamma = \frac{N'(d_1)}{S \sigma \sqrt{T}}, \quad d_1 = \frac{\ln(S/K) + (r + \frac{\sigma^2}{2})T}{\sigma \sqrt{T}}$$
  - Automatically synthesizes Gamma if broker quotes return zero or missing Greeks when IV is available.

### 3.3 Term-Structure / DTE-Weighted GEX
- **Status**: ✅ **Implemented** in [src/gex/quant/gex.py](src/gex/quant/gex.py).
- **Details**:
  - Time-decay weighting ($\tau$-weighted GEX) measuring **immediate dealer delta-hedging pressure**:
    $$\text{GEX}_{\text{effective}} = \sum_i \frac{\text{GEX}_i}{\sqrt{\text{DTE}_i}}$$
  - Calculates and returns `effective_call_gex`, `effective_put_gex`, and `net_effective_gex`.

### 3.4 Realistic Slippage & Bid-Ask Friction
- **Status**: ✅ **Implemented** in [src/gex/screening/selector.py](src/gex/screening/selector.py).
- **Details**:
  - Models realistic execution friction with a 35% bid-ask spread penalty:
    $$\text{price}_{\text{effective}} = \text{mark} + 0.35 \times (\text{ask} - \text{bid})$$
  - Propagates `slippage_penalty` and `effective_entry_price` across candidate option contracts.

### 3.5 Multi-Account In-Memory Cache Isolation
- **Status**: ✅ **Implemented** in [src/gex/storage/persistence.py](src/gex/storage/persistence.py).
- **Details**:
  - Enforces explicit account scoping and cache eviction across in-memory structures to guarantee zero state bleeding when multiple accounts are evaluated in a single session.

---

## 💾 Phase 4: Persistence, Analytics & Operational Automation

### 4.1 Embedded Database Engine (SQLite)
- **Status**: ✅ **Implemented** in [src/gex/storage/db.py](src/gex/storage/db.py).
- **Details**:
  - Embedded SQLite database engine (`data/trades.db`) featuring ACID transactions, indexed schemas (`trades`, `gex_snapshots`), and analytical aggregations (`query_trade_metrics`).
  - Automatically synchronizes closed option and stock positions, computing win rates, profit factor, average hold times, and realized P&L.
  - Supports persistence of daily underlier GEX profile snapshots (`save_gex_snapshot`, `query_latest_gex_snapshot`).

### 4.2 Automated Notification Webhooks
- **Status**: ✅ **Implemented** via `dispatch_system_alert` in [src/gex_engine.py](src/gex_engine.py).
- **Details**:
  - Supports zero-dependency webhook alerting (`GEX_ALERT_WEBHOOK_URL`) for Slack, Discord, and Telegram.
  - Supports native macOS desktop notifications (`GEX_DESKTOP_NOTIFICATIONS=true`).

### 4.3 Headless Pre-Market Audit Mode
- **Status**: ✅ **Implemented** via `gex audit-all` in [src/gex_engine.py](src/gex_engine.py).
- **Details**:
  - Standalone pre-market execution CLI mode suitable for automated cron schedules.
  - Automatically audits all active accounts, evaluates Stops 1–5, checks regime gates, generates executive markdown morning briefs (or JSON via `--json`), and triggers alerts via `--alert`.

---

## 🚀 Phase 5: Advanced Strategy Engineering & Backtesting (Future Horizons)

### 5.1 Historical Options Replay & Backtesting Engine
- **Objective**: Develop an offline simulation harness that iterates across historical option chains and price historicals (`data/downloads/`) to evaluate setup win rates, stop performance, and profit expectancy without broker interaction.
- **Components**:
  - Virtual portfolio state machine simulating order fills, slippage, and Stop 1–5 exits.
  - Parameter grid search (optimal target delta, DTE windows, stalling thresholds).

### 5.2 Dynamic Delta Rolling & Profit Optimization
- **Objective**: Implement systematic option contract rolling rules when positions achieve significant gains:
  - Roll up and out (e.g. from Delta $\ge 0.70$ back to Delta $0.45$, extending DTE back to 30–45 days) to extract realized capital while maintaining upside convexity.
  - Systematic stop ratchet adjustments upon reaching +50% and +100% ROI.

### 5.3 Automated Macro Hedge Sizing
- **Objective**: Quantitative hedging framework when Regime Gates shift to `DEFENSIVE` or `BLOCKED`:
  - Compute total portfolio beta-weighted directional delta against SPY.
  - Determine optimal hedge contract allocation (SPY / QQQ put spreads) to neutralize directional exposure while maintaining high-conviction individual GEX setups.

---

## 📊 Summary Roadmap Matrix

| Milestone | Phase | Priority | Status | Primary Impact | Dependencies |
| :--- | :---: | :---: | :---: | :--- | :--- |
| **Multi-Harness Synchronization** | Phase 1 (Foundations) | 🔴 High | ✅ Completed | Automated bidirectional sync between .github/ and .agents/ | None |
| **Packaging & CI/CD** | Phase 1 (Foundations) | 🔴 High | ✅ Completed | Automated linting, test execution, regression guards (146 tests) | None |
| **Modular Package Refactoring** | Phase 2 (Modularization) | 🔴 High | ✅ Completed | Clean domain packages (`core`, `quant`, `risk`, `screening`, `storage`, `presentation`) | Phase 1 |
| **Strict Domain Models & Adapters** | Phase 2 (Modularization) | 🔴 High | ✅ Completed | Strongly typed dataclasses with ingestion boundary adapters | Phase 2 |
| **Modular Roadmap Test Suite** | Phase 2 (Modularization) | 🟡 Medium | ✅ Completed | 146 unit tests passing across all domain packages | Phase 2 |
| **Zero-Crossing Linear Interpolation** | Phase 3 (Quant Modeling) | 🔴 High | ✅ Completed | Exact continuous zero-crossing strikes for pTrans & nTrans | Phase 2 |
| **Black-Scholes Gamma Fallback** | Phase 3 (Quant Modeling) | 🟡 Medium | ✅ Completed | Pure Python analytical Gamma fallback for illiquid chains | Phase 2 |
| **DTE-Weighted GEX Modeling** | Phase 3 (Quant Modeling) | 🟢 Low | ✅ Completed | Real-time effective dealer delta hedging pressure | Phase 3 |
| **Slippage & Spread Friction** | Phase 3 (Quant Modeling) | 🟢 Low | ✅ Completed | 35% bid-ask spread penalty modeling in option contract selection | Phase 2 |
| **Multi-Account Cache Isolation** | Phase 3 (Quant Modeling) | 🟡 Medium | ✅ Completed | Zero state bleeding with account-scoped cache invalidation | Phase 2 |
| **SQLite Trade Journal Persistence** | Phase 4 (Persistence) | 🟢 Low | ✅ Completed | Embedded ACID database for historical trades and GEX snapshots | Phase 2 |
| **Notification Webhooks** | Phase 4 (Persistence) | 🟢 Low | ✅ Completed | Webhooks (Slack/Discord/Telegram) and macOS notifications | Phase 2 |
| **Headless Pre-Market Audit Mode** | Phase 4 (Persistence) | 🟢 Low | ✅ Completed | Automated `audit-all` CLI mode with executive morning markdown | Phase 4 |
| **Historical Replay & Backtesting** | Phase 5 (Future) | 🟡 Medium | 📋 Planned | Offline simulation harness for rule validation | Phase 4 |
| **Dynamic Delta Rolling Engine** | Phase 5 (Future) | 🟢 Low | 📋 Planned | Systematic roll-up/roll-out rules for winning options | Phase 3 |
| **Automated Macro Hedge Sizing** | Phase 5 (Future) | 🟢 Low | 📋 Planned | Beta-weighted SPY/QQQ hedge sizing on defensive regime transitions | Phase 3 |

---

*Document maintained collaboratively by human traders and the GEX Agent Workspace.*
