"""
Intraday GEX level breach monitor and real-time alert engine.
Monitors active option and stock holdings across accounts against structural GEX thresholds
(nTrans stop breach, +GEX profit target touch, trailing giveback, and catastrophic stops),
dispatching deduplicated alerts via webhooks and desktop notifications.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import os
import re
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from src.gex.core.config import (
    ANALYSES_FILE,
    DATA_DIR,
    OPTIONS_FILE,
    mask_account,
    sanitize_account,
)


@dataclass(slots=True)
class PositionBreachAlert:
    """Represents a structural level breach or profit target trigger for an active holding."""
    symbol: str
    position_id: str
    position_type: str  # "option" or "stock"
    breach_type: str  # "STOP1_NTRANS", "PROFIT_TARGET_GEX", "T2_TARGET", "STOP2_MAX_ASSET", "STOP5_CATASTROPHIC"
    spot: float
    threshold: float
    message: str
    action: str
    account: str = ""
    masked_account: str = ""
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert breach alert to a serializable dictionary."""
        return asdict(self)


def evaluate_holding_breaches(
    positions_data: Dict[str, Any],
    analyses_data: Dict[str, Any],
    spot_fetcher: Callable[[str], Optional[float]],
    account: str = "",
) -> List[PositionBreachAlert]:
    """
    Evaluates active holdings within positions_data against structural GEX levels in analyses_data.
    
    Args:
        positions_data: Dict containing 'options_positions' and 'stocks_positions'.
        analyses_data: Dict mapping ticker symbols to GEX profile/analysis levels.
        spot_fetcher: Callable that returns the latest spot price for a given ticker symbol.
        account: Account identifier string.

    Returns:
        List of PositionBreachAlert objects representing triggered levels.
    """
    alerts: List[PositionBreachAlert] = []
    masked = mask_account(account) if account else ""
    ts = datetime.now(timezone.utc).isoformat()

    # 1. Evaluate Options Positions
    options = positions_data.get("options_positions", {})
    if isinstance(options, dict):
        for opt_id, details in options.items():
            if not isinstance(details, dict):
                continue
            underlier = str(details.get("Underlier") or details.get("symbol") or "").upper()
            if not underlier:
                continue

            spot = spot_fetcher(underlier)
            if spot is None or spot <= 0.0:
                # Fallback to mark/strike price heuristic if underlier spot unavailable
                continue

            levels = analyses_data.get(underlier, {})
            ntrans = levels.get("nTrans")
            ptrans = levels.get("pTrans")
            gex_t1 = levels.get("+GEX")
            t2_target = levels.get("t2_target")

            purchase_premium = float(details.get("Purchase Premium") or details.get("average_buy_price") or 0.0)
            mark_price = float(details.get("Mark Price") or details.get("current_price") or purchase_premium)
            target_mode = str(details.get("Target Mode") or "T1").upper()

            pl_pct = ((mark_price - purchase_premium) / purchase_premium) * 100.0 if purchase_premium > 0 else 0.0

            # Stop 1 (Structural Stop): Spot < nTrans
            stop1_triggered = False
            if ntrans is not None and spot < float(ntrans):
                stop1_triggered = True
                alerts.append(
                    PositionBreachAlert(
                        symbol=underlier,
                        position_id=str(opt_id),
                        position_type="option",
                        breach_type="STOP1_NTRANS",
                        spot=spot,
                        threshold=float(ntrans),
                        message=f"Spot ${spot:.2f} breached below structural support nTrans ${float(ntrans):.2f}",
                        action="Immediate Exit (Stop 1 Structural Breach)",
                        account=account,
                        masked_account=masked,
                        timestamp=ts,
                    )
                )

            # Profit Target (+GEX / T1 Target): Spot >= +GEX
            if gex_t1 is not None and float(gex_t1) > 0 and spot >= float(gex_t1):
                alerts.append(
                    PositionBreachAlert(
                        symbol=underlier,
                        position_id=str(opt_id),
                        position_type="option",
                        breach_type="PROFIT_TARGET_GEX",
                        spot=spot,
                        threshold=float(gex_t1),
                        message=f"Spot ${spot:.2f} reached +GEX profit target ${float(gex_t1):.2f}",
                        action="Lock in T1 Profit / Evaluate Partial Close",
                        account=account,
                        masked_account=masked,
                        timestamp=ts,
                    )
                )

            # T2 Target: Spot >= T2 Target (when position is managed under T2 target mode)
            if target_mode == "T2":
                t2_val = float(t2_target) if t2_target is not None else (float(gex_t1) * 1.10 if gex_t1 else None)
                if t2_val is not None and spot >= t2_val:
                    alerts.append(
                        PositionBreachAlert(
                            symbol=underlier,
                            position_id=str(opt_id),
                            position_type="option",
                            breach_type="T2_TARGET",
                            spot=spot,
                            threshold=t2_val,
                            message=f"Spot ${spot:.2f} met T2 profit target ${t2_val:.2f}",
                            action="Lock in Full T2 Gains / Exit Position",
                            account=account,
                            masked_account=masked,
                            timestamp=ts,
                        )
                    )

            # Stop 2 (Max Asset Stop below pTrans): Spot < pTrans with option loss <= -10% (secondary to Stop 1)
            if not stop1_triggered and ptrans is not None and spot < float(ptrans) and pl_pct <= -10.0:
                alerts.append(
                    PositionBreachAlert(
                        symbol=underlier,
                        position_id=str(opt_id),
                        position_type="option",
                        breach_type="STOP2_MAX_ASSET",
                        spot=spot,
                        threshold=float(ptrans),
                        message=f"Spot ${spot:.2f} below pTrans ${float(ptrans):.2f} with option loss {pl_pct:+.1f}% <= -10.0%",
                        action="Immediate Exit (Stop 2 Max Asset Stop)",
                        account=account,
                        masked_account=masked,
                        timestamp=ts,
                    )
                )

            # Stop 5 (Catastrophic Risk Stop): Hard loss <= -50%
            if pl_pct <= -50.0:
                alerts.append(
                    PositionBreachAlert(
                        symbol=underlier,
                        position_id=str(opt_id),
                        position_type="option",
                        breach_type="STOP5_CATASTROPHIC",
                        spot=spot,
                        threshold=-50.0,
                        message=f"Option position value loss {pl_pct:+.1f}% breached catastrophic -50% threshold",
                        action="Immediate Exit (Stop 5 Catastrophic Loss)",
                        account=account,
                        masked_account=masked,
                        timestamp=ts,
                    )
                )

    # 2. Evaluate Stocks Positions
    stocks = positions_data.get("stocks_positions", {})
    if isinstance(stocks, dict):
        for ticker, details in stocks.items():
            if not isinstance(details, dict):
                continue
            symbol = str(ticker).upper()
            spot = spot_fetcher(symbol)
            if spot is None or spot <= 0.0:
                continue

            levels = analyses_data.get(symbol, {})
            ntrans = levels.get("nTrans")
            gex_t1 = levels.get("+GEX")

            avg_px = float(details.get("Average Buy Price") or details.get("average_buy_price") or 0.0)
            pl_pct = ((spot - avg_px) / avg_px) * 100.0 if avg_px > 0 else 0.0

            # Stop 1 (Structural Stop): Spot < nTrans
            if ntrans is not None and spot < float(ntrans):
                alerts.append(
                    PositionBreachAlert(
                        symbol=symbol,
                        position_id=symbol,
                        position_type="stock",
                        breach_type="STOP1_NTRANS",
                        spot=spot,
                        threshold=float(ntrans),
                        message=f"Stock spot ${spot:.2f} breached below structural support nTrans ${float(ntrans):.2f}",
                        action="Immediate Exit (Stop 1 Structural Breach)",
                        account=account,
                        masked_account=masked,
                        timestamp=ts,
                    )
                )

            # Profit Target (+GEX): Spot >= +GEX
            if gex_t1 is not None and float(gex_t1) > 0 and spot >= float(gex_t1):
                alerts.append(
                    PositionBreachAlert(
                        symbol=symbol,
                        position_id=symbol,
                        position_type="stock",
                        breach_type="PROFIT_TARGET_GEX",
                        spot=spot,
                        threshold=float(gex_t1),
                        message=f"Stock spot ${spot:.2f} reached +GEX profit target ${float(gex_t1):.2f}",
                        action="Lock in Stock Target / Scale Out",
                        account=account,
                        masked_account=masked,
                        timestamp=ts,
                    )
                )

            # Stop 5 (Catastrophic Stop): Stock loss <= -50%
            if pl_pct <= -50.0:
                alerts.append(
                    PositionBreachAlert(
                        symbol=symbol,
                        position_id=symbol,
                        position_type="stock",
                        breach_type="STOP5_CATASTROPHIC",
                        spot=spot,
                        threshold=-50.0,
                        message=f"Stock unrealized loss {pl_pct:+.1f}% breached catastrophic -50% threshold",
                        action="Immediate Exit (Stop 5 Catastrophic Loss)",
                        account=account,
                        masked_account=masked,
                        timestamp=ts,
                    )
                )

    return alerts


