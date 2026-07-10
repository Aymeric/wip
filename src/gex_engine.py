#!/usr/bin/env python3
"""
📊 GEX Options & Agentic Portfolio Trading Suite CLI Engine

This module serves as the primary technical execution layer for a rules-based options swing trading
and risk management system. Based on GEX (Gamma Exposure) and underlier dealer positioning mechanics,
the CLI automates:
  1. Broad-market Daily Regime Gates validation and authorization evaluation.
  2. Scanning, filtering, and caching prospective candidate equity symbols.
  3. Dynamic single-options setup grading with offline profile derivation logic.
  4. Real-time active portfolio tracking with profit-target, structural, time-limit, and momentum stop-losses.

File Paths and Cache Databases managed:
  - REGIME_FILE (data/regime.json): Daily market index, sector ETF breadth, and market gates cache.
  - ANALYSES_FILE (data/ticker_analyses.json): Incremental quantitative setup-grading persistent store.
  - OPTIONS_FILE (data/active_positions.json): Sized option transactions and Greeks tracker.
  - CANDIDATES_FILE (data/candidate_stocks.json): Screened and prioritized underlier candidates.
"""

import os
import sys
import json
import argparse
import re
import shutil
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

@dataclass
class RegimeGates:
    basket_gate: str
    bull_bear_ratio: float
    bull_bear_gate: str
    vix_delta_gate: str
    system_authorization: str
    gates_passed: int

    def validate(self) -> bool:
        """Validates internal gates metrics."""
        if self.basket_gate not in ("PASS", "FAIL"):
            raise ValueError(f"Invalid basket_gate: {self.basket_gate}")
        if self.bull_bear_gate not in ("PASS", "FAIL"):
            raise ValueError(f"Invalid bull_bear_gate: {self.bull_bear_gate}")
        if self.vix_delta_gate not in ("PASS", "FAIL"):
            raise ValueError(f"Invalid vix_delta_gate: {self.vix_delta_gate}")
        if not (0 <= self.gates_passed <= 3):
            raise ValueError(f"Invalid gates_passed: {self.gates_passed}")
        if self.bull_bear_ratio < 0:
            raise ValueError(f"Invalid bull_bear_ratio: {self.bull_bear_ratio}")
        return True


@dataclass
class OptionPosition:
    option_id: str
    underlier: str
    strike: float
    expiration: str
    type: str  # 'call' or 'put'
    purchase_premium: float
    mark_price: float
    days_held: int
    stalling_days: int
    target_mode: str = "T1"
    t2_target: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    open_interest: Optional[int] = None
    imp_vol: Optional[float] = None
    beta_sector_tag: str = "Technology/Beta"
    entry_date: Optional[str] = None

    def validate(self) -> bool:
        """Validates option position parameters."""
        if not self.option_id:
            raise ValueError("option_id cannot be empty")
        if not self.underlier:
            raise ValueError("underlier cannot be empty")
        if self.strike <= 0:
            raise ValueError(f"strike must be positive: {self.strike}")
        if self.type.lower() not in ("call", "put"):
            raise ValueError(f"type must be 'call' or 'put': {self.type}")
        if self.purchase_premium <= 0:
            raise ValueError(f"purchase_premium must be positive: {self.purchase_premium}")
        if self.mark_price < 0:
            raise ValueError(f"mark_price cannot be negative: {self.mark_price}")
        if self.days_held < 1:
            raise ValueError(f"days_held must be >= 1: {self.days_held}")
        if self.stalling_days < 0:
            raise ValueError(f"stalling_days must be >= 0: {self.stalling_days}")
        if self.target_mode not in ("T1", "T2"):
            raise ValueError(f"target_mode must be 'T1' or 'T2': {self.target_mode}")
        return True


@dataclass
class StockPosition:
    ticker: str
    shares: float
    average_buy_price: float
    current_price: float
    beta_sector_tag: str = "Equity"
    entry_date: Optional[str] = None
    asset_cost_basis: float = 0.0
    current_value: float = 0.0

    def validate(self) -> bool:
        """Validates stock position parameters."""
        if not self.ticker:
            raise ValueError("ticker cannot be empty")
        if self.shares <= 0:
            raise ValueError(f"shares must be positive: {self.shares}")
        if self.average_buy_price <= 0:
            raise ValueError(f"average_buy_price must be positive: {self.average_buy_price}")
        if self.current_price < 0:
            raise ValueError(f"current_price cannot be negative: {self.current_price}")
        return True


@dataclass
class OptionSentiment:
    ticker: str
    sentiment: float
    buzz: str  # 'High', 'Medium', 'Low', 'None'
    narrative: str
    last_updated: Optional[str] = field(default=None)

    def validate(self) -> bool:
        """Validates sentiment parameters."""
        if not self.ticker:
            raise ValueError("ticker cannot be empty")
        if not (-1.0 <= self.sentiment <= 1.0):
            raise ValueError(f"sentiment must be between -1.0 and +1.0: {self.sentiment}")
        if self.buzz not in ("High", "Medium", "Low", "None", "Med"):
            raise ValueError(f"buzz must be High, Medium, Low, or None: {self.buzz}")
        return True


# Define file paths relative to active workspace (current directory)
REGIME_FILE = "data/regime.json"
ANALYSES_FILE = "data/ticker_analyses.json"
OPTIONS_FILE = "data/active_positions.json"
CANDIDATES_FILE = "data/candidate_stocks.json"
SCANS_DIR = "data/scans"
SENTIMENT_FILE = "data/reddit_sentiment.json"

# Standard Mechanical Screener Baseline Filter Constants
MIN_PRICE = 5.0
MAX_PRICE = 1000.0
MIN_VOLUME = 200000
MIN_CHG_PCT = 0.3
MIN_MARKET_CAP = 1000000000



def print_color(text: str, color_code: str, bold: bool = False) -> None:
    """Prints text in ANSI color if the output is a tty."""
    if sys.stdout.isatty():
        prefix = f"\033[{1 if bold else 0};{color_code}m"
        suffix = "\033[0m"
        print(f"{prefix}{text}{suffix}")
    else:
        print(text)


def format_color(text: str, color_code: str, bold: bool = False) -> str:
    """Formats text with ANSI color codes if the output is a tty."""
    if sys.stdout.isatty():
        return f"\033[{1 if bold else 0};{color_code}m{text}\033[0m"
    return text


def str2bool(value: Any) -> bool:
    """Parses CLI boolean flags reliably (argparse type=bool treats 'False' as True)."""
    if isinstance(value, bool):
        return value
    if value.lower() in ("true", "t", "yes", "y", "1"):
        return True
    if value.lower() in ("false", "f", "no", "n", "0"):
        return False
    raise argparse.ArgumentTypeError(f"Boolean value expected, got '{value}'")


def load_json(filepath: str, default: Any) -> Any:
    """Loads a JSON file from disk, returning default if absent or corrupted."""
    if not os.path.exists(filepath):
        return default
    try:
        if os.path.getsize(filepath) == 0:
            return default
    except Exception:
        pass
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load {filepath}: {e}", file=sys.stderr)
        return default


def save_json(filepath: str, data: Any) -> None:
    """Saves a Python dictionary/list structure to filepath as formatted JSON."""
    try:
        dir_name = os.path.dirname(filepath)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error: Failed to save to {filepath}: {e}", file=sys.stderr)


def get_regime_status() -> Dict[str, Any]:
    """Retrieves and packages current broad market Daily Regime Gates metrics."""
    regime = load_json(REGIME_FILE, {})
    etf_details = regime.get("etf_details", {})
    
    spy_det = etf_details.get("SPY", {})
    qqq_det = etf_details.get("QQQ", {})
    hyg_det = etf_details.get("HYG", {})
    
    spy_pct = spy_det.get("Daily Change %", regime.get("spy_change_pct", 0.0))
    qqq_pct = qqq_det.get("Daily Change %", regime.get("qqq_change_pct", 0.0))
    hyg_pct = hyg_det.get("Daily Change %", regime.get("hyg_change_pct", None))
    
    bull_count = sum(1 for sym, det in etf_details.items() if sym != "HYG" and det.get("Classification") == "BULLISH")
    if not etf_details:
        bull_count = regime.get("bull_count", 0)
        
    bear_count = sum(1 for sym, det in etf_details.items() if sym != "HYG" and det.get("Classification") == "BEARISH")
    if not etf_details:
        bear_count = regime.get("bear_count", 0)
        
    if bear_count > 0:
        bull_bear_ratio = round(bull_count / bear_count, 3)
    else:
        bull_bear_ratio = float(bull_count) if etf_details else regime.get("bull_bear_ratio", 0.0)
        
    basket_gate = regime.get("basket_gate")
    if basket_gate is None:
        basket_gate = "PASS" if (spy_pct > 0.5 or qqq_pct > 0.5) else "FAIL"
        
    bull_bear_gate = regime.get("bull_bear_gate")
    if bull_bear_gate is None:
        bull_bear_gate = "PASS" if bull_bear_ratio > 3.0 else "FAIL"
        
    vix_spot = regime.get("vix_spot", 0.0)
    vix_bearish = regime.get("vix_bearish", None)
    
    vix_delta_gate = regime.get("vix_delta_gate")
    if vix_delta_gate is None:
        vix_delta_gate = "PASS" if vix_bearish else "FAIL"
        
    system_auth = regime.get("system_authorization", "BLOCKED")
    
    gates_passed = regime.get("gates_passed")
    if gates_passed is None:
        gates_passed = sum(1 for g in (basket_gate, bull_bear_gate, vix_delta_gate) if g == "PASS")
    
    return {
        "spy_pct": spy_pct,
        "qqq_pct": qqq_pct,
        "basket_gate": basket_gate,
        "bull_count": bull_count,
        "bear_count": bear_count,
        "bull_bear_ratio": bull_bear_ratio,
        "bull_bear_gate": bull_bear_gate,
        "vix_spot": vix_spot,
        "vix_bearish": vix_bearish,
        "vix_delta_gate": vix_delta_gate,
        "system_authorization": system_auth,
        "hyg_pct": hyg_pct,
        "gates_passed": gates_passed,
        "etf_details": etf_details
    }


def compute_regime_gates(spy_pct: float, qqq_pct: float, bull_count: int, bear_count: int, vix_dealer_delta_bearish: bool) -> Tuple[str, float, str, str, str, int]:
    """Mechanically computes the three Daily Regime Gates and system authorization.

    - Basket Gate: SPY or QQQ up more than +0.5% in the session.
    - Bull:Bear Gate: bullish-to-bearish ratio > 3.0:1.
    - VIX Delta Gate: dealer positioning on VIX is bearish (bullish for equities).
    Track 1 (Mechanical P2P) requires >= 2/3 gates; Track 2 (B Continuation) requires 3/3.
    """
    basket_gate = "PASS" if (spy_pct > 0.5 or qqq_pct > 0.5) else "FAIL"
    
    bull_bear_ratio = round(bull_count / bear_count, 3) if bear_count > 0 else float(bull_count)
    bull_bear_gate = "PASS" if bull_bear_ratio > 3.0 else "FAIL"
    
    vix_delta_gate = "PASS" if vix_dealer_delta_bearish else "FAIL"
    
    gates_passed = sum(1 for g in (basket_gate, bull_bear_gate, vix_delta_gate) if g == "PASS")
    if gates_passed == 3:
        system_auth = "ALL TRACKS OK"
    elif gates_passed == 2:
        system_auth = "TRACK 1 OK"
    else:
        system_auth = "BLOCKED"
        
    return basket_gate, bull_bear_ratio, bull_bear_gate, vix_delta_gate, system_auth, gates_passed


