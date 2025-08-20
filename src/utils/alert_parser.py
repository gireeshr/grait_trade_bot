import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# Example line:
# CRCL - MA Alert - 1 - price: 139.00 - SMA_20: 140.80,  EMA_20: 141.12, EMA_9: 138.78 - 20250815040103

LINE_RE = re.compile(
    r"""
    ^
    (?P<symbol>[A-Z]+(?:\.[A-Z]+)?)\s*-\s*MA\s+Alert\s*-\s*(?P<alert>\d+)\s*-\s*
    price:\s*(?P<price>-?\d+(?:\.\d+)?)\s*-\s*
    SMA_20:\s*(?P<sma20>-?\d+(?:\.\d+)?),\s*EMA_20:\s*(?P<ema20>-?\d+(?:\.\d+)?),\s*EMA_9:\s*(?P<ema9>-?\d+(?:\.\d+)?)
    \s*-\s*
    (?P<ts>\d{14})
    $
    """,
    re.VERBOSE,
)

@dataclass(frozen=True)
class ParsedAlert:
    symbol: str
    price: float
    sma20: float
    ema20: float
    ema9: float
    ts: datetime
    alert_id: int

def parse_alert_line(line: str) -> Optional[ParsedAlert]:
    m = LINE_RE.match(line.strip())
    if not m: return None
    ts = datetime.strptime(m.group("ts"), "%Y%m%d%H%M%S")
    return ParsedAlert(
        symbol=m.group("symbol"),
        price=float(m.group("price")),
        sma20=float(m.group("sma20")),
        ema20=float(m.group("ema20")),
        ema9=float(m.group("ema9")),
        ts=ts,
        alert_id=int(m.group("alert")),
    )
