"""
Risk management and exit stops calculation module for GEX Options Trading System.
Implements the strict priority order of Stops 1 through 5:
- Stop 1: Structural Stop (Close below nTrans / secondary support)
- Stop 2: Trailing Volatility / Profit Drawdown Stop
- Stop 3: Time Stop / Theta Gate (DTE <= 14 or velocity stall)
- Stop 4: Macro / Regime Transition Stop
- Stop 5: Catastrophic Risk Hard Stop (-50% position value)
"""

from typing import Optional, Tuple


def compute_exit_rule_state(
    spot: float,
    purchase_premium: float,
    mark_price: float,
    ptrans: Optional[float],
    ntrans: Optional[float],
    gex_t1: Optional[float],
    days_held: int,
    stalling_counter: int,
    dte: Optional[int],
    target_mode: str = "T1",
    t2_target: Optional[float] = None,
) -> Tuple[str, str, str, str, str]:
    """
    Computes systematic exit rule evaluation logic, proposed actions, and time status.

    Returns:
        tuple[str, str, str, str, str]: (exit_rule_state, proposed_action, time_status, distance_ntrans, distance_max_stop)
    """
    pl_pct = ((mark_price - purchase_premium) / purchase_premium) * 100 if purchase_premium else 0.0

    exit_rule_state = "HOLD"
    proposed_action = "No Action"
    time_status = "ON TRACK"

    # Stop 1 (Structural Stop): Spot < nTrans
    distance_ntrans = "N/A"
    if ntrans:
        dist = ((spot - ntrans) / ntrans) * 100
        distance_ntrans = f"{dist:+.2f}%"
        if spot < ntrans:
            exit_rule_state = "STOP TRIGGERED (Structural Stop: Spot < nTrans)"
            proposed_action = "Immediate Exit (Structural Stop)"

    # Stop 2 (Trailing Volatility Stop / Max Asset Stop below pTrans)
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

    # Stop 3 (Time Stop / Velocity check): Day 7 progress limit
    if days_held >= 7:
        if dte is not None and dte > 90:
            # LEAPs / long-dated options have negligible theta decay; exempt from the 7-day velocity time stop
            time_status = "ON TRACK (LEAP/Long-DTE Exempt)"
        elif gex_t1 and ptrans:
            full_run = gex_t1 - ptrans
            made_progress = spot - ptrans
            progress_pct = (made_progress / full_run) * 100 if full_run > 0 else 0.0
            if progress_pct < 50.0:
                if not exit_rule_state.startswith("STOP TRIGGERED"):
                    exit_rule_state = "STOP TRIGGERED (Time Stop: <50% progress by Day 7)"
                    proposed_action = "Immediate Exit (Time Stop)"
                time_status = "STALE (Time Limit Exceeded)"

    # Stalling stop
    if stalling_counter >= 3:
        if not exit_rule_state.startswith("STOP TRIGGERED"):
            exit_rule_state = "STOP TRIGGERED (Stalling Stop: <10% daily progress for 3 consecutive days)"
            proposed_action = "Immediate Exit (Stalling Stop)"
        time_status = "STALLED"

    # Target mode logic (T1 vs T2)
    if target_mode == "T2":
        if pl_pct <= 0.0:
            if not exit_rule_state.startswith("STOP TRIGGERED"):
                exit_rule_state = "STOP TRIGGERED (Trailed Stop: Option at or below entry premium)"
                proposed_action = "Immediate Exit (Trailed Stop at Entry Premium to protect T1 gains)"

        target_price = t2_target if t2_target is not None else (gex_t1 * 1.10 if gex_t1 else None)
        if target_price and spot >= target_price:
            if not exit_rule_state.startswith("STOP TRIGGERED"):
                exit_rule_state = "PROFIT TAKE (T2 TARGET MET)"
                proposed_action = "Exit position to lock in full T2/Lock & Ride gains"
    else:
        if gex_t1 and spot >= gex_t1:
            if not exit_rule_state.startswith("STOP TRIGGERED"):
                if pl_pct < 0:
                    exit_rule_state = "UNDERLIER TARGET MET (Option in Loss)"
                    proposed_action = "Exit position to limit further losses (Strike/Maturity mismatch or decay)"
                else:
                    exit_rule_state = "PROFIT TAKE (T1 TARGET MET)"
                    proposed_action = "Exit for 100% gains OR Trail stop to entry price and target structural T2"

    # Stop 3 (Theta Gate / Time Stop): Hard exit when DTE <= 14 days
    if dte is not None and 0 <= dte <= 14:
        if (
            not exit_rule_state.startswith("STOP TRIGGERED")
            and not exit_rule_state.startswith("PROFIT TAKE")
            and exit_rule_state != "UNDERLIER TARGET MET (Option in Loss)"
        ):
            exit_rule_state = "STOP TRIGGERED (Theta Stop: DTE <= 14 days)"
            proposed_action = "Immediate Exit (Theta Stop)"
            time_status = "THETA EXHAUSTION (DTE <= 14)"

    # Stop 5 (Catastrophic Risk Stop): Hard stop at -50% position value
    if pl_pct <= -50.0:
        if not exit_rule_state.startswith("STOP TRIGGERED"):
            exit_rule_state = "STOP TRIGGERED (Catastrophic Risk Stop: Loss <= -50%)"
            proposed_action = "Immediate Exit (Catastrophic Risk Stop)"

    if dte is not None and dte < 0:
        exit_rule_state = "EXPIRED (Contract past expiration)"
        proposed_action = "Remove from tracker via close-position"
        time_status = "EXPIRED"

    if exit_rule_state == "HOLD" and ptrans and spot < ptrans:
        exit_rule_state = "WATCH"
        proposed_action = "Hold existing, but add NOTHING"

    return exit_rule_state, proposed_action, time_status, distance_ntrans, distance_max_stop