def discover_account_position_files(target_account: str = "") -> List[Tuple[str, str]]:
    """Discovers account identifier and position file path pairs."""
    clean_account = sanitize_account(target_account) if target_account else ""
    files_to_check: List[Tuple[str, str]] = []

    if clean_account:
        path = os.path.join(DATA_DIR, f"active_positions_{clean_account}.json")
        if not os.path.exists(path):
            path = OPTIONS_FILE
        files_to_check.append((clean_account, path))
    else:
        if os.path.exists(DATA_DIR):
            for fname in sorted(os.listdir(DATA_DIR)):
                if fname.startswith("active_positions") and fname.endswith(".json"):
                    fpath = os.path.join(DATA_DIR, fname)
                    m = re.match(r"active_positions_([A-Za-z0-9_-]+)\.json", fname)
                    acc = m.group(1) if m else "default"
                    files_to_check.append((acc, fpath))
        if not files_to_check:
            files_to_check.append(("default", OPTIONS_FILE))

    return files_to_check


def run_monitor_pass(
    account: str = "",
    alert: bool = False,
    alert_cache: Optional[Set[Tuple[str, str, str]]] = None,
    spot_fetcher: Optional[Callable[[str], Optional[float]]] = None,
    dispatch_fn: Optional[Callable[[str, str], bool]] = None,
    positions_loader: Optional[Callable[[str], Dict[str, Any]]] = None,
    analyses_loader: Optional[Callable[[], Dict[str, Any]]] = None,
    account_files_discoverer: Optional[Callable[[str], List[Tuple[str, str]]]] = None,
) -> Dict[str, Any]:
    """
    Executes a single monitoring pass across active accounts, checking holding levels and dispatching alerts.

    Args:
        account: Optional account scoping string.
        alert: Boolean flag indicating whether to dispatch system alerts upon breaches.
        alert_cache: Set of (account, position_id, breach_type) tracking previously dispatched alerts.
        spot_fetcher: Callable returning current spot price for a ticker.
        dispatch_fn: Alert dispatching function (defaults to dispatch_system_alert).
        positions_loader: Optional positions loader function.
        analyses_loader: Optional analyses loader function.
        account_files_discoverer: Optional callable discovering account/filepath tuples.

    Returns:
        Dict containing pass summary, checked positions count, and list of breach alerts.
    """
    import json
    from src.gex.storage.persistence import load_json

    if spot_fetcher is None:
        from src.gex_engine import find_latest_underlier_spot
        spot_fetcher = find_latest_underlier_spot

    if dispatch_fn is None:
        from src.gex_engine import dispatch_system_alert
        dispatch_fn = dispatch_system_alert

    if positions_loader is None:
        positions_loader = lambda path: load_json(path, {})

    if analyses_loader is None:
        analyses_loader = lambda: load_json(ANALYSES_FILE, {})

    if account_files_discoverer is None:
        account_files_discoverer = discover_account_position_files

    if alert_cache is None:
        alert_cache = set()

    analyses = analyses_loader()
    account_files = account_files_discoverer(account)

    all_breaches: List[PositionBreachAlert] = []
    total_positions_checked = 0
    accounts_checked = []
    dispatched_alerts_count = 0

    for acc_id, filepath in account_files:
        if not os.path.exists(filepath):
            continue
        data = positions_loader(filepath)
        opts_count = len(data.get("options_positions", {})) if isinstance(data.get("options_positions"), dict) else 0
        stocks_count = len(data.get("stocks_positions", {})) if isinstance(data.get("stocks_positions"), dict) else 0
        total_positions_checked += (opts_count + stocks_count)
        accounts_checked.append(acc_id)

        breaches = evaluate_holding_breaches(data, analyses, spot_fetcher, account=acc_id)
        for b in breaches:
            all_breaches.append(b)
            dedup_key = (b.account, b.position_id, b.breach_type)

            if alert and dedup_key not in alert_cache:
                alert_title = f"🚨 GEX Alert: {b.symbol} {b.breach_type}"
                alert_body = f"[{b.masked_account or b.account}] {b.message}\nAction: {b.action}"
                success = dispatch_fn(alert_title, alert_body)
                if success:
                    alert_cache.add(dedup_key)
                    dispatched_alerts_count += 1

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "accounts_checked": accounts_checked,
        "total_positions_checked": total_positions_checked,
        "breaches_count": len(all_breaches),
        "dispatched_alerts_count": dispatched_alerts_count,
        "breaches": [b.to_dict() for b in all_breaches],
    }


