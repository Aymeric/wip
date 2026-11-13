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
6. **Phase 6: Capital Efficiency & Multi-Leg Spread Engineering** (Defined-Risk Vertical Spreads, Dynamic Collars).

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

### 1.4 Static Analysis CI Gate (ruff + mypy) ([#162](https://github.com/Aymeric/wip/issues/162))
- **Status**: ✅ **Implemented** (configured in [pyproject.toml](pyproject.toml), executed in [.github/workflows/ci.yml](.github/workflows/ci.yml), and documented in [README.md](README.md)).
- **Need & Outcome**: `ruff` and `mypy` are configured in [pyproject.toml](pyproject.toml) but never executed in [.github/workflows/ci.yml](.github/workflows/ci.yml), so lint and type regressions in the modular `src/gex/` packages go undetected.
- **Action Items**:
  - [x] Add `ruff check` and `mypy src/gex` steps to the CI matrix.
  - [x] Establish a baseline (per-module ignores/allowlist) so the gate starts green without a mass rewrite.
  - [x] Ratchet strictness per package (`core`, `quant`, `risk` first) and document the local commands in [README.md](README.md).

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

## 🚀 Phase 5: Advanced Strategy Engineering & Operational Automation

### 5.1 Historical Options Replay & Backtesting Engine ([#193](https://github.com/Aymeric/wip/issues/193))
- **Need & Outcome**: Enable systematic backtesting and offline simulation of the GEX trading rules across cached historical option chains and price series (`data/downloads/`). Validates win rate, expectancy, and parameter sensitivity (delta targets, stalling days, stop thresholds) without capital risk.
- **Action Items**:
  - [ ] Implement `src/gex/backtest/engine.py` with virtual portfolio state machine and trade ledger.
  - [ ] Build historical quote replay harness parsing dated JSON files in `data/downloads/`.
  - [ ] Implement simulated fill models incorporating the 35% bid-ask spread slippage penalty.
  - [ ] Calculate backtest performance metrics (Sharpe ratio, Sortino ratio, max drawdown, win rate by market regime).
  - [ ] Expose CLI command `python3 src/gex_engine.py backtest --start YYYY-MM-DD --end YYYY-MM-DD`.

### 5.2 Dynamic Delta Rolling & Profit Optimization Engine
- **Status**: ✅ **Implemented** (module in [src/gex/risk/rolling.py](src/gex/risk/rolling.py); CLI command `evaluate-rolls` in [src/gex_engine.py](src/gex_engine.py); tests in [tests/test_rolling.py](tests/test_rolling.py)).
- **Need & Outcome**: When long call options move deeply into the money (Delta $\ge 0.70$ or $>+50\%$ gain), gamma and convexity diminish while capital at risk increases. This engine systematically identifies roll candidates to lock in realized gains, reset DTE back to 30–45 days, and restore optimal delta ($\approx 0.45$).
- **Action Items**:
  - [x] Implement `src/gex/risk/rolling.py` to evaluate roll eligibility for active positions.
  - [x] Compute net credit/debit for rolling out and up to target strike (Delta 0.40–0.50, 30–45 DTE).
  - [x] Implement systematic profit-ratchet rules (+50% giveback trailing stop adjustment).
  - [x] Integrate roll recommendations into `portfolio-risk-manager` and `agentic-trader` approval flows.
  - [x] Expose CLI command `python3 src/gex_engine.py evaluate-rolls --account ACCOUNT_NUMBER`.

