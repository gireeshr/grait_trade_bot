from dataclasses import dataclass, field
from collections import deque
from datetime import datetime
from typing import Deque, Optional, Iterable

@dataclass
class IndicatorSeries:
    maxlen: int = 200
    values: Deque[float] = field(default_factory=lambda: deque(maxlen=200))
    timestamps: Deque[datetime] = field(default_factory=lambda: deque(maxlen=200))

    def update(self, value: float, ts: datetime) -> None:
        self.values.append(value)
        self.timestamps.append(ts)

    def current(self) -> Optional[float]:
        return self.values[-1] if self.values else None

    def prev(self, n: int = 1) -> Optional[float]:
        if n <= 0 or n > len(self.values): return None
        return list(self.values)[-n-0]

    def last_n(self, n: int) -> Iterable[float]:
        if n <= 0: return []
        return list(self.values)[-n:]

@dataclass
class Indicator:
    # we mirror your file-provided indicators directly
    price: IndicatorSeries = field(default_factory=lambda: IndicatorSeries(maxlen=2048))
    sma20: IndicatorSeries = field(default_factory=lambda: IndicatorSeries(maxlen=2048))
    ema20: IndicatorSeries = field(default_factory=lambda: IndicatorSeries(maxlen=2048))
    ema9: IndicatorSeries  = field(default_factory=lambda: IndicatorSeries(maxlen=2048))
