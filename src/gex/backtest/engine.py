"""
Historical Options Replay & Backtesting Engine for the GEX Options Trading System.
Implements the virtual portfolio state machine, dated snapshot replay harness,
simulated execution fill models with 35% bid-ask spread penalty, Stops 1-5
evaluation, and quantitative risk/expectancy analytics (Sharpe, Sortino, Max Drawdown).
"""

import math
import os
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from src.gex.core.config import DOWNLOADS_DIR, validate_safe_path
from src.gex.core.models import (
    BacktestConfig,
    BacktestDailySnapshot,
    BacktestResult,
    BacktestTrade,
)
from src.gex.quant.gex import derive_gex_profile, extract_quotes_list
from src.gex.risk.stops import compute_exit_rule_state
from src.gex.screening.selector import select_best_option
from src.gex.storage.persistence import load_json


def calculate_simulated_entry_fill(quote: Dict[str, Any], slippage_penalty_pct: float = 0.35) -> float:
    """Calculates realistic simulated entry fill price incorporating the 35% bid-ask spread penalty.
    
    Formula: price_entry = mark + slippage_penalty_pct * (ask - bid)
    """
    bid = float(quote.get("bid_price") or quote.get("bid") or 0.0)
    ask = float(quote.get("ask_price") or quote.get("ask") or 0.0)
    mark = float(
        quote.get("adjusted_mark_price")
        or quote.get("mark_price")
        or quote.get("mark")
        or ((bid + ask) / 2.0 if (bid + ask) > 0 else 0.0)
    )
    spread = max(0.0, ask - bid)
    entry_fill = mark + slippage_penalty_pct * spread
    return round(max(0.01, entry_fill), 2)


def calculate_simulated_exit_fill(quote: Dict[str, Any], slippage_penalty_pct: float = 0.35) -> float:
    """Calculates realistic simulated exit fill price incorporating the 35% bid-ask spread penalty.
    
    Formula: price_exit = mark - slippage_penalty_pct * (ask - bid)
    """
    bid = float(quote.get("bid_price") or quote.get("bid") or 0.0)
    ask = float(quote.get("ask_price") or quote.get("ask") or 0.0)
    mark = float(
        quote.get("adjusted_mark_price")
        or quote.get("mark_price")
        or quote.get("mark")
        or ((bid + ask) / 2.0 if (bid + ask) > 0 else 0.0)
    )
    spread = max(0.0, ask - bid)
    exit_fill = mark - slippage_penalty_pct * spread
    return round(max(0.01, exit_fill), 2)


def derive_exit_code_from_state(exit_state: str) -> str:
    """Maps exit_rule_state text from compute_exit_rule_state to standardized stop codes."""
    if "Structural Stop" in exit_state or "Spot < nTrans" in exit_state:
        return "STOP1"
    elif "Max Asset Stop" in exit_state or "Trailed Stop" in exit_state:
        return "STOP2"
    elif "Theta Stop" in exit_state or "DTE <= 14" in exit_state:
        return "STOP3_THETA"
    elif "Time Stop" in exit_state or "Day 7" in exit_state:
        return "STOP3_VELOCITY"
    elif "Stalling Stop" in exit_state:
        return "STOP3_STALL"
    elif "Macro" in exit_state or "Regime" in exit_state:
        return "STOP4_MACRO"
    elif "Catastrophic Risk Stop" in exit_state or "-50%" in exit_state:
        return "STOP5_HARD"
    elif "T2 TARGET MET" in exit_state:
        return "PROFIT_TARGET_T2"
    elif "T1 TARGET MET" in exit_state or "PROFIT TAKE" in exit_state:
        return "PROFIT_TARGET_T1"
    elif "EXPIRED" in exit_state:
        return "EXPIRED"
    return "STOP1"