def cmd_update_regime(args):
    """Recomputes the Daily Regime Gates from raw market inputs and persists them."""
    cached_regime = load_json(REGIME_FILE, {})
    
    spy_val = args.spy
    qqq_val = args.qqq
    bulls_val = args.bulls
    bears_val = args.bears
    vix_bearish_val = args.vix_bearish
    vix_spot_val = args.vix_spot
    hyg_val = getattr(args, "hyg", None)
    
    if hasattr(args, "etf_file") and args.etf_file:
        try:
            with open(args.etf_file, "r") as f:
                etf_data = json.load(f)
                
            results = []
            if isinstance(etf_data, dict):
                results = etf_data.get("data", {}).get("results", [])
                if not results:
                    results = etf_data.get("results", [])
                if not results:
                    results = etf_data.get("data", [])
            elif isinstance(etf_data, list):
                results = etf_data
                
            reference_etfs = {
                "SPY", "QQQ", "IWM", "DIA", 
                "XLK", "XLF", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLRE", "XLE", "XLC", "HYG"
            }
            
            spy_pct = 0.0
            qqq_pct = 0.0
            bull_count = 0
            bear_count = 0
            found_symbols = {}
            detailed_etfs = {}
            
            for item in results:
                if not isinstance(item, dict):
                    continue
                q = item.get("quote", item)
                if not isinstance(q, dict):
                    continue
                symbol = q.get("symbol")
                if not symbol:
                    continue
                sym_upper = symbol.upper()
                if sym_upper in reference_etfs:
                    # Resolve price choosing non-reg or reg based on timestamps
                    nonreg_t = q.get("venue_last_non_reg_trade_time") or ""
                    reg_t = q.get("venue_last_trade_time") or ""
                    
                    price = 0.0
                    if nonreg_t > reg_t and q.get("last_non_reg_trade_price") is not None:
                        try:
                            price = float(q["last_non_reg_trade_price"])
                        except ValueError:
                            pass
                    if price <= 0.0 and q.get("last_trade_price") is not None:
                        try:
                            price = float(q["last_trade_price"])
                        except ValueError:
                            pass
                            
                    prev_close = 0.0
                    if q.get("adjusted_previous_close") is not None:
                        try:
                            prev_close = float(q["adjusted_previous_close"])
                        except ValueError:
                            pass
                            
                    chg_pct = 0.0
                    if price > 0.0 and prev_close > 0.0:
                        chg_pct = ((price - prev_close) / prev_close) * 100.0
                        found_symbols[sym_upper] = chg_pct
                        
                    classification = "FLAT"
                    if sym_upper != "HYG":
                        if chg_pct > 0.1:
                            classification = "BULLISH"
                        elif chg_pct < -0.1:
                            classification = "BEARISH"
                    else:
                        if chg_pct > 0.0:
                            classification = "BULLISH"
                        elif chg_pct < 0.0:
                            classification = "BEARISH"
                            
                    etf_segment_names = {
                        "SPY": "S&P 500 Broad Market",
                        "QQQ": "Nasdaq 100 Growth Index",
                        "IWM": "Russell 2000 Small Caps",
                        "DIA": "Dow Jones Industrials Value",
                        "XLK": "Technology",
                        "XLF": "Financials",
                        "XLV": "Health Care",
                        "XLY": "Consumer Discretionary",
                        "XLP": "Consumer Staples",
                        "XLI": "Industrials",
                        "XLU": "Utilities",
                        "XLB": "Materials",
                        "XLRE": "Real Estate",
                        "XLE": "Energy",
                        "XLC": "Communication Services",
                        "HYG": "High Yield Corporate Bond ETF"
                    }
                    
                    detailed_etfs[sym_upper] = {
                        "Ticker": sym_upper,
                        "ETF Segment / Sector Name": etf_segment_names.get(sym_upper, "Unknown Sector"),
                        "Price": round(price, 2) if price > 0.0 else round(prev_close, 2),
                        "Daily Change %": round(chg_pct, 4),
                        "Classification": classification
                    }
                        
            # Calculate SPY, QQQ changes
            spy_pct = found_symbols.get("SPY", 0.0)
            qqq_pct = found_symbols.get("QQQ", 0.0)
            
            # Count bulls and bears
            for sym, chg in found_symbols.items():
                if sym == "HYG":
                    continue
                if chg > 0.1:
                    bull_count += 1
                elif chg < -0.1:
                    bear_count += 1
                    
            spy_val = spy_pct
            qqq_val = qqq_pct
            bulls_val = bull_count
            bears_val = bear_count
            
            if "HYG" in found_symbols:
                hyg_val = found_symbols["HYG"]
            
            print(format_color(f"📊 Auto-derived regime metrics from {args.etf_file}:", "32", bold=True))
            print(f"  -> SPY Change: {spy_pct:+.2f}%, QQQ Change: {qqq_pct:+.2f}%")
            if "HYG" in found_symbols:
                print(f"  -> HYG Credit Change: {found_symbols['HYG']:+.2f}%")
            print(f"  -> Bulls: {bull_count}, Bears: {bear_count} (out of {len(found_symbols) - (1 if 'HYG' in found_symbols else 0)} tracked reference ETFs)")
            
            # If VXX or UVXY are in findings, we can use their signs as a fallback VIX Delta gate proxy
            if vix_bearish_val is None:
                for item in results:
                    q = item.get("quote", item) if isinstance(item, dict) else {}
                    if not isinstance(q, dict): continue
                    s = q.get("symbol", "").upper()
                    if s in ("VXX", "UVXY"):
                        nonreg_t = q.get("venue_last_non_reg_trade_time") or ""
                        reg_t = q.get("venue_last_trade_time") or ""
                        p = 0.0
                        if nonreg_t > reg_t and q.get("last_non_reg_trade_price") is not None:
                            p = float(q["last_non_reg_trade_price"]) or 0.0
                        if p <= 0.0 and q.get("last_trade_price") is not None:
                            p = float(q["last_trade_price"]) or 0.0
                        pc = float(q.get("adjusted_previous_close") or 0.0)
                        if p > 0.0 and pc > 0.0:
                            proxy_chg = ((p - pc) / pc) * 100.0
                            vix_bearish_val = proxy_chg < 0.0
                            print(f"  -> Derived VIX bearish from proxy {s} (% change: {proxy_chg:+.2f}%): {vix_bearish_val}")
                            break
                if vix_bearish_val is None:
                    # Fallback default if not derivable from file
                    vix_bearish_val = False
                    print("  -> VIX Bearish could not be resolved from proxy underliers in ETF file. Defaulting to False (Conservative).")
                            
        except Exception as e:
            print(f"Error parsing ETF quotes file: {e}", file=sys.stderr)
            
    if spy_val is None or qqq_val is None or bulls_val is None or bears_val is None or vix_bearish_val is None:
        print("Error: Missing required metrics for Daily Regime check. Pass them via --spy, --qqq, --bulls, --bears, --vix-bearish, or use --etf-file.", file=sys.stderr)
        sys.exit(1)
        
    basket_gate, bull_bear_ratio, bull_bear_gate, vix_delta_gate, system_auth, gates_passed = compute_regime_gates(
        spy_val, qqq_val, bulls_val, bears_val, vix_bearish_val
    )
    
    etf_details = cached_regime.get("etf_details", {})
    if hasattr(args, "etf_file") and args.etf_file and "found_symbols" in locals():
        etf_details = detailed_etfs
    else:
        # Fallback construct basic etf_details objects on manual arguments update
        etf_segment_names = {
            "SPY": "S&P 500 Broad Market",
            "QQQ": "Nasdaq 100 Growth Index",
            "HYG": "High Yield Corporate Bond ETF"
        }
        for sym, val in [("SPY", spy_val), ("QQQ", qqq_val), ("HYG", hyg_val)]:
            if val is not None:
                chg_pct = float(val)
                classification = "FLAT"
                if sym != "HYG":
                    if chg_pct > 0.1:
                        classification = "BULLISH"
                    elif chg_pct < -0.1:
                        classification = "BEARISH"
                else:
                    if chg_pct > 0.0:
                        classification = "BULLISH"
                    elif chg_pct < 0.0:
                        classification = "BEARISH"
                etf_details[sym] = {
                    "Ticker": sym,
                    "ETF Segment / Sector Name": etf_segment_names.get(sym, "Unknown Sector"),
                    "Price": 0.0,
                    "Daily Change %": round(chg_pct, 4),
                    "Classification": classification
                }

    regime_data = {
        "basket_gate": basket_gate,
        "bull_bear_gate": bull_bear_gate,
        "vix_spot": round(vix_spot_val, 2) if vix_spot_val is not None else cached_regime.get("vix_spot", 0.0),
        "vix_bearish": vix_bearish_val,
        "vix_delta_gate": vix_delta_gate,
        "system_authorization": system_auth,
        "gates_passed": gates_passed,
        "etf_details": etf_details,
        "last_updated": datetime.today().strftime('%Y-%m-%d')
    }
    
    save_json(REGIME_FILE, regime_data)
    
    print(f"Regime gates recomputed and saved to {REGIME_FILE} ({gates_passed}/3 gates passed).\n")
    cmd_status(args)


def cmd_status(args):
    """View the current Daily Regime Gates."""
    # 📅 Cache Freshness validation preflight health check
    today_local = datetime.today().strftime('%Y-%m-%d')
    today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    files_to_check = {
        "Daily Regime": (REGIME_FILE, "run 'update-regime' subcommand"),
        "Candidates List": (CANDIDATES_FILE, "run 'update-candidates' subcommand"),
        "Active Options": (OPTIONS_FILE, "update options manually or via sync"),
        "Ticker Analyses": (ANALYSES_FILE, "run 'analyze' subcommand for candidate symbols")
    }
    
    print("### 📅 Cache Freshness Report")
    for label, (filepath, action) in files_to_check.items():
        if not os.path.exists(filepath):
            print(f"- **{label}**: {format_color('MISSING', '31', bold=True)} -> *Action: {action}*")
        else:
            file_date = ""
            try:
                with open(filepath, "r") as f:
                    content = json.load(f)
                if isinstance(content, dict):
                    if "last_updated" in content:
                        val = content["last_updated"]
                        if "T" in val:
                            file_date = val.split("T")[0]
                        else:
                            file_date = val
                    elif "analyzed_date" in content:
                        file_date = content.get("analyzed_date", "")
            except Exception:
                pass
            
            if not file_date:
                try:
                    mtime = os.path.getmtime(filepath)
                    file_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
                except Exception:
                    file_date = "UNKNOWN"
            
            if file_date in (today_local, today_utc):
                print(f"- **{label}**: {format_color(f'FRESH ({file_date})', '32')}")
            else:
                print(f"- **{label}**: {format_color(f'STALE ({file_date})', '33')} -> *Action: {action}*")
    print()

    regime = get_regime_status()
    
    print("### 📊 GEX Regime Check")
    
    # Let's apply neat styling / colors for CLI output readability
    bgate_status = format_color(regime['basket_gate'], "32" if regime['basket_gate'] == "PASS" else "31", bold=True)
    bbgate_status = format_color(regime['bull_bear_gate'], "32" if regime['bull_bear_gate'] == "PASS" else "31", bold=True)
    vixgate_status = format_color(regime['vix_delta_gate'], "32" if regime['vix_delta_gate'] == "PASS" else "31", bold=True)
    
    spy_pct_str = f"{regime['spy_pct']:+.2f}%"
    qqq_pct_str = f"{regime['qqq_pct']:+.2f}%"
    spy_color = "32" if regime['spy_pct'] >= 0.5 else ("31" if regime['spy_pct'] < 0 else "33")
    qqq_color = "32" if regime['qqq_pct'] >= 0.5 else ("31" if regime['qqq_pct'] < 0 else "33")
    spy_color_str = format_color(spy_pct_str, spy_color)
    qqq_color_str = format_color(qqq_pct_str, qqq_color)
    
    ratio_str = f"{regime['bull_bear_ratio']:.2f}:1"
    ratio_color = "32" if regime['bull_bear_ratio'] >= 3.0 else "31"
    ratio_color_str = format_color(ratio_str, ratio_color)
    
    system_auth_str = regime['system_authorization']
    if "BLOCK" in system_auth_str:
        system_auth_str = format_color(system_auth_str, "31", bold=True)
    else:
        system_auth_str = format_color(system_auth_str, "32", bold=True)
        
    print(f"- **Basket Gate**: {bgate_status} (SPY: {spy_color_str}, QQQ: {qqq_color_str})")
    
    etf_details = regime.get("etf_details", {})
    bullish_etfs = [sym for sym, det in etf_details.items() if sym != "HYG" and det.get("Classification") == "BULLISH"]
    bearish_etfs = [sym for sym, det in etf_details.items() if sym != "HYG" and det.get("Classification") == "BEARISH"]
    bull_str = ", ".join(sorted(bullish_etfs)) if bullish_etfs else "None"
    bear_str = ", ".join(sorted(bearish_etfs)) if bearish_etfs else "None"
    print(f"- **Bull:Bear Gate**: {bbgate_status} (Ratio: {ratio_color_str}, Bulls: {regime['bull_count']} [{bull_str}], Bears: {regime['bear_count']} [{bear_str}] from {REGIME_FILE} Cache)")
    
    print(f"- **VIX Delta Gate**: {vixgate_status} (VIX Spot: {regime['vix_spot']:.2f})")
    print(f"- **System Authorization**: {system_auth_str}")
    
    hyg_pct = regime.get("hyg_pct")
    if hyg_pct is not None:
        hyg_color = "31" if hyg_pct <= -0.3 else ("32" if hyg_pct > 0 else "33")
        hyg_pct_str = format_color(f"{hyg_pct:+.2f}%", hyg_color)
        print(f"- **HYG Credit Overlay**: {hyg_pct_str}")
        
        equities_bullish = regime["spy_pct"] > 0.0 or regime["qqq_pct"] > 0.0
        if hyg_pct < -0.3 and equities_bullish:
            print_color("\n⚠️ CREDIT DIVERGENCE DETECTED: HYG daily change of < -0.30% while equities are positive.", "33", bold=True)
            print_color("⚠️ RISK MITIGATION TRIGGERED: Reduce position sizing on new options entries by 50%.", "33", bold=True)
            
    # Simple alert or summary
    if regime['system_authorization'] == "BLOCKED":
        print_color("\n🛑 SYSTEM STATUS: BLOCKED. No new entries authorized today.", "31", bold=True)
    else:
        print_color(f"\n✅ SYSTEM STATUS: AUTHORIZED ({regime['system_authorization']}). New trade entries are permitted.", "32", bold=True)


def calculate_grade(ticker, spot, ptrans, ntrans, gex, cotmp, extra_rules=None):
    """
    Grades a single stock setup based on the GEX system's 11 structural rules.
    
    The 11 Rules are:
      1. Total Call GEX is positive (bullish posture).
      2. Total Call GEX exceeds absolute value of Total Put GEX (net positive positioning).
      3. Underlier Spot price is above the largest negative GEX strike / Center of Put Mass (COTMP).
      4. Largest positive GEX target strike (+GEX / T1 Target) is above current stock Spot price.
      5. Positive transition (pTrans) sits above negative transition (nTrans).
      6. Stock Spot price sits above pTrans (entry trigger rule).
      7. Total Open Interest (OI) exceeds 10,000 contracts for structural depth.
      8. 30-day option implied volatility (IV30) is below historical 90-day realized volatility (HV90).
      9. Open Interest depth at the +GEX target strike exceeds all other strikes.
      10. Dealer net gamma positioning at the current Spot is net positive.
      11. Underlier's 10-day realized volatility (RV10) is compressed (<= 35%).
      
    Args:
        ticker (str): The ticker symbol.
        spot (float): Underlier spot price.
        ptrans (float): Positive transition level (pTrans).
        ntrans (float): Negative transition level (nTrans).
        gex (float): Target positive GEX strike level (+GEX).
        cotmp (float): Center of Put Mass strike (COTMP).
        extra_rules (dict, optional): Boolean flags for rules requiring raw options/volatility data (1, 2, 7, 8, 9, 10, 11).
        
    Returns:
        tuple[int, list[bool]]: (grade, rules_checklist) where grade is the integer score (0-11)
                                 and rules_checklist is a list of Boolean indicators for each of the 11 rules.
    """
    if extra_rules is None:
        extra_rules = {}

    rules = [False] * 11
    
    # Rule 1: Total call GEX is positive
    rules[0] = extra_rules.get("total_call_gex_positive", True)
    
    # Rule 2: Call GEX exceeds absolute Put GEX
    rules[1] = extra_rules.get("call_gex_gt_put_gex", True)
    
    # Rule 3: Spot price is above largest negative GEX strike (usually COTMP or similar)
    rules[2] = spot > cotmp
    
    # Rule 4: Largest single $+GEX$ target strike is above current Spot price
    rules[3] = gex > spot
    
    # Rule 5: pTrans sits above nTrans
    rules[4] = ptrans > ntrans
    
    # Rule 6: Spot sits above positive transition (pTrans) -> Wait, watchdog buffer allows pending.
    # The rule checklist itself matches: Spot price sits above pTrans.
    rules[5] = spot > ptrans
    
    # Rule 7: Total OI exceeds 10,000 contracts
    rules[6] = extra_rules.get("total_oi_gt_10000", True)
    
    # Rule 8: 30-day option implied volatility is below historical 90-day volatility
    rules[7] = extra_rules.get("iv_30_lt_hv_90", True)
    
    # Rule 9: Open Interest depth at +GEX target strike exceeds all other strikes
    rules[8] = extra_rules.get("oi_depth_target_positive", True)
    
    # Rule 10: Dealer net gamma positioning at current Spot is net positive
    rules[9] = extra_rules.get("dealer_gamma_net_positive", True)
    
    # Rule 11: Underlier current 10-day realized volatility is stable/compressed (<= 35%)
    rules[10] = extra_rules.get("rv_10_stable", True)
    
    grade = sum(1 for r in rules if r)
    return grade, rules


