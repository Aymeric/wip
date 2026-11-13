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
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from src.gex.core.config import (
    ANALYSES_FILE,
    DATA_DIR,
    OPTIONS_FILE,
    mask_account,
    sanitize_account,
)


@dataclass
class AlertState:
    """Tracks stateful monitoring attributes for an active position breach level."""
    account: str
    position_id: str
    breach_type: str
    symbol: str
    last_dispatched_at: float = 0.0
    last_dispatched_spot: float = 0.0
    alert_count_today: int = 0
    is_armed: bool = True
    session_date: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Converts AlertState to serializable dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AlertState":
        """Reconstructs AlertState from dictionary."""
        return cls(
            account=str(data.get("account", "")),
            position_id=str(data.get("position_id", "")),
            breach_type=str(data.get("breach_type", "")),
            symbol=str(data.get("symbol", "")),
            last_dispatched_at=float(data.get("last_dispatched_at", 0.0)),
            last_dispatched_spot=float(data.get("last_dispatched_spot", 0.0)),
            alert_count_today=int(data.get("alert_count_today", 0)),
            is_armed=bool(data.get("is_armed", True)),
            session_date=str(data.get("session_date", "")),
        )


class AlertStateManager:
    """
    State machine managing alert deduplication, cooldown intervals, hysteresis deadbands,
    and webhook burst rate-limiting across active portfolio positions.
    """

    def __init__(
        self,
        cooldown_seconds: float = 1800.0,
        deadband_pct: float = 0.0025,
        max_burst: int = 5,
        burst_window_seconds: float = 60.0,
        state_file: Optional[str] = None,
    ):
        self.cooldown_seconds = cooldown_seconds
        self.deadband_pct = deadband_pct
        self.max_burst = max_burst
        self.burst_window_seconds = burst_window_seconds
        self.state_file = state_file
        self.states: Dict[Tuple[str, str, str], AlertState] = {}
        self.recent_dispatch_timestamps: List[float] = []
        self.today_session: str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if self.state_file and os.path.exists(self.state_file):
            self.load_from_file(self.state_file)

    def _get_key(self, account: str, position_id: str, breach_type: str) -> Tuple[str, str, str]:
        return (account, position_id, breach_type)

    def _ensure_session_date(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self.today_session:
            self.today_session = today
            for state in self.states.values():
                state.alert_count_today = 0
                state.session_date = today

    def update_spot_and_rearm(
        self,
        symbol: str,
        spot: float,
        analyses_data: Dict[str, Any],
    ) -> None:
        """
        Evaluates spot relative to GEX thresholds and re-arms previously triggered alerts
        if spot has cleared the hysteresis deadband.
        """
        if spot <= 0.0 or not analyses_data:
            return

        levels = analyses_data.get(symbol, {})
        ntrans = levels.get("nTrans")
        ptrans = levels.get("pTrans")
        gex_t1 = levels.get("+GEX")
        t2_target = levels.get("t2_target")

        for key, state in self.states.items():
            if state.symbol != symbol or state.is_armed:
                continue

            breach_type = state.breach_type

            # Downside breaches (nTrans Stop 1, pTrans Stop 2)
            # Must rise above threshold * (1 + deadband_pct) to re-arm
            if breach_type == "STOP1_NTRANS" and ntrans is not None:
                rearm_level = float(ntrans) * (1.0 + self.deadband_pct)
                if spot >= rearm_level:
                    state.is_armed = True
            elif breach_type == "STOP2_MAX_ASSET" and ptrans is not None:
                rearm_level = float(ptrans) * (1.0 + self.deadband_pct)
                if spot >= rearm_level:
                    state.is_armed = True

            # Upside breaches (+GEX Profit Target, T2 Target)
            # Must pull back below threshold * (1 - deadband_pct) to re-arm
            elif breach_type == "PROFIT_TARGET_GEX" and gex_t1 is not None:
                rearm_level = float(gex_t1) * (1.0 - self.deadband_pct)
                if spot <= rearm_level:
                    state.is_armed = True
            elif breach_type == "T2_TARGET":
                target_val = float(t2_target) if t2_target is not None else (float(gex_t1) * 1.10 if gex_t1 else None)
                if target_val is not None:
                    rearm_level = target_val * (1.0 - self.deadband_pct)
                    if spot <= rearm_level:
                        state.is_armed = True

    def should_dispatch(
        self,
        alert: "PositionBreachAlert",
        current_time: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """
        Determines whether a detected breach alert should be dispatched.
        Checks:
        1. Catastrophic escalation (always permitted for STOP5)
        2. Hysteresis trigger arming
        3. Cooldown interval
        4. Global sliding-window webhook rate limit

        Returns:
            Tuple[bool, str]: (should_send, reason)
        """
        self._ensure_session_date()
        now = current_time if current_time is not None else time.time()
        key = self._get_key(alert.account, alert.position_id, alert.breach_type)

        state = self.states.get(key)
        if state is None:
            # First time breach is observed
            state = AlertState(
                account=alert.account,
                position_id=alert.position_id,
                breach_type=alert.breach_type,
                symbol=alert.symbol,
                last_dispatched_at=0.0,
                last_dispatched_spot=0.0,
                alert_count_today=0,
                is_armed=True,
                session_date=self.today_session,
            )
            self.states[key] = state

        # Catastrophic Stop 5: Emergency rule
        if alert.breach_type == "STOP5_CATASTROPHIC":
            return (True, "EMERGENCY_CATASTROPHIC")

        # 1. Check hysteresis trigger arming
        if not state.is_armed:
            return (False, "DISARMED_HYSTERESIS (Spot must cross deadband to re-arm)")

        # 2. Check cooldown interval
        elapsed = now - state.last_dispatched_at
        if state.last_dispatched_at > 0.0 and elapsed < self.cooldown_seconds:
            remaining = int(self.cooldown_seconds - elapsed)
            return (False, f"COOLDOWN_ACTIVE ({remaining}s remaining)")

        # 3. Check global webhook rate limit
        cutoff = now - self.burst_window_seconds
        self.recent_dispatch_timestamps = [t for t in self.recent_dispatch_timestamps if t > cutoff]
        if len(self.recent_dispatch_timestamps) >= self.max_burst:
            return (False, f"RATE_LIMITED (Max {self.max_burst} alerts/min reached)")

        return (True, "OK")

    def record_dispatch(
        self,
        alert: "PositionBreachAlert",
        current_time: Optional[float] = None,
    ) -> None:
        """Records a successful alert dispatch, disarms the trigger, and tracks rate limits."""
        self._ensure_session_date()
        now = current_time if current_time is not None else time.time()
        key = self._get_key(alert.account, alert.position_id, alert.breach_type)

        state = self.states.get(key)
        if state is None:
            state = AlertState(
                account=alert.account,
                position_id=alert.position_id,
                breach_type=alert.breach_type,
                symbol=alert.symbol,
                session_date=self.today_session,
            )
            self.states[key] = state

        state.last_dispatched_at = now
        state.last_dispatched_spot = alert.spot
        state.alert_count_today += 1
        state.is_armed = False

        self.recent_dispatch_timestamps.append(now)

        if self.state_file:
            self.save_to_file(self.state_file)

    def get_daily_digest(self) -> Dict[str, Any]:
        """Returns consolidated daily alert digest summary."""
        self._ensure_session_date()
        active_alerts = []
        for key, s in sorted(self.states.items(), key=lambda x: (x[1].symbol, x[1].breach_type)):
            if s.alert_count_today > 0:
                active_alerts.append({
                    "account": s.account,
                    "symbol": s.symbol,
                    "position_id": s.position_id,
                    "breach_type": s.breach_type,
                    "alert_count_today": s.alert_count_today,
                    "last_dispatched_at": datetime.fromtimestamp(s.last_dispatched_at, tz=timezone.utc).isoformat() if s.last_dispatched_at > 0 else None,
                    "last_dispatched_spot": s.last_dispatched_spot,
                    "is_armed": s.is_armed,
                })
        return {
            "session_date": self.today_session,
            "total_dispatched_today": sum(s.alert_count_today for s in self.states.values()),
            "tracked_holdings_count": len(self.states),
            "active_alerts": active_alerts,
        }

    def save_to_file(self, filepath: str) -> None:
        """Atomically persists alert state to JSON file."""
        import json
        import tempfile
        dirname = os.path.dirname(os.path.abspath(filepath))
        os.makedirs(dirname, exist_ok=True)
        data = {
            "session_date": self.today_session,
            "states": {f"{k[0]}|{k[1]}|{k[2]}": s.to_dict() for k, s in self.states.items()},
        }
        with tempfile.NamedTemporaryFile("w", dir=dirname, delete=False, suffix=".tmp") as tf:
            json.dump(data, tf, indent=2)
            tmp_path = tf.name
        os.replace(tmp_path, filepath)

    def load_from_file(self, filepath: str) -> None:
        """Loads alert state from JSON file."""
        import json
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.today_session = data.get("session_date", self.today_session)
            raw_states = data.get("states", {})
            for k_str, s_dict in raw_states.items():
                parts = k_str.split("|", 2)
                if len(parts) == 3:
                    key = (parts[0], parts[1], parts[2])
                    self.states[key] = AlertState.from_dict(s_dict)
        except Exception:
            pass


def format_alert_digest(digest: Dict[str, Any]) -> str:
    """Formats daily alert digest into a human-readable summary block."""
    from src.gex.presentation.ascii_art import format_color
    session_date = digest.get("session_date", "")
    total = digest.get("total_dispatched_today", 0)
    active = digest.get("active_alerts", [])
    lines = [
        f"📊 Intraday Alert Digest — Session: {session_date}",
        f"Total Alerts Dispatched Today: {total}",
        f"Tracked Level Triggers: {digest.get('tracked_holdings_count', 0)}",
    ]
    if active:
        lines.append("\nActive Trigger Records:")
        lines.append(f"  {'Symbol':<6} | {'Account':<12} | {'Breach Type':<18} | {'Count':<5} | {'Armed':<5} | {'Last Dispatched'}")
        lines.append("  " + "-" * 75)
        for a in active:
            armed_str = "YES" if a.get("is_armed") else "NO"
            armed_c = "32" if a.get("is_armed") else "33"
            armed_fmt = format_color(armed_str, armed_c)
            last_dt = a.get("last_dispatched_at") or "N/A"
            if "T" in last_dt:
                last_dt = last_dt.split("T")[1][:8] + " UTC"
            lines.append(
                f"  {a.get('symbol', ''):<6} | {mask_account(a.get('account', '')):<12} | {a.get('breach_type', ''):<18} | "
                f"{a.get('alert_count_today', 0):<5} | {armed_fmt:<14} | {last_dt}"
            )
    else:
        lines.append("No alerts have been dispatched in this session.")
    return "\n".join(lines)


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
    alert_cache: Optional[Union[AlertStateManager, Set[Tuple[str, str, str]]]] = None,
    spot_fetcher: Optional[Callable[[str], Optional[float]]] = None,
    dispatch_fn: Optional[Callable[[str, str], bool]] = None,
    positions_loader: Optional[Callable[[str], Dict[str, Any]]] = None,
    analyses_loader: Optional[Callable[[], Dict[str, Any]]] = None,
    account_files_discoverer: Optional[Callable[[str], List[Tuple[str, str]]]] = None,
    cooldown_seconds: float = 1800.0,
    deadband_pct: float = 0.0025,
) -> Dict[str, Any]:
    """
    Executes a single monitoring pass across active accounts, checking holding levels and dispatching alerts.

    Args:
        account: Optional account scoping string.
        alert: Boolean flag indicating whether to dispatch system alerts upon breaches.
        alert_cache: AlertStateManager instance or set of (account, position_id, breach_type) tracking dispatched alerts.
        spot_fetcher: Callable returning current spot price for a ticker.
        dispatch_fn: Alert dispatching function (defaults to dispatch_system_alert).
        positions_loader: Optional positions loader function.
        analyses_loader: Optional analyses loader function.
        account_files_discoverer: Optional callable discovering account/filepath tuples.
        cooldown_seconds: Cooldown in seconds before allowing repeat alert for same holding/breach.
        deadband_pct: Hysteresis deadband ratio before re-arming trigger (e.g. 0.0025 for 0.25%).

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
        alert_cache = AlertStateManager(cooldown_seconds=cooldown_seconds, deadband_pct=deadband_pct)

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

        # Update spot prices and check re-arming for active positions if using AlertStateManager
        if isinstance(alert_cache, AlertStateManager):
            options = data.get("options_positions", {})
            if isinstance(options, dict):
                for details in options.values():
                    if isinstance(details, dict):
                        u = str(details.get("Underlier") or details.get("symbol") or "").upper()
                        if u:
                            sp = spot_fetcher(u)
                            if sp is not None and sp > 0:
                                alert_cache.update_spot_and_rearm(u, sp, analyses)
            stocks = data.get("stocks_positions", {})
            if isinstance(stocks, dict):
                for ticker in stocks.keys():
                    sym = str(ticker).upper()
                    sp = spot_fetcher(sym)
                    if sp is not None and sp > 0:
                        alert_cache.update_spot_and_rearm(sym, sp, analyses)

        breaches = evaluate_holding_breaches(data, analyses, spot_fetcher, account=acc_id)
        for b in breaches:
            all_breaches.append(b)

            if alert:
                if isinstance(alert_cache, AlertStateManager):
                    should_send, reason = alert_cache.should_dispatch(b)
                    if should_send:
                        alert_title = f"🚨 GEX Alert: {b.symbol} {b.breach_type}"
                        alert_body = f"[{b.masked_account or b.account}] {b.message}\nAction: {b.action}"
                        success = dispatch_fn(alert_title, alert_body)
                        if success:
                            alert_cache.record_dispatch(b)
                            dispatched_alerts_count += 1
                else:
                    dedup_key = (b.account, b.position_id, b.breach_type)
                    if dedup_key not in alert_cache:
                        alert_title = f"🚨 GEX Alert: {b.symbol} {b.breach_type}"
                        alert_body = f"[{b.masked_account or b.account}] {b.message}\nAction: {b.action}"
                        success = dispatch_fn(alert_title, alert_body)
                        if success:
                            alert_cache.add(dedup_key)
                            dispatched_alerts_count += 1

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "accounts_checked": accounts_checked,
        "total_positions_checked": total_positions_checked,
        "breaches_count": len(all_breaches),
        "dispatched_alerts_count": dispatched_alerts_count,
        "breaches": [b.to_dict() for b in all_breaches],
    }
    if isinstance(alert_cache, AlertStateManager):
        summary["digest"] = alert_cache.get_daily_digest()
    return summary


def monitor_daemon(
    interval: int = 60,
    account: str = "",
    alert: bool = False,
    max_iterations: Optional[int] = None,
    spot_fetcher: Optional[Callable[[str], Optional[float]]] = None,
    dispatch_fn: Optional[Callable[[str, str], bool]] = None,
    output_stream: Any = sys.stdout,
    cooldown: int = 1800,
    deadband: float = 0.25,
    show_digest: bool = False,
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
        cooldown: Cooldown interval in seconds (default: 1800).
        deadband: Hysteresis deadband in percent (default: 0.25%).
        show_digest: Whether to print daily digest block on each pass.
    """
    alert_manager = AlertStateManager(
        cooldown_seconds=float(cooldown),
        deadband_pct=float(deadband) / 100.0,
    )
    iteration = 0
    print(
        f"🛰️ GEX Level Breach Monitor active. Interval: {interval}s | Alert: {alert} | Cooldown: {cooldown}s | "
        f"Deadband: {deadband:.2f}% | Account: {account or 'All'}",
        file=output_stream,
    )

    try:
        while True:
            iteration += 1
            result = run_monitor_pass(
                account=account,
                alert=alert,
                alert_cache=alert_manager,
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

            if show_digest:
                digest = result.get("digest")
                if digest:
                    print("\n" + format_alert_digest(digest), file=output_stream)

            if max_iterations is not None and iteration >= max_iterations:
                break

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n🛑 GEX Level Breach Monitor terminated by user.", file=output_stream)
        if show_digest:
            print("\n" + format_alert_digest(alert_manager.get_daily_digest()), file=output_stream)
