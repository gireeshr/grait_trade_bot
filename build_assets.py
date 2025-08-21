# build_assets.py  (place this file in the same folder as: stocks.py, stock_config.py, trade_asset.py)
from __future__ import annotations
import os
from typing import List, Optional
from dotenv import load_dotenv

# ---- direct imports (adjust if your files are in a package) ----
from stocks import Stock
from stock_config import StockConfig
from trade_asset import DayTradeAsset

# ---- env helpers ----
def _getenv_any(keys: List[str], default: Optional[str] = None) -> Optional[str]:
    for k in keys:
        v = os.getenv(k)
        if v not in (None, ""): return v
    return default

def _as_int(v: Optional[str], default: Optional[int] = None) -> Optional[int]:
    try: return int(v) if v is not None else default
    except: return default

def _as_float(v: Optional[str], default: Optional[float] = None) -> Optional[float]:
    try: return float(v) if v is not None else default
    except: return default

def _as_bool(v: Optional[str], default: Optional[bool] = None) -> Optional[bool]:
    if v is None: return default
    return v.strip().lower() in {"1","true","yes","y","on"}

def _apply(obj, name: str, value) -> None:
    if value is None: return
    setter = getattr(obj, f"set_{name}", None)
    if callable(setter):
        try: setter(value); return
        except Exception: pass
    if hasattr(obj, name):
        try: setattr(obj, name, value)
        except Exception: pass

# ---- build StockConfig from .env for a symbol ----
def make_stock_config_from_env(symbol: str) -> StockConfig:
    s = symbol.upper()

    broker  = _getenv_any([f"BROKER_{s}", "BROKER"])
    webhook = _getenv_any([f"WEBHOOK_{s}", "WEBHOOK"]) or (_getenv_any([f"WEBHOOK_{broker.upper()}"]) if broker else None)

    qty            = _as_int(_getenv_any([f"QTY_{s}", f"{s}_QTY", "DEFAULT_QTY"]))
    risk_per_trade = _as_float(_getenv_any([f"RISK_PER_TRADE_{s}", "RISK_PER_TRADE"]))
    max_loss_trade = _as_float(_getenv_any([f"MAX_LOSS_PER_TRADE_{s}", "MAX_LOSS_PER_TRADE"]))
    tif           = _getenv_any([f"TIF_{s}", "TIF"])
    price_policy  = _getenv_any([f"PRICE_POLICY_{s}", "PRICE_POLICY"])
    tags_raw      = _getenv_any([f"TAGS_{s}", "TAGS"])
    notes         = _getenv_any([f"NOTES_{s}", "NOTES"])
    blocked       = _as_bool(_getenv_any([f"BLOCKED_{s}", "BLOCKED"]))

    # Try common ctor shapes
    try:
        cfg = StockConfig(sym=symbol, broker_name=broker, webhook=webhook)
    except TypeError:
        try:
            cfg = StockConfig(symbol=symbol, broker_name=broker, webhook=webhook)
        except TypeError:
            cfg = StockConfig()
            _apply(cfg, "sym", symbol); _apply(cfg, "symbol", symbol)
            _apply(cfg, "broker_name", broker); _apply(cfg, "webhook", webhook)

    _apply(cfg, "default_qty", qty); _apply(cfg, "qty", qty)
    _apply(cfg, "risk_per_trade", risk_per_trade)
    _apply(cfg, "max_loss_per_trade", max_loss_trade)
    _apply(cfg, "tif", tif)
    for pp in ("opt_price_policy", "price_policy"): _apply(cfg, pp, price_policy)
    if tags_raw: _apply(cfg, "tags", [t.strip() for t in tags_raw.split(",") if t.strip()])
    _apply(cfg, "notes", notes)
    _apply(cfg, "is_blocked", blocked); _apply(cfg, "is_bocked", blocked)
    return cfg

# ---- factory: build assets from list of symbols ----
def create_day_trade_assets(symbols: List[str]) -> List[DayTradeAsset]:
    load_dotenv()
    assets: List[DayTradeAsset] = []
    for sym in symbols:
        cfg = make_stock_config_from_env(sym)
        try:
            stock = Stock(symbol=sym)
        except TypeError:
            try: stock = Stock(sym=sym)
            except TypeError: stock = Stock(sym)  # positional
        asset = DayTradeAsset(stock=stock, config=cfg)
        qty = _as_int(_getenv_any([f"QTY_{sym.upper()}", f"{sym.upper()}_QTY", "DEFAULT_QTY"]))
        _apply(asset, "qty", qty)
        assets.append(asset)
    return assets

def symbols_from_env() -> List[str]:
    load_dotenv()
    raw = os.getenv("SYMBOLS")
    return [s.strip().upper() for s in raw.split(",")] if raw else []

if __name__ == "__main__":
    syms = symbols_from_env() or ["AAPL","TSLA","SPY"]
    for a in create_day_trade_assets(syms):
        sym = getattr(a.stock, "symbol", getattr(a.stock, "sym", "<?>"))
        qty = getattr(a, "qty", None)
        cfg = getattr(a, "config", None)
        broker = getattr(cfg, "broker_name", getattr(cfg, "broker", None)) if cfg else None
        webhook = getattr(cfg, "webhook", None) if cfg else None
        tick_size = getattr(a.stock, "tick_size", getattr(a.stock, "tick_size", "<?>"))
        print(f"{sym}: qty={qty} broker={broker} webhook={webhook} tick_size={tick_size}")