def derive_gex_profile(inst_data, quotes_data, spot):
    """
    Derives GEX levels and key option metrics (COTMP, pTrans, nTrans, +GEX)
    from Robinhood options instruments and quotes payloads.
    
    Args:
        inst_data (dict or list): Options instruments JSON payload
        quotes_data (dict or list): Options quotes JSON payload
        spot (float): Current underlier spot price
        
    Returns:
        dict: Derived levels, rules, and intermediate calculations.
    """
    instruments_list = []
    if isinstance(inst_data, dict):
        if "data" in inst_data and isinstance(inst_data["data"], dict):
            instruments_list = inst_data["data"].get("instruments", [])
        else:
            instruments_list = inst_data.get("instruments", [])
    elif isinstance(inst_data, list):
        instruments_list = inst_data
        
    inst_map = {}
    for inst in instruments_list:
        if not isinstance(inst, dict) or "id" not in inst:
            continue
        try:
            inst_map[inst["id"]] = {
                "strike": float(inst["strike_price"]) if "strike_price" in inst else float(inst.get("strike", 0.0)),
                "type": inst["type"]
            }
        except (ValueError, KeyError):
            continue
        
    quotes_list = []
    if isinstance(quotes_data, dict):
        quotes_list = quotes_data.get("data", {}).get("results", [])
        if not quotes_list:
            quotes_list = quotes_data.get("data", [])
        if not quotes_list:
            quotes_list = quotes_data.get("results", [])
    elif isinstance(quotes_data, list):
        quotes_list = quotes_data
        
    strike_put_oi = {}
    strike_call_oi = {}
    strike_put_gex = {}
    strike_call_gex = {}
    total_oi = 0
    total_call_gex = 0.0
    total_put_gex = 0.0
    
    iv_sum = 0.0
    iv_count = 0
    
    calc_spot = spot if spot is not None else 100.0
    
    for q_item in quotes_list:
        if not isinstance(q_item, dict):
            continue
        q = q_item.get("quote", q_item)
        if not isinstance(q, dict):
            continue
        opt_id = q.get("instrument_id") or q.get("id") or q.get("instrument")
        if not opt_id or opt_id not in inst_map:
            continue
            
        try:
            oi = int(q.get("open_interest") or 0)
            gamma = float(q.get("gamma") or 0.0)
            iv = float(q.get("implied_volatility") or q.get("implied_vol", 0.0))
        except (ValueError, TypeError):
            continue
            
        strike = inst_map[opt_id]["strike"]
        opt_type = inst_map[opt_id]["type"]
        
        total_oi += oi
        gex_val = oi * gamma * 100.0 * calc_spot
        
        # IV proxy (within 15% of spot)
        if abs(strike - calc_spot) / calc_spot <= 0.15:
            if iv > 0.0:
                iv_sum += iv
                iv_count += 1
                
        if opt_type == "put":
            strike_put_oi[strike] = strike_put_oi.get(strike, 0) + oi
            strike_put_gex[strike] = strike_put_gex.get(strike, 0.0) + gex_val
            total_put_gex += gex_val
        elif opt_type == "call":
            strike_call_oi[strike] = strike_call_oi.get(strike, 0) + oi
            strike_call_gex[strike] = strike_call_gex.get(strike, 0.0) + gex_val
            total_call_gex += gex_val
            
    if total_oi <= 0:
        return {
            "total_oi": 0,
            "iv_sum": 0.0,
            "iv_count": 0,
            "derived_cotmp": calc_spot * 0.95,
            "derived_ptrans": calc_spot * 0.98,
            "derived_ntrans": calc_spot * 0.95,
            "derived_gex": calc_spot * 1.05,
            "total_call_gex": 0.0,
            "total_put_gex": 0.0,
            "rule1_derived": False,
            "rule2_derived": False,
            "rule7_derived": False,
            "rule9_derived": False,
            "rule10_derived": False,
        }
        
    # COTMP = weighted put strike
    sum_strike_put_oi = sum(s * oi for s, oi in strike_put_oi.items())
    sum_put_oi = sum(strike_put_oi.values())
    derived_cotmp = sum_strike_put_oi / sum_put_oi if sum_put_oi > 0 else calc_spot * 0.95
    
    # pTrans = strike at/below spot with largest put OI
    at_below_spot_puts = {s: oi for s, oi in strike_put_oi.items() if s <= calc_spot}
    if at_below_spot_puts:
        # Sort by strike descending so in case of tie we get highest strike closest to spot
        sorted_puts = sorted(at_below_spot_puts.items(), key=lambda item: (item[1], item[0]), reverse=True)
        derived_ptrans = sorted_puts[0][0]
    else:
        derived_ptrans = calc_spot * 0.98
        
    # nTrans = strike below pTrans with next largest put OI
    below_ptrans_puts = {s: oi for s, oi in strike_put_oi.items() if s < derived_ptrans}
    if below_ptrans_puts:
        # Sort by strike descending so in case of tie we get highest strike closest to pTrans
        sorted_below_puts = sorted(below_ptrans_puts.items(), key=lambda item: (item[1], item[0]), reverse=True)
        derived_ntrans = sorted_below_puts[0][0]
    else:
        derived_ntrans = derived_ptrans * 0.95
        
    # +GEX = strike at/above spot with largest call OI
    at_above_spot_calls = {s: oi for s, oi in strike_call_oi.items() if s >= calc_spot}
    if at_above_spot_calls:
        # Sort by strike ascending so that in case of a tie (e.g. all 0), we get lowest strike closest to spot
        sorted_calls = sorted(at_above_spot_calls.items(), key=lambda item: (item[1], -item[0]), reverse=True)
        derived_gex = sorted_calls[0][0]
    else:
        derived_gex = calc_spot * 1.05
        
    rule1_derived = total_call_gex > 0
    rule2_derived = total_call_gex > abs(total_put_gex)
    rule7_derived = total_oi > 10000
    
    call_oi_at_target = strike_call_oi.get(derived_gex, 0)
    max_call_oi = max(strike_call_oi.values()) if strike_call_oi else 0
    rule9_derived = call_oi_at_target >= max_call_oi if max_call_oi > 0 else True
    
    all_strikes = sorted(list(set(strike_put_gex.keys()) | set(strike_call_gex.keys())))
    nearest_strike = min(all_strikes, key=lambda s: abs(s - calc_spot)) if all_strikes else calc_spot
    net_gex_nearest = strike_call_gex.get(nearest_strike, 0.0) - strike_put_gex.get(nearest_strike, 0.0)
    rule10_derived = net_gex_nearest >= 0.0
    
    return {
        "total_oi": total_oi,
        "iv_sum": iv_sum,
        "iv_count": iv_count,
        "derived_cotmp": derived_cotmp,
        "derived_ptrans": derived_ptrans,
        "derived_ntrans": derived_ntrans,
        "derived_gex": derived_gex,
        "total_call_gex": total_call_gex,
        "total_put_gex": total_put_gex,
        "rule1_derived": rule1_derived,
        "rule2_derived": rule2_derived,
        "rule7_derived": rule7_derived,
        "rule9_derived": rule9_derived,
        "rule10_derived": rule10_derived,
    }


def calculate_annualized_vol(returns_list):
    """Calculates annualized volatility from daily log returns."""
    import math
    n = len(returns_list)
    if n < 2:
        return 0.0
    mean_ret = sum(returns_list) / n
    variance = sum((x - mean_ret) ** 2 for x in returns_list) / (n - 1)
    stdev_ret = math.sqrt(variance)
    return stdev_ret * math.sqrt(252) * 100.0


def derive_volatility_profile(hist_data, symbol, iv_sum, iv_count):
    """
    Calculates proxy volatility indicators (RV10, HV90, IV30) and applies rules.
    
    Args:
        hist_data (dict or list): Historical closes JSON payload
        symbol (str): Stock ticker symbol
        iv_sum (float): sum of weighted IVs
        iv_count (int): count of IV occurrences
        
    Returns:
        dict: Derived volatilities and rules.
    """
    import math
    bars = []
    if isinstance(hist_data, dict):
        results = hist_data.get("data", {}).get("results", [])
        if not results:
            results = hist_data.get("results", [])
        if results:
            for res in results:
                if res.get("symbol", "").upper() == symbol:
                    bars = res.get("bars", [])
                    break
        if not bars:
            bars = hist_data.get("bars", [])
    elif isinstance(hist_data, list):
        bars = hist_data
        
    if not bars:
        return {
            "iv30_val": 0.0,
            "hv90_val": 0.0,
            "rv10_val": 0.0,
            "rule8_derived": True,
            "rule11_derived": True
        }
        
    # Sort chronologically by begins_at
    if isinstance(bars[0], dict) and "begins_at" in bars[0]:
        bars = sorted(bars, key=lambda x: x.get("begins_at", ""))
        
    closes = []
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        try:
            val = float(bar.get("close_price") or bar.get("close", 0.0))
            if val > 0.0:
                closes.append(val)
        except (ValueError, TypeError):
            continue
            
    if len(closes) <= 1:
        return {
            "iv30_val": 0.0,
            "hv90_val": 0.0,
            "rv10_val": 0.0,
            "rule8_derived": True,
            "rule11_derived": True
        }
        
    log_returns = [math.log(closes[i] / closes[i-1]) for i in range(1, len(closes))]
    
    # HV90 proxy (using exactly the last 90 log returns for 90-day realized volatility window)
    hv90_val = calculate_annualized_vol(log_returns[-90:])
    
    # RV10 proxy (using exactly the last 10 log returns for 10-day volatility compression)
    rv10_val = calculate_annualized_vol(log_returns[-10:])
    
    iv30_val = (iv_sum / iv_count) * 100.0 if iv_count > 0 else 0.0
    
    rule8_derived = iv30_val < hv90_val if iv30_val > 0.0 and hv90_val > 0.0 else True
    rule11_derived = rv10_val <= 35.0 if rv10_val > 0.0 else True
    
    return {
        "iv30_val": iv30_val,
        "hv90_val": hv90_val,
        "rv10_val": rv10_val,
        "rule8_derived": rule8_derived,
        "rule11_derived": rule11_derived
    }


def select_best_option(inst_data, quotes_data, spot, gex_target, today_override=None, target_delta=0.45, min_dte=30, max_dte=45):
    """
    Isolates and recommends the single best call option contract based on
    the 5-step Option Selection Protocol.
    """
    # 1. Parse instruments
    instruments_list = []
    if isinstance(inst_data, dict):
        if "data" in inst_data and isinstance(inst_data["data"], dict):
            instruments_list = inst_data["data"].get("instruments", [])
        else:
            instruments_list = inst_data.get("instruments", [])
    elif isinstance(inst_data, list):
        instruments_list = inst_data

    inst_map = {}
    for inst in instruments_list:
        if not isinstance(inst, dict) or "id" not in inst:
            continue
        try:
            inst_map[inst["id"]] = {
                "strike": float(inst["strike_price"]) if "strike_price" in inst else float(inst.get("strike", 0.0)),
                "type": inst["type"].lower(),
                "expiration_date": inst.get("expiration_date"),
                "symbol": inst.get("chain_symbol", "")
            }
        except (ValueError, KeyError, TypeError):
            continue

    # 2. Parse quotes
    quotes_list = []
    if isinstance(quotes_data, dict):
        quotes_list = quotes_data.get("data", {}).get("results", [])
        if not quotes_list:
            quotes_list = quotes_data.get("data", [])
        if not quotes_list:
            quotes_list = quotes_data.get("results", [])
    elif isinstance(quotes_data, list):
        quotes_list = quotes_data

    quotes_map = {}
    for q_item in quotes_list:
        if not isinstance(q_item, dict):
            continue
        q = q_item.get("quote", q_item)
        if not isinstance(q, dict):
            continue
        opt_id = q.get("instrument_id") or q.get("id") or q.get("instrument")
        if not opt_id:
            continue
        quotes_map[opt_id] = q

    # 3. Identify and score monthly/active expiration dates
    expirations = set()
    for inst in inst_map.values():
        if inst["expiration_date"] and inst["type"] == "call":
            expirations.add(inst["expiration_date"])

    if not expirations:
        return None, []

    today = today_override if today_override else datetime.today().date()
    if isinstance(today, str):
        today = datetime.strptime(today, "%Y-%m-%d").date()
    elif isinstance(today, datetime):
        today = today.date()

    valid_expirations = []
    for exp_str in expirations:
        try:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            dte = (exp_date - today).days
            # Exclude short-term weekly expirations (< 14 days)
            if dte >= 14:
                valid_expirations.append((exp_str, dte))
        except (ValueError, TypeError):
            continue

    if not valid_expirations:
        return None, []

    # Choose the expiration date closest to min_dte to max_dte calendar days.
    # We want to minimize distance to the min_dte-max_dte window.
    # If in window target distance is 0, else distance is to the nearest boundary.
    def exp_target_distance(item):
        exp_str, dte = item
        if min_dte <= dte <= max_dte:
            return (0, abs(dte - min_dte))
        else:
            return (1, min(abs(dte - min_dte), abs(dte - max_dte)))

    # Sort expirations to find the single best matching expiration date
    valid_expirations.sort(key=exp_target_distance)
    chosen_exp, chosen_dte = valid_expirations[0]

    # Gather contracts for this expiration
    eligible_contracts = []
    for opt_id, inst in inst_map.items():
        if inst["expiration_date"] == chosen_exp and inst["type"] == "call":
            q = quotes_map.get(opt_id)
            if not q:
                continue
            
            try:
                strike = inst["strike"]
                bid = float(q.get("bid_price") or 0.0)
                ask = float(q.get("ask_price") or 0.0)
                mark = float(q.get("mark_price") or q.get("adjusted_mark_price") or ((bid + ask) / 2.0))
                oi = int(q.get("open_interest") or 0)
                vol = int(q.get("volume") or 0)
                delta = float(q.get("delta") or 0.0) if q.get("delta") is not None else None
                gamma = float(q.get("gamma") or 0.0) if q.get("gamma") is not None else None
                iv = float(q.get("implied_volatility") or q.get("implied_vol", 0.0))
            except (ValueError, TypeError):
                continue

            # Crucial Constraint: Strike strictly below +GEX (T1 target)
            if gex_target and strike >= gex_target:
                continue

            # Bid-Ask Spread Limit (The Liquidity Gate)
            spread = ask - bid
            spread_ok = False
            if mark <= 2.0:
                spread_ok = (spread <= 0.15)
            elif mark <= 5.0:
                spread_ok = (spread <= 0.25)
            else:
                spread_ok = (spread <= 0.10 * bid) if bid > 0 else (spread <= 0.10 * mark)

            oi_ok = (oi >= 500)
            liquidity_passed = oi_ok and spread_ok

            # Strike Selection Guidelines:
            # - Preferred strike is closest to ATM or slightly OTM (0.0% to +5.0% above current Spot)
            # - Or Delta range between 0.40 and 0.50 (inclusive)
            pct_above_spot = ((strike - spot) / spot) * 100 if spot > 0 else 0.0
            strike_preferred = (0.0 <= pct_above_spot <= 5.0)

            delta_preferred = False
            if delta is not None:
                delta_preferred = (target_delta - 0.05 <= delta <= target_delta + 0.05)

            # Scoring contracts
            # Tier 1: Liquidity passed + strike or delta preferred
            # Tier 2: Liquidity passed
            # Tier 3: Liquidity failed + strike or delta preferred
            # Tier 4: Liquidity failed
            
            tier = 4
            if liquidity_passed:
                if strike_preferred or delta_preferred:
                    tier = 1
                else:
                    tier = 2
            else:
                if strike_preferred or delta_preferred:
                    tier = 3

            # Score within tier
            dist_to_atm = abs(strike - spot)
            dist_to_ideal_delta = abs(delta - target_delta) if delta is not None else 1.0

            eligible_contracts.append({
                "option_id": opt_id,
                "strike": strike,
                "expiration_date": chosen_exp,
                "dte": chosen_dte,
                "bid": bid,
                "ask": ask,
                "mark": mark,
                "spread": spread,
                "spread_ok": spread_ok,
                "oi": oi,
                "oi_ok": oi_ok,
                "vol": vol,
                "delta": delta,
                "gamma": gamma,
                "iv": iv,
                "liquidity_passed": liquidity_passed,
                "strike_preferred": strike_preferred,
                "delta_preferred": delta_preferred,
                "pct_above_spot": pct_above_spot,
                "tier": tier,
                "dist_to_atm": dist_to_atm,
                "dist_to_ideal_delta": dist_to_ideal_delta
            })

    if not eligible_contracts:
        return None, []

    # Sort eligible contracts:
    # 1. Lower tier is better (1 is best, 4 is worst)
    # 2. Prefer delta-preferred or strike-preferred
    # 3. Minimize distance to ATM (closest to spot is ATM/slightly OTM)
    # 4. If we have Delta, minimize distance to ideal delta (0.45)
    eligible_contracts.sort(key=lambda x: (
        x["tier"],
        x["dist_to_atm"] if x["delta"] is None else x["dist_to_ideal_delta"],
        x["dist_to_atm"]
    ))

    best_contract = eligible_contracts[0]
    return best_contract, eligible_contracts