class HistoricalReplayHarness:
    """Discovers, parses, and chronologically sequences historical options, underlier,
    and market regime data from dated downloads directories (YYYYMMDD)."""

    def __init__(self, downloads_dir: str = DOWNLOADS_DIR):
        self.downloads_dir = validate_safe_path(downloads_dir)

    def discover_dated_directories(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> List[Tuple[str, str]]:
        """Finds all valid dated subdirectories (YYYYMMDD) within the date window.

        Args:
            start_date: Start date string (YYYY-MM-DD or YYYYMMDD)
            end_date: End date string (YYYY-MM-DD or YYYYMMDD)

        Returns:
            List of (iso_date_str, absolute_dir_path) sorted chronologically.
        """
        if not os.path.exists(self.downloads_dir):
            return []

        start_clean = start_date.replace("-", "") if start_date else None
        end_clean = end_date.replace("-", "") if end_date else None

        dated_dirs: List[Tuple[str, str]] = []
        for entry in os.listdir(self.downloads_dir):
            full_path = os.path.join(self.downloads_dir, entry)
            if not os.path.isdir(full_path):
                continue

            # Must match YYYYMMDD format
            if not (len(entry) == 8 and entry.isdigit()):
                continue

            if start_clean and entry < start_clean:
                continue
            if end_clean and entry > end_clean:
                continue

            iso_date = f"{entry[:4]}-{entry[4:6]}-{entry[6:8]}"
            dated_dirs.append((iso_date, full_path))

        dated_dirs.sort(key=lambda x: x[0])
        return dated_dirs

    def load_day_market_regime(self, dir_path: str) -> Dict[str, Any]:
        """Loads and evaluates market regime status for a specific dated directory."""
        etf_candidates = [
            os.path.join(dir_path, "etf_quotes.json"),
            os.path.join(dir_path, "ETF_QUOTES.JSON"),
        ]
        etf_file = next((f for f in etf_candidates if os.path.exists(f)), None)

        if not etf_file:
            return {
                "system_auth": "ALL TRACKS OK",
                "basket_gate": "PASS",
                "bull_bear_gate": "PASS",
                "vix_delta_gate": "PASS",
                "gates_passed": 3,
                "spy_pct": 0.0,
                "qqq_pct": 0.0,
            }

        try:
            etf_data = load_json(etf_file, {})
            results = []
            if isinstance(etf_data, dict):
                results = (
                    etf_data.get("data", {}).get("results", [])
                    or etf_data.get("results", [])
                    or etf_data.get("data", [])
                )
            elif isinstance(etf_data, list):
                results = etf_data

            reference_etfs = {
                "SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLV", "XLY",
                "XLP", "XLI", "XLU", "XLB", "XLRE", "XLE", "XLC", "HYG"
            }
            spy_pct = 0.0
            qqq_pct = 0.0
            bull_count = 0
            bear_count = 0

            for item in results:
                if not isinstance(item, dict):
                    continue
                q = item.get("quote", item)
                sym = (q.get("symbol") or item.get("symbol") or "").upper()
                if sym not in reference_etfs:
                    continue

                price = float(
                    q.get("last_trade_price")
                    or q.get("last_extended_hours_trade_price")
                    or q.get("mark_price")
                    or 0.0
                )
                prev_close = float(
                    q.get("previous_close")
                    or q.get("adjusted_previous_close")
                    or 0.0
                )
                pct_chg = ((price - prev_close) / prev_close) * 100 if prev_close > 0 else 0.0

                if sym == "SPY":
                    spy_pct = pct_chg
                elif sym == "QQQ":
                    qqq_pct = pct_chg

                if pct_chg > 0:
                    bull_count += 1
                elif pct_chg < 0:
                    bear_count += 1

            basket_gate = "PASS" if (spy_pct > 0.5 or qqq_pct > 0.5) else "FAIL"
            bull_bear_ratio = round(bull_count / bear_count, 3) if bear_count > 0 else float(bull_count)
            bull_bear_gate = "PASS" if bull_bear_ratio > 3.0 else "FAIL"
            vix_delta_gate = "PASS"  # Default unless explicit inverse VIX breach

            gates_passed = sum(1 for g in (basket_gate, bull_bear_gate, vix_delta_gate) if g == "PASS")
            if gates_passed == 3:
                system_auth = "ALL TRACKS OK"
            elif gates_passed == 2:
                system_auth = "TRACK 1 OK"
            else:
                system_auth = "BLOCKED"

            return {
                "system_auth": system_auth,
                "basket_gate": basket_gate,
                "bull_bear_gate": bull_bear_gate,
                "vix_delta_gate": vix_delta_gate,
                "gates_passed": gates_passed,
                "spy_pct": spy_pct,
                "qqq_pct": qqq_pct,
                "bull_bear_ratio": bull_bear_ratio,
            }
        except Exception:
            return {
                "system_auth": "ALL TRACKS OK",
                "basket_gate": "PASS",
                "bull_bear_gate": "PASS",
                "vix_delta_gate": "PASS",
                "gates_passed": 3,
                "spy_pct": 0.0,
                "qqq_pct": 0.0,
            }

    def load_day_underlier_quotes(self, dir_path: str) -> Dict[str, float]:
        """Extracts underlier spot prices available in a dated directory."""
        spots: Dict[str, float] = {}
        if not os.path.exists(dir_path):
            return spots

        for fn in os.listdir(dir_path):
            if not fn.endswith(".json"):
                continue
            fl = fn.lower()
            if "underlier_quote" in fl or "equity_quote" in fl or fl.startswith("quotes_"):
                data = load_json(os.path.join(dir_path, fn), {})
                results = []
                if isinstance(data, dict):
                    results = data.get("results", []) or data.get("data", {}).get("results", [])
                elif isinstance(data, list):
                    results = data

                for item in results:
                    if not isinstance(item, dict):
                        continue
                    sym = (item.get("symbol") or "").upper()
                    price = float(
                        item.get("last_trade_price")
                        or item.get("mark_price")
                        or item.get("bid_price")
                        or 0.0
                    )
                    if sym and price > 0:
                        spots[sym] = price
        return spots

    def load_day_option_chains(self, dir_path: str) -> Dict[str, Dict[str, Any]]:
        """Extracts options instruments and quotes per symbol in a dated directory."""
        chains: Dict[str, Dict[str, Any]] = {}
        if not os.path.exists(dir_path):
            return chains

        files = os.listdir(dir_path)
        # Pair instruments with quotes
        inst_files: Dict[str, str] = {}
        quote_files: Dict[str, str] = {}

        for fn in files:
            if not fn.endswith(".json"):
                continue
            fl = fn.lower()
            # Detect symbol
            sym_match = re.search(r"^([a-z0-9]+)_", fl) or re.search(r"option_[a-z]+_([a-z0-9]+)\.json", fl)
            sym = ""
            if sym_match:
                sym = sym_match.group(1).upper()
            else:
                # Try prefix up to first underscore
                parts = fl.split("_")
                if parts and len(parts[0]) <= 5 and parts[0].isalnum():
                    sym = parts[0].upper()

            if not sym or sym in ("ETF", "SCAN", "PNL", "REALIZED", "OPTIONS", "EQUITY"):
                continue

            full_p = os.path.join(dir_path, fn)
            if "instrument" in fl:
                inst_files[sym] = full_p
            elif "quote" in fl and "underlier" not in fl and "equity" not in fl:
                quote_files[sym] = full_p

        all_syms = set(inst_files.keys()) | set(quote_files.keys())
        for sym in all_syms:
            if sym in inst_files and sym in quote_files:
                inst_data = load_json(inst_files[sym], {})
                quote_data = load_json(quote_files[sym], {})
                chains[sym] = {"instruments": inst_data, "quotes": quote_data}

        return chains

    def load_day_candidates(self, dir_path: str) -> List[Dict[str, Any]]:
        """Extracts candidate underliers discovered or scanned on that date."""
        candidates: List[Dict[str, Any]] = []
        if not os.path.exists(dir_path):
            return candidates

        scan_files = [
            "scan_gex_momentum_raw.json",
            "gex_momentum_candidates.json",
            "scan_high_options_vol_iv_raw.json",
            "high_options_volume_and_iv.json",
            "watchlist_gex_daily_candidates.json",
        ]
        seen_syms = set()

        for sfn in scan_files:
            fp = os.path.join(dir_path, sfn)
            if not os.path.exists(fp):
                continue

            data = load_json(fp, {})
            items = []
            if isinstance(data, dict):
                items = (
                    data.get("results", [])
                    or data.get("data", {}).get("results", [])
                    or data.get("items", [])
                )
            elif isinstance(data, list):
                items = data

            for item in items:
                sym = ""
                if isinstance(item, dict):
                    sym = (item.get("symbol") or item.get("ticker") or "").upper()
                elif isinstance(item, str):
                    sym = item.strip().upper()

                if sym and sym not in seen_syms:
                    seen_syms.add(sym)
                    candidates.append({"symbol": sym, "source": sfn})

        return candidates


class BacktestEngine:
    """Virtual portfolio state machine for historical options backtesting."""

    def __init__(self, config: BacktestConfig, harness: Optional[HistoricalReplayHarness] = None):
        self.config = config
        self.harness = harness or HistoricalReplayHarness()
        self.cash = config.initial_capital
        self.active_positions: Dict[str, Dict[str, Any]] = {}
        self.closed_trades: List[BacktestTrade] = []
        self.daily_snapshots: List[BacktestDailySnapshot] = []
        self.trade_counter = 0

    def run(self) -> BacktestResult:
        """Executes the daily simulation loop across all discovered historical dates."""
        dated_dirs = self.harness.discover_dated_directories(
            start_date=self.config.start_date,
            end_date=self.config.end_date,
        )

        if not dated_dirs:
            # Empty backtest fallback
            return calculate_backtest_metrics(
                config=self.config,
                start_date=self.config.start_date or "",
                end_date=self.config.end_date or "",
                simulation_days=0,
                initial_capital=self.config.initial_capital,
                final_equity=self.config.initial_capital,
                closed_trades=[],
                daily_snapshots=[],
            )

        sim_start_date = dated_dirs[0][0]
        sim_end_date = dated_dirs[-1][0]

        for current_date, dir_path in dated_dirs:
            dt_current = date.fromisoformat(current_date)

            # Step 1: Evaluate Market Regime
            regime = self.harness.load_day_market_regime(dir_path)
            regime_auth = regime.get("system_auth", "ALL TRACKS OK")

            # Load daily market data
            underlier_spots = self.harness.load_day_underlier_quotes(dir_path)
            chains = self.harness.load_day_option_chains(dir_path)

            # Step 2: Mark-to-Market & Evaluate Exits for Active Positions
            self._process_active_positions(
                dt_current=dt_current,
                current_date_str=current_date,
                underlier_spots=underlier_spots,
                chains=chains,
                regime=regime,
            )

            # Step 3: Candidate Discovery, Grading, and Entry
            if regime_auth != "BLOCKED" and len(self.active_positions) < self.config.max_active_positions:
                self._process_new_entries(
                    dt_current=dt_current,
                    current_date_str=current_date,
                    underlier_spots=underlier_spots,
                    chains=chains,
                    candidates=self.harness.load_day_candidates(dir_path),
                    regime_auth=regime_auth,
                )

            # Step 4: Record Daily Equity Snapshot
            positions_equity = sum(
                pos["current_mark"] * pos["contracts"] * 100 for pos in self.active_positions.values()
            )
            total_equity = self.cash + positions_equity
            unrealized_pnl = total_equity - self.config.initial_capital

            self.daily_snapshots.append(
                BacktestDailySnapshot(
                    date=current_date,
                    cash=self.cash,
                    portfolio_equity=total_equity,
                    unrealized_pnl=unrealized_pnl,
                    open_positions_count=len(self.active_positions),
                    regime_status=regime_auth,
                )
            )

        # Mark any remaining open positions at simulation end
        final_equity = self.daily_snapshots[-1].portfolio_equity if self.daily_snapshots else self.cash

        return calculate_backtest_metrics(
            config=self.config,
            start_date=sim_start_date,
            end_date=sim_end_date,
            simulation_days=len(dated_dirs),
            initial_capital=self.config.initial_capital,
            final_equity=final_equity,
            closed_trades=self.closed_trades,
            daily_snapshots=self.daily_snapshots,
        )

    def _process_active_positions(
        self,
        dt_current: date,
        current_date_str: str,
        underlier_spots: Dict[str, float],
        chains: Dict[str, Dict[str, Any]],
        regime: Dict[str, Any],
    ) -> None:
        """Evaluates Stops 1-5, Profit Targets, and marked quotes for open positions."""
        closed_trade_ids: List[str] = []

        for trade_id, pos in list(self.active_positions.items()):
            sym = pos["symbol"]
            strike = pos["strike"]
            exp_date_str = pos["expiration_date"]
            dt_exp = date.fromisoformat(exp_date_str[:10])
            dte = max(0, (dt_exp - dt_current).days)
            days_held = (dt_current - date.fromisoformat(pos["entry_date"])).days

            # Update spot price if available
            spot = underlier_spots.get(sym, pos.get("last_spot", strike))
            pos["last_spot"] = spot

            # Check for fresh option quote
            chain = chains.get(sym)
            quote_dict: Optional[Dict[str, Any]] = None
            if chain:
                quotes = extract_quotes_list(chain.get("quotes", []))
                for q in quotes:
                    inst = q.get("instrument") or {}
                    opt_id = str(q.get("option_id") or q.get("instrument_id") or inst.get("id") or "")
                    if opt_id and opt_id == pos["option_id"]:
                        quote_dict = q
                        break

            if quote_dict:
                mark_price = float(
                    quote_dict.get("adjusted_mark_price")
                    or quote_dict.get("mark_price")
                    or quote_dict.get("mark")
                    or pos["current_mark"]
                )
                pos["current_mark"] = mark_price
                pos["quote_dict"] = quote_dict
            else:
                mark_price = pos["current_mark"]
                quote_dict = pos.get("quote_dict") or {
                    "mark_price": mark_price,
                    "bid_price": mark_price * 0.95,
                    "ask_price": mark_price * 1.05,
                }

            # Evaluate Stops 1-5 via compute_exit_rule_state
            ptrans = pos.get("ptrans")
            ntrans = pos.get("ntrans")
            gex_t1 = pos.get("gex_t1")

            exit_rule_state, _, _, _, _ = compute_exit_rule_state(
                spot=spot,
                purchase_premium=pos["entry_price"],
                mark_price=mark_price,
                ptrans=ptrans,
                ntrans=ntrans,
                gex_t1=gex_t1,
                days_held=days_held,
                stalling_counter=pos.get("stalling_counter", 0),
                dte=dte,
                target_mode=self.config.target_mode,
            )

            # Check Macro / Regime Stop (Stop 4)
            if regime.get("system_auth") == "BLOCKED" and days_held >= 2:
                if not exit_rule_state.startswith("STOP TRIGGERED") and not exit_rule_state.startswith("PROFIT TAKE"):
                    exit_rule_state = "STOP TRIGGERED (Macro / Regime Transition Stop)"

            # Check expiration
            if dte <= 0:
                exit_rule_state = "EXPIRED"

            should_exit = (
                exit_rule_state.startswith("STOP TRIGGERED")
                or exit_rule_state.startswith("PROFIT TAKE")
                or exit_rule_state == "EXPIRED"
            )

            if should_exit:
                exit_code = derive_exit_code_from_state(exit_rule_state)
                exit_fill = calculate_simulated_exit_fill(quote_dict, self.config.slippage_penalty_pct)
                if exit_code == "EXPIRED":
                    exit_fill = max(0.0, spot - strike)  # In-the-money intrinsic value at expiration

                proceeds = exit_fill * pos["contracts"] * 100
                realized_pnl = proceeds - pos["cost_basis"]
                realized_pnl_pct = (
                    ((exit_fill - pos["entry_price"]) / pos["entry_price"]) * 100
                    if pos["entry_price"] > 0
                    else 0.0
                )

                closed_trade = BacktestTrade(
                    trade_id=trade_id,
                    symbol=sym,
                    option_id=pos["option_id"],
                    strike=strike,
                    expiration_date=exp_date_str,
                    entry_date=pos["entry_date"],
                    exit_date=current_date_str,
                    entry_price=pos["entry_price"],
                    exit_price=exit_fill,
                    contracts=pos["contracts"],
                    cost_basis=pos["cost_basis"],
                    realized_pnl=realized_pnl,
                    realized_pnl_pct=realized_pnl_pct,
                    holding_days=days_held,
                    exit_reason=exit_code,
                    regime_at_entry=pos["regime_at_entry"],
                    status="CLOSED",
                )
                self.closed_trades.append(closed_trade)
                self.cash += proceeds
                closed_trade_ids.append(trade_id)

        for tid in closed_trade_ids:
            del self.active_positions[tid]

    def _process_new_entries(
        self,
        dt_current: date,
        current_date_str: str,
        underlier_spots: Dict[str, float],
        chains: Dict[str, Dict[str, Any]],
        candidates: List[Dict[str, Any]],
        regime_auth: str,
    ) -> None:
        """Screens candidate setups and enters compliant options positions."""
        active_symbols = {p["symbol"] for p in self.active_positions.values()}

        # Pool symbols from candidates and chains
        candidate_syms = [c["symbol"] for c in candidates if c.get("symbol")]
        for s in chains.keys():
            if s not in candidate_syms:
                candidate_syms.append(s)

        for sym in candidate_syms:
            if sym in active_symbols:
                continue
            if len(self.active_positions) >= self.config.max_active_positions:
                break

            chain = chains.get(sym)
            if not chain:
                continue

            inst_data = chain.get("instruments", {})
            quote_data = chain.get("quotes", {})
            spot = underlier_spots.get(sym)
            if not spot:
                # Infer spot from chain or ATM mark
                quotes_list = extract_quotes_list(quote_data)
                if quotes_list:
                    spot = float(
                        quotes_list[0].get("last_trade_price")
                        or quotes_list[0].get("adjusted_mark_price")
                        or 100.0
                    )
                else:
                    continue

            # Derive GEX profile
            try:
                gex_profile = derive_gex_profile(inst_data, quote_data, spot=spot)
            except Exception:
                continue

            if isinstance(gex_profile, dict):
                ptrans = gex_profile.get("derived_ptrans")
                ntrans = gex_profile.get("derived_ntrans")
                gex_t1 = gex_profile.get("derived_gex")
            else:
                ptrans = getattr(gex_profile, "derived_ptrans", None)
                ntrans = getattr(gex_profile, "derived_ntrans", None)
                gex_t1 = getattr(gex_profile, "derived_gex", None)

            # Enforce Rule 4 invariant: pTrans > nTrans and spot >= nTrans
            if not (ptrans and ntrans and ptrans > ntrans):
                continue
            if spot < ntrans:
                continue

            # Select best option contract using 5-step protocol
            best_opt, _ = select_best_option(
                inst_data=inst_data,
                quotes_data=quote_data,
                spot=spot,
                gex_target=gex_t1,
                today_override=dt_current,
                target_delta=self.config.target_delta,
                min_dte=self.config.min_dte,
                max_dte=self.config.max_dte,
            )

            if not best_opt:
                continue

            # Check pricing and sizing
            entry_price = calculate_simulated_entry_fill(best_opt, self.config.slippage_penalty_pct)
            contract_cost = entry_price * 100.0
            if contract_cost <= 0:
                continue

            portfolio_equity = self.cash + sum(
                p["current_mark"] * p["contracts"] * 100 for p in self.active_positions.values()
            )
            max_position_dollars = portfolio_equity * self.config.position_size_pct
            contracts = max(1, int(max_position_dollars // contract_cost))
            total_outlay = contracts * contract_cost

            if total_outlay > self.cash:
                # Downsize if possible
                contracts = int(self.cash // contract_cost)
                total_outlay = contracts * contract_cost

            if contracts >= 1 and total_outlay <= self.cash:
                self.trade_counter += 1
                trade_id = f"BT-{sym}-{self.trade_counter:04d}"

                self.cash -= total_outlay
                self.active_positions[trade_id] = {
                    "trade_id": trade_id,
                    "symbol": sym,
                    "option_id": str(best_opt.get("option_id") or best_opt.get("instrument_id") or best_opt.get("id") or ""),
                    "strike": float(best_opt.get("strike_price") or best_opt.get("strike") or 0.0),
                    "expiration_date": str(best_opt.get("expiration_date") or ""),
                    "entry_date": current_date_str,
                    "entry_price": entry_price,
                    "current_mark": float(best_opt.get("mark_price") or entry_price),
                    "contracts": contracts,
                    "cost_basis": total_outlay,
                    "last_spot": spot,
                    "ptrans": ptrans,
                    "ntrans": ntrans,
                    "gex_t1": gex_t1,
                    "regime_at_entry": regime_auth,
                    "quote_dict": best_opt,
                    "stalling_counter": 0,
                }
                active_symbols.add(sym)


def calculate_backtest_metrics(
    config: BacktestConfig,
    start_date: str,
    end_date: str,
    simulation_days: int,
    initial_capital: float,
    final_equity: float,
    closed_trades: List[BacktestTrade],
    daily_snapshots: List[BacktestDailySnapshot],
) -> BacktestResult:
    """Computes comprehensive quantitative performance and risk metrics."""
    total_trades = len(closed_trades)
    winning_trades = sum(1 for t in closed_trades if (t.realized_pnl or 0.0) > 0.0)
    losing_trades = sum(1 for t in closed_trades if (t.realized_pnl or 0.0) <= 0.0)
    win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0

    total_realized_pnl = sum((t.realized_pnl or 0.0) for t in closed_trades)
    total_return_pct = (
        ((final_equity - initial_capital) / initial_capital) * 100.0 if initial_capital > 0 else 0.0
    )

    gross_profits = sum((t.realized_pnl or 0.0) for t in closed_trades if (t.realized_pnl or 0.0) > 0.0)
    gross_losses = abs(sum((t.realized_pnl or 0.0) for t in closed_trades if (t.realized_pnl or 0.0) < 0.0))

    if gross_losses > 0:
        profit_factor = gross_profits / gross_losses
    elif gross_profits > 0:
        profit_factor = 999.99
    else:
        profit_factor = 0.0

    avg_holding_days = (
        sum(t.holding_days for t in closed_trades) / total_trades if total_trades > 0 else 0.0
    )

    # Maximum Drawdown from daily snapshots
    max_drawdown_pct = 0.0
    peak_equity = initial_capital
    daily_returns: List[float] = []

    for i, snap in enumerate(daily_snapshots):
        eq = snap.portfolio_equity
        if eq > peak_equity:
            peak_equity = eq
        if peak_equity > 0:
            dd = ((peak_equity - eq) / peak_equity) * 100.0
            if dd > max_drawdown_pct:
                max_drawdown_pct = dd

        if i > 0:
            prev_eq = daily_snapshots[i - 1].portfolio_equity
            r = (eq - prev_eq) / prev_eq if prev_eq > 0 else 0.0
            daily_returns.append(r)

    # Sharpe and Sortino ratios (annualized with 252 trading days)
    sharpe_ratio = 0.0
    sortino_ratio = 0.0
    if len(daily_returns) >= 2:
        mean_r = sum(daily_returns) / len(daily_returns)
        var_r = sum((r - mean_r) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        std_r = math.sqrt(var_r)

        if std_r > 0:
            sharpe_ratio = (mean_r / std_r) * math.sqrt(252)

        downside_sq = [min(0.0, r) ** 2 for r in daily_returns]
        downside_dev = math.sqrt(sum(downside_sq) / len(daily_returns))
        if downside_dev > 0:
            sortino_ratio = (mean_r / downside_dev) * math.sqrt(252)

    # Stratify trades by regime at entry
    trades_by_regime: Dict[str, Dict[str, Any]] = {}
    for regime_name in ("ALL TRACKS OK", "TRACK 1 OK", "BLOCKED"):
        r_trades = [t for t in closed_trades if t.regime_at_entry == regime_name]
        r_total = len(r_trades)
        r_wins = sum(1 for t in r_trades if (t.realized_pnl or 0.0) > 0.0)
        r_pnl = sum((t.realized_pnl or 0.0) for t in r_trades)
        r_wr = (r_wins / r_total * 100.0) if r_total > 0 else 0.0
        trades_by_regime[regime_name] = {
            "total_trades": r_total,
            "winning_trades": r_wins,
            "win_rate": round(r_wr, 1),
            "realized_pnl": round(r_pnl, 2),
        }

    # Exit reason breakdown
    trades_by_exit_reason: Dict[str, int] = {}
    for t in closed_trades:
        reason = t.exit_reason or "UNKNOWN"
        trades_by_exit_reason[reason] = trades_by_exit_reason.get(reason, 0) + 1

    return BacktestResult(
        config=config,
        start_date=start_date,
        end_date=end_date,
        simulation_days=simulation_days,
        initial_capital=initial_capital,
        final_equity=final_equity,
        total_realized_pnl=total_realized_pnl,
        total_return_pct=total_return_pct,
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=win_rate,
        profit_factor=profit_factor,
        max_drawdown_pct=max_drawdown_pct,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        avg_holding_days=avg_holding_days,
        trades_by_regime=trades_by_regime,
        trades_by_exit_reason=trades_by_exit_reason,
        daily_snapshots=daily_snapshots,
        trades=closed_trades,
    )


def simulate_backtest(
    config: Optional[BacktestConfig] = None,
    downloads_dir: str = DOWNLOADS_DIR,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    initial_capital: float = 100000.0,
) -> BacktestResult:
    """Convenience helper to initialize and run a backtest simulation."""
    if config is None:
        config = BacktestConfig(
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
        )
    harness = HistoricalReplayHarness(downloads_dir=downloads_dir)
    engine = BacktestEngine(config=config, harness=harness)
    return engine.run()
