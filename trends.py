#!/usr/bin/env python3
from __future__ import annotations

import argparse, os, re, sys, time, json
from dataclasses import dataclass, field, asdict
from math import floor
from typing import Optional, Dict, Any, List, Iterable, Callable, Tuple, Literal
from datetime import datetime

# ------------------------------- Trends --------------------------------------
def is_downtrend(rec: Dict[str, Any]) -> bool: return rec["sma20"] > rec["ema20"] > rec["ema9"]
def is_uptrend(rec: Dict[str, Any]) -> bool: return rec["sma20"] < rec["ema20"] < rec["ema9"]
Trend = Optional[Literal["UP","DOWN"]]

def trend_of(rec: Dict[str, Any]) -> Trend:
    if is_uptrend(rec): return "UP"
    if is_downtrend(rec): return "DOWN"
    return None

# ------------------------------ File outputs ---------------------------------
def write_trend_lines(records: List[Dict[str, Any]], out_path: str, trend_fn: Callable[[Dict[str, Any]], bool]) -> int:
    n = 0
    with open(out_path, "w", encoding="utf-8") as out:
        for row in records:
            if trend_fn(row["rec"]):
                out.write(row["raw"] + "\n")
                n += 1
    return n

def find_streaks(records: List[Dict[str, Any]], trend_fn: Callable[[Dict[str, Any]], bool]) -> List[Tuple[List[int], float, float]]:
    """
    Returns list of (indices_in_streak, start_price, end_price)
    start_price: first price OUTSIDE the streak on the left (if available), else first inside.
    end_price:   first price OUTSIDE the streak on the right (if available), else last inside.
    """
    streaks: List[Tuple[List[int], float, float]] = []
    cur: List[int] = []

    def finalize(cur_idx: List[int]):
        if not cur_idx: return
        left_idx = cur_idx[0] - 1
        right_idx = cur_idx[-1] + 1
        start_price = records[cur_idx[0]]["rec"]["price"]
        end_price = records[cur_idx[-1]]["rec"]["price"]
        if left_idx >= 0: start_price = records[left_idx]["rec"]["price"]
        if right_idx < len(records): end_price = records[right_idx]["rec"]["price"]
        streaks.append((cur_idx.copy(), start_price, end_price))

    for i, row in enumerate(records):
        if trend_fn(row["rec"]): cur.append(i)
        else: finalize(cur); cur = []
    finalize(cur)
    return streaks

def write_streaks(records: List[Dict[str, Any]], out_path: str, trend_name: str, trend_fn: Callable[[Dict[str, Any]], bool]) -> int:
    streaks = find_streaks(records, trend_fn)
    with open(out_path, "w", encoding="utf-8") as out:
        for i, (idxs, start_price, end_price) in enumerate(streaks, start=1):
            header = f"===== {trend_name} Streak #{i} | length: {len(idxs)} | start_price: {start_price:.2f} | end_price: {end_price:.2f} ====="
            out.write(header + "\n")
            for idx in idxs: out.write(records[idx]["raw"] + "\n")
            out.write("\n")
    return len(streaks)


# ------------------------------- Position state ------------------------------
@dataclass
class PositionState:
    side: Optional[Literal["CALL","PUT"]] = None
    last_trend: Trend = None

def handle_trend(trend: Trend, state: PositionState, symbol: str, broker: BrokerInterface, qty: int = 1, context: Optional[Dict[str, Any]] = None, reenter_on_reverse: bool = True) -> str:
    """
    Acts on the new trend:
      - Uptrend -> BUY CALL
      - Downtrend -> BUY PUT
      - Reversal -> EXIT then (optionally) re-enter
    Returns action label.
    """
    context = context or {}
    if trend is None:
        state.last_trend = None
        return "NO_TREND"

    desired_side: Optional[Literal["CALL","PUT"]] = "CALL" if trend == "UP" else "PUT"

    if state.side is None:
        (broker.buy_call if desired_side=="CALL" else broker.buy_put)(symbol, qty, context)
        state.side = desired_side; state.last_trend = trend
        return f"OPENED_{desired_side}"

    if state.side == desired_side:
        state.last_trend = trend
        return "HELD"

    broker.exit_position(symbol, context)
    state.side = None
    if not reenter_on_reverse:
        state.last_trend = trend
        return "REVERSED_EXITED"

    (broker.buy_call if desired_side=="CALL" else broker.buy_put)(symbol, qty, context)
    state.side = desired_side; state.last_trend = trend
    return "REVERSED_EXITED_OPENED"