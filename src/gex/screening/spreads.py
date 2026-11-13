"""
Defined-risk vertical debit spread modeling, selection, and payoff engine.
Pairs long ATM/near-OTM options with short +GEX call wall strikes to reduce capital outlay,
mitigate volatility crush, and peg profit realization to structural dealer resistance.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple, Set

from src.gex.core.models import VerticalSpread
from src.gex.quant.gex import extract_quotes_list


def calculate_spread_payoff(
    long_strike: float,
    short_strike: float,
    long_mark: float,
    short_mark: float,
    long_ask: Optional[float] = None,
    long_bid: Optional[float] = None,
    short_ask: Optional[float] = None,
    short_bid: Optional[float] = None,
    slippage_factor: float = 0.35,
) -> Dict[str, float]:
    """Computes debit, maximum profit, maximum loss, breakeven, and risk/reward for a vertical call spread.

    Args:
        long_strike: Lower strike (bought)
        short_strike: Upper strike (sold)
        long_mark: Mark price of long call
        short_mark: Mark price of short call
        long_ask: Ask price of long call (defaults to long_mark)
        long_bid: Bid price of long call (defaults to long_mark)
        short_ask: Ask price of short call (defaults to short_mark)
        short_bid: Bid price of short call (defaults to short_mark)
        slippage_factor: Bid-ask spread penalty modeling execution friction (0.35 = 35% of spread)

    Returns:
        dict with net_debit, max_profit, max_loss, breakeven, risk_reward_ratio, capital_savings_pct.
    """
    if short_strike <= long_strike:
        raise ValueError(f"short_strike ({short_strike}) must be strictly greater than long_strike ({long_strike})")

    l_ask = long_ask if long_ask is not None and long_ask > 0 else long_mark
    l_bid = long_bid if long_bid is not None and long_bid > 0 else long_mark
    s_ask = short_ask if short_ask is not None and short_ask > 0 else short_mark
    s_bid = short_bid if short_bid is not None and short_bid > 0 else short_mark

    natural_debit = max(0.01, l_ask - s_bid)

    # Mid debit with slippage friction
    mid_diff = long_mark - short_mark
    spread_friction = ((l_ask - l_bid) + (s_ask - s_bid)) * slippage_factor * 0.5
    realistic_debit = max(0.01, mid_diff + spread_friction)

    width = short_strike - long_strike
    net_debit = min(width, realistic_debit)

    max_loss = net_debit * 100.0
    max_profit = max(0.0, (width - net_debit) * 100.0)
    breakeven = long_strike + net_debit

    rr_ratio = (max_profit / max_loss) if max_loss > 0 else 999.0

    naked_long_cost = max(0.01, long_mark * 100.0)
    capital_savings_pct = max(0.0, ((naked_long_cost - max_loss) / naked_long_cost) * 100.0)

    return {
        "net_debit": net_debit,
        "natural_debit": natural_debit,
        "width": width,
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakeven": breakeven,
        "risk_reward_ratio": rr_ratio,
        "capital_savings_pct": capital_savings_pct,
    }


def select_vertical_spread(
    inst_data: Any,
    quotes_data: Any,
    spot: float,
    gex_target: Optional[float] = None,
    earnings_date: Optional[str] = None,
    today_override: Optional[Any] = None,
    target_delta: float = 0.45,
    min_dte: int = 30,
    max_dte: int = 45,
) -> Tuple[Optional[VerticalSpread], List[VerticalSpread]]:
    """Identifies and ranks the best defined-risk debit call vertical spreads pairing
    an ATM long call with a short call pegged to the +GEX call wall.

    Args:
        inst_data: Options instruments payload (dict or list)
        quotes_data: Options quotes payload (dict or list)
        spot: Current underlier spot price
        gex_target: Target +GEX call wall strike (short leg target)
        earnings_date: Known earnings report date for pre-earnings blackout check
        today_override: Date override for testing/deterministic runs
        target_delta: Ideal long leg delta target (defaults to 0.45)
        min_dte: Minimum target expiration horizon in days (defaults to 30)
        max_dte: Maximum target expiration horizon in days (defaults to 45)

    Returns:
        tuple: (best_spread, all_eligible_spreads)
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

    by_exp: Dict[str, List[Tuple[str, float]]] = {}
    expirations = set()
    for inst in instruments_list:
        if type(inst) is not dict:
            continue
        opt_type = inst.get("type")
        if opt_type != "call" and opt_type != "CALL":
            if opt_type == "put" or opt_type == "PUT" or type(opt_type) is not str or opt_type.lower() != "call":
                continue
        try:
            opt_id = inst["id"]
            if not opt_id:
                continue
            strike = float(inst["strike_price"])
            exp_str = inst["expiration_date"]
        except KeyError:
            opt_id = inst.get("id")
            if not opt_id:
                continue
            strike_val = inst.get("strike_price")
            strike = float(strike_val) if strike_val is not None else float(inst.get("strike", 0.0))
            exp_str = inst.get("expiration_date")
        except (ValueError, TypeError):
            continue

        if exp_str:
            if exp_str in by_exp:
                by_exp[exp_str].append((opt_id, strike))
            else:
                by_exp[exp_str] = [(opt_id, strike)]
                expirations.add(exp_str)

    if not expirations:
        return None, []

    # 2. Identify target expiration
    if today_override:
        if isinstance(today_override, str):
            today = date.fromisoformat(today_override[:10])
        elif isinstance(today_override, datetime):
            today = today_override.date()
        else:
            today = today_override
    else:
        today = date.today()

    valid_expirations = []
    for exp_str in expirations:
        try:
            exp_date = date.fromisoformat(exp_str)
            dte = (exp_date - today).days
            if dte >= 14:
                valid_expirations.append((exp_str, dte))
        except (ValueError, TypeError):
            continue

    if not valid_expirations:
        return None, []

    def exp_target_distance(item: Tuple[str, int]) -> Tuple[int, int]:
        _, dte = item
        if min_dte <= dte <= max_dte:
            return (0, abs(dte - min_dte))
        return (1, min(abs(dte - min_dte), abs(dte - max_dte)))

    chosen_exp, chosen_dte = min(valid_expirations, key=exp_target_distance)

    earnings_blocked = False
    if earnings_date:
        try:
            e_dt = date.fromisoformat(earnings_date[:10]) if isinstance(earnings_date, str) else earnings_date
            exp_dt = date.fromisoformat(chosen_exp)
            if e_dt <= exp_dt:
                earnings_blocked = True
        except (ValueError, TypeError):
            pass

    # 3. Parse quotes for chosen expiration
    target_contracts = by_exp.get(chosen_exp, [])
    target_opt_ids = {opt_id for opt_id, _ in target_contracts}
    quotes_list = extract_quotes_list(quotes_data)

    quotes_map: Dict[str, Dict[str, Any]] = {}
    for q_item in quotes_list:
        if type(q_item) is not dict:
            continue
        q = q_item["quote"] if ("quote" in q_item and type(q_item["quote"]) is dict) else q_item
        try:
            opt_id = q["instrument_id"]
        except KeyError:
            opt_id = q.get("instrument_id") or q.get("id") or q.get("instrument")
        if opt_id in target_opt_ids:
            quotes_map[opt_id] = q

    # Build parsed contract objects
    parsed_contracts: List[Dict[str, Any]] = []
    for opt_id, strike in target_contracts:
        q = quotes_map.get(opt_id)
        if not q:
            continue
        try:
            bid = float(q.get("bid_price") or 0.0)
            ask = float(q.get("ask_price") or 0.0)
            raw_mark = q.get("mark_price") or q.get("adjusted_mark_price")
            mark = float(raw_mark) if raw_mark is not None else ((bid + ask) * 0.5)
            oi = int(q.get("open_interest") or 0)
            raw_delta = q.get("delta")
            delta = float(raw_delta) if raw_delta is not None else None
            spread = ask - bid

            # Basic liquidity checks
            if mark <= 2.0:
                spread_ok = (spread <= 0.20)
            elif mark <= 5.0:
                spread_ok = (spread <= 0.35)
            else:
                spread_ok = (spread <= 0.15 * bid) if bid > 0 else (spread <= 0.15 * mark)
            oi_ok = (oi >= 250)

            parsed_contracts.append({
                "opt_id": opt_id,
                "strike": strike,
                "bid": bid,
                "ask": ask,
                "mark": mark,
                "oi": oi,
                "delta": delta,
                "spread_ok": spread_ok,
                "oi_ok": oi_ok,
            })
        except (ValueError, TypeError):
            continue

    if len(parsed_contracts) < 2:
        return None, []

    # Sort parsed contracts by strike ascending
    parsed_contracts.sort(key=lambda c: c["strike"])

    # Separate candidates into candidate long legs and candidate short legs
    # Long candidates: strike < gex_target (if target provided) or strike near spot
    long_candidates = []
    short_candidates = []

    for c in parsed_contracts:
        # Long leg criteria: strike <= spot * 1.05 and strike < (gex_target or 999999.0)
        # Delta preferably 0.30 to 0.65
        is_long_eligible = False
        if gex_target:
            if c["strike"] < gex_target:
                is_long_eligible = True
        else:
            if c["strike"] <= spot * 1.05:
                is_long_eligible = True

        if is_long_eligible:
            long_candidates.append(c)

        # Short leg criteria: strike > spot and (if gex_target, near gex_target)
        if c["strike"] > spot:
            short_candidates.append(c)

    if not long_candidates or not short_candidates:
        return None, []

    symbol = ""
    if instruments_list and isinstance(instruments_list[0], dict):
        symbol = str(instruments_list[0].get("chain_symbol") or instruments_list[0].get("symbol") or "").upper()

    evaluated_spreads: List[VerticalSpread] = []

    for lc in long_candidates:
        for sc in short_candidates:
            if sc["strike"] <= lc["strike"]:
                continue

            try:
                payoff = calculate_spread_payoff(
                    long_strike=lc["strike"],
                    short_strike=sc["strike"],
                    long_mark=lc["mark"],
                    short_mark=sc["mark"],
                    long_ask=lc["ask"],
                    long_bid=lc["bid"],
                    short_ask=sc["ask"],
                    short_bid=sc["bid"],
                )
            except ValueError:
                continue

            net_delta = (lc["delta"] - sc["delta"]) if (lc["delta"] is not None and sc["delta"] is not None) else None
            spread_ok = lc["spread_ok"] and sc["spread_ok"]
            oi_ok = lc["oi_ok"] and sc["oi_ok"]

            spread = VerticalSpread(
                symbol=symbol,
                expiration_date=chosen_exp,
                dte=chosen_dte,
                long_strike=lc["strike"],
                short_strike=sc["strike"],
                long_option_id=lc["opt_id"],
                short_option_id=sc["opt_id"],
                long_mark=lc["mark"],
                short_mark=sc["mark"],
                long_ask=lc["ask"],
                long_bid=lc["bid"],
                short_ask=sc["ask"],
                short_bid=sc["bid"],
                net_debit=payoff["net_debit"],
                max_profit=payoff["max_profit"],
                max_loss=payoff["max_loss"],
                breakeven=payoff["breakeven"],
                risk_reward_ratio=payoff["risk_reward_ratio"],
                capital_savings_pct=payoff["capital_savings_pct"],
                long_delta=lc["delta"],
                short_delta=sc["delta"],
                net_delta=net_delta,
                long_oi=lc["oi"],
                short_oi=sc["oi"],
                earnings_blocked=earnings_blocked,
                spread_ok=spread_ok,
                oi_ok=oi_ok,
            )
            evaluated_spreads.append(spread)

    if not evaluated_spreads:
        return None, []

    # Scoring algorithm for ranking candidate spreads
    def score_spread(s: VerticalSpread) -> float:
        score = 0.0

        # 1. Risk/Reward ratio (prefer RR >= 1.5, max bonus up to 3.0)
        score += min(s.risk_reward_ratio, 4.0) * 20.0

        # 2. Capital savings (prefer 30-50% savings)
        score += (s.capital_savings_pct / 100.0) * 25.0

        # 3. Long leg delta alignment to target_delta (0.45)
        if s.long_delta is not None:
            delta_diff = abs(s.long_delta - target_delta)
            score += max(0.0, (0.15 - delta_diff) / 0.15) * 20.0

        # 4. Short strike alignment to +GEX target
        if gex_target is not None:
            gex_dist = abs(s.short_strike - gex_target)
            rel_dist = gex_dist / max(1.0, gex_target)
            score += max(0.0, (0.05 - rel_dist) / 0.05) * 25.0

        # 5. Liquidity bonuses / penalties
        if s.spread_ok:
            score += 10.0
        else:
            score -= 20.0

        if s.oi_ok:
            score += 10.0
        else:
            score -= 15.0

        if s.earnings_blocked:
            score -= 50.0

        return score

    evaluated_spreads.sort(key=score_spread, reverse=True)
    best_spread = evaluated_spreads[0] if evaluated_spreads else None

    return best_spread, evaluated_spreads