### 5.3 Automated Portfolio Beta-Weighted Macro Hedging Engine
- **Status**: ✅ **Implemented** (module in [src/gex/risk/hedge.py](src/gex/risk/hedge.py); CLI command `hedge-plan` in [src/gex_engine.py](src/gex_engine.py); tests in [tests/test_hedge.py](tests/test_hedge.py)).
- **Need & Outcome**: During market-wide regime transitions to `DEFENSIVE` or `BLOCKED` (Stop 4), closing all single-stock setups prematurely can disrupt high-conviction structural holds. This engine derives an optimal index hedge (SPY/QQQ debit put spreads) sized to neutralize portfolio beta-weighted directional delta.
- **Action Items**:
  - [x] Implement `src/gex/risk/hedge.py` calculating aggregate beta-weighted directional delta:
    $$\Delta_{\text{portfolio, SPY}} = \sum_i \beta_i \cdot \Delta_i \cdot \frac{S_i}{S_{\text{SPY}}}$$
  - [x] Derive target hedge contract allocation using SPY / QQQ put debit spreads.
  - [x] Define entry, sizing, and exit rules for macro hedges linked to Market Regime Gates transitions.
  - [x] Expose CLI command `python3 src/gex_engine.py hedge-plan --account ACCOUNT_NUMBER`.

### 5.4 Intraday GEX Level Breach Monitor & Real-Time Alert Daemon
- **Status**: ✅ **Implemented** (module in [src/gex/screening/monitor.py](src/gex/screening/monitor.py); CLI command `monitor` in [src/gex_engine.py](src/gex_engine.py); tests in [tests/test_monitor.py](tests/test_monitor.py)).
- **Need & Outcome**: Daily GEX levels ($pTrans$, $nTrans$, $+GEX$) provide structural runway bounds, but underlying spot prices can breach $nTrans$ (Stop 1) or reach $+GEX$ (Profit Target) during trading hours. This daemon monitors active holdings in near-real-time and dispatches instant webhook/desktop alerts upon level breaches.
- **Action Items**:
  - [x] Implement `src/gex/screening/monitor.py` with lightweight polling/event loop for active position underliers.
  - [x] Compare intraday quotes against active holding GEX thresholds ($nTrans$ stop breach, $+GEX$ target touch, trailing stop giveback).
  - [x] Integrate with `dispatch_system_alert` for instant Slack, Discord, Telegram, and desktop notifications.
  - [x] Expose CLI daemon command `python3 src/gex_engine.py monitor --interval SECONDS --alert`.

### 5.5 Stop-Coded Exit Attribution ([#163](https://github.com/Aymeric/wip/issues/163))
- **Status**: ✅ **Implemented** (codes in [src/gex/core/config.py](src/gex/core/config.py); tests in [tests/test_exit_attribution.py](tests/test_exit_attribution.py)).
- **Need & Outcome**: The SQLite `trades.exit_reason` column ([src/gex/storage/db.py](src/gex/storage/db.py)) always records `MANUAL` because `close-position` / `close-stock` accept no reason. Coding every exit against the Stop 1–5 hierarchy lets the trade journal measure expectancy and adherence per stop.
- **Action Items**:
  - [x] Add a validated `--reason {STOP1,STOP2,STOP3,STOP4,STOP5,TARGET,MANUAL,RECONCILED}` flag to `close-position` and `close-stock`.
  - [x] Persist the code to JSON closed caches and SQLite `exit_reason`; map trade-history reconciliation closes to `RECONCILED`.
  - [x] Add per-exit-reason win rate / expectancy breakdown to `journal`, and update `portfolio-risk-manager` / `agentic-trader` skills to pass the triggering stop.

### 5.6 Approval Decision Ledger ([#164](https://github.com/Aymeric/wip/issues/164))
- **Status**: ✅ **Implemented** (SQLite ledger in [src/gex/storage/db.py](src/gex/storage/db.py); CLI commands `record-decision` and `decisions` in [src/gex_engine.py](src/gex_engine.py); tests in [tests/test_decision_ledger.py](tests/test_decision_ledger.py)).
- **Need & Outcome**: Execution approval requests (entries and exits) are only printed to the terminal, and the `ask_question` answer is not persisted. A durable ledger provides provenance for every decision and lets the journal audit mechanical adherence vs. human overrides.
- **Action Items**:
  - [x] Add a `decisions` SQLite table (timestamp, masked account, symbol/contract, action, grade, regime gates, triggering stop, recommendation, human answer, order ref).
  - [x] Expose `record-decision` and `decisions --account ACCOUNT_NUMBER` CLI commands; never store credentials or full account numbers.
  - [x] Wire `gex-orchestrator` / `agentic-trader` skills to record each approval outcome, including declines and skipped/ambiguous answers.

