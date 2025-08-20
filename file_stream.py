# file_stream.py
import asyncio, os, contextlib
from datetime import datetime
from typing import AsyncIterator, Dict, List, Optional
from alert_parser import parse_alert_line, ParsedAlert

class FileTailer:
    def __init__(self, filepath: str, symbol: str):
        self.filepath = filepath
        self.symbol = symbol
        self._pos: int = 0                      # how far we've read (byte offset)
        self._last_ts: Optional[datetime] = None  # last timestamp processed (dedupe)

    async def follow(self, poll_sec: float = 0.25) -> AsyncIterator[ParsedAlert]:
        # start at EOF (tail-only). Use 0 to backfill.
        if os.path.exists(self.filepath):
            self._pos = os.path.getsize(self.filepath)
        else:
            while not os.path.exists(self.filepath):
                await asyncio.sleep(poll_sec)
            self._pos = os.path.getsize(self.filepath)

        while True:
            try:
                size = os.path.getsize(self.filepath)

                # file truncated/rotated → restart from beginning
                if size < self._pos:
                    self._pos = 0

                # new content appended → read delta from _pos to EOF
                if size > self._pos:
                    with open(self.filepath, "r", encoding="utf-8") as f:
                        f.seek(self._pos)
                        for line in f:
                            alert = parse_alert_line(line)
                            if alert and alert.symbol == self.symbol:
                                # optional dedupe by timestamp
                                if self._last_ts is None or alert.ts > self._last_ts:
                                    self._last_ts = alert.ts
                                    yield alert
                        # advance our cursor to current EOF
                        self._pos = f.tell()

            except FileNotFoundError:
                # ok during rotation; wait for file to reappear
                pass

            # pacing (latency vs CPU tradeoff)
            await asyncio.sleep(poll_sec)

async def merged_file_stream(symbol_to_path: Dict[str, str]) -> AsyncIterator[List[ParsedAlert]]:
    tailers = [FileTailer(path, sym) for sym, path in symbol_to_path.items()]
    queues = {t.symbol: asyncio.Queue() for t in tailers}

    async def pump(tailer: FileTailer):
        async for alert in tailer.follow():
            await queues[tailer.symbol].put(alert)

    tasks = [asyncio.create_task(pump(t)) for t in tailers]

    try:
        while True:
            batch: List[ParsedAlert] = []

            # drain all ready items across all symbols, non-blocking
            for sym, q in queues.items():
                try:
                    while True:
                        batch.append(q.get_nowait())
                        q.task_done()
                except asyncio.QueueEmpty:
                    pass

            if batch:
                yield batch

            await asyncio.sleep(0.1)

    finally:
        # ensure tailer tasks are cancelled cleanly
        for t in tasks:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t
