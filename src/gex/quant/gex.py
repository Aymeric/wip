"""
Gamma Exposure (GEX) profiling and dealer positioning analytics.
Derives COTMP, pTrans, nTrans, +GEX, -GEX Put Wall, and Rule 1-10 indicators
from options chains and quote matrices.
"""

import math
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from src.gex.quant.greeks import (
    calculate_black_scholes_gamma,
    find_flip_strikes,
    select_transition_points,
)


_DEFAULT_DTE_WEIGHT = 0.18257418583505537  # 1.0 / math.sqrt(30.0)


def extract_quotes_list(quotes_data: Any) -> List[Any]:
    """Extracts a normalized quotes list from dict or list data payload."""
    if isinstance(quotes_data, list):
        return quotes_data
    if isinstance(quotes_data, dict):
        data = quotes_data.get("data")
        quotes_list = []
        if isinstance(data, dict):
            quotes_list = data.get("results", [])
        elif isinstance(data, list):
            quotes_list = data

        if not quotes_list:
            res = quotes_data.get("results")
            if isinstance(res, list):
                quotes_list = res

        return quotes_list if isinstance(quotes_list, list) else []
    return []


def derive_gex_profile(
    inst_data: Any,
    quotes_data: Any,
    spot: Optional[float] = None,
) -> Dict[str, Any]:
    """Derives GEX levels and key option metrics (COTMP, pTrans, nTrans, +GEX)
    from Robinhood options instruments and quotes payloads.

    Args:
        inst_data: Options instruments JSON payload (dict or list)
        quotes_data: Options quotes JSON payload (dict or list)
        spot: Current underlier spot price (defaults to 100.0 if None)

    Returns:
        dict: Derived levels, rules, and intermediate calculations.
    """
    instruments_list = []
    if isinstance(inst_data, list):
        instruments_list = inst_data
    elif isinstance(inst_data, dict):
        inst_dict = inst_data.get("data")
        if isinstance(inst_dict, dict):
            instruments_list = inst_dict.get("instruments", [])
        else:
            instruments_list = inst_data.get("instruments", [])

    # Performance optimization (Bolt):
    # - Direct type() identity checks avoid isinstance MRO traversal.
    # - Precalculate dte_val and dte_weight per expiration date in exp_cache.
    # - Direct inst_map.get(opt_id) lookup for quote payloads avoids redundant key checks.
    today_d = date.today()
    exp_cache = {}
    inst_map = {}
    for inst in instruments_list:
        if type(inst) is not dict:
            continue
        opt_id = inst.get("id")
        if not opt_id:
            continue
        try:
            strike = float(inst.get("strike_price") or inst.get("strike", 0.0))
            opt_type = inst.get("type")
            exp_str = inst.get("expiration_date") or inst.get("exp_date")
            if exp_str:
                cached = exp_cache.get(exp_str)
                if cached is None:
                    try:
                        exp_date = date.fromisoformat(exp_str[:10])
                        d_val = float(max((exp_date - today_d).days, 0))
                        w_val = 1.0 / math.sqrt(max(d_val, 1.0))
                        cached = (d_val, w_val)
                    except Exception:
                        cached = (30.0, _DEFAULT_DTE_WEIGHT)
                    exp_cache[exp_str] = cached
                dte_val, dte_weight = cached
            else:
                dte_val, dte_weight = 30.0, _DEFAULT_DTE_WEIGHT
            inst_map[opt_id] = (strike, opt_type, dte_val, dte_weight)
        except (ValueError, KeyError, TypeError):
            continue

    quotes_list = extract_quotes_list(quotes_data)

    strike_put_oi = {}
    strike_call_oi = {}
    strike_put_gex = {}
    strike_call_gex = {}
    total_oi = 0
    total_call_gex = 0.0
    total_put_gex = 0.0
    effective_call_gex = 0.0
    effective_put_gex = 0.0
    sum_strike_put_oi = 0.0
    sum_put_oi = 0

    iv_sum = 0.0
    iv_count = 0

    calc_spot = spot if spot is not None else 100.0
    spot_iv_bound = calc_spot * 0.15
    spot_x_100 = calc_spot * 100.0

    for q_item in quotes_list:
        if type(q_item) is not dict:
            continue
        q = q_item["quote"] if ("quote" in q_item and type(q_item["quote"]) is dict) else q_item

        try:
            opt_id = q["instrument_id"]
            raw_oi = q["open_interest"]
            raw_gamma = q["gamma"]
            raw_iv = q["implied_volatility"]
            oi = int(raw_oi) if raw_oi else 0
            gamma = float(raw_gamma) if raw_gamma else 0.0
            iv = float(raw_iv) if raw_iv else 0.0
        except KeyError:
            opt_id = q.get("instrument_id") or q.get("id") or q.get("instrument")
            try:
                raw_oi = q.get("open_interest")
                oi = int(raw_oi) if raw_oi else 0
                raw_gamma = q.get("gamma")
                gamma = float(raw_gamma) if raw_gamma else 0.0
                raw_iv = q.get("implied_volatility")
                if raw_iv is None:
                    raw_iv = q.get("implied_vol")
                iv = float(raw_iv) if raw_iv else 0.0
            except (ValueError, TypeError):
                continue
        except (ValueError, TypeError):
            continue

        inst_info = inst_map.get(opt_id)
        if inst_info is None:
            continue

        strike, opt_type, dte_val, dte_weight = inst_info

        # Analytical Black-Scholes Gamma fallback if broker feed returns zero or missing gamma
        if gamma <= 0.0 and iv > 0.0:
            gamma = calculate_black_scholes_gamma(calc_spot, strike, dte_val, iv)

        total_oi += oi
        gex_val = oi * gamma * spot_x_100
        effective_gex_val = gex_val * dte_weight

        # IV proxy (within 15% of spot)
        diff = strike - calc_spot
        abs_diff = diff if diff >= 0.0 else -diff
        if abs_diff <= spot_iv_bound and iv > 0.0:
            iv_sum += iv
            iv_count += 1

        if opt_type == "put":
            if strike in strike_put_oi:
                strike_put_oi[strike] += oi
                strike_put_gex[strike] += gex_val
            else:
                strike_put_oi[strike] = oi
                strike_put_gex[strike] = gex_val
            total_put_gex += gex_val
            effective_put_gex += effective_gex_val
            sum_strike_put_oi += strike * oi
            sum_put_oi += oi
        elif opt_type == "call":
            if strike in strike_call_oi:
                strike_call_oi[strike] += oi
                strike_call_gex[strike] += gex_val
            else:
                strike_call_oi[strike] = oi
                strike_call_gex[strike] = gex_val
            total_call_gex += gex_val
            effective_call_gex += effective_gex_val

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
            "effective_call_gex": 0.0,
            "effective_put_gex": 0.0,
            "net_gex": 0.0,
            "net_effective_gex": 0.0,
            "flip_strikes": [],
            "put_wall": calc_spot * 0.95,
            "rule1_derived": False,
            "rule2_derived": False,
            "rule7_derived": False,
            "rule9_derived": False,
            "rule10_derived": False,
        }

    # COTMP = weighted put strike
    derived_cotmp = sum_strike_put_oi / sum_put_oi if sum_put_oi > 0 else calc_spot * 0.95

    # Put Wall = strike at/below spot with largest put OI
    put_wall = None
    max_pw_key = (-1, -1.0)
    for strike, oi in strike_put_oi.items():
        if strike <= calc_spot:
            key = (oi, strike)
            if key > max_pw_key:
                max_pw_key = key
                put_wall = strike
    if put_wall is None:
        put_wall = calc_spot * 0.95

    # Secondary Put Wall = strike below put_wall with next largest put OI
    secondary_put_wall = None
    max_spw_key = (-1, -1.0)
    for strike, oi in strike_put_oi.items():
        if strike < put_wall:
            key = (oi, strike)
            if key > max_spw_key:
                max_spw_key = key
                secondary_put_wall = strike
    if secondary_put_wall is None:
        secondary_put_wall = put_wall * 0.95

    # pTrans & nTrans via continuous zero-crossing linear interpolation
    all_strikes_set = set(strike_put_gex.keys())
    all_strikes_set.update(strike_call_gex.keys())
    all_strikes = sorted(all_strikes_set)

    net_gex_items = [
        (s, strike_call_gex.get(s, 0.0) - strike_put_gex.get(s, 0.0))
        for s in all_strikes
    ]
    flip_strikes = find_flip_strikes(net_gex_items)
    derived_ptrans, derived_ntrans = select_transition_points(
        flip_strikes=flip_strikes,
        spot=calc_spot,
        cotmp=derived_cotmp,
        put_wall=put_wall,
        secondary_put_wall=secondary_put_wall,
    )

    # +GEX = strike at/above spot with largest call OI
    derived_gex = None
    max_gex_key = (-1, float('-inf'))
    for strike, oi in strike_call_oi.items():
        if strike >= calc_spot:
            key = (oi, -strike)
            if key > max_gex_key:
                max_gex_key = key
                derived_gex = strike
    if derived_gex is None:
        derived_gex = calc_spot * 1.05

    rule1_derived = total_call_gex > 0
    rule2_derived = total_call_gex > abs(total_put_gex)
    rule7_derived = total_oi > 10000

    call_oi_at_target = strike_call_oi.get(derived_gex, 0)
    max_call_oi = max(strike_call_oi.values()) if strike_call_oi else 0
    rule9_derived = call_oi_at_target >= max_call_oi if max_call_oi > 0 else True

    nearest_strike = calc_spot
    min_dist_key = (float('inf'), float('inf'))
    for strike in all_strikes:
        diff = strike - calc_spot
        dist = diff if diff >= 0 else -diff
        dist_key = (dist, strike)
        if dist_key < min_dist_key:
            min_dist_key = dist_key
            nearest_strike = strike

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
        "effective_call_gex": effective_call_gex,
        "effective_put_gex": effective_put_gex,
        "net_gex": total_call_gex - total_put_gex,
        "net_effective_gex": effective_call_gex - effective_put_gex,
        "flip_strikes": flip_strikes,
        "put_wall": put_wall,
        "rule1_derived": rule1_derived,
        "rule2_derived": rule2_derived,
        "rule7_derived": rule7_derived,
        "rule9_derived": rule9_derived,
        "rule10_derived": rule10_derived,
    }
