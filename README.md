# Robinhood Agentic Trading Portfolio Review

Use this lightweight workflow to review a Robinhood portfolio and generate actionable recommendations.

## 1) Inputs to gather

- Current holdings (ticker, shares, average cost, current value)
- Cash balance
- Risk tolerance (low / medium / high)
- Time horizon (short / medium / long term)
- Constraints (tax sensitivity, sector limits, max single-position %)

## 2) Portfolio checks

1. **Concentration risk**  
   Flag positions above 15-20% of total portfolio value.
2. **Diversification**  
   Check exposure by sector and asset class (stocks, ETFs, cash).
3. **Volatility fit**  
   Ensure portfolio beta/volatility matches the target risk tolerance.
4. **Liquidity and cash buffer**  
   Keep enough cash for near-term needs and market flexibility.
5. **Rebalancing drift**  
   Compare current weights to target weights and identify drift.

## 3) Recommendation framework

- **Reduce** overweight positions beyond concentration limits.
- **Add** broad-market ETFs for core diversification.
- **Rebalance** periodically (monthly/quarterly or threshold-based).
- **Set risk controls** (position sizing, stop-loss policy, max drawdown rules).
- **Review costs and taxes** before trades (fees, spreads, short-term gains).

## 4) Example recommendation output format

```text
Portfolio summary:
- Total value: $X
- Largest position: TICKER at Y%
- Cash: Z%
- Risk profile fit: Good / Needs adjustment

Recommendations:
1) Trim TICKER by N% to reduce concentration risk.
2) Add diversified ETF (e.g., VTI/VOO) to improve sector balance.
3) Increase cash to M% for short-term stability.
4) Rebalance monthly with a +/-5% drift threshold.
```

> This repository content is educational and not financial advice.
