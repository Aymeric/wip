# GEX Trading System Rules & Behavioral Constraints

These rules are enforced across all sessions in this workspace.

## 1. Tool Mapping & Interaction Protocol
- **Human Decisions**: Whenever user input, account selection, gate bypass, or trade confirmation is needed, call the `ask_question` tool.
- **Single / Multi-Select**: Use `is_multi_select: false` for single choices and `is_multi_select: true` for multi-account selections.
- **Safety Gate**: Never infer consent or trade approval from informal conversational text.

## 2. API & Tool Batch Chunking Limits
- **Option Contract Quotes**: When calling `robinhood-trading/get_option_quotes`, chunk queries into batches of **at most 40 contract IDs** per call to avoid HTTP 414 URI length errors.
- **Equity Fundamentals**: When calling `robinhood-trading/get_equity_fundamentals`, chunk queries into batches of **at most 10 symbols** per call.
- **Watchlists**: Query watchlist items sequentially, never concurrently.

## 3. Account Scoping & CLI Command Rules
- **Account Identifier**: Always determine and require the target Robinhood account number before executing portfolio-affecting commands.
- **CLI Commands**: Every invocation of `update-option`, `update-stock`, `portfolio`, `sync-positions`, and `sync-pnl` must explicitly supply `--account ACCOUNT_NUMBER`.
- **Position Files**: Active positions are saved to `data/active_positions_ACCOUNT_NUMBER.json` and closed positions to `data/closed_positions_ACCOUNT_NUMBER.json`.

## 4. Exit Stop Hierarchy (Stops 1 to 5)
1. **Stop 1 (Structural Stop)**: Close below $nTrans$ (Secondary Support). Exit at the next session open.
2. **Stop 2 (Trailing Volatility Stop)**: 20% giveback of maximum unrealized gain.
3. **Stop 3 (Time Stop / Theta Gate)**: Exit if DTE falls below 14 days or trade stalls $>10$ trading days without progress.
4. **Stop 4 (Macro / Regime Stop)**: Market regime failure (Bull:Bear $< 3.0:1$ or VIX expansion) triggers defensive review.
5. **Stop 5 (Catastrophic Risk Stop)**: Hard stop at -50% loss of position premium.

## 5. Market Session & Freshness
- Derive the **Effective Session Date** from the latest completed regular US equity trading session. Never use wall-clock calendar date on weekends or market holidays.
- Outdated cached analyses (>1 session old) must be marked `HISTORICAL/STALE` and cannot authorize new entries.