### 5.7 IV Rank / IV Percentile Entry Context ([#165](https://github.com/Aymeric/wip/issues/165))
- **Need & Outcome**: Entry screening uses an absolute IV floor (≥ 30%) only. *Hypothesis*: buying single-leg premium when IV is high relative to the underlier's own history degrades expectancy. Relative IV context would inform contract selection and grading.
- **Action Items**:
  - [x] Capture daily ATM IV (30-day) into `gex_snapshots` alongside GEX levels.
  - [x] Implement IV rank / percentile in `src/gex/quant/` with explicit `UNKNOWN` when history is below a minimum lookback.
  - [x] Surface IVR in `analyze` / candidate tables as informational first; promote to a gate only after backtest evidence (depends on 5.1).

### 5.8 CLI Extraction into `src/gex/cli/` ([#166](https://github.com/Aymeric/wip/issues/166))
- **Need & Outcome**: [src/gex_engine.py](src/gex_engine.py) is ~6,600 lines hosting 28 subcommands while `src/gex/cli/` is empty. Phase 5 adds four more commands; extracting command handlers reduces regression risk and review cost.
- **Action Items**:
  - [ ] Move argparse wiring and `cmd_*` handlers into `src/gex/cli/` modules grouped by domain (portfolio, screening, regime, journal, ops).
  - [ ] Keep `python3 src/gex_engine.py <subcommand>` and existing root re-exports 100% backward compatible.
  - [ ] Full test suite and harness sync pass unchanged after extraction.

### 5.9 Second-Order Dealer Exposure Modeling (Vanna & Charm Profiles) ([#194](https://github.com/Aymeric/wip/issues/194))
- **Status**: ✅ **Implemented** (Greeks in [src/gex/quant/greeks.py](src/gex/quant/greeks.py); GEX profile derivation in [src/gex/quant/gex.py](src/gex/quant/gex.py); domain models in [src/gex/core/models.py](src/gex/core/models.py); presentation in [src/gex/presentation/formatters.py](src/gex/presentation/formatters.py); tests in [tests/test_vanna_charm.py](tests/test_vanna_charm.py)).
- **Need & Outcome**: While Gamma Exposure (GEX) models price acceleration, dealer delta hedging is also heavily driven by implied volatility changes ($\text{Vanna} = \partial \Delta / \partial \sigma$) and time decay ($\text{Charm} = \partial \Delta / \partial t$). Capturing Vanna and Charm provides leading indicators for market direction ahead of volatility events (FOMC, CPI, earnings) and weekend theta decay.
- **Action Items**:
  - [x] Implement analytical Black-Scholes Vanna and Charm formulations in `src/gex/quant/greeks.py`.
  - [x] Aggregate strike-level net Vanna and Charm exposures into `derive_gex_profile` and domain models in `src/gex/core/models.py`.
  - [x] Calculate net Vanna asymmetry score and Charm tilt to detect whether dealer decay will create buying or selling pressure.
  - [x] Surface Vanna/Charm exposure metrics in Runway Maps and `analyze` CLI output.

