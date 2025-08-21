from __future__ import annotations

import argparse, os, re, sys, time, json
from dataclasses import dataclass, field, asdict
from math import floor
from typing import Optional, Dict, Any, List, Iterable, Callable, Tuple, Literal
from datetime import datetime
from trends import Trend, trend_of
from options import OptionContract
from stock_config import StockConfig
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # match your actual module name/path; use local if files sit together
    from trade_asset import DayTradeAsset

# --------------------------- Stocks + Options model --------------------------
Side = Literal["LONG","SHORT"]
Right = Literal["C","P"]


@dataclass
class Stock:
    def __init__(
        self,
        symbol : Optional[str] = None,
    ) -> None:
        self.symbol = symbol

    # Identity & trading meta (stock)
    symbol: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    tick_size: float = 0.01
    lot_size: int = 1
    tags: List[str] = field(default_factory=list)
    notes: Optional[str] = None
    catalyst: Optional[str] = None

    # Liquidity snapshot (optional)
    avg_vol_20d: Optional[int] = None
    premarket_vol: Optional[int] = None
    float_shares_millions: Optional[float] = None

    # Live/last quote snapshot (stock)
    last: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    vwap: Optional[float] = None
    atr: Optional[float] = None
    updated_at: Optional[str] = None

    # Intraday levels (stock)
    premarket_high: Optional[float] = None
    premarket_low: Optional[float] = None
    open_range_high: Optional[float] = None
    open_range_low: Optional[float] = None
    yesterday_high: Optional[float] = None
    yesterday_low: Optional[float] = None

    # Risk config (shared)
    risk_pct_per_trade: float = 0.005
    max_dollars_risk: Optional[float] = None
    slippage_cents: float = 1.0
    fee_per_share: float = 0.0

    # Options defaults
    option_tick: float = 0.01
    option_multiplier: int = 100
    opt_target_delta: float = 0.30
    opt_prefer_dte: int = 0
    opt_max_debit: Optional[float] = None
    opt_price_policy: Literal["MID","BID","ASK","MARK","LAST"] = "MID"

    # Trend state (derived)
    trend: Trend = None
    previous_trend: Trend = None

    # Asset configuration
    # stock_config = StockConfig(symbol)

    _cached: Dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.config is None:
            # runtime import to avoid circular import problems
            try:
                from stock_config import StockConfig
            except ImportError:
                from stock_config import StockConfig  # fallback if you use src.*
            # try common constructor shapes
            try:
                self.config = StockConfig(symbol=self.symbol)
            except TypeError:
                try:
                    self.config = StockConfig(sym=self.symbol)
                except TypeError:
                    self.config = StockConfig()
                    if hasattr(self.config, "symbol"): self.config.symbol = self.symbol

    # Utilities
    def touch(self) -> None: self.updated_at = datetime.utcnow().isoformat(timespec="seconds")+"Z"
    def add_tag(self, tag: str) -> None:
        if tag not in self.tags: self.tags.append(tag)
    def remove_tag(self, tag: str) -> None:
        if tag in self.tags: self.tags.remove(tag)
    def round_price(self, price: float) -> float: return round(round(price / self.tick_size) * self.tick_size, 10)
    def round_qty(self, qty: int) -> int:
        qty = int(qty); return max(self.lot_size, (qty // self.lot_size) * self.lot_size)
    def update_quote(self, last: Optional[float]=None, bid: Optional[float]=None, ask: Optional[float]=None, vwap: Optional[float]=None) -> None:
        if last is not None: self.last = float(last)
        if bid is not None: self.bid = float(bid)
        if ask is not None: self.ask = float(ask)
        if vwap is not None: self.vwap = float(vwap)
        self.touch()
    def set_levels(self, pre_hi: Optional[float]=None, pre_lo: Optional[float]=None, orb_hi: Optional[float]=None, orb_lo: Optional[float]=None, y_hi: Optional[float]=None, y_lo: Optional[float]=None) -> None:
        if pre_hi is not None: self.premarket_high = self.round_price(pre_hi)
        if pre_lo is not None: self.premarket_low = self.round_price(pre_lo)
        if orb_hi is not None: self.open_range_high = self.round_price(orb_hi)
        if orb_lo is not None: self.open_range_low = self.round_price(orb_lo)
        if y_hi is not None: self.yesterday_high = self.round_price(y_hi)
        if y_lo is not None: self.yesterday_low = self.round_price(y_lo)
        self.touch()

    # Trend getters/setters
    def get_trend(self) -> Trend: return self.trend
    def get_previous_trend(self) -> Trend: return self.previous_trend
    def set_trend(self, new_trend: Trend) -> Trend:
        self.previous_trend = self.trend; self.trend = new_trend; return self.trend
    def update_trend_from_record(self, rec: Dict[str, Any]) -> Trend:
        return self.set_trend(trend_of(rec))
    def is_uptrend(self) -> bool: return self.trend == "UP"
    def is_downtrend(self) -> bool: return self.trend == "DOWN"
    def reversed_trend(self) -> bool:
        return (self.previous_trend is not None) and (self.trend is not None) and (self.trend != self.previous_trend)

    # Risk & sizing (stock)
    def risk_dollars(self, account_equity: float, risk_pct: Optional[float]=None) -> float:
        rp = self.risk_pct_per_trade if risk_pct is None else risk_pct
        dollars = account_equity * rp
        if self.max_dollars_risk is not None: dollars = min(dollars, self.max_dollars_risk)
        return max(0.0, float(dollars))
    def size_for_entry(self, entry: float, stop: float, account_equity: float, risk_pct: Optional[float]=None, include_costs: bool=True) -> int:
        entry = self.round_price(entry); stop = self.round_price(stop)
        per_share_risk = abs(entry - stop)
        if include_costs: per_share_risk += (self.slippage_cents/100.0) + self.fee_per_share
        if per_share_risk <= 0: return 0
        qty = floor(self.risk_dollars(account_equity, risk_pct) / per_share_risk)
        return self.round_qty(qty)

    # Targets (stock)
    def compute_targets(self, side: Side, entry: float, stop: float, rr: float=2.0, extra_targets: Optional[List[float]]=None) -> Dict[str, Any]:
        entry = self.round_price(entry); stop = self.round_price(stop); risk = abs(entry - stop)
        if risk <= 0: return {"tp": None, "custom": []}
        tp = self.round_price(entry + rr*risk) if side=="LONG" else self.round_price(entry - rr*risk)
        custom = []
        if extra_targets:
            for r in extra_targets:
                custom.append(self.round_price(entry + (r*risk) if side=="LONG" else entry - (r*risk)))
        return {"tp": tp, "custom": custom}

    # Order payloads (stock)
    def order_bracket_stock(self, side: Side, entry: float, stop: float, qty: int, rr: float=2.0, tif: str="DAY", order_type: str="LIMIT") -> Dict[str, Any]:
        entry = self.round_price(entry); stop = self.round_price(stop); tgt = self.compute_targets(side, entry, stop, rr=rr)
        return {
            "asset_type": "STOCK", "symbol": self.symbol, "side": "BUY" if side=="LONG" else "SELL_SHORT",
            "qty": int(qty), "type": order_type, "limit_price": entry if order_type=="LIMIT" else None, "time_in_force": tif,
            "bracket": {"take_profit": {"price": tgt["tp"]} if tgt["tp"] else None, "stop_loss": {"price": stop}},
            "meta": {"tick_size": self.tick_size, "lot_size": self.lot_size, "tags": list(self.tags), "notes": self.notes}
        }

    # Options helpers
    def _round_option(self, px: float) -> float: return round(round(px / self.option_tick) * self.option_tick, 10)
    def pick_option(self, chain: Iterable[Dict[str, Any] | OptionContract], right: Right, target_delta: Optional[float]=None, prefer_dte: Optional[int]=None, max_debit: Optional[float]=None) -> Optional[OptionContract]:
        td = self.opt_target_delta if target_delta is None else target_delta
        pd = self.opt_prefer_dte if prefer_dte is None else prefer_dte
        cap = self.opt_max_debit if max_debit is None else max_debit
        norm: List[OptionContract] = []
        for x in chain:
            oc = x if isinstance(x, OptionContract) else OptionContract(symbol=x.get("symbol", self.symbol), expiry=x["expiry"], strike=float(x["strike"]), right=x["right"], multiplier=int(x.get("multiplier", self.option_multiplier)), bid=x.get("bid"), ask=x.get("ask"), mark=x.get("mark"), last=x.get("last"), delta=x.get("delta"), gamma=x.get("gamma"), theta=x.get("theta"), vega=x.get("vega"), iv=x.get("iv"), volume=x.get("volume"), open_interest=x.get("open_interest"), dte=x.get("dte"))
            if oc.right == right: norm.append(oc)
        if not norm: return None
        if any(c.dte is not None for c in norm):
            best_dte = min({c.dte for c in norm if c.dte is not None}, key=lambda d: abs(d - pd))
            norm = [c for c in norm if c.dte == best_dte] or norm
        if cap is not None:
            norm = [c for c in norm if (c.premium_for(self.opt_price_policy) or 0) <= cap] or norm
        def delta_err(c: OptionContract) -> float:
            if c.delta is None: return 1e9
            want = td if right=="C" else -abs(td)
            return abs(c.delta - want)
        chosen = min(norm, key=delta_err)
        prem = chosen.premium_for(self.opt_price_policy)
        if prem is None:
            for pol in ("MARK","LAST","MID","ASK","BID"):
                prem = chosen.premium_for(pol)
                if prem is not None: break
        chosen.mark = prem if chosen.mark is None else chosen.mark
        return chosen
    def size_options_single(self, premium: float, account_equity: float, risk_pct: Optional[float]=None) -> int:
        risk_cap = self.risk_dollars(account_equity, risk_pct)
        per_contract_risk = max(0.0, premium) * self.option_multiplier
        if per_contract_risk <= 0: return 0
        return max(0, floor(risk_cap / per_contract_risk))
    def order_option_single(self, contract: OptionContract, qty: int, price_policy: Optional[Literal["MID","BID","ASK","MARK","LAST"]]=None, limit_price: Optional[float]=None, tif: str="DAY", order_type: str="LIMIT") -> Dict[str, Any]:
        pol = self.opt_price_policy if price_policy is None else price_policy
        px = self._round_option(contract.premium_for(pol) if limit_price is None else limit_price)
        return {
            "asset_type": "OPTION", "underlying": contract.symbol,
            "option": {"expiry": contract.expiry, "strike": float(contract.strike), "right": contract.right, "multiplier": int(contract.multiplier)},
            "side": "BUY_TO_OPEN", "qty": int(qty), "type": order_type, "limit_price": px if order_type=="LIMIT" else None, "time_in_force": tif,
            "meta": {"price_policy": pol, "delta": contract.delta, "iv": contract.iv, "dte": contract.dte, "tags": list(self.tags), "notes": self.notes}
        }
    def build_option_long(self, right: Right, chain: Iterable[Dict[str, Any] | OptionContract], account_equity: float, risk_pct: Optional[float]=None, price_policy: Optional[Literal["MID","BID","ASK","MARK","LAST"]]=None, tif: str="DAY", order_type: str="LIMIT") -> Optional[Dict[str, Any]]:
        chosen = self.pick_option(chain, right)
        if not chosen: return None
        pol = self.opt_price_policy if price_policy is None else price_policy
        premium = chosen.premium_for(pol)
        if premium is None: return None
        premium = self._round_option(premium)
        qty = self.size_options_single(premium, account_equity, risk_pct)
        preview = {"underlying": self.symbol, "contract": {"expiry": chosen.expiry, "strike": chosen.strike, "right": chosen.right}, "premium": premium, "contracts": qty, "notional_debit": round(premium * self.option_multiplier * qty, 2), "delta": chosen.delta, "dte": chosen.dte}
        order = self.order_option_single(chosen, qty, price_policy=pol, tif=tif, order_type=order_type)
        return {"preview": preview, "order": order}

    # Persistence
    def to_dict(self) -> Dict[str, Any]: d = asdict(self); d.pop("_cached", None); return d
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DayTradeAsset": return cls(**d)
    @staticmethod
    def save_watchlist(items: List["DayTradeAsset"], path: str) -> None:
        with open(path, "w", encoding="utf-8") as f: json.dump([i.to_dict() for i in items], f, indent=2)
    @staticmethod
    def load_watchlist(path: str) -> List["DayTradeAsset"]:
        with open(path, "r", encoding="utf-8") as f: data = json.load(f)
        return [DayTradeAsset.from_dict(x) for x in data]