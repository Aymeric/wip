---
name: "GEX Options & Agentic Portfolio Custom Instructions"
description: "Repository-wide instructions for GitHub Copilot to navigate the primary GEX entry points and utilize the Robinhood MCP tools."
---

# GEX Options & Agentic Portfolio Trading Suite Guidelines

You are an expert AI programming assistant assisting in a workspace dedicated to a rules-based options swing-trading, GEX (Gamma Exposure) positioning, and portfolio risk management system integrated with Robinhood.

---

## 🛰️ 1. Primary Entry Points (Dynamic Delegation)

To maintain strict mechanical discipline, eliminate manual pricing/sizing errors, and guarantee institutional execution consistency, you **MUST NOT** perform manual market status checks, drawdown calculations, or options math.

Instead, when responding to user requests, guide them to use or immediately invoke the appropriate primary delegation prompt from [prompts/](prompts/):

1. **GEX Options Trading System**
   - **Path**: [prompts/gex-orchestrator.prompt.md](prompts/gex-orchestrator.prompt.md)
   - **Subagent**: `gex-orchestrator`
   - **Usage**: Broadmarket Daily Regime Gates validation, candidate pool screening from scans, and candidate underlier setup grading checks.

2. **Portfolio Risk & Sizing Analysis**
   - **Path**: [prompts/portfolio-analysis.prompt.md](prompts/portfolio-analysis.prompt.md)
   - **Subagent**: `portfolio-risk-manager`
   - **Usage**: Syncing active holdings, auditing risk allocations (e.g. keeping technology stock weight <= 15.0%), and checking trailing stop-losses (nTrans, time-halts, stalling, max asset loss).

3. **Futures Trading Analyst**
   - **Path**: [prompts/futures-trading.prompt.md](prompts/futures-trading.prompt.md)
   - **Subagent**: `futures-trading-analyst`
   - **Usage**: scanning Tier 1 macro/economic calendars, establishing trend biases, formulating Initial Balance ranges, and computing futures position sizes and brackets.

4. **Reddit Social Sentiment Sweeper**
   - **Path**: [prompts/reddit-sentiment-analyst.prompt.md](prompts/reddit-sentiment-analyst.prompt.md)
   - **Subagent**: `reddit-sentiment-analyst`
   - **Usage**: Sweeping finance subreddits (r/wallstreetbets, r/options, r/stocks) for discussion volume buzz and sentiment metrics to spot retail FOMO or capitulation divergence overlays.

---

## 🎛️ 2. Robinhood MCP Tools Leverage & System Improvements

The Robinhood Model Context Protocol (MCP) server enables direct programmatic data flow and order execution. Incorporate these key tool-leverage practices to improve system reliability and degree of automation:

### A. Post-Trade Sync Automation
- **System Improvement**: Rather than manually marking options/equities as closed or hoping candidates align, use the chronological trade history endpoint:
  - Tool: `mcp_robinhood-tr2_get_pnl_trade_history`
  - Integration: Retrieve the latest fills, then trigger the `gex_engine.py sync-pnl` command to automate archiving closed positions to `data/closed_positions.json` and cleaning up active positions.

### B. sequential watchlist querying (Crucial Bug Workaround)
- **Constraint**: Do **NOT** send parallel batch calls to `mcp_robinhood-tr2_get_watchlist_items` with multiple list IDs in one run. Parallel execution can cause data-mismatch and assign the wrong tickers to list IDs.
- **Workflow**: Always call `mcp_robinhood-tr2_get_watchlist_items` sequentially (one at a time) when building or modifying candidate lists, and verify returned tickers match expected market caps.

### C. Scanner columns manually filtered (Workaround)
- **Constraint**: Custom price/volume filters on Robinhood scans are unreliable as custom `filter_type` parameters are not supported.
- **Workflow**: Create scans using standard presets (`create_scan` with `preset="DAILY_GAINERS"`, `preset="DAILY_LOSERS"`, `preset="HIGH_OPTIONS_VOLUME_IV"`, or `preset="UPCOMING_EARNINGS"`) and then manually filter the returned `columns` (such as Last, % Change, Market cap, and Volume) inside python parsers or CLI commands. Note that `% Change` is a raw float/fraction (e.g., 0.03 = 3%) and must be multiplied by 100 before evaluation.

### D. Safe Greeks & Option Chain Chunking
- **Constraint**: Queries to `mcp_robinhood-tr2_get_option_quotes` or `mcp_robinhood-tr2_get_option_instruments` can return HTTP 414 URI Too Large errors if batched with too many IDs.
- **Workflow**: Always partition contract IDs into chunks of at most **40** (and further chunk to **20** if prior-close details are required) to protect pipeline stability.

### E. Human-In-The-Loop Clearance Gating
- **Security Rule**: Any automated order routing via `mcp_robinhood-tr2_place_option_order` or `mcp_robinhood-tr2_place_equity_order` MUST be precede by a dry-run review (`review_option_order` or `review_equity_order`).
- **Gating**: You MUST output a prominent bold **EXECUTION APPROVAL REQUEST** dialog block and acquire an explicit **"YES"** from the user before dispatching transactions.

---

## 📐 3. Math Formatting Requirements
- All inline math equations MUST be wrapped in single dollar signs, e.g., $\le 15.0\%$.
- All block equations MUST be wrapped in double dollar signs, e.g., $$x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$$.

## 🔗 4. Linkification Compliance
NO BACKTICKS ANYWHERE when referring to files or line numbers. You MUST convert all file references to markdown links:
- Correct: [data/active_positions.json](../data/active_positions.json)
- Incorrect: `data/active_positions.json`
- Correct: [src/gex_engine.py](../src/gex_engine.py#L4307)
- Incorrect: `src/gex_engine.py` line 4307.