def cmd_analyze(args):
    """Grades and analyzes options setups for a given ticker."""
    symbol = args.symbol.upper()
    analyses = load_json(ANALYSES_FILE, {})
    
    cached = analyses.get(symbol, {})
    
    # Fallback spot from candidates if not passed and not cached
    spot = args.spot if args.spot is not None else cached.get("Spot")
    if spot is None:
        cand_data = load_json(CANDIDATES_FILE, {})
        for c in cand_data.get("candidates", []):
            if c["symbol"].upper() == symbol:
                spot = c["price"]
                break

    inst_data = None
    quotes_data = None
    # If inst-file and quote-file are passed, perform mechanical local GEX profile derivation
    if hasattr(args, "inst_file") and args.inst_file and hasattr(args, "quote_file") and args.quote_file:
        try:
            with open(args.inst_file, "r") as f:
                inst_data = json.load(f)
            with open(args.quote_file, "r") as f:
                quotes_data = json.load(f)
                
            calc_spot = spot if spot is not None else 100.0
            gex_profile = derive_gex_profile(inst_data, quotes_data, calc_spot)
            
            # Map parameters from gex_profile dict
            total_oi = gex_profile["total_oi"]
            total_call_gex = gex_profile["total_call_gex"]
            total_put_gex = gex_profile["total_put_gex"]
            derived_ptrans = gex_profile["derived_ptrans"]
            derived_ntrans = gex_profile["derived_ntrans"]
            derived_gex = gex_profile["derived_gex"]
            derived_cotmp = gex_profile["derived_cotmp"]
            
            # Set rule arguments if they are None
            if args.ptrans is None: args.ptrans = round(derived_ptrans, 2)
            if args.ntrans is None: args.ntrans = round(derived_ntrans, 2)
            if args.gex is None: args.gex = round(derived_gex, 2)
            if args.cotmp is None: args.cotmp = round(derived_cotmp, 2)
            
            if args.rule1 is None: args.rule1 = gex_profile["rule1_derived"]
            if args.rule2 is None: args.rule2 = gex_profile["rule2_derived"]
            if args.rule7 is None: args.rule7 = gex_profile["rule7_derived"]
            if args.rule9 is None: args.rule9 = gex_profile["rule9_derived"]
            if args.rule10 is None: args.rule10 = gex_profile["rule10_derived"]
            
            if total_oi > 0:
                # If hist-file is passed, derive Rule 8 and Rule 11 volatility proxies
                if hasattr(args, "hist_file") and args.hist_file:
                    try:
                        with open(args.hist_file, "r") as f:
                            hist_data = json.load(f)
                        
                        vol_profile = derive_volatility_profile(hist_data, symbol, gex_profile["iv_sum"], gex_profile["iv_count"])
                        
                        if args.rule8 is None: args.rule8 = vol_profile["rule8_derived"]
                        if args.rule11 is None: args.rule11 = vol_profile["rule11_derived"]
                        
                        print(format_color(f"📈 Volatility Profile Derivation complete for {symbol}:", "32", bold=True))
                        print(f"  -> IV30 Proxy: {vol_profile['iv30_val']:.2f}% vs HV90 Proxy: {vol_profile['hv90_val']:.2f}% (Rule8: {vol_profile['rule8_derived']})")
                        print(f"  -> RV10: {vol_profile['rv10_val']:.2f}% (Rule11 Setup Vol Compression: {'PASS' if vol_profile['rule11_derived'] else 'FAIL'})")
                    except Exception as ve:
                        print(f"Error deriving volatility indices from historical price files: {ve}", file=sys.stderr)
                
                print(format_color(f"🤖 Upgraded GEX Derivation complete for {symbol}:", "32", bold=True))
                print(f"  -> COTMP: ${derived_cotmp:.2f}, pTrans: ${derived_ptrans:.2f}, nTrans: ${derived_ntrans:.2f}, +GEX: ${derived_gex:.2f}")
                print(f"  -> Call GEX: ${total_call_gex:,.2f}, Put GEX: ${total_put_gex:,.2f} (Rule2: {gex_profile['rule2_derived']})")
        except Exception as e:
            print(f"Error deriving GEX profile from option data files: {e}", file=sys.stderr)

    ptrans = args.ptrans if args.ptrans is not None else cached.get("pTrans")
    ntrans = args.ntrans if args.ntrans is not None else cached.get("nTrans")
    gex = args.gex if args.gex is not None else cached.get("+GEX")
    cotmp = args.cotmp if args.cotmp is not None else cached.get("COTMP")
    db_change = args.db_change if args.db_change is not None else cached.get("db_change")
    spike_crash = args.spike_crash if args.spike_crash is not None else cached.get("spike_crash", False)
    
    if None in (spot, ptrans, ntrans, gex, cotmp, db_change):
        print(f"Error: Missing required metrics for {symbol}. Pass them via command line arguments or ensure they exist in {ANALYSES_FILE}.", file=sys.stderr)
        print("Required fields: --spot, --ptrans, --ntrans, --gex, --cotmp, --db-change", file=sys.stderr)
        sys.exit(1)
        
    # Calculate Grade (rule overrides fall back to cached values, then True)
    rule_overrides = {
        "rule1": args.rule1 if args.rule1 is not None else cached.get("rule1", True),
        "rule2": args.rule2 if args.rule2 is not None else cached.get("rule2", True),
        "rule7": args.rule7 if args.rule7 is not None else cached.get("rule7", True),
        "rule8": args.rule8 if args.rule8 is not None else cached.get("rule8", True),
        "rule9": args.rule9 if args.rule9 is not None else cached.get("rule9", True),
        "rule10": args.rule10 if args.rule10 is not None else cached.get("rule10", True),
        "rule11": args.rule11 if args.rule11 is not None else cached.get("rule11", True),
    }
    extra_rules = {
        "total_call_gex_positive": rule_overrides["rule1"],
        "call_gex_gt_put_gex": rule_overrides["rule2"],
        "total_oi_gt_10000": rule_overrides["rule7"],
        "iv_30_lt_hv_90": rule_overrides["rule8"],
        "oi_depth_target_positive": rule_overrides["rule9"],
        "dealer_gamma_net_positive": rule_overrides["rule10"],
        "rv_10_stable": rule_overrides["rule11"],
    }
    
    grade, rule_checklist = calculate_grade(symbol, spot, ptrans, ntrans, gex, cotmp, extra_rules)
    
    # Calculate COTMP Cushion
    # Formula: ((Spot - COTMP) / COTMP) * 100
    cotmp_cushion = round(((spot - cotmp) / cotmp) * 100, 2)
    
    # Calculate Risk/Reward
    # Formula: Reward = (+GEX - Spot), Risk = Spot - pTrans
    reward = gex - spot
    risk = spot - ptrans
    rr_ratio = round(reward / risk, 2) if risk > 0 else 999.0
    
    # Define Signal Status & Classification
    # Watchdog buffer is 0.5% below pTrans. If Spot reaches watchdog buffer or above setup rules
    watchdog_threshold = ptrans * 0.995
    
    status = "BLOCKED"
    reasons = []
    
    if grade < 9:
        reasons.append(f"Grade <= 8 ({grade}/11)")
    
    # db_change filter: must satisfy db_change >= 0.50 (Grade 11 DEEP = 0.30)
    db_threshold = 0.50
    if grade == 11 and cotmp_cushion >= 1.0 and cotmp_cushion < 2.0:
        db_threshold = 0.30
    if cached.get("pegged_1_00_sessions", 0) >= 2:
        db_threshold = 0.0  # Exempt
        
    if db_change < db_threshold:
        reasons.append(f"db_change {db_change:.2f} < threshold {db_threshold:.2f}")
        
    # COTMP Cushion target: Spot >= 2.0% above COTMP (Grade 11 or high db_change >= 0.50 can use 1.0%)
    cushion_threshold = 2.0
    if grade == 11 or db_change >= 0.50:
        cushion_threshold = 1.0
        
    if cotmp_cushion < cushion_threshold:
        reasons.append(f"COTMP Cushion {cotmp_cushion:.2f}% < threshold {cushion_threshold:.2f}%")
        
    if spike_crash:
        reasons.append("Spike-Crash Pattern profile detected")
        
    if rr_ratio < 2.0:
        reasons.append(f"Risk/Reward ratio {rr_ratio:.2f} < 2.00")
        
    if not reasons:
        if spot >= ptrans:
            status = "CONFIRMED"
        elif spot >= watchdog_threshold:
            status = f"PENDING (watchdog)"
        else:
            status = "PENDING (below watchdog)"
    else:
        status = f"BLOCKED ({', '.join(reasons)})"
        
    # Update analyses file
    analyses[symbol] = {
        "Ticker": symbol,
        "Spot": round(spot, 2),
        "Grade": grade,
        "pTrans": round(ptrans, 2),
        "nTrans": round(ntrans, 2),
        "+GEX": round(gex, 2),
        "COTMP": round(cotmp, 2),
        "db_change": round(db_change, 2),
        "COTMP Cushion": cotmp_cushion,
        "Risk/Reward": rr_ratio,
        "Signal Status": status,
        "analyzed_date": datetime.today().strftime('%Y-%m-%d'),
        "spike_crash": bool(spike_crash),
        **rule_overrides
    }
    # Keep count of pegged sessions if db_change is exactly 1.00
    if db_change == 1.00:
        analyses[symbol]["pegged_1_00_sessions"] = cached.get("pegged_1_00_sessions", 0) + 1
    else:
        analyses[symbol]["pegged_1_00_sessions"] = 0
        
    save_json(ANALYSES_FILE, analyses)
    
    # Print results formatted perfectly
    grade_color = "32" if grade >= 9 else "31"
    db_color = "32" if db_change >= db_threshold else "31"
    cushion_color = "32" if cotmp_cushion >= cushion_threshold else "31"
    sc_color = "31" if spike_crash else "32"
    rr_color = "32" if rr_ratio >= 2.0 else "31"
    
    status_fmt = format_color(status, "32" if status.startswith("CONFIRMED") else ("33" if status.startswith("PENDING") else "31"), bold=True)
    
    print(f"### 🔍 Setup Breakdown: {symbol}")
    print(f"- **Current Spot**: ${spot:.2f}")
    print(f"- **Key Gamma Levels**:")
    print(f"  - pTrans (Positive Transition): ${ptrans:.2f}")
    print(f"  - nTrans (Negative Transition): ${ntrans:.2f}")
    print(f"  - +GEX (T1 Target): ${gex:.2f}")
    print(f"  - COTMP (Center of Put Mass): ${cotmp:.2f}")
    print(f"- **Core Filters**:")
    print(f"  1. **Structural Grade**: {format_color(f'{grade}/11', grade_color)} (Status: {format_color('PASS' if grade >= 9 else 'FAIL', grade_color, bold=True)})")
    print(f"  2. **db_change (Delta Balance Change)**: {format_color(f'{db_change:.2f}', db_color)} (Status: {format_color('PASS' if db_change >= db_threshold else 'FAIL', db_color, bold=True)})")
    print(f"  3. **COTMP Cushion**: {format_color(f'{cotmp_cushion:.2f}%', cushion_color)} (Status: {format_color('PASS' if cotmp_cushion >= cushion_threshold else 'FAIL', cushion_color, bold=True)})")
    print(f"  4. **Spike-Crash Check**: {format_color('FAIL - Blocked' if spike_crash else 'PASS - No Pattern', sc_color, bold=True)}")
    print(f"  5. **Risk/Reward Ratio**: {format_color(f'{rr_ratio:.2f}:1', rr_color)} (Status: {format_color('PASS' if rr_ratio >= 2.0 else 'FAIL', rr_color, bold=True)})")
    print(f"\n### 🚀 Status & Action")
    print(f"- **Signal Status**: {status_fmt}")
    if status.startswith("CONFIRMED"):
        print_color(f"- **Recommended Play**: Underlier Spot is above pTrans. Look for bullish Option contract entry targeting ${gex:.2f}.", "32", bold=True)
    elif status.startswith("PENDING"):
        print_color(f"- **Recommended Play**: Setup valid. Standard watch list entry activated. Look for 5-minute close above pTrans (${ptrans:.2f}) to trigger execution.", "33", bold=True)
    else:
        print_color(f"- **Recommended Play**: NO ENTRY. Setup blocked by system safeguards.", "31", bold=True)

    if inst_data is not None and quotes_data is not None:
        target_delta = getattr(args, "target_delta", 0.45)
        min_dte = getattr(args, "min_dte", 30)
        max_dte = getattr(args, "max_dte", 45)
        best_option, _ = select_best_option(
            inst_data, quotes_data, spot, gex,
            target_delta=target_delta, min_dte=min_dte, max_dte=max_dte
        )
        if best_option:
            print(f"\n### 🎯 Option Selection Recommendation")
            print(f"- **Target Contract**: Call Option strike ${best_option['strike']:.2f} expiring {best_option['expiration_date']} (DTE: {best_option['dte']})")
            print(f"- **Option ID**: {best_option['option_id']}")
            print(f"- **Greeks & Pricing**:")
            print(f"  - Mark Price: ${best_option['mark']:.2f} (Ask: ${best_option['ask']:.2f}, Bid: ${best_option['bid']:.2f}, Spread: ${best_option['spread']:.2f})")
            delta_str = f"{best_option['delta']:.4f}" if best_option['delta'] is not None else "N/A"
            gamma_str = f"{best_option['gamma']:.4f}" if best_option['gamma'] is not None else "N/A"
            print(f"  - Delta: {delta_str} | Gamma: {gamma_str} | Implied Vol: {best_option['iv']*100:.1f}%")
            print(f"  - Liquidity Metrics: Open Interest: {best_option['oi']} | Volume: {best_option['vol']}")
            
            # Print spread and liquidity warnings
            flags = []
            if not best_option['spread_ok']:
                flags.append("HIGH-SPREAD RISK")
            if not best_option['oi_ok']:
                flags.append("LOW-OI RISK")
            
            if flags:
                flag_str = " | ".join(flags)
                print(format_color(f"  - ⚠️ WARNING: [{flag_str}] contract has wide bid-ask spread or insufficient open interest.", "33", bold=True))
            else:
                print(format_color("  - ✅ LIQUIDITY GATE: PASS", "32"))

            # Sizing / Constraints calculator
            net_liq = getattr(args, "net_liq", None)
            if net_liq is None:
                net_liq = 50000.0
            
            max_risk = net_liq * 0.03
            cost_per_contract = best_option['mark'] * 100.0
            if cost_per_contract > 0:
                max_contracts = int(max_risk // cost_per_contract)
            else:
                max_contracts = 0
                
            print(f"- **Aggregate Sizing Simulation**:")
            print(f"  - Portfolio Net Liq Reference: ${net_liq:,.2f}")
            print(f"  - Single-Leg Max Sizing Allowed (3.0% Net Liq): ${max_risk:,.2f}")
            print(f"  - Estimated Sizing Recommendation: {format_color(f'{max_contracts} contracts', '32', bold=True)} at ${best_option['mark']:.2f} per premium (Total Premium: ${max_contracts * cost_per_contract:,.2f})")


def compute_exit_rule_state(spot, purchase_premium, mark_price, ptrans, ntrans, gex_t1, days_held, stalling_counter, dte, target_mode="T1", t2_target=None):
    """
    Computes exit rule evaluation logic, proposed actions, and time status.
    
    Returns:
        tuple[str, str, str, str, str]: (exit_rule_state, proposed_action, time_status, distance_ntrans, distance_max_stop)
    """
    pl_pct = ((mark_price - purchase_premium) / purchase_premium) * 100 if purchase_premium else 0.0
    
    exit_rule_state = "HOLD"
    proposed_action = "No Action"
    time_status = "ON TRACK"
    
    distance_ntrans = "N/A"
    if ntrans:
        dist = ((spot - ntrans) / ntrans) * 100
        distance_ntrans = f"{dist:+.2f}%"
        if spot < ntrans:
            exit_rule_state = "STOP TRIGGERED (Structural Stop: Spot < nTrans)"
            proposed_action = "Immediate Exit (Structural Stop)"
            
    distance_max_stop = "N/A"
    if ptrans:
        if spot < ptrans:
            if not exit_rule_state.startswith("STOP TRIGGERED"):
                if pl_pct <= -10.0:
                    exit_rule_state = "STOP TRIGGERED (Max Asset Stop: -10% option loss below pTrans)"
                    proposed_action = "Immediate Exit (Max Asset Stop)"
            distance_max_stop = f"{pl_pct:+.2f}% vs -10.00% max"
        else:
            distance_max_stop = "Protection dormant (Spot > pTrans)"
            
    if days_held >= 7:
        if gex_t1 and ptrans:
            full_run = gex_t1 - ptrans
            made_progress = spot - ptrans
            progress_pct = (made_progress / full_run) * 100 if full_run > 0 else 0.0
            if progress_pct < 50.0:
                if not exit_rule_state.startswith("STOP TRIGGERED"):
                    exit_rule_state = "STOP TRIGGERED (Time Stop: <50% progress by Day 7)"
                    proposed_action = "Immediate Exit (Time Stop)"
                time_status = "STALE (Time Limit Exceeded)"
                
    if stalling_counter >= 3:
        if not exit_rule_state.startswith("STOP TRIGGERED"):
            exit_rule_state = "STOP TRIGGERED (Stalling Stop: <10% daily progress for 3 consecutive days)"
            proposed_action = "Immediate Exit (Stalling Stop)"
        time_status = "STALLED"
        
    if target_mode == "T2":
        # Sizing / protect T1 gains: Trail stop to entry price
        if pl_pct <= 0.0:
            if not exit_rule_state.startswith("STOP TRIGGERED"):
                exit_rule_state = "STOP TRIGGERED (Trailed Stop: Option at or below entry premium)"
                proposed_action = "Immediate Exit (Trailed Stop at Entry Premium to protect T1 gains)"
                
        # Target evaluation for T2
        target_price = t2_target if t2_target is not None else (gex_t1 * 1.10 if gex_t1 else None)
        if target_price and spot >= target_price:
            if not exit_rule_state.startswith("STOP TRIGGERED"):
                exit_rule_state = "PROFIT TAKE (T2 TARGET MET)"
                proposed_action = "Exit position to lock in full T2/Lock & Ride gains"
    else:
        # Standard T1 target evaluation
        if gex_t1 and spot >= gex_t1:
            if not exit_rule_state.startswith("STOP TRIGGERED"):
                if pl_pct < 0:
                    exit_rule_state = "UNDERLIER TARGET MET (Option in Loss)"
                    proposed_action = "Exit position to limit further losses (Strike/Maturity mismatch or decay)"
                else:
                    exit_rule_state = "PROFIT TAKE (T1 TARGET MET)"
                    proposed_action = "Exit for 100% gains OR Trail stop to entry price and target structural T2"

    if dte is not None and dte < 0:
        exit_rule_state = "EXPIRED (Contract past expiration)"
        proposed_action = "Remove from tracker via close-position"
        time_status = "EXPIRED"
        
    if exit_rule_state == "HOLD" and ptrans and spot < ptrans:
        exit_rule_state = "WATCH"
        proposed_action = "Hold existing, but add NOTHING"
        
    return exit_rule_state, proposed_action, time_status, distance_ntrans, distance_max_stop


def cmd_portfolio(args):
    """Tracks position exits, risk sizing weights, and portfolio metrics."""
    options = load_json(OPTIONS_FILE, {"options_positions": {}, "stocks_positions": {}})
    analyses = load_json(ANALYSES_FILE, {})
    
    positions = options.get("options_positions", {})
    stocks = options.get("stocks_positions", {})
    
    if not positions and not stocks:
        print("### 🛡️ Active Portfolio Tracker & Exits (Current Positions)")
        print("No open positions found in cache.")
        return
        
    print("### 🛡️ Active Portfolio Tracker & Exits (Current Positions)")
    
    tech_exposure = 0.0
    net_liq = args.net_liq if args.net_liq is not None else 50000.0 # Default total workspace valuation estimate
    total_cost_basis = 0.0
    total_current_value = 0.0
    
    if positions:
        print("\n### 🛡️ Active Options Positions (GEX Tracked)")
    for opt_id, details in positions.items():
        ticker = details.get("Underlier")
        purchase_premium = float(details.get("Purchase Premium", 1.0))
        mark_price = float(details.get("Mark Price", 1.0))
        strike = details.get("Strike")
        expiration = details.get("Expiration")
        opt_type = details.get("Type")
        
        # Calculate P&L
        pl_dollar = (mark_price - purchase_premium) * 100
        pl_pct = ((mark_price - purchase_premium) / purchase_premium) * 100
        
        # Fetch levels from analyses if available
        levels = analyses.get(ticker, {})
        ptrans = levels.get("pTrans")
        ntrans = levels.get("nTrans")
        gex_t1 = levels.get("+GEX")
        spot = args.spot_overrides.get(ticker) if args.spot_overrides else None
        if spot is None:
            spot = levels.get("Spot")
        if spot is None:
            spot = details.get("Underlier Spot") or details.get("Spot")
            
        if spot is None:
            # Fallback mock spot to keep calculations running
            spot = float(strike) if strike else 100.0
            
        # Determine tracking days (derived from Entry Date when available)
        days_held = details.get("Days Held", 1)
        entry_date = details.get("Entry Date")
        if entry_date:
            try:
                days_held = max((datetime.today() - datetime.strptime(entry_date, "%Y-%m-%d")).days + 1, 1)
                details["Days Held"] = days_held
            except ValueError:
                pass

        # Days to expiration
        dte = None
        if expiration:
            try:
                dte = (datetime.strptime(expiration, "%Y-%m-%d") - datetime.today()).days
            except ValueError:
                pass
        
        # Calculate stops
        stalling_counter = details.get("Stalling Days", 0)
        target_mode = details.get("Target Mode", "T1")
        t2_target = details.get("T2 Target")
        if t2_target is not None:
            try:
                t2_target = float(t2_target)
            except (ValueError, TypeError):
                t2_target = None
                
        exit_rule_state, proposed_action, time_status, distance_ntrans, distance_max_stop = compute_exit_rule_state(
            spot, purchase_premium, mark_price, ptrans, ntrans, gex_t1, days_held, stalling_counter, dte,
            target_mode=target_mode, t2_target=t2_target
        )
            
        # Update metrics in position state
        details["Current Value"] = mark_price * 100
        details["P&L ($)"] = round(pl_dollar, 2)
        details["P&L (%)"] = round(pl_pct, 2)
        sizing_risk_weight = ((details["Asset Cost Basis"] if "Asset Cost Basis" in details else (purchase_premium * 100)) / net_liq) * 100
        details["Sizing Risk Weight (%)"] = round(sizing_risk_weight, 2)
        
        details_sector_tag = details.get("Beta Sector Tag", "Equity")
        if "Technology" in details_sector_tag or "Beta" in details_sector_tag:
            tech_exposure += sizing_risk_weight
            
        # Format strings with CLI colors
        pl_color = "32" if pl_pct >= 0 else "31"
        status_colors = {
            "HOLD": ("32", False),
            "WATCH": ("33", False),
            "PROFIT TAKE (T1 TARGET MET)": ("32", True),
            "PROFIT TAKE (T2 TARGET MET)": ("32", True),
            "UNDERLIER TARGET MET (Option in Loss)": ("31", True),
            "STOP TRIGGERED (Structural Stop: Spot < nTrans)": ("31", True),
            "STOP TRIGGERED (Max Asset Stop: -10% option loss below pTrans)": ("31", True),
            "STOP TRIGGERED (Time Stop: <50% progress by Day 7)": ("31", True),
            "STOP TRIGGERED (Stalling Stop: <10% daily progress for 3 consecutive days)": ("31", True),
            "STOP TRIGGERED (Trailed Stop: Option at or below entry premium)": ("31", True),
            "EXPIRED (Contract past expiration)": ("31", True),
        }
        color_code, bold = status_colors.get(exit_rule_state, ("31", True))
        exit_rule_fmt = format_color(exit_rule_state, color_code, bold=bold)
        
        # Print position
        print(f"- **{format_color(ticker, '35', bold=True)}**: Current Spot {format_color(f'${spot:.2f}', '36')} vs Avg Buy Premium {format_color(f'${purchase_premium:.2f}', '33')} / Mark {format_color(f'${mark_price:.2f}', '33')} (Gain/Loss: {format_color(f'{pl_pct:+.2f}%', pl_color, bold=True)})")
        print(f"  - **Exits Rule State**: [{exit_rule_fmt}]")
        print(f"  - **Target Mode**: [{target_mode}]{' (Target Strike: $' + f'{t2_target:.2f}' + ')' if t2_target else ''}")
        print(f"  - **Distance to Structural Stop (nTrans at ${ntrans if ntrans else 0.0:.2f})**: {distance_ntrans}")
        print(f"  - **Distance to Max Asset Stop**: {distance_max_stop}")
        dte_str = f", DTE: {dte}" if dte is not None else ""
        print(f"  - **Time / Momentum Tracking**: Day [{days_held}] of 7 (Status: [{time_status}]{dte_str})")
        print(f"  - **Proposed Action**: [{format_color(proposed_action, color_code, bold=bold)}]")
        
        # Accumulate aggregate metrics
        total_cost_basis += details.get("Asset Cost Basis") or (purchase_premium * 100.0)
        total_current_value += details.get("Current Value") or (mark_price * 100.0)

    if stocks:
        print("\n### 📈 Active Stock Positions")
    for ticker, details in stocks.items():
        shares = float(details.get("Shares", 0.0))
        avg_price = float(details.get("Average Buy Price", 0.0))
        
        levels = analyses.get(ticker, {})
        ptrans = levels.get("pTrans")
        ntrans = levels.get("nTrans")
        gex_t1 = levels.get("+GEX")
        
        spot = args.spot_overrides.get(ticker) if args.spot_overrides else None
        if spot is None:
            spot = levels.get("Spot")
        if spot is None:
            spot = details.get("Current Price") or details.get("Spot")
        if spot is None:
            spot = avg_price
            
        cost_basis = shares * avg_price
        curr_val = shares * spot
        pl_dollar = curr_val - cost_basis
        pl_pct = (pl_dollar / cost_basis) * 100.0 if cost_basis > 0 else 0.0
        
        # Determine exit rule states for stocks
        exit_rule_state = "HOLD"
        proposed_action = "No Action"
        
        distance_ntrans = "N/A"
        if ntrans:
            dist = ((spot - ntrans) / ntrans) * 100
            distance_ntrans = f"{dist:+.2f}%"
            if spot < ntrans:
                exit_rule_state = "STOP TRIGGERED (Structural Stop: Spot < nTrans)"
                proposed_action = "Immediate Exit (Structural Stop)"
                
        if exit_rule_state == "HOLD":
            if gex_t1 and spot >= gex_t1:
                exit_rule_state = "PROFIT TAKE (T1 TARGET MET)"
                proposed_action = "Exit position or scale out at +GEX target to lock in gains"
            elif ptrans and spot < ptrans:
                exit_rule_state = "WATCH"
                proposed_action = "Hold existing, but add NOTHING"
                
        details["Current Price"] = spot
        details["Current Value"] = curr_val
        details["P&L ($)"] = round(pl_dollar, 2)
        details["P&L (%)"] = round(pl_pct, 2)
        sizing_risk_weight = (cost_basis / net_liq) * 100
        details["Sizing Risk Weight (%)"] = round(sizing_risk_weight, 2)
        
        details_sector_tag = details.get("Beta Sector Tag", "Equity")
        if "Technology" in details_sector_tag or "Beta" in details_sector_tag:
            tech_exposure += sizing_risk_weight
            
        pl_color = "32" if pl_pct >= 0 else "31"
        status_colors = {
            "HOLD": ("32", False),
            "WATCH": ("33", False),
            "PROFIT TAKE (T1 TARGET MET)": ("32", True),
            "STOP TRIGGERED (Structural Stop: Spot < nTrans)": ("31", True),
        }
        color_code, bold = status_colors.get(exit_rule_state, ("31", True))
        exit_rule_fmt = format_color(exit_rule_state, color_code, bold=bold)
        
        print(f"- **{format_color(ticker, '35', bold=True)}**: Current Spot {format_color(f'${spot:.2f}', '36')} vs Avg Buy Price {format_color(f'${avg_price:.2f}', '33')} (Shares: {shares:,.2f} | Gain/Loss: {format_color(f'{pl_pct:+.2f}%', pl_color, bold=True)} / {format_color(f'${pl_dollar:+.2f}', pl_color, bold=True)})")
        print(f"  - **Exits Rule State**: [{exit_rule_fmt}]")
        print(f"  - **Distance to GEX nTrans Stop (nTrans at ${ntrans if ntrans else 0.0:.2f})**: {distance_ntrans}")
        print(f"  - **Proposed Action**: [{format_color(proposed_action, color_code, bold=bold)}]")
        
        total_cost_basis += cost_basis
        total_current_value += curr_val
        
    # Aggregate Portfolio Metrics
    unrealized_pl_dlr = total_current_value - total_cost_basis
    unrealized_pl_pct = (unrealized_pl_dlr / total_cost_basis) * 100.0 if total_cost_basis > 0 else 0.0
    options_exposure_pct = (total_current_value / net_liq) * 100.0
    cash_buffer = net_liq - total_current_value
    cash_buffer_pct = (cash_buffer / net_liq) * 100.0
    
    pl_color = "32" if unrealized_pl_dlr >= 0 else "31"
    cash_buffer_status = format_color("PASS", "32", bold=True) if cash_buffer_pct >= 20.0 else format_color("WARNING (Low liquid buffer <20%)", "31", bold=True)
    
    print("\n### 📈 Aggregate Portfolio Summary")
    print(f"- **Total Portfolio Net Liquidation (Net Liq)**: ${net_liq:,.2f}")
    print(f"- **Total Positions Cost Basis**: ${total_cost_basis:,.2f}")
    print(f"- **Total Positions Market Value**: ${total_current_value:,.2f} ({options_exposure_pct:.2f}% allocation)")
    print(f"- **Total Unrealized P&L**: {format_color(f'${unrealized_pl_dlr:+,.2f}', pl_color, bold=True)} ({format_color(f'{unrealized_pl_pct:+.2f}%', pl_color, bold=True)})")
    print(f"- **Cash Buffer / Liquid Reserves**: ${cash_buffer:,.2f} ({cash_buffer_pct:.2f}% of Net Liq) | Status: {cash_buffer_status}")
    
    closed_options = options.get("closed_options", [])
    closed_stocks = options.get("closed_stocks", [])
    if closed_options or closed_stocks:
        print("\n### 📊 Realized Performance Stats")
        
        # Options specific stats
        if closed_options:
            total_closed_opt = len(closed_options)
            profitable_closed_opt = sum(1 for p in closed_options if p.get("Realized P&L ($)", 0.0) > 0.0)
            win_rate_opt = (profitable_closed_opt / total_closed_opt) * 100.0 if total_closed_opt > 0 else 0.0
            total_realized_opt = sum(p.get("Realized P&L ($)", 0.0) for p in closed_options)
            gross_p_opt = sum(p.get("Realized P&L ($)", 0.0) for p in closed_options if p.get("Realized P&L ($)", 0.0) > 0.0)
            gross_l_opt = abs(sum(p.get("Realized P&L ($)", 0.0) for p in closed_options if p.get("Realized P&L ($)", 0.0) < 0.0))
            pf_opt = f"{gross_p_opt / gross_l_opt:.2f}" if gross_l_opt > 0 else f"{gross_p_opt:.2f}" if gross_p_opt > 0 else "N/A"
            opt_color = "32" if total_realized_opt >= 0 else "31"
            print(f"- **Options Stats** ({total_closed_opt} trades): Realized Win Rate {win_rate_opt:.1f}% ({profitable_closed_opt}/{total_closed_opt} profitable) | Total Realized P&L: {format_color(f'${total_realized_opt:+,.2f}', opt_color, bold=True)} | PF: {pf_opt}")
            
        # Stocks specific stats
        if closed_stocks:
            total_closed_stk = len(closed_stocks)
            profitable_closed_stk = sum(1 for s in closed_stocks if s.get("Realized P&L ($)", 0.0) > 0.0)
            win_rate_stk = (profitable_closed_stk / total_closed_stk) * 100.0 if total_closed_stk > 0 else 0.0
            total_realized_stk = sum(s.get("Realized P&L ($)", 0.0) for s in closed_stocks)
            gross_p_stk = sum(s.get("Realized P&L ($)", 0.0) for s in closed_stocks if s.get("Realized P&L ($)", 0.0) > 0.0)
            gross_l_stk = abs(sum(s.get("Realized P&L ($)", 0.0) for s in closed_stocks if s.get("Realized P&L ($)", 0.0) < 0.0))
            pf_stk = f"{gross_p_stk / gross_l_stk:.2f}" if gross_l_stk > 0 else f"{gross_p_stk:.2f}" if gross_p_stk > 0 else "N/A"
            stk_color = "32" if total_realized_stk >= 0 else "31"
            print(f"- **Stocks Stats** ({total_closed_stk} trades): Realized Win Rate {win_rate_stk:.1f}% ({profitable_closed_stk}/{total_closed_stk} profitable) | Total Realized P&L: {format_color(f'${total_realized_stk:+,.2f}', stk_color, bold=True)} | PF: {pf_stk}")
            
        # Unified combined stats
        if closed_options and closed_stocks:
            all_closed = closed_options + closed_stocks
            total_closed_all = len(all_closed)
            profitable_closed_all = sum(1 for p in all_closed if p.get("Realized P&L ($)", 0.0) > 0.0)
            win_rate_all = (profitable_closed_all / total_closed_all) * 100.0 if total_closed_all > 0 else 0.0
            total_realized_all = sum(p.get("Realized P&L ($)", 0.0) for p in all_closed)
            gross_p_all = sum(p.get("Realized P&L ($)", 0.0) for p in all_closed if p.get("Realized P&L ($)", 0.0) > 0.0)
            gross_l_all = abs(sum(p.get("Realized P&L ($)", 0.0) for p in all_closed if p.get("Realized P&L ($)", 0.0) < 0.0))
            pf_all = f"{gross_p_all / gross_l_all:.2f}" if gross_l_all > 0 else f"{gross_p_all:.2f}" if gross_p_all > 0 else "N/A"
            all_color = "32" if total_realized_all >= 0 else "31"
            print(f"- **Total Combined Realized P&L**: {format_color(f'${total_realized_all:+,.2f}', all_color, bold=True)} | Win Rate {win_rate_all:.1f}% | Combined PF: {pf_all}")
        
    print("\n### 📏 Sizing Constraints Checklist")
    # Sizing constraints check
    over_allocated = []
    for opt_id, details in positions.items():
        risk_weight = details.get("Sizing Risk Weight (%)", 0.0)
        tk = details.get("Underlier")
        if risk_weight > 3.0:
            over_allocated.append(f"{tk} ({risk_weight:.2f}% > 3.0%)")
            
    single_leg_ok = len(over_allocated) == 0
    single_leg_fmt = format_color("PASS", "32", bold=True) if single_leg_ok else format_color(f"FAIL ({', '.join(over_allocated)})", "31", bold=True)
    print(f"- **Single-Leg Sizing Limit (<= 3.0% of Net Liq)**: {single_leg_fmt}")
    
    sector_cap_ok = tech_exposure <= 15.0
    sector_cap_fmt = format_color("PASS", "32", bold=True) if sector_cap_ok else format_color("FAIL", "31", bold=True)
    print(f"- **Sector Sizing Cap (Tech/Beta <= 15.0% of Net Liq)**: "
          f"{sector_cap_fmt} (Tech Sizing exposure: {format_color(f'{tech_exposure:.2f}%', '32' if sector_cap_ok else '31')})")
    
    # Sizing warnings for high concentration (exceeding 15% of net liq)
    high_concentration = []
    for opt_id, details in positions.items():
        curr_val = details.get("Current Value")
        if curr_val is None:
            curr_val = float(details.get("Mark Price", 1.0)) * 100.0
        curr_weight = (curr_val / net_liq) * 100.0
        if curr_weight >= 15.0:
            high_concentration.append(f"{details.get('Underlier')} ({curr_weight:.2f}%)")
            
    for ticker, details in stocks.items():
        curr_val = details.get("Current Value")
        if curr_val is None:
            shares = float(details.get("Shares", 0.0))
            spot = float(details.get("Current Price", 0.0))
            if spot <= 0.0:
                spot = float(details.get("Average Buy Price", 0.0))
            curr_val = shares * spot
        curr_weight = (curr_val / net_liq) * 100.0
        if curr_weight >= 15.0:
            high_concentration.append(f"{ticker} ({curr_weight:.2f}%)")
    
    if high_concentration:
        print_color(f"\n⚠️ HIGH CONCENTRATION ALERT: {', '.join(high_concentration)} exceed 15-20% portfolio Net Liquidation threshold.", "31", bold=True)
        print_color("⚠️ RECOMMENDED ACTION: Trim or reduce position exposure to maintain aggregate capital health.", "31", bold=False)
        
    if not sector_cap_ok:
        print_color(f"\n⚠️ SECTOR EXPOSURE ALERT: High-beta tech/beta exposure exceeds 15.0% ({tech_exposure:.2f}%).", "33", bold=True)
        print_color("⚠️ RECOMMENDED ACTION: Consider implementing broad-market sector hedges using S&P 500 or ETF benchmarks to defend capital variance.", "33", bold=False)
    
    # Save the updated indicators
    options["options_positions"] = positions
    save_json(OPTIONS_FILE, options)


def cmd_add_pos(args):
    """Add new options position manually."""
    options = load_json(OPTIONS_FILE, {"options_positions": {}})
    positions = options.get("options_positions", {})
    
    if args.option_id in positions:
        print(f"Error: Option ID {args.option_id} already exists in portfolio. Use update-option to modify it.", file=sys.stderr)
        sys.exit(1)
        
    try:
        datetime.strptime(args.expiration, "%Y-%m-%d")
    except ValueError:
        print(f"Error: Expiration '{args.expiration}' must be a valid date in YYYY-MM-DD format.", file=sys.stderr)
        sys.exit(1)
    
    positions[args.option_id] = {
        "Option ID": args.option_id,
        "Underlier": args.underlier.upper(),
        "Strike": f"{args.strike:.2f}",
        "Expiration": args.expiration,
        "Type": args.type.lower(),
        "Purchase Premium": args.purchase_premium,
        "Delta": str(args.delta),
        "Gamma": str(args.gamma),
        "Mark Price": args.purchase_premium,
        "Open Interest": args.open_interest,
        "ImpVol": str(args.imp_vol),
        "Asset Cost Basis": args.purchase_premium * 100,
        "Current Value": args.purchase_premium * 100,
        "P&L (%)": 0.0,
        "P&L ($)": 0.0,
        "Sizing Risk Weight (%)": 0.0,
        "Beta Sector Tag": args.sector,
        "Entry Date": datetime.today().strftime('%Y-%m-%d'),
        "Days Held": 1,
        "Stalling Days": 0,
        "Target Mode": "T1",
        "T2 Target": None
    }
    
    options["options_positions"] = positions
    save_json(OPTIONS_FILE, options)
    print(f"Successfully added options position for {args.underlier.upper()} in {OPTIONS_FILE}.")


def cmd_add_stock_pos(args):
    """Add new stock position manually."""
    options = load_json(OPTIONS_FILE, {"options_positions": {}, "stocks_positions": {}})
    stocks = options.setdefault("stocks_positions", {})
    ticker = args.ticker.upper()
    
    if ticker in stocks:
        print(f"Error: Stock Ticker {ticker} already exists in portfolio. Use update-stock to modify it.", file=sys.stderr)
        sys.exit(1)
        
    stocks[ticker] = {
        "Ticker": ticker,
        "Shares": args.shares,
        "Average Buy Price": args.average_buy_price,
        "Current Price": args.average_buy_price,
        "Beta Sector Tag": args.sector,
        "Entry Date": datetime.today().strftime('%Y-%m-%d'),
        "Asset Cost Basis": args.shares * args.average_buy_price,
        "Current Value": args.shares * args.average_buy_price,
        "P&L (%)": 0.0,
        "P&L ($)": 0.0,
        "Sizing Risk Weight (%)": 0.0
    }
    
    options["stocks_positions"] = stocks
    save_json(OPTIONS_FILE, options)
    print(f"Successfully added stock position for {ticker} in {OPTIONS_FILE}.")


def cmd_update_stock_pos(args):
    """Update stock position shares or price."""
    options = load_json(OPTIONS_FILE, {"options_positions": {}, "stocks_positions": {}})
    stocks = options.get("stocks_positions", {})
    ticker = args.ticker.upper()
    
    if ticker not in stocks:
        print(f"Error: Stock position for {ticker} not found in portfolio.", file=sys.stderr)
        sys.exit(1)
        
    target_stock = stocks[ticker]
    if args.price is not None:
        target_stock["Current Price"] = args.price
    if args.shares is not None:
        target_stock["Shares"] = args.shares
        target_stock["Asset Cost Basis"] = args.shares * target_stock.get("Average Buy Price", 0.0)
    if args.sector is not None:
        target_stock["Beta Sector Tag"] = args.sector
        
    # Save the updated stocks dict back using stocks_positions
    options["stocks_positions"] = stocks
    save_json(OPTIONS_FILE, options)
    print(f"Successfully updated metrics for stock {ticker} in {OPTIONS_FILE}.")


def cmd_close_stock_pos(args):
    """Close a stock position and archive standard P&L."""
    options = load_json(OPTIONS_FILE, {"options_positions": {}, "stocks_positions": {}})
    stocks = options.get("stocks_positions", {})
    ticker = args.ticker.upper()
    
    if ticker not in stocks:
        print(f"Error: Stock position for {ticker} not found in portfolio.", file=sys.stderr)
        sys.exit(1)
        
    closed = options.setdefault("closed_stocks", [])
    details = stocks.pop(ticker)
    
    shares = float(details.get("Shares", 0.0))
    avg_price = float(details.get("Average Buy Price", 0.0))
    close_price = args.close_price if args.close_price is not None else float(details.get("Current Price", avg_price))
    
    cost_basis = shares * avg_price
    current_val = shares * close_price
    realized_dollar = current_val - cost_basis
    realized_pct = (realized_dollar / cost_basis) * 100.0 if cost_basis > 0 else 0.0
    
    details["Close Price"] = close_price
    details["Close Date"] = datetime.today().strftime('%Y-%m-%d')
    details["Realized P&L ($)"] = round(realized_dollar, 2)
    details["Realized P&L (%)"] = round(realized_pct, 2)
    closed.append(details)
    
    pl_color = "32" if realized_dollar >= 0 else "31"
    print(f"Closed stock position for {ticker}: "
          + format_color(f"Realized P&L {realized_pct:+.2f}% (${realized_dollar:+.2f})", pl_color, bold=True))
          
    options["stocks_positions"] = stocks
    save_json(OPTIONS_FILE, options)
    print(f"Archived stock position for {ticker} to closed_stocks in {OPTIONS_FILE}.")


def cmd_update_opt(args):
    """Update options evaluation price/mark and momentum tracking."""
    options = load_json(OPTIONS_FILE, {"options_positions": {}})
    positions = options.get("options_positions", {})
    
    target_pos = None
    for opt_id, details in positions.items():
        if opt_id == args.option_id or details.get("Underlier") == args.option_id.upper():
            target_pos = details
            break
            
    if not target_pos:
        print(f"Error: Option position with ID or Ticker {args.option_id} not found in portfolio.", file=sys.stderr)
        sys.exit(1)
        
    if args.mark is not None:
        target_pos["Mark Price"] = args.mark
    if args.delta is not None:
        target_pos["Delta"] = str(args.delta)
    if args.gamma is not None:
        target_pos["Gamma"] = str(args.gamma)
    if args.oi is not None:
        target_pos["Open Interest"] = args.oi
    if args.iv is not None:
        target_pos["ImpVol"] = str(args.iv)
    if args.days is not None:
        target_pos["Days Held"] = args.days
    if args.stalling_days is not None:
        target_pos["Stalling Days"] = args.stalling_days
    if getattr(args, "target_mode", None) is not None:
        target_pos["Target Mode"] = args.target_mode
    if getattr(args, "t2_target", None) is not None:
        target_pos["T2 Target"] = args.t2_target
        
    save_json(OPTIONS_FILE, options)
    print(f"Successfully updated metrics for option {args.option_id} in {OPTIONS_FILE}.")


def cmd_close_pos(args):
    """Close a tracked options position and archive its realized P&L."""
    options = load_json(OPTIONS_FILE, {"options_positions": {}})
    positions = options.get("options_positions", {})
    
    matches = [
        opt_id for opt_id, details in positions.items()
        if opt_id == args.option_id or details.get("Underlier") == args.option_id.upper()
    ]
    if not matches:
        print(f"Error: Option position with ID or Ticker {args.option_id} not found in portfolio.", file=sys.stderr)
        sys.exit(1)
        
    closed = options.setdefault("closed_options", [])
    for opt_id in matches:
        details = positions.pop(opt_id)
        purchase_premium = float(details.get("Purchase Premium", 0.0))
        close_premium = args.close_premium if args.close_premium is not None else float(details.get("Mark Price", purchase_premium))
        realized_dollar = round((close_premium - purchase_premium) * 100, 2)
        realized_pct = round(((close_premium - purchase_premium) / purchase_premium) * 100, 2) if purchase_premium else 0.0
        
        details["Close Premium"] = close_premium
        details["Close Date"] = datetime.today().strftime('%Y-%m-%d')
        details["Realized P&L ($)"] = realized_dollar
        details["Realized P&L (%)"] = realized_pct
        closed.append(details)
        
        pl_color = "32" if realized_dollar >= 0 else "31"
        print(f"Closed {details.get('Underlier')} {details.get('Strike')} {details.get('Type')} ({opt_id}): "
              + format_color(f"Realized P&L {realized_pct:+.2f}% (${realized_dollar:+.2f})", pl_color, bold=True))
        
    options["options_positions"] = positions
    save_json(OPTIONS_FILE, options)
    print(f"Archived {len(matches)} position(s) to closed_options in {OPTIONS_FILE}.")


def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '_', text)
    return text.strip('_')