def monitor_daemon(
    interval: int = 60,
    account: str = "",
    alert: bool = False,
    max_iterations: Optional[int] = None,
    spot_fetcher: Optional[Callable[[str], Optional[float]]] = None,
    dispatch_fn: Optional[Callable[[str, str], bool]] = None,
    output_stream: Any = sys.stdout,
) -> None:
    """
    Continuous monitoring loop polling active holdings against structural GEX thresholds.

    Args:
        interval: Polling interval in seconds (default: 60).
        account: Account scoping string.
        alert: Boolean flag indicating whether to dispatch notifications.
        max_iterations: Optional maximum iterations count before exiting (useful for tests).
        spot_fetcher: Optional spot price resolver callback.
        dispatch_fn: Optional alert dispatcher callback.
        output_stream: Output stream for logging prints.
    """
    alert_cache: Set[Tuple[str, str, str]] = set()
    iteration = 0
    print(f"🛰️ GEX Level Breach Monitor active. Interval: {interval}s | Alert: {alert} | Account: {account or 'All'}", file=output_stream)

    try:
        while True:
            iteration += 1
            result = run_monitor_pass(
                account=account,
                alert=alert,
                alert_cache=alert_cache,
                spot_fetcher=spot_fetcher,
                dispatch_fn=dispatch_fn,
            )

            ts = result.get("timestamp", "")
            breaches = result.get("breaches", [])
            checked = result.get("total_positions_checked", 0)

            if breaches:
                print(f"[{ts}] Checked {checked} position(s) -> ⚠️ {len(breaches)} LEVEL BREACH(ES) DETECTED:", file=output_stream)
                for b in breaches:
                    acc_label = b.get("masked_account") or b.get("account") or "Account"
                    print(
                        f"  - [{acc_label}] {b.get('symbol')} ({b.get('position_type')}): "
                        f"{b.get('breach_type')} (Spot ${b.get('spot', 0.0):.2f} vs Level ${b.get('threshold', 0.0):.2f}) -> {b.get('action')}",
                        file=output_stream,
                    )
            else:
                print(f"[{ts}] Checked {checked} position(s) -> ✅ All holdings within structural runway bounds.", file=output_stream)

            if max_iterations is not None and iteration >= max_iterations:
                break

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n🛑 GEX Level Breach Monitor terminated by user.", file=output_stream)
