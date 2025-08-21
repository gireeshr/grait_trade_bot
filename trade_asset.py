from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
from indicators import Indicator
from dataclasses import dataclass, field, asdict
from typing import TYPE_CHECKING, Optional, Dict, Any

if TYPE_CHECKING:
    from stocks import Stock                  # adjust path to your actual module
    from stock_config import StockConfig      # adjust path to your actual module

@dataclass
class DayTradeAsset:
    # __slots__ = ("stock","config","qty","entry_price","last_price","trend","previous_trend")  # include all fields you define
    stock: "Stock"
    config: "StockConfig"
    indicators: Indicator = field(default_factory=Indicator)
    qty: int = 0
    entry_price: Optional[float] = None
    last_price: Optional[float] = None
    trend: str | None = None
    previous_trend: str | None = None

    @property
    def symbol(self) -> str: return self.stock.symbol

    @property
    def pnl(self) -> Optional[float]:
        if self.entry_price is None or self.last_price is None or self.qty == 0: return None
        return (self.last_price - self.entry_price) * self.qty

    def update_price(self, price: float) -> None:
        if price <= 0: raise ValueError("Price must be positive")
        self.last_price = price

    def to_log(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol, "qty": self.qty, "entry_price": self.entry_price, "last_price": self.last_price, "pnl": self.pnl,
            "sma20": self.indicators.sma20.current(), "ema20": self.indicators.ema20.current(), "ema9": self.indicators.ema9.current()
        }