def persist_new_scans():
    """
    Scans the current directory and all subdirectories in data/downloads/
    for raw Robinhood scan downloads.
    When a valid scan is found, it copies/persists it to the local scans/ directory
    for offline analysis, using both a 'latest' filename and a timestamped file.
    If the source file was in the current workspace root (cwd), it is deleted to
    keep the root clean; otherwise (e.g. historical downloads under data/downloads),
    the original raw file is preserved.
    """
    cwd = "."
    os.makedirs(SCANS_DIR, exist_ok=True)
    os.makedirs(os.path.join(SCANS_DIR, "history"), exist_ok=True)
    persisted_files = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Gather search locations: list of (filepath, should_delete_after_copy)
    search_paths = []
    
    # 1) Search current directory
    for item in os.listdir(cwd):
        if item.endswith(".json") and item not in (REGIME_FILE, ANALYSES_FILE, OPTIONS_FILE, CANDIDATES_FILE):
            search_paths.append((os.path.join(cwd, item), True))
            
    # 2) Search data/downloads directory recursively
    downloads_dir = "data/downloads"
    if os.path.exists(downloads_dir):
        for root, dirs, files in os.walk(downloads_dir):
            for file in files:
                if file.endswith(".json"):
                    search_paths.append((os.path.join(root, file), False))

    # Deduplicate search paths by resolving real absolute paths
    unique_paths = {}
    for filepath, should_delete in search_paths:
        if os.path.isfile(filepath):
            abs_path = os.path.abspath(filepath)
            if abs_path not in unique_paths:
                unique_paths[abs_path] = (filepath, should_delete)

    for abs_path, (filepath, should_delete) in unique_paths.items():
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            
            # Verify if this is a Robinhood scan result structure
            scan_result = None
            if isinstance(data, dict):
                scan_result = data.get("data", {}).get("result", {})
                if not scan_result or not isinstance(scan_result, dict):
                    scan_result = data.get("result", {})
                if not scan_result or not isinstance(scan_result, dict):
                    scan_result = data
            
            if isinstance(scan_result, dict):
                scan_title = scan_result.get("scan_title")
                scan_id = scan_result.get("scan_id")
                
                if scan_title and scan_id:
                    slug_title = slugify(scan_title)
                    latest_filename = f"{slug_title}.json"
                    timestamped_filename = f"{slug_title}_{timestamp}.json"
                    
                    latest_path = os.path.join(SCANS_DIR, latest_filename)
                    timestamped_path = os.path.join(SCANS_DIR, "history", timestamped_filename)
                    
                    # Copy file to persist it locally
                    shutil.copy2(filepath, latest_path)
                    shutil.copy2(filepath, timestamped_path)
                    
                    print(f"Persisted scan '{scan_title}' locally:")
                    print(f"  -> {latest_path} (Latest)")
                    print(f"  -> {timestamped_path} (Timestamped)")
                    
                    if should_delete:
                        os.remove(filepath)
                        print(f"  Removed raw temporary file: {filepath}")
                    
                    persisted_files.append((scan_title, latest_path))
        except Exception:
            # Ignore non-matching or corrupted JSON files
            continue
            
    return persisted_files