### 5.10 Alert Hysteresis & Notification Rate-Limiting Engine ([#195](https://github.com/Aymeric/wip/issues/195))
- **Status**: ✅ **Implemented** (state machine & hysteresis in [src/gex/screening/monitor.py](src/gex/screening/monitor.py); CLI options in [src/gex_engine.py](src/gex_engine.py); tests in [tests/test_alert_hysteresis.py](tests/test_alert_hysteresis.py)).
- **Need & Outcome**: Intraday level breach monitoring (`src/gex/screening/monitor.py`) can generate duplicate alerts and exceed webhook rate limits when underlying spot prices oscillate rapidly across $nTrans$ (Stop 1) or $+GEX$ (Profit Target). A stateful alerting engine with cooldowns and hysteresis deadbands ensures reliable alerting without notification fatigue.
- **Action Items**:
  - [x] Implement an alert tracking state machine in `src/gex/screening/monitor.py` or dedicated alerting module.
  - [x] Enforce configurable per-symbol/per-stop alert cooldown intervals (e.g. 30–60 minutes between repeat alerts).
  - [x] Add a $\pm 0.25\%$ hysteresis deadband around key GEX boundaries before re-arming level breach triggers.
  - [x] Support consolidated end-of-day alert digests and prevent webhook HTTP 429 throttling.

---

## 🏛️ Phase 6: Capital Efficiency & Multi-Leg Spread Engineering

### 6.1 Defined-Risk Vertical Spread Architecture & Payoff Engine ([#196](https://github.com/Aymeric/wip/issues/196))
- **Status**: ✅ **Implemented** (module in [src/gex/screening/spreads.py](src/gex/screening/spreads.py); domain model in [src/gex/core/models.py](src/gex/core/models.py); presentation in [src/gex/presentation/formatters.py](src/gex/presentation/formatters.py); CLI command `select-spreads` in [src/gex_engine.py](src/gex_engine.py); tests in [tests/test_vertical_spreads.py](tests/test_vertical_spreads.py)).
- **Need & Outcome**: Long single-leg options experience severe theta decay and IV crush when underliers trade at elevated implied volatility (e.g., IV rank > 70%). A defined-risk debit vertical spread engine allows buying an ATM/near-OTM contract and selling an OTM strike at the $+GEX$ call wall, reducing capital outlay by 30–50% and matching profit targets directly to dealer resistance bounds.
- **Action Items**:
  - [x] Implement vertical spread modeling in `src/gex/screening/selector.py` (or `src/gex/screening/spreads.py`) to pair long ATM strikes with short $+GEX$ call wall strikes.
  - [x] Compute net debit, maximum profit, maximum loss, breakeven, and risk/reward ratios with realistic bid-ask spread slippage.
  - [x] Integrate spread selection into candidate generation for elevated IV regimes (IV rank > 70%).
  - [x] Expose CLI command `python3 src/gex_engine.py select-spreads --symbol TICKER`.

---

## 📊 Summary Roadmap Matrix

> **Current Shipped Release**: **v1.1.0** (incorporating all milestones across Phase 1, Phase 2, Phase 3, and Phase 4).

