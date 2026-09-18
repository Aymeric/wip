# System Instructions: GEX Trading System

When working in this repository:

1. **Strict Quantitative Framework**:
   - Do not perform manual calculations for option Greeks, GEX indicators, regime breadth, or position sizing. Use `python3 src/gex_engine.py <subcommand>`.
   - Never infer, guess, or assume missing market data. If live quotes or GEX levels are unavailable, record `UNKNOWN/BLOCKED` with explicit evidence.

2. **User Interaction Convention**:
   - For all user prompts requiring decisions, confirmations, account picks (unless explicitly specified in the prompt), or gate skips, invoke the `ask_question` tool.
   - Never ask or confirm orders via free-form chat.

3. **Account Partitioning**:
   - Every operation touching Robinhood positions or P&L must be account-scoped. Always specify `--account ACCOUNT_NUMBER` in CLI invocations.
   - Store active positions in `data/active_positions_<account>.json` and closed positions in `data/closed_positions_<account>.json`.

4. **Options Candidates Discovery**:
   - The candidate discovery pipeline must source and evaluate **options candidates**, not just stock underliers.
   - Sourcing must query the dedicated Robinhood Options Watchlist via `robinhood-trading/get_option_watchlist`, prioritize underliers with liquid options (30d options volume $\ge 10,000$, IV $\ge 30\%$, relative options volume), and isolate 30–45 DTE single-leg option contract candidates.
   - Persist underlier setups in `data/candidate_stocks.json` and option contract candidates in `data/candidate_options.json`.

5. **Skills & Prompts Directory**:
   - Workspace Skills are located in `.agents/skills/`.
   - Workspace Prompts are located in `.agents/prompts/`.
   - Workspace Agent definitions are in `.agents/agents/`.
   - Workspace rules reside in `.agents/rules/`.