def cmd_update_candidates(args):
    """Sources, persists, filters, and saves candidates from raw scan files."""
    # First persist any new scan downloads
    persist_new_scans()
    
    # Load active positions to exclude (both options and stocks)
    options = load_json(OPTIONS_FILE, {"options_positions": {}, "stocks_positions": {}})
    positions = options.get("options_positions", {})
    stocks = options.get("stocks_positions", {})
    
    active_positions_set = set()
    if positions:
        for details in positions.values():
            underlier = details.get("Underlier")
            if underlier:
                active_positions_set.add(underlier.upper())
    if stocks:
        for ticker in stocks.keys():
            active_positions_set.add(ticker.upper())
            
    active_positions = sorted(list(active_positions_set))
    if active_positions:
        print(f"Loaded active positions to exclude: {active_positions}")
        
    candidates = {}
    
    min_price = getattr(args, "min_price", MIN_PRICE)
    max_price = getattr(args, "max_price", MAX_PRICE)
    min_volume = getattr(args, "min_volume", MIN_VOLUME)
    min_change = getattr(args, "min_change", MIN_CHG_PCT)
    min_market_cap = getattr(args, "min_market_cap", MIN_MARKET_CAP)
    
    def process_scan_file(filepath, source_name):
        if not os.path.exists(filepath):
            print(f"Offline file not found for {source_name}: {filepath}")
            return
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading offline file {filepath}: {e}", file=sys.stderr)
            return

        results = data.get("data", {}).get("result", {}).get("results", [])
        print(f"Read {len(results)} items from offline scan '{source_name}' ({filepath})")
        
        for item in results:
            ticker = item.get("ticker", "").upper()
            if not ticker or ticker in active_positions:
                continue
            columns = item.get("columns", {})
            
            try:
                price = float(columns.get("Last", 0))
                volume = float(columns.get("Volume", 0))
                chg_pct = float(columns.get("% Change", 0)) * 100.0
                market_cap = float(columns.get("Market cap", 0)) if columns.get("Market cap") else 0.0
            except Exception:
                continue
                
            # Apply filters
            if not (min_price <= price <= max_price):
                continue
            if volume < min_volume:
                continue
            if chg_pct < min_change:
                continue
            if market_cap < min_market_cap:
                continue
                
            iv = None
            if "Implied volatility" in columns and columns["Implied volatility"] is not None:
                try:
                    iv = float(columns["Implied volatility"])
                except ValueError:
                    pass
                    
            rel_opt_vol = None
            if "Relative options volume" in columns and columns["Relative options volume"] is not None:
                try:
                    rel_opt_vol = float(columns["Relative options volume"])
                except ValueError:
                    pass

            # Deduplicate or merge
            if ticker in candidates:
                if iv is not None:
                    candidates[ticker]["iv"] = iv
                if rel_opt_vol is not None:
                    candidates[ticker]["relative_options_volume"] = rel_opt_vol
            else:
                candidates[ticker] = {
                    "symbol": ticker,
                    "source": "scanner",
                    "price": round(price, 2),
                    "chg_pct": round(chg_pct, 4),
                    "iv": iv,
                    "relative_options_volume": rel_opt_vol,
                    "market_cap": market_cap
                }

    # Automatically discover and process all offline scans under SCANS_DIR
    scans_processed = []
    if os.path.exists(SCANS_DIR):
        for item in sorted(os.listdir(SCANS_DIR)):
            if item.endswith(".json"):
                full_path = os.path.join(SCANS_DIR, item)
                if os.path.isfile(full_path):
                    try:
                        with open(full_path, 'r') as f:
                            sdata = json.load(f)
                        scan_result = sdata.get("data", {}).get("result", {})
                        if not scan_result or not isinstance(scan_result, dict):
                            scan_result = sdata.get("result", {})
                        if not scan_result or not isinstance(scan_result, dict):
                            scan_result = sdata
                        if isinstance(scan_result, dict) and scan_result.get("scan_title"):
                            title = scan_result.get("scan_title")
                            process_scan_file(full_path, title)
                            scans_processed.append(title)
                    except Exception:
                        continue

    # Fallback to defaults if no dynamic scans were processed
    if not scans_processed:
        process_scan_file(os.path.join(SCANS_DIR, "gex_momentum_candidates.json"), "GEX Momentum Candidates")
        process_scan_file(os.path.join(SCANS_DIR, "high_options_volume_and_iv.json"), "High options volume and IV")
        scans_processed = ["GEX Momentum Candidates", "High options volume and IV"]
    
    candidate_list = list(candidates.values())
    # Sort candidates by relative options volume if available, or day change % descending
    candidate_list.sort(key=lambda x: (x["relative_options_volume"] if x["relative_options_volume"] is not None else -1, x["chg_pct"]), reverse=True)
    
    utc_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    output_data = {
        "last_updated": utc_time,
        "source_scans": sorted(list(set(scans_processed))),
        "user_additions": [],
        "excluded_active_positions": active_positions,
        "total": len(candidate_list),
        "candidates": candidate_list
    }
    
    save_json(CANDIDATES_FILE, output_data)
    
    print(f"Wrote {len(candidate_list)} candidates to {CANDIDATES_FILE}")
    for c in candidate_list[:10]:
        print(f"  - {c['symbol']}: price=${c['price']}, change={c['chg_pct']:.2f}%, iv={c['iv']}, rel_opt_vol={c['relative_options_volume']}")


