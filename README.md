# 📊 GEX Options & Agentic Portfolio Trading Suite

Welcome to the GEX Options & Agentic Portfolio Trading Suite! This repository provides an automated, programmatic mechanical trading workflow that integrates dealer gamma positioning checks, rule-based portfolio risk-management, futures strategy analysis, and secure execution on Robinhood.

The system consists of a Python mechanical GEX engine CLI and specialized Copilot prompts designed to guide interactive swing-trading decisions.

---

## 🛠️ Repository Components

This workspace is structured as follows:

1. **Python Mechanical GEX Engine**:
   - [gex_engine.py](gex_engine.py): The main execution script. It enforces dynamic options analyses, status updates, portfolio trailing/loss stops, and tracks risk allocations.
2. **Persistent Local Cache Databases**:
   - [regime.json](regime.json): Holds the computed status, gates, and metrics for the broad market Daily Regime Gates.
   - [ticker_analyses.json](ticker_analyses.json): Accumulates setup grading metrics (Spot, transition levels, Delta Balance change thresholds). See [ticker_analyses.json Schema Documentation](#-ticker_analysesjson-schema-documentation) below for the complete specification.
   - [active_options.json](active_options.json): Records open options positions, premium tracking, holding period, and stalling status. See [active_options.json Schema Documentation](#-active_optionsjson-schema-documentation) below for the complete specification.
3. **Specialized Copilot Prompt Manifests** (located in the `.github/prompts/` directory):
   - [gex-regime-trading.prompt.md](.github/prompts/gex-regime-trading.prompt.md): Implements rules-based options swing trading using GEX/dealer positioning mechanics.
   - [robinhood-portfolio-analysis.prompt.md](.github/prompts/robinhood-portfolio-analysis.prompt.md): Pulls and parses holdings, evaluates cash reserves, and designs customized allocation rebalancing recommendations.
   - [robinhood-agentic-trading.prompt.md](.github/prompts/robinhood-agentic-trading.prompt.md): Orchestrates buying power validation, tradability sweeps, and handles limit-order routing.
   - [futures-trading-strategy.prompt.md](.github/prompts/futures-trading-strategy.prompt.md): Analyzes multi-timeframe trends, Initial Balance ranges, VWAP deviations, and strict contract-sizing calculations.

---

## 🚀 Getting Started

### 1) Prerequisites
- Python 3.8 or higher.
- A functional terminal or shell environment.

### 2) Running the CLI Engine
The core execution script is [gex_engine.py](gex_engine.py). It operates via subcommands to parse different mechanical gates:

#### Check broad market authorization regime:
```bash
python3 gex_engine.py status
```

#### Recompute the Daily Regime Gates from raw market inputs:
```bash
python3 gex_engine.py update-regime --spy 0.62 --qqq 1.10 --bulls 120 --bears 35 --vix-bearish True --vix-spot 15.20
```
Gates are computed mechanically: **Basket** (SPY or QQQ > $+0.5\%$), **Bull:Bear** (ratio $> 3.0{:}1$), **VIX Delta** (dealer positioning bearish on VIX). Authorization resolves to `ALL TRACKS OK` (3/3), `TRACK 1 OK` (2/3), or `BLOCKED`.

#### Dynamically grade a quantitative GEX setup:
```bash
python3 gex_engine.py analyze AAPL --spot 289.55 --ptrans 285.00 --ntrans 282.00 --gex 310.00 --cotmp 280.00 --db-change 0.55
```

#### Run mechanics and trailing stops on active options positions:
```bash
python3 gex_engine.py portfolio
```

#### Manually append a new tracked contract:
```bash
python3 gex_engine.py add-position <option_id> <ticker> <strike> <expiration> <type> <purchase_premium>
```

#### Update specific contract tracking metrics:
```bash
python3 gex_engine.py update-option <option_id_or_ticker> --mark <mark_price> --days <days_held>
```

#### Close a tracked contract and archive realized P&L:
```bash
python3 gex_engine.py close-position <option_id_or_ticker> --close-premium <exit_premium>
```

---

## 📐 Portfolio Recommendation Framework

When executing portfolio reviews manually or via [robinhood-portfolio-analysis.prompt.md](.github/prompts/robinhood-portfolio-analysis.prompt.md), apply the following standard mechanics:

- **Trim or Reduce**: Any position exceeding $15\text{--}20\%$ of net liquidation value to contain concentration risk.
- **Add Sector Hedges**: Offset technology-biased exposure using broad-market instruments (e.g., Core S&P 500 or Total Stock Market indexes).
- **Enforce Single-Leg Limits**: Keep option sizing at $\le 3.0\%$ of Net Liq per position and cap technology beta at $\le 15.0\%$ cumulative.
- **Maintain Liquidity**: Always preserve a cash buffer for near-term flexibility.

---

## 🗄️ active_options.json Schema Documentation

The cache file [active_options.json](active_options.json) acts as the local storage layer tracking active underlier positions, option Greeks, trailing progress, and time constraints. 

### Schema Definition
```json
{
  "active_positions": {
    "<Option_ID_UUID>": {
      "Option ID": "79cd3800-e848-4d58-8997-308576acad72",
      "Underlier": "NKE",
      "Strike": "40.00",
      "Expiration": "2026-10-16",
      "Type": "call",
      "Purchase Premium": "4.75",
      "Delta": "0.734159",
      "Gamma": "0.036034",
      "Mark Price": 6.15,
      "Open Interest": 1317,
      "ImpVol": "0.389144",
      "Asset Cost Basis": 475.0,
      "Current Value": 615.0,
      "P&L (%)": 29.47,
      "P&L ($)": 140.0,
      "Sizing Risk Weight (%)": 0.92,
      "Beta Sector Tag": "Consumer Cyclical",
      "Days Held": 1,
      "Stalling Days": 0
    }
  }
}
```

### Parameter Details

| Field | Type | Description |
| :--- | :--- | :--- |
| `Option ID` | String | Unique contract tracking UUID sourced from Robinhood's instrument list. |
| `Underlier` | String | Capitalized ticker symbol of the underlying equity asset (e.g. `AAPL`). |
| `Strike` | String | Option contract target purchase strike price. |
| `Expiration` | String | Contract maturity date encoded in `YYYY-MM-DD` sequence. |
| `Type` | String | Option transaction parameter: `"call"` or `"put"`. |
| `Purchase Premium` | Decimal | Premium price per contract paid on order execution. |
| `Delta` | String | Real-time rate of option price change relative to underlying changes. |
| `Gamma` | String | Underlier-hedging rate of change tracking speed. |
| `Mark Price` | Float | Most recent mid-market price valuation of the contract. |
| `Open Interest` | Int | Cumulative counter tracking total active contracts. |
| `ImpVol` | String | Real-time Black-Scholes implied volatility (IV). |
| `Asset Cost Basis` | Float | Total original purchase capital committed ($\text{Purchase Premium} \times 100$). |
| `Current Value` | Float | Standard live market value of the contract ($\text{Mark Price} \times 100$). |
| `P&L (%)` | Float | Relative total return calculated directly from cost basis and mark price. |
| `P&L ($)` | Float | Nominal dollars returned to date. |
| `Sizing Risk Weight (%)` | Float | Portion of targeted Portfolio Value ($\text{Net Liq}$) allocated to this contract. |
| `Beta Sector Tag` | String| Sector classification identifier, utilized to compute aggregate technology industry limits. |
| `Days Held` | Int | Incremental tracker checking how long positions are maintained for structural time halts. |
| `Stalling Days` | Int | Standard sequential counter storing days of insufficient momentum. |

---

## 🗄️ ticker_analyses.json Schema Documentation

The cache file [ticker_analyses.json](ticker_analyses.json) is the incremental setup-grading store. Each analyzed candidate is merged in using its **ticker symbol as the unique key**, allowing setup analyses to accrue and persist across distinct sessions. Entries are written by the `analyze` CLI subcommand and refreshed with live spot prices (extended-hours preferred) on every prompt execution.

### Schema Definition
```json
{
  "<TICKER>": {
    "Ticker": "AAPL",
    "Spot": 289.55,
    "Grade": 11,
    "pTrans": 285.0,
    "nTrans": 282.0,
    "+GEX": 310.0,
    "COTMP": 280.0,
    "db_change": 0.55,
    "COTMP Cushion": 3.41,
    "Risk/Reward": 4.49,
    "Signal Status": "CONFIRMED",
    "analyzed_date": "2026-07-05",
    "pegged_1_00_sessions": 0
  }
}
```

### Parameter Details

| Field | Type | Description |
| :--- | :--- | :--- |
| `Ticker` | String | Capitalized underlier symbol; duplicates the object key for self-contained records. |
| `Spot` | Float | Latest underlier price. Uses `last_non_reg_trade_price` when its timestamp is more recent than `last_trade_price`, otherwise `last_trade_price`. |
| `Grade` | Int | Structural quality score out of 11 boolean rules (call/put GEX ratios, OI depth, gamma positioning). $\ge 9$ required; $\le 8$ is a hard block. |
| `pTrans` | Float | Positive transition level. Spot must sit above it for entry; entry trigger is a 5-minute candle close above it. |
| `nTrans` | Float | Negative transition level — the structural stop (Stop 1: exit next open on a close below it). |
| `+GEX` | Float | Largest positive GEX concentration above spot; the $T1$ profit target. |
| `COTMP` | Float | Center of Put Mass — the structural floor used for the cushion filter. |
| `db_change` | Float | Delta Balance change vs. the prior session. Threshold $\ge 0.50$ (or $\ge 0.30$ for Grade 11 DEEP names). |
| `COTMP Cushion` | Float | Percent distance of spot above COTMP: $\frac{\text{Spot} - \text{COTMP}}{\text{COTMP}} \times 100$. Threshold $\ge 2.0\%$ (or $1.0\%$ for Grade 11 DEEP / high db_change names). Recomputed on every spot refresh. |
| `Risk/Reward` | Float | $\frac{\text{+GEX} - \text{Spot}}{\text{Spot} - \text{pTrans}}$; must be $\ge 2.0$. May be negative when spot is above +GEX, or `999.0` as a sentinel when risk is non-positive. |
| `Signal Status` | String | Classification outcome: `CONFIRMED`, `PENDING`, or `BLOCKED (...)` with the failed-filter reasons embedded in parentheses. |
| `analyzed_date` | String | Date of the most recent full grading pass, encoded `YYYY-MM-DD`. |
| `pegged_1_00_sessions` | Int | Consecutive sessions with delta balance pegged at $1.00$. At $\ge 2$, the name is fully positioned and exempt from the db_change filter. Optional — absent on older records. |

---

> **Disclaimer**: *The content of this repository is strictly for educational and automation demonstration purposes. None of the included materials, code, or metrics constitute official financial, tax, or investment advice.*