| Milestone | Phase | Priority | Status | Primary Impact | Dependencies |
| :--- | :---: | :---: | :---: | :--- | :--- |
| **Multi-Harness Synchronization** | Phase 1 (Foundations) | 🔴 High | ✅ Completed | Automated bidirectional sync between .github/ and .agents/ | None |
| **Packaging & CI/CD** | Phase 1 (Foundations) | 🔴 High | ✅ Completed | Automated linting, test execution, regression guards (152 tests) | None |
| **Modular Package Refactoring** | Phase 2 (Modularization) | 🔴 High | ✅ Completed | Clean domain packages (`core`, `quant`, `risk`, `screening`, `storage`, `presentation`) | Phase 1 |
| **Strict Domain Models & Adapters** | Phase 2 (Modularization) | 🔴 High | ✅ Completed | Strongly typed dataclasses with ingestion boundary adapters | Phase 2 |
| **Modular Roadmap Test Suite** | Phase 2 (Modularization) | 🟡 Medium | ✅ Completed | 152 unit tests passing across all domain packages | Phase 2 |
| **Zero-Crossing Linear Interpolation** | Phase 3 (Quant Modeling) | 🔴 High | ✅ Completed | Exact continuous zero-crossing strikes for pTrans & nTrans | Phase 2 |
| **Black-Scholes Gamma Fallback** | Phase 3 (Quant Modeling) | 🟡 Medium | ✅ Completed | Pure Python analytical Gamma fallback for illiquid chains | Phase 2 |
| **DTE-Weighted GEX Modeling** | Phase 3 (Quant Modeling) | 🟢 Low | ✅ Completed | Real-time effective dealer delta hedging pressure | Phase 3 |
| **Slippage & Spread Friction** | Phase 3 (Quant Modeling) | 🟢 Low | ✅ Completed | 35% bid-ask spread penalty modeling in option contract selection | Phase 2 |
| **Multi-Account Cache Isolation** | Phase 3 (Quant Modeling) | 🟡 Medium | ✅ Completed | Zero state bleeding with account-scoped cache invalidation | Phase 2 |
| **SQLite Trade Journal Persistence** | Phase 4 (Persistence) | 🟢 Low | ✅ Completed | Embedded ACID database for historical trades and GEX snapshots | Phase 2 |
| **Notification Webhooks** | Phase 4 (Persistence) | 🟢 Low | ✅ Completed | Webhooks (Slack/Discord/Telegram) and macOS notifications | Phase 2 |
| **Headless Pre-Market Audit Mode** | Phase 4 (Persistence) | 🟢 Low | ✅ Completed | Automated `audit-all` CLI mode with executive morning markdown | Phase 4 |
| **Historical Replay & Backtesting** | Phase 5 (Advanced Strategy) | 🟡 Medium | 📋 Planned | Offline simulation harness for rule validation across downloads | Phase 4 |
| **Dynamic Delta Rolling Engine** | Phase 5 (Advanced Strategy) | 🟢 Low | ✅ Completed | Systematic roll-up/roll-out rules for winning options (Delta >= 0.70) | Phase 3 |
| **Automated Macro Hedge Sizing** | Phase 5 (Advanced Strategy) | 🟢 Low | ✅ Completed | Beta-weighted SPY/QQQ hedge sizing on defensive regime transitions | Phase 3 |
| **Intraday Level Breach Monitor** | Phase 5 (Advanced Strategy) | 🟡 Medium | ✅ Completed | Real-time monitoring daemon for Stop 1 / Profit Target breaches | Phase 4 |
| **Static Analysis CI Gate** | Phase 1 (Foundations) | 🟡 Medium | ✅ Completed | ruff + mypy enforced in CI with baseline ratchet | Phase 1 |
| **Stop-Coded Exit Attribution** | Phase 5 (Advanced Strategy) | 🔴 High | ✅ Completed | Per-stop expectancy via coded `exit_reason` | Phase 4 |
| **Approval Decision Ledger** | Phase 5 (Advanced Strategy) | 🟡 Medium | ✅ Completed | Durable provenance of approvals, declines, and overrides | Phase 4 |
| **IV Rank / Percentile Context** | Phase 5 (Advanced Strategy) | 🟢 Low | ✅ Completed | Relative IV context for entries (gate only after backtest) | 5.1 |
| **CLI Extraction (`src/gex/cli/`)** | Phase 5 (Advanced Strategy) | 🟡 Medium | 📋 Planned | Smaller engine module; safer Phase 5 command additions | Phase 2 |
| **Vanna & Charm Exposure** | Phase 5 (Advanced Strategy) | 🟡 Medium | ✅ Completed | Second-order dealer exposure modeling for vol crush and decay flows | Phase 3 |
| **Alert Hysteresis & Rate-Limiting** | Phase 5 (Advanced Strategy) | 🟢 Low | ✅ Completed | Stateful cooldowns and deadbands for intraday webhook alerts | 5.4 |
| **Defined-Risk Vertical Spreads** | Phase 6 (Multi-Leg Spreads) | 🟡 Medium | ✅ Completed | Debit call spreads pegged to +GEX call walls for high IV regimes | 5.7 |

---

*Document maintained collaboratively by human traders and the GEX Agent Workspace.*