def cmd_update_sentiment(args):
    """Registers or updates Reddit sentiment details for a ticker."""
    sentiment_db = load_json(SENTIMENT_FILE, {})
    ticker = args.ticker.upper()
    
    buzz = args.buzz
    if buzz == "Med":
        buzz = "Medium"
        
    utc_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    sentiment_obj = OptionSentiment(
        ticker=ticker,
        sentiment=args.score,
        buzz=buzz,
        narrative=args.narrative,
        last_updated=utc_time
    )
    
    try:
        sentiment_obj.validate()
    except ValueError as e:
        print(f"Error validating sentiment data: {e}", file=sys.stderr)
        sys.exit(1)
        
    sentiment_db[ticker] = {
        "Ticker": sentiment_obj.ticker,
        "Sentiment": sentiment_obj.sentiment,
        "Buzz": sentiment_obj.buzz,
        "Narrative": sentiment_obj.narrative,
        "last_updated": sentiment_obj.last_updated
    }
    
    save_json(SENTIMENT_FILE, sentiment_db)
    print(f"Successfully saved Reddit sentiment for {format_color(ticker, '35', bold=True)}.")


def cmd_sentiment(args):
    """Displays Reddit sentiment analysis dashboard and divergence alerts."""
    sentiment_db = load_json(SENTIMENT_FILE, {})
    analyses = load_json(ANALYSES_FILE, {})
    options = load_json(OPTIONS_FILE, {"options_positions": {}, "stocks_positions": {}})
    candidates_data = load_json(CANDIDATES_FILE, {"candidates": []})
    
    positions = options.get("options_positions", {})
    stocks = options.get("stocks_positions", {})
    candidates_list = candidates_data.get("candidates", [])
    
    cand_symbols = {c.get("symbol").upper() for c in candidates_list if c.get("symbol")}
    opt_symbols = {details.get("Underlier").upper() for details in positions.values() if details.get("Underlier")}
    stk_symbols = {t.upper() for t in stocks.keys()}
    
    if not sentiment_db:
        print("### 🧠 Reddit Social Sentiment & GEX Divergence Dashboard")
        print("No Reddit sentiment records found in database. Update sentiment using update-sentiment command.")
        return
        
    total_candidates = sum(1 for sym in sentiment_db if sym in cand_symbols)
    total_active = sum(1 for sym in sentiment_db if sym in opt_symbols or sym in stk_symbols)
    
    print("## Reddit Sentiment Analysis Report")
    print("\n### Executive Summary:")
    print(f"- **Scanned Assets**: {total_candidates} candidates, {total_active} active positions")
    
    # Calculate highest and lowest buzz
    sorted_sentiment = sorted(sentiment_db.values(), key=lambda x: x.get("Sentiment", 0.0))
    if sorted_sentiment:
        lowest = sorted_sentiment[0]
        highest = sorted_sentiment[-1]
        
        high_ticker = highest.get("Ticker")
        high_score = highest.get("Sentiment", 0.0)
        high_score_colored = format_color(f"{high_score:+.2f}", "32" if high_score >= 0 else "31", bold=True)
        print(f"- **Highest Retail Buzz**: {format_color(high_ticker, '35', bold=True)} (Sentiment: {high_score_colored})")

        low_ticker = lowest.get("Ticker")
        low_score = lowest.get("Sentiment", 0.0)
        low_score_colored = format_color(f"{low_score:+.2f}", "32" if low_score >= 0 else "31", bold=True)
        print(f"- **Lowest Retail Buzz / Capitulation**: {format_color(low_ticker, '35', bold=True)} (Sentiment: {low_score_colored})")
        
    print("\n### Detailed Sentiment Dashboard:")
    print("| Ticker | Asset Type | Reddit Buzz | Sentiment (-1 to +1) | Retail Narrative & Catalysts | GEX Alignment / Threat Level | Action Recommendation |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    
    fomo_alerts = []
    cap_alerts = []
    apathy_alerts = []
    
    for ticker, data in sorted(sentiment_db.items()):
        ticker_upper = ticker.upper()
        sentiment = float(data.get("Sentiment", 0.0))
        buzz = data.get("Buzz", "None")
        narrative = data.get("Narrative", "")
        
        # Determine Asset Type
        if ticker_upper in opt_symbols:
            asset_type = "Active Option"
        elif ticker_upper in stk_symbols:
            asset_type = "Active Stock"
        elif ticker_upper in cand_symbols:
            asset_type = "Candidate"
        else:
            asset_type = "Custom"
            
        # Retrieve GEX metrics from analyses and active positions
        levels = analyses.get(ticker_upper, {})
        ptrans = levels.get("pTrans")
        ntrans = levels.get("nTrans")
        gex_t1 = levels.get("+GEX")
        cotmp = levels.get("COTMP")
        
        spot = levels.get("Spot")
        if spot is None:
            if ticker_upper in stocks:
                spot = stocks[ticker_upper].get("Current Price") or stocks[ticker_upper].get("Spot")
            elif ticker_upper in positions:
                # Find the option slot
                for opt_details in positions.values():
                    if opt_details.get("Underlier") == ticker_upper:
                        spot = opt_details.get("Underlier Spot") or opt_details.get("Spot")
                        break
                        
        if spot is None:
            for c in candidates_list:
                if c.get("symbol") == ticker_upper:
                    spot = c.get("price")
                    break
                    
        # Check alignment / threat levels
        threat_level = "NEUTRAL / BALANCED"
        recommendation = "Hold according to core GEX mechanical trail"
        
        if spot is not None:
            spot_val = float(spot)
            ptrans_val = float(ptrans) if ptrans is not None else None
            ntrans_val = float(ntrans) if ntrans is not None else None
            gex_t1_val = float(gex_t1) if gex_t1 is not None else None
            cotmp_val = float(cotmp) if cotmp is not None else None
            
            # Helper for pTrans alignment
            pt_align = ""
            if ptrans_val is not None:
                pt_align = f" | pTrans: {'Spot >' if spot_val >= ptrans_val else 'Spot <'} ${ptrans_val:.2f}"
            
            # Helper for GEX/Wall
            wall_str = f" | Wall (+GEX): ${gex_t1_val:.2f}" if gex_t1_val is not None else ""
            
            # 1. FOMO Alert: Bullish sentiment and spot near/above Call Wall
            if sentiment >= 0.7 and gex_t1_val is not None and spot_val >= gex_t1_val * 0.98:
                threat_level = format_color(f"⚠️ FOMO ALERT (Spot: ${spot_val:.2f} vs Wall: ${gex_t1_val:.2f}{pt_align})", "31", bold=True)
                recommendation = "Chasing at +GEX. Avoid straight calls; Trim or write credits."
                fomo_alerts.append((ticker_upper, spot_val, gex_t1_val, sentiment))
            # 2. Capitulation watch: Bearish sentiment and spot testing support floor
            elif sentiment <= -0.7:
                support_floor = ntrans_val if ntrans_val is not None else cotmp_val
                    
                if support_floor is not None and spot_val <= support_floor * 1.03:
                    threat_level = format_color(f"📉 CAPITULATION WATCH (Spot: ${spot_val:.2f} vs Floor: ${support_floor:.2f}{pt_align})", "33", bold=True)
                    recommendation = "Value testing GEX floor. Monitor for reversal signs."
                    cap_alerts.append((ticker_upper, spot_val, support_floor, sentiment))
            # 3. Volumetric Apathy: Active positions with muted buzz/neutral sentiment
            elif asset_type in ("Active Option", "Active Stock") and (abs(sentiment) <= 0.3 or buzz in ("Low", "None")):
                threat_level = format_color(f"💤 VOLUMETRIC APATHY (Spot: ${spot_val:.2f}{wall_str}{pt_align})", "34")
                recommendation = "Muted sentiment. Hand off to mechanical trail/stops."
                apathy_alerts.append((ticker_upper, sentiment, buzz))
            # 4. Aligned setups for candidates
            elif asset_type == "Candidate" and sentiment >= 0.4:
                headroom_str = ""
                if gex_t1_val is not None:
                    if gex_t1_val > spot_val:
                        headroom = ((gex_t1_val - spot_val) / spot_val) * 100
                        headroom_str = f" - {headroom:.1f}% to +GEX (${gex_t1_val:.2f})"
                    else:
                        headroom_str = f" - At/Above +GEX (${gex_t1_val:.2f})"
                threat_level = format_color(f"👍 BULLISH ALIGNED (Spot: ${spot_val:.2f}{pt_align}{headroom_str})", "32")
                recommendation = "Isolate options; setup has structural headroom to run."
            else:
                support_floor = ntrans_val if ntrans_val is not None else cotmp_val
                
                levels_info = f"Spot: ${spot_val:.2f}{pt_align}"
                if support_floor is not None and gex_t1_val is not None:
                    threat_level = f"NEUTRAL / BALANCED ({levels_info} | Range: ${support_floor:.2f} - ${gex_t1_val:.2f})"
                elif gex_t1_val is not None:
                    threat_level = f"NEUTRAL / BALANCED ({levels_info} | Wall: ${gex_t1_val:.2f})"
                elif support_floor is not None:
                    threat_level = f"NEUTRAL / BALANCED ({levels_info} | Floor: ${support_floor:.2f})"
                else:
                    threat_level = f"NEUTRAL / BALANCED ({levels_info})"
        else:
            if sentiment >= 0.7:
                threat_level = "HIGH RETAIL BUZZ"
                recommendation = "Monitor spot relation to GEX call wall before entering"
            elif sentiment <= -0.7:
                threat_level = "EXTREME PANIC / APATHY"
                recommendation = "Check for capitulation setup near GEX support"
                
        sent_color = "32" if sentiment >= 0.4 else "31" if sentiment <= -0.4 else "37"
        sentiment_fmt = format_color(f"{sentiment:+.2f}", sent_color, bold=True)
        
        # Print table row
        print(f"| {format_color(ticker_upper, '35', bold=True)} | {asset_type} | {buzz} | {sentiment_fmt} | {narrative} | {threat_level} | {recommendation} |")
        
    # Key Social Hype & Divergence Alerts print out
    print("\n### Key Social Hype & Divergence Alerts:")
    idx = 1
    for ticker_upper, spot_val, gex_val, sentiment in fomo_alerts:
        print(f"{idx}. {format_color('⚠️ FOMO ALERT: ' + ticker_upper, '31', bold=True)}: Retail sentiment is extremely exuberant ({sentiment:+.2f}) on {ticker_upper}, but current price (${spot_val:.2f}) sits directly at or above the call wall of ${gex_val:.2f} found in {ANALYSES_FILE}. Chasing calls at this level carries a high risk of decay or reversal.")
        idx += 1
    for ticker_upper, spot_val, floor_val, sentiment in cap_alerts:
        print(f"{idx}. {format_color('📉 CAPITULATION WATCH: ' + ticker_upper, '33', bold=True)}: Retail sentiment is deeply bearish ({sentiment:+.2f}) on {ticker_upper}, but the price (${spot_val:.2f}) is testing its GEX floor/support level (${floor_val:.2f}). Monitor for momentum reversal patterns for a contrarian recovery.")
        idx += 1
    for ticker_upper, sentiment, buzz in apathy_alerts:
        print(f"{idx}. {format_color('💤 VOLUMETRIC APATHY: ' + ticker_upper, '34', bold=True)}: Active position {ticker_upper} is currently showing minimal social activity (Sentiment: {sentiment:+.2f}, Buzz: {buzz}). This matches the stalling or structural stops tracked in GEX local portfolio mechanics.")
        idx += 1
    if idx == 1:
        print("No high-risk sentiment divergence flags found today. Setup alignments remain within standard execution parameters.")
        
    print("\n### Actionable Strategic Adjustments:")
    print("- **Candidate Setup Refinement**: Prioritize setup evaluations for candidates with high organic retail buzz (aligned with GEX headroom runway) to ensure sustained breakouts.")
    print("- **Active Position Protection**: Be disciplined on exiting BABA or dry options exhibiting volumetric apathy, as institutional rotations support the systematic stops.")


def main():
    parser = argparse.ArgumentParser(
        description="GEX Options Mechanical Engine - Rule validation CLI and storage keeper"
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # status subcommand
    subparsers.add_parser("status", help="Analyze broader Daily Regime Gates and authorization.")
    
    # update-regime subcommand
    p_regime = subparsers.add_parser("update-regime", help="Recompute Daily Regime Gates from raw market inputs.")
    p_regime.add_argument("--spy", type=float, help="SPY session change percent (e.g. 0.62)")
    p_regime.add_argument("--qqq", type=float, help="QQQ session change percent (e.g. 1.10)")
    p_regime.add_argument("--bulls", type=int, help="Count of bullish (green) symbols in the sector ETF list")
    p_regime.add_argument("--bears", type=int, help="Count of bearish (red) symbols in the sector ETF list")
    p_regime.add_argument("--vix-bearish", type=str2bool, dest="vix_bearish", help="Dealer VIX positioning is bearish/short vol (True/False)")
    p_regime.add_argument("--vix-spot", type=float, dest="vix_spot", help="Current VIX spot level")
    p_regime.add_argument("--hyg", type=float, help="HYG credit high-yield bond daily change percent (e.g. -0.35)")
    p_regime.add_argument("--etf-file", type=str, help="ETF Quotes JSON file to calculate regime gates automatically")

    # analyze subcommand
    p_analyze = subparsers.add_parser("analyze", help="Grades dynamic options candidate setups.")
    p_analyze.add_argument("symbol", type=str, help="Ticker symbol (e.g. AAPL, AMD)")
    p_analyze.add_argument("--spot", type=float, help="Current spot price")
    p_analyze.add_argument("--ptrans", type=float, help="Positive transition level")
    p_analyze.add_argument("--ntrans", type=float, help="Negative transition level")
    p_analyze.add_argument("--gex", type=float, help="Target positive GEX target level (+GEX / T1)")
    p_analyze.add_argument("--cotmp", type=float, help="Center of Put Mass strike price")
    p_analyze.add_argument("--db-change", type=float, dest="db_change", help="Delta Balance Session change")
    p_analyze.add_argument("--spike-crash", action="store_true", dest="spike_crash", help="Trigger Spike-Crash check warning.")
    p_analyze.add_argument("--inst-file", type=str, help="Option instruments JSON file for derivation")
    p_analyze.add_argument("--quote-file", type=str, help="Option quotes JSON file for derivation")
    p_analyze.add_argument("--hist-file", type=str, help="Underlier historical daily closes JSON file for volatility derivation")
    p_analyze.add_argument("--net-liq", type=float, dest="net_liq", help="Estimated Portfolio Net Liq value for sizing checks")
    p_analyze.add_argument("--target-delta", type=float, dest="target_delta", default=0.45, help="Option selection target delta (default: 0.45)")
    p_analyze.add_argument("--min-dte", type=int, dest="min_dte", default=30, help="Option selection minimum DTE (default: 30)")
    p_analyze.add_argument("--max-dte", type=int, dest="max_dte", default=45, help="Option selection maximum DTE (default: 45)")
    
    # Grade Checklist overrides if needed
    p_analyze.add_argument("--rule1", type=str2bool, help="Overriding total call GEX is positive (True/False)")
    p_analyze.add_argument("--rule2", type=str2bool, help="Overriding call GEX exceeds PUT GEX (True/False)")
    p_analyze.add_argument("--rule7", type=str2bool, help="Overriding Total OI > 10,000 contracts (True/False)")
    p_analyze.add_argument("--rule8", type=str2bool, help="Overriding IV < HV (True/False)")
    p_analyze.add_argument("--rule9", type=str2bool, help="Overriding OI Target strike is largest (True/False)")
    p_analyze.add_argument("--rule10", type=str2bool, help="Overriding Dealer Spot net gamma positive (True/False)")
    p_analyze.add_argument("--rule11", type=str2bool, help="Overriding Underlier RV_10 <= 35%% (True/False)")
    
    # portfolio subcommand
    p_port = subparsers.add_parser("portfolio", help="Analyzes position exits, trailing stops, and sizing limits.")
    p_port.add_argument("--net-liq", type=float, dest="net_liq", help="Estimated Portfolio Net Liq value for sizing checks")
    p_port.add_argument("--spot-overrides", type=str, dest="spot_overrides", help="Comma-separated ticker=price overrides, e.g. AAPL=290,BABA=81")
    
    # add-position subcommand
    p_add_pos = subparsers.add_parser("add-position", help="Register a option contract in tracking sheet.")
    p_add_pos.add_argument("option_id", type=str, help="Option contract ID")
    p_add_pos.add_argument("underlier", type=str, help="Stock ticker symbol")
    p_add_pos.add_argument("strike", type=float, help="Strike price of option")
    p_add_pos.add_argument("expiration", type=str, help="Expiration date (YYYY-MM-DD)")
    p_add_pos.add_argument("type", type=str, choices=["call", "put"], help="Option contract call/put type")
    p_add_pos.add_argument("purchase_premium", type=float, help="Initial premium paid for contract")
    p_add_pos.add_argument("--delta", type=float, default=0.5, help="Delta (e.g. 0.52)")
    p_add_pos.add_argument("--gamma", type=float, default=0.01, help="Gamma (e.g. 0.02)")
    p_add_pos.add_argument("--open-interest", type=int, default=1000, help="Total open interest")
    p_add_pos.add_argument("--imp-vol", type=float, default=0.35, help="Implied volatility (e.g. 0.42)")
    p_add_pos.add_argument("--sector", type=str, default="Technology/Beta", help="Target sector classification (e.g. Technology/Beta, Consumer Cyclical)")
    
    # update-option subcommand
    p_up_opt = subparsers.add_parser("update-option", help="Updates pricing metrics or momentum trackers for options tracking")
    p_up_opt.add_argument("option_id", type=str, help="Option ID or Ticker underlier name")
    p_up_opt.add_argument("--mark", type=float, help="New current Mark Price")
    p_up_opt.add_argument("--delta", type=float, help="New option Delta")
    p_up_opt.add_argument("--gamma", type=float, help="New option Gamma")
    p_up_opt.add_argument("--oi", type=int, help="New option Open Interest")
    p_up_opt.add_argument("--iv", type=float, help="New option Implied Vol")
    p_up_opt.add_argument("--days", type=int, help="Override Days Held")
    p_up_opt.add_argument("--stalling-days", type=int, help="Set stalling counter")
    p_up_opt.add_argument("--target-mode", type=str, choices=["T1", "T2"], help="Set target mode for trailing rules (T1, T2)")
    p_up_opt.add_argument("--t2-target", type=float, help="Set secondary structural T2 target price")
    
    # close-position subcommand
    p_close_pos = subparsers.add_parser("close-position", help="Close a tracked option position and archive realized P&L.")
    p_close_pos.add_argument("option_id", type=str, help="Option ID or Ticker underlier name")
    p_close_pos.add_argument("--close-premium", type=float, dest="close_premium", help="Exit premium received (defaults to last Mark Price)")
    
    # add-stock subcommand
    p_add_stock = subparsers.add_parser("add-stock", help="Register a stock position in tracking sheet.")
    p_add_stock.add_argument("ticker", type=str, help="Stock ticker symbol")
    p_add_stock.add_argument("shares", type=float, help="Number of shares purchased")
    p_add_stock.add_argument("average_buy_price", type=float, help="Average cost paid per share")
    p_add_stock.add_argument("--sector", type=str, default="Equity", help="Target sector tag (default: Equity)")

    # update-stock subcommand
    p_up_stock = subparsers.add_parser("update-stock", help="Update stock tracking metrics.")
    p_up_stock.add_argument("ticker", type=str, help="Stock ticker symbol")
    p_up_stock.add_argument("--price", type=float, help="New current stock price")
    p_up_stock.add_argument("--shares", type=float, help="New stock shares count")
    p_up_stock.add_argument("--sector", type=str, help="New stock sector tag")

    # close-stock subcommand
    p_close_stock = subparsers.add_parser("close-stock", help="Close a tracked stock position and archive standard P&L.")
    p_close_stock.add_argument("ticker", type=str, help="Stock ticker symbol")
    p_close_stock.add_argument("--close-price", type=float, dest="close_price", help="Exit price received per share (defaults to last current price)")

    # update-candidates subcommand
    p_candidates = subparsers.add_parser("update-candidates", help="Persist downloaded scans and update candidate_stocks.json.")
    p_candidates.add_argument("--min-price", type=float, dest="min_price", default=MIN_PRICE, help=f"Minimum stock price (default: {MIN_PRICE})")
    p_candidates.add_argument("--max-price", type=float, dest="max_price", default=MAX_PRICE, help=f"Maximum stock price (default: {MAX_PRICE})")
    p_candidates.add_argument("--min-volume", type=float, dest="min_volume", default=MIN_VOLUME, help=f"Minimum average trading volume (default: {MIN_VOLUME})")
    p_candidates.add_argument("--min-change", type=float, dest="min_change", default=MIN_CHG_PCT, help=f"Minimum stock price day change percent (default: {MIN_CHG_PCT})")
    p_candidates.add_argument("--min-market-cap", type=float, dest="min_market_cap", default=MIN_MARKET_CAP, help=f"Minimum market capitalization (default: {MIN_MARKET_CAP})")
    
    # sentiment subcommand
    subparsers.add_parser("sentiment", help="Display Reddit sentiment analysis dashboard and divergence alerts.")

    # update-sentiment subcommand
    p_up_sent = subparsers.add_parser("update-sentiment", help="Register/update Reddit sentiment data for a ticker.")
    p_up_sent.add_argument("ticker", type=str, help="Ticker symbol (e.g. BABA)")
    p_up_sent.add_argument("--score", type=float, required=True, help="Sentiment score from -1.0 (capitulation) to +1.0 (FOMO)")
    p_up_sent.add_argument("--buzz", type=str, choices=["High", "Medium", "Low", "None", "Med"], required=True, help="Discussion volume / buzz")
    p_up_sent.add_argument("--narrative", type=str, required=True, help="Core narrative thesis / catalysts")

    args = parser.parse_args()
    
    # Process spot overrides if they are provided
    spot_overrides_dict = {}
    if hasattr(args, "spot_overrides") and args.spot_overrides is not None:
        try:
            pairs = args.spot_overrides.split(",")
            for pair in pairs:
                k, v = pair.split("=")
                spot_overrides_dict[k.strip().upper()] = float(v)
        except Exception as e:
            print(f"Warning: Failed to parse spot overrides: {e}", file=sys.stderr)
    args.spot_overrides = spot_overrides_dict
    
    if args.command == "status":
        cmd_status(args)
    elif args.command == "update-regime":
        cmd_update_regime(args)
    elif args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "portfolio":
        cmd_portfolio(args)
    elif args.command == "add-position":
        cmd_add_pos(args)
    elif args.command == "update-option":
        cmd_update_opt(args)
    elif args.command == "close-position":
        cmd_close_pos(args)
    elif args.command == "add-stock":
        cmd_add_stock_pos(args)
    elif args.command == "update-stock":
        cmd_update_stock_pos(args)
    elif args.command == "close-stock":
        cmd_close_stock_pos(args)
    elif args.command == "update-candidates":
        cmd_update_candidates(args)
    elif args.command == "sentiment":
        cmd_sentiment(args)
    elif args.command == "update-sentiment":
        cmd_update_sentiment(args)


if __name__ == "__main__":
    main()
