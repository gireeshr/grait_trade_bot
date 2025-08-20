# test_file_stream.py
import argparse, asyncio, os, sys, contextlib
from datetime import datetime
from typing import Dict, Set, List, Optional, Callable, Awaitable

# Your modules
from alert_parser import parse_alert_line, ParsedAlert
from file_stream import merged_file_stream
from trade_asset import TradeAsset
from stock import Stock
from stock_config import StockConfig
from trading_engine import TradingEngine

def daily_filename(symbol: str, day: str | None = None, out_dir: str | None = None) -> str:
    day = day or datetime.utcnow().strftime("%Y%m%d")
    fname = f"{symbol}_price_{day}.txt"
    return os.path.join(out_dir or ".", fname)

def scan_symbols(consolidated_path: str) -> Set[str]:
    """First pass: collect all symbols present in the consolidated input file."""
    symbols: Set[str] = set()
    with open(consolidated_path, "r", encoding="utf-8") as f:
        for line in f:
            al = parse_alert_line(line)
            if al: symbols.add(al.symbol)
    return symbols

async def replay_consolidated(consolidated_path: str, symbol_to_path: Dict[str, str], delay_sec: float = 2.0) -> None:
    """
    Producer: reads the consolidated file line-by-line and appends each parsed
    alert into the correct per-symbol file, sleeping delay_sec between lines.
    """
    # Ensure clean files for a fresh run
    for p in symbol_to_path.values():
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").close()

    with open(consolidated_path, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.rstrip("\r\n")
            al = parse_alert_line(raw)
            if not al:
                print(f"[replay] Skipping unparsable line: {raw}", file=sys.stderr)
                await asyncio.sleep(delay_sec); continue

            out_file = symbol_to_path.get(al.symbol)
            if not out_file:
                print(f"[replay] Symbol {al.symbol} not mapped; skipping.", file=sys.stderr)
                await asyncio.sleep(delay_sec); continue

            with open(out_file, "a", encoding="utf-8") as out:
                out.write(raw + "\n")
                out.flush()
                os.fsync(out.fileno())

            print(f"[replay] -> {os.path.basename(out_file)} | {raw}")
            await asyncio.sleep(delay_sec)

async def consume_stream_print(symbol_to_path: Dict[str, str]) -> None:
    """Consumer mode: print alerts as they are detected by merged_file_stream."""
    async for batch in merged_file_stream(symbol_to_path):
        for al in batch:
            print(
                f"[stream] {al.symbol} @ {al.ts:%Y-%m-%d %H:%M:%S} | "
                f"price={al.price:.2f} sma20={al.sma20:.2f} ema20={al.ema20:.2f} ema9={al.ema9:.2f} "
                f"(alert_id={al.alert_id})"
            )

async def default_order_handler(asset: TradeAsset, action: str) -> None:
    """Mock async order handler for TradingEngine."""
    if action == "BUY" and asset.qty == 0:
        asset.qty = min(asset.config.max_qty, 10)
        asset.entry_price = asset.last_price
        print(f"[order] BUY {asset.symbol} {asset.qty} @ {asset.last_price:.2f}")
    elif action == "SELL_ALL" and asset.qty > 0:
        print(f"[order] SELL_ALL {asset.symbol} {asset.qty} @ {asset.last_price:.2f} | PnL={asset.pnl}")
        asset.qty = 0

async def consume_stream_engine(symbol_to_path: Dict[str, str], max_qty: int, broker: str, risk: float) -> None:
    """
    Consumer mode: wire merged_file_stream into TradingEngine.
    Creates TradeAssets dynamically from the symbol list and runs the engine.
    """
    # Build assets from symbols
    assets: List[TradeAsset] = []
    for sym in symbol_to_path.keys():
        assets.append(
            TradeAsset(
                stock=Stock(sym),
                config=StockConfig(max_qty=max_qty, risk_per_trade=risk, broker=broker),
            )
        )

    # Minimal engine: we reuse its on_alerts by feeding ParsedAlert batches as they arrive
    engine = TradingEngine(assets, order_handler=default_order_handler)

    # We re-implement a small runner here to avoid modifying your engine:
    async for batch in merged_file_stream(symbol_to_path):
        # Convert the alerts into the engine's expected flow:
        # trading_engine.TradingEngine already exposes on_alerts(List[ParsedAlert])
        await engine.on_alerts(batch)

async def main_async(consolidated_path: str, out_dir: str | None, day: str | None, delay_sec: float,
                     mode: str, max_qty: int, broker: str, risk: float) -> None:
    # 1) Discover symbols in consolidated file
    symbols = scan_symbols(consolidated_path)
    if not symbols:
        print("No parsable alerts found in the consolidated file.", file=sys.stderr)
        return

    # 2) Build per-symbol daily file paths
    symbol_to_path: Dict[str, str] = {sym: daily_filename(sym, day=day, out_dir=out_dir) for sym in symbols}

    # 3) Start consumer (print or engine) and producer (replay consolidated)
    if mode == "print":
        consumer_task = asyncio.create_task(consume_stream_print(symbol_to_path))
    else:
        consumer_task = asyncio.create_task(consume_stream_engine(symbol_to_path, max_qty=max_qty, broker=broker, risk=risk))

    producer_task = asyncio.create_task(replay_consolidated(consolidated_path, symbol_to_path, delay_sec=delay_sec))

    # 4) Wait for producer to finish, let consumer drain, then cancel consumer
    await producer_task
    await asyncio.sleep(1.0)
    consumer_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await consumer_task

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Replay a consolidated alerts file and test file_stream in real time.")
    p.add_argument("consolidated_file", help="Path to consolidated alerts file (one alert per line).")
    p.add_argument("--out-dir", default=".", help="Directory for per-symbol daily files. Default: current directory.")
    p.add_argument("--day", default=None, help="Override YYYYMMDD for daily filename. Default: today's UTC date.")
    p.add_argument("--delay", type=float, default=2.0, help="Seconds between lines during replay. Default: 2.0")
    p.add_argument("--mode", choices=["print", "engine"], default="print", help="Choose to print alerts or drive TradingEngine.")
    p.add_argument("--max-qty", type=int, default=100, help="Default max_qty per TradeAsset when using engine mode.")
    p.add_argument("--broker", default="tastytrade", help="Broker label for TradeAssets in engine mode.")
    p.add_argument("--risk", type=float, default=0.01, help="risk_per_trade for TradeAssets in engine mode.")
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    try:
        asyncio.run(
            main_async(
                consolidated_path=args.consolidated_file,
                out_dir=args.out_dir,
                day=args.day,
                delay_sec=args.delay,
                mode=args.mode,
                max_qty=args.max_qty,
                broker=args.broker,
                risk=args.risk,
            )
        )
    except KeyboardInterrupt:
        print("Stopped.")
