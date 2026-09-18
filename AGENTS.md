# GEX Options Trading System - Agent Workspace

Welcome to the **Gamma Exposure (GEX) Options Trading System** agent workspace. This project is a systematic, mechanical swing-trading platform for single-stock options engineered around dealer gamma positioning, volatility regimes, and liquidity dynamics.

---

## 1. System Architecture & Agent Integration

Agents and skills in this workspace operate under strict quantitative discipline and separation of concerns.

```mermaid
graph TD
    User([User Prompt / Request]) --> Orchestrator["Skill: gex-orchestrator"]
    Orchestrator --> Phase1["Phase I: Risk & Audit"]
    Orchestrator --> Phase2["Phase II: Discovery & Sentiment"]
    Orchestrator --> Phase3["Phase III: Grading & Selection"]
    Orchestrator --> Phase4["Phase IV: Execution & Handoff"]

    subgraph "Phase I: Risk & Audit"
        Regime["market-regime-analyst"]
        Portfolio["portfolio-risk-manager"]
        Journal["trade-journal-analyst"]
    end

    subgraph "Phase II: Discovery & Sentiment"
        Candidates["gex-candidate-generator"]
        Sentiment["reddit-sentiment-analyst"]
    end

    subgraph "Phase III: Setup Engineering"
        Grader["gex-setup-grader"]
        Selector["option-selector"]
    end

    subgraph "Phase IV: Execution"
        Trader["agentic-trader"]
    end

    Phase1 --> Regime & Portfolio & Journal
    Phase2 --> Candidates & Sentiment
    Phase3 --> Grader --> Selector
    Phase4 --> Trader
```

---

## 2. Core Execution Principles & Behavioral Directives

1. **Strict Tool-Mediated Human Interaction**:
   - For every question, clarification, choice, or confirmation directed to the human, use the `ask_question` tool.
   - Never request or infer confirmation through ordinary chat text.
   - Use fixed options with clear labels. A skipped, empty, or ambiguous response never authorizes a trade, broker write, gate skip, or override.

2. **Mandatory Account Preflight**:
   - Establish the target Robinhood account first via `robinhood-trading/get_accounts` and `robinhood-trading/get_portfolio`.
   - Prompt the user using `ask_question` with masked account labels, account type, buying power, and `agentic_allowed` status.
   - All downstream CLI commands (e.g. `update-option`, `update-stock`, `portfolio`, `sync-positions`, `sync-pnl`) **MUST** explicitly pass `--account ACCOUNT_NUMBER`.
   - Never combine or aggregate accounts unless explicitly instructed by the user.

3. **Batch Chunking & Tool Guardrails**:
   - **Option Quotes**: Chunk contract lookups (`get_option_quotes`) into batches of **at most 40 contract IDs** per query to prevent HTTP 414 errors.
   - **Equity Fundamentals**: Chunk symbols in `get_equity_fundamentals` to batches of **at most 10 symbols** per request.
   - **Sequential Watchlist Queries**: Never query `get_watchlist_items` in parallel; run sequentially to avoid index scrambling.

4. **Exit Stop Priority Order (Stops 1 to 5)**:
   - **Stop 1 (Structural Stop)**: Close below $nTrans$ (Secondary Support). Exit at next session open.
   - **Stop 2 (Trailing Volatility Stop)**: Profit drawdown from peak (e.g. 20% giveback of max gain).
   - **Stop 3 (Time Stop / Theta Gate)**: Exit if DTE falls below 14 days or position stalls $>10$ trading days without progress.
   - **Stop 4 (Macro / Regime Stop)**: Bearish regime transition or Bull:Bear ratio collapse.
   - **Stop 5 (Catastrophic Risk Stop)**: Hard stop at -50% position value.

5. **No Manual Calculations**:
   - Always run the deterministic Python engine: `python3 src/gex_engine.py <subcommand>`.
   - Track workflow state using `python3 src/gex_engine.py workflow` and `update-workflow`.

6. **Watchlist Separation & Synchronization**:
   - **Pending Stock Candidates**: Add screened and pending stock candidates (underliers) to the equity watchlist (`GEX_DAILY_CANDIDATES`) via `robinhood-trading/add_to_watchlist` using `symbols`.
   - **Option Candidates**: Add isolated option contract candidates separately to the dedicated Robinhood **"options watchlist"** via `robinhood-trading/add_option_to_watchlist` using `option_ids`.
   - Never mix equity and options watchlist tools.

---

## 3. Skills Catalog in `.agents/skills/`

The workspace discovers and activates the following skills:

| Skill | Directory | Core Function |
| :--- | :--- | :--- |
| **gex-orchestrator** | [gex-orchestrator](.agents/skills/gex-orchestrator/SKILL.md) | End-to-end daily GEX run, account selection, Phase I-IV execution. |
| **market-regime-analyst** | [market-regime-analyst](.agents/skills/market-regime-analyst/SKILL.md) | Basket gate, 15-ETF Bull:Bear ratio, VIX delta compression. |
| **portfolio-risk-manager** | [portfolio-risk-manager](.agents/skills/portfolio-risk-manager/SKILL.md) | Live position sync, Stop 1-5 evaluation, buying power budgeting. |
| **gex-candidate-generator** | [gex-candidate-generator](.agents/skills/gex-candidate-generator/SKILL.md) | Robinhood scans, curated lists, technical alerts (RSI/MACD). |
| **gex-setup-grader** | [gex-setup-grader](.agents/skills/gex-setup-grader/SKILL.md) | Option chain parsing, pTrans/nTrans derivation, 11-Rule checklist. |
| **option-selector** | [option-selector](.agents/skills/option-selector/SKILL.md) | Isolates 30-45 DTE contracts, earnings preflight, spread checks. |
| **agentic-trader** | [agentic-trader](.agents/skills/agentic-trader/SKILL.md) | Pre-trade clearance, sizing, order simulation, execution confirmation. |
| **trade-journal-analyst** | [trade-journal-analyst](.agents/skills/trade-journal-analyst/SKILL.md) | Realized P&L reconciliation, rule adherence audit, recommendations. |
| **reddit-sentiment-analyst** | [reddit-sentiment-analyst](.agents/skills/reddit-sentiment-analyst/SKILL.md) | Social sentiment on WSB/options/stocks, FOMO / Capitulation alerts. |
| **futures-trading-analyst** | [futures-trading-analyst](.agents/skills/futures-trading-analyst/SKILL.md) | Multi-timeframe futures trend analysis (/ES, /NQ), pivot levels. |

---

## 4. MCP Servers Configuration

Configured in [.agents/mcp_config.json](.agents/mcp_config.json):
- `robinhood-trading`: `npx mcp-remote https://agent.robinhood.com/mcp/trading`
- `mcp-reddit`: `npx -y mcp-reddit`
