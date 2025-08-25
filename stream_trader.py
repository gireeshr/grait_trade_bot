from __future__ import annotations

import os, sys, time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Dict, Optional, List, Any

# ---- Required: your helpers from price_alerts.py (already added earlier) ----
import price_alerts as pa

# ---- type-only imports for Pylance; do NOT import these at runtime
if TYPE_CHECKING:
    from indicators import Indicator
    from trade_asset import DayTradeAsset



# ----------------------------- Utilities -----------------------------

def _apply(obj: Any, name: str, value: Any) -> None:
    """Set attribute via set_<name>() if present, else setattr if allowed."""
    if value is None: return
    setter = getattr(obj, f"set_{name}", None)
    if callable(setter):
        try: setter(value); return
        except Exception: pass
    if hasattr(obj, name):
        try: setattr(obj, name, value)
        except Exception: pass


@dataclass
class TradeSignal:
    symbol: str
    action: str          # "BUY_CALL" | "BUY_PUT" | "EXIT" | "HOLD"
    reason: str
    timestamp: Any       # datetime
    price: float
    extras: Dict[str, Any]


# ----------------------------- Trend helpers -----------------------------

def derive_trend(price: float, ema9: float, ema20: float, sma20: float) -> str:
    """Simple, readable trend heuristic. Customize as needed."""
    if ema9 > ema20 > sma20 and price >= ema9:
        return "uptrend"
    if ema9 < ema20 < sma20 and price <= ema9:
        return "downtrend"
    return "neutral"


# ----------------------------- Criteria (pluggable) -----------------------------

# 1) Stacked MAs (EMA9>EMA20>SMA20 bullish; inverse bearish). Exit on reversal.
def criteria_stacked(rec: dict, ind: "Indicator", asset: "DayTradeAsset", prev_trend: Optional[str]) -> "TradeSignal":
    sym, price, ema9, ema20, sma20 = rec["symbol"], rec["price"], rec["ema9"], rec["ema20"], rec["sma20"]
    trend = derive_trend(price, ema9, ema20, sma20)

    if prev_trend and trend != prev_trend and prev_trend in {"uptrend", "downtrend"}:
        return TradeSignal(sym, "EXIT", f"Trend reversed {prev_trend} -> {trend}", rec["ts"], price,
                           {"trend": trend, "prev_trend": prev_trend})

    if trend == "uptrend":
        return TradeSignal(sym, "BUY_CALL", "Stacked bullish trend", rec["ts"], price,
                           {"trend": trend})
    if trend == "downtrend":
        return TradeSignal(sym, "BUY_PUT", "Stacked bearish trend", rec["ts"], price,
                           {"trend": trend})
    return TradeSignal(sym, "HOLD", "Neutral trend", rec["ts"], price, {"trend": trend})


# 2) EMA crossover (9/20) with SMA20 as higher-timeframe filter. Exit on opposite cross.
def criteria_crossover(rec: dict, ind: "Indicator", asset: "DayTradeAsset", prev_trend: Optional[str]) -> "TradeSignal":
    sym, price, ema9, ema20, sma20 = rec["symbol"], rec["price"], rec["ema9"], rec["ema20"], rec["sma20"]
    # Infer "signal" from last two EMA points if available; fall back to level check
    # (Indicator series are assumed to have .values or behave like lists)
    # We won't mutate Indicator; we just read.
    try:
        # Try to detect cross using the previous bar if present
        ema9_prev = ind.ema9.values[-2] if hasattr(ind.ema9, "values") and len(ind.ema9.values) >= 2 else None  # type: ignore
        ema20_prev = ind.ema20.values[-2] if hasattr(ind.ema20, "values") and len(ind.ema20.values) >= 2 else None  # type: ignore
    except Exception:
        ema9_prev = ema20_prev = None

    bullish_now = ema9 > ema20 and price >= sma20
    bearish_now = ema9 < ema20 and price <= sma20

    crossed_up = ema9_prev is not None and ema20_prev is not None and ema9_prev <= ema20_prev and ema9 > ema20
    crossed_dn = ema9_prev is not None and ema20_prev is not None and ema9_prev >= ema20_prev and ema9 < ema20

    if crossed_up and bullish_now:
        return TradeSignal(sym, "BUY_CALL", "EMA9 crossed above EMA20 (filtered by SMA20)", rec["ts"], price, {})
    if crossed_dn and bearish_now:
        return TradeSignal(sym, "BUY_PUT", "EMA9 crossed below EMA20 (filtered by SMA20)", rec["ts"], price, {})

    # Exit if cross the other way relative to prior trend
    if prev_trend == "uptrend" and bearish_now:
        return TradeSignal(sym, "EXIT", "Bullish -> bearish regime shift", rec["ts"], price, {})
    if prev_trend == "downtrend" and bullish_now:
        return TradeSignal(sym, "EXIT", "Bearish -> bullish regime shift", rec["ts"], price, {})

    trend = "uptrend" if bullish_now else "downtrend" if bearish_now else "neutral"
    return TradeSignal(sym, "HOLD", "No actionable cross", rec["ts"], price, {"trend": trend})


