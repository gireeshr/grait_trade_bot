from __future__ import annotations

import argparse, os, re, sys, time, json
from dataclasses import dataclass, field, asdict
from math import floor
from typing import Optional, Dict, Any, List, Iterable, Callable, Tuple, Literal
from datetime import datetime
from trends import Trend, trend_of


@dataclass
class OptionContract:
    symbol: str
    expiry: str
    strike: float
    right: Right
    multiplier: int = 100
    bid: Optional[float] = None
    ask: Optional[float] = None
    mark: Optional[float] = None
    last: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    iv: Optional[float] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None
    dte: Optional[int] = None
    def mid(self) -> Optional[float]:
        if self.bid is not None and self.ask is not None: return (self.bid + self.ask) / 2.0
        return self.mark if self.mark is not None else self.last
    def premium_for(self, price_policy: Literal["MID","BID","ASK","MARK","LAST"]="MID") -> Optional[float]:
        return {"MID": self.mid(), "BID": self.bid, "ASK": self.ask, "MARK": self.mark, "LAST": self.last}[price_policy]