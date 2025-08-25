#!/usr/bin/env python3
from __future__ import annotations

import argparse, os, sys, time
from typing import TYPE_CHECKING, List, Optional

# Import your helpers (they must exist in price_alerts.py as added earlier)
import price_alerts as pa

if TYPE_CHECKING:
    from indicators import Indicator


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Test reader/streamer for MA alert files -> Indicator values"
    )
    p.add_argument("--symbols", required=True, help="Comma-separated symbols, e.g. TSLA,AAPL,SPY")
    p.add_argument("--date", dest="date_suffix", default=None, help="YYYYMMDD (defaults to today)")
    p.add_argument("--dir", dest="workdir", default=None, help="Directory containing <SYMBOL>_price_<YYYYMMDD>.txt")
    p.add_argument("--once", action="store_true", help="Read once and exit")
    p.add_argument("--stream", action="store_true", help="Continuously stream updates")
    p.add_argument("--interval", type=float, default=None, help="Override POLL_INTERVAL (seconds) for streaming")
    return p.parse_args()


def pretty_dump(rec: dict) -> str:
    return (f"{rec['symbol']} ts={rec['ts']:%Y-%m-%d %H:%M:%S} "
            f"price={rec['price']} sma20={rec['sma20']} ema20={rec['ema20']} ema9={rec['ema9']} alert={rec['alert']}")


def read_once(symbols: List[str], date_suffix: Optional[str]) -> None:
    print("== Read once ==")
    for s in symbols:
        price = pa.get_s_price(s, date_suffix=date_suffix)
        rec = pa.get_indicator_values(s, date_suffix=date_suffix)
        if price is None and rec is None:
            print(f"{s}: no data")
            continue
        if price is not None:
            print(f"{s}: last price = {price}")
        if rec is not None:
            print("   ", pretty_dump(rec))


def stream(symbols: List[str], date_suffix: Optional[str], interval_override: Optional[float]) -> None:
    if interval_override is not None:
        # monkey-patch the polling cadence without touching existing logic
        try:
            pa.POLL_INTERVAL = interval_override  # type: ignore[attr-defined]
            print(f"(Using POLL_INTERVAL={interval_override}s)")
        except Exception:
            print("Could not override POLL_INTERVAL; proceeding with default.")

    def on_update(sym: str, ind: "Indicator", rec: dict) -> None:
        print(pretty_dump(rec))
        # If you want to peek at the Indicator series lengths, uncomment:
        # print(f"  lens: price={len(ind.price)} sma20={len(ind.sma20)} ema20={len(ind.ema20)} ema9={len(ind.ema9)}")

    print("== Streaming (Ctrl+C to stop) ==")
    try:
        pa.stream_indicator_updates(symbols, date_suffix=date_suffix, on_update=on_update)
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as e:
        print(f"Stream error: {e}")
        sys.exit(1)


def main() -> None:
    args = parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        print("No symbols provided.")
        sys.exit(2)

    # Optional: run in a different directory where the <SYMBOL>_price_<YYYYMMDD>.txt files sit
    if args.workdir:
        os.chdir(args.workdir)

    # Quick sanity: show which files we’ll read (use the same builder as price_alerts)
    try:
        builder = pa._symbol_file  # type: ignore[attr-defined]
        for s in symbols:
            print(f"{s} -> {builder(s, args.date_suffix)}")
    except Exception:
        pass

    if args.once:
        read_once(symbols, args.date_suffix)

    if args.stream:
        stream(symbols, args.date_suffix, args.interval)

    if not args.once and not args.stream:
        # default to --once if neither flag is provided
        read_once(symbols, args.date_suffix)


if __name__ == "__main__":
    main()