# ----------------------------- Runner -----------------------------

def run_streaming_trader(
    symbols: List[str],
    assets_by_symbol: Dict[str, "DayTradeAsset"],
    criteria: Callable[[dict, "Indicator", "DayTradeAsset", Optional[str]], "TradeSignal"] = criteria_stacked,
    on_signal: Optional[Callable[["TradeSignal", "DayTradeAsset", "Indicator", dict], None]] = None,
    date_suffix: Optional[str] = None,
    interval_override: Optional[float] = None,
) -> None:
    """
    Continuously read alert files, update Indicator + DayTradeAsset, and emit trade signals.
    - symbols: list of tickers to watch
    - assets_by_symbol: mapping 'SYM' -> DayTradeAsset (provide your existing assets)
    - criteria: plug-and-play decision function (see above)
    - on_signal: callback(signal, asset, indicator, rec) to place/cancel orders
    - date_suffix: 'YYYYMMDD' to replay a specific day; None = today
    - interval_override: if you want faster polling than price_alerts.POLL_INTERVAL
    """
    if interval_override is not None:
        try:
            pa.POLL_INTERVAL = interval_override  # type: ignore[attr-defined]
        except Exception:
            pass

    # We keep one Indicator per symbol (created inside price_alerts.stream_indicator_updates)
    # We'll track last trend to generate clean EXIT on reversals.
    last_trend: Dict[str, str] = {}

    def _update_asset_from_rec(asset: DayTradeAsset, rec: dict, trend: Optional[str]) -> None:
        # Push latest numbers onto the asset if fields/methods exist. No class changes required.
        _apply(asset, "last_price", rec["price"])
        _apply(asset, "price", rec["price"])
        _apply(asset, "sma20", rec["sma20"])
        _apply(asset, "ema20", rec["ema20"])
        _apply(asset, "ema9", rec["ema9"])
        if trend is not None:
            # Respect your existing naming if present
            _apply(asset, "trend", trend)
            # Preserve previous trend if supported
            if hasattr(asset, "previous_trend"):
                try:
                    prev = getattr(asset, "trend", None)
                    if prev and prev != trend:
                        _apply(asset, "previous_trend", prev)
                except Exception:
                    pass

    def _on_update(sym: str, ind: Indicator, rec: dict) -> None:
        SYM = sym.upper()
        asset = assets_by_symbol.get(SYM)
        if asset is None:
            return  # symbol not in your watchlist, skip

        # Decide trend (for logging / asset update convenience)
        trend = derive_trend(rec["price"], rec["ema9"], rec["ema20"], rec["sma20"])
        _update_asset_from_rec(asset, rec, trend)

        # Build signal with your chosen criteria
        signal = criteria(rec, ind, asset, last_trend.get(SYM))

        # Update last_trend from signal.extras/trend if any
        if signal.action != "HOLD":
            if "trend" in signal.extras:
                last_trend[SYM] = signal.extras["trend"]
            else:
                # fall back to derived trend
                last_trend[SYM] = trend

        # Hand off to your trading system
        if on_signal:
            try:
                on_signal(signal, asset, ind, rec)
            except Exception as e:
                print(f"[{SYM}] on_signal error: {e}")

    # Kick off continuous loop using your existing reader
    pa.stream_indicator_updates(symbols, date_suffix=date_suffix, on_update=_on_update)


# ----------------------------- Example callback -----------------------------

def print_signal(signal: "TradeSignal", asset: "DayTradeAsset", ind: "Indicator", rec: dict) -> None:
    """
    Default on_signal callback that just logs.
    Replace this with an executor that places/cancels orders via your broker.
    """
    extra = f" trend={signal.extras.get('trend')}" if signal.extras else ""
    print(f"[{signal.symbol}] {signal.timestamp:%H:%M:%S} {signal.action} @ {signal.price}{extra}")
