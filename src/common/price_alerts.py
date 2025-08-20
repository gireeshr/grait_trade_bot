import imaplib
import email
from datetime import datetime
import time
import os
import re
from dotenv import load_dotenv
from typing import Optional, List, Set   # ← NEW

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS & REGEX
# ──────────────────────────────────────────────────────────────────────────────
DASH = r'[–-]'
PRICE = r'\d+(?:\.\d+)?'
TIMESTAMP = r'\d{14}'
# pattern = re.compile(
#     rf"""^
#         (?P<symbol>[A-Z]+(?:\.[A-Z]+)?)
#         \s*{DASH}\s*Renko\s*{DASH}\s*
#         {PRICE}\s*{DASH}\s*
#         {TIMESTAMP}
#         $""",
#     re.VERBOSE,
# )

# pattern = re.compile(
#     r"""
#     ^
#     (?P<symbol>TSLA)\s*-\s*MA\s+Alert\s*-\s*(?P<alert>\d+)\s*-\s*
#     price:\s*(?P<price>-?\d+(?:\.\d+)?)
#     \s*-\s*
#     SMA_20:\s*(?P<sma20>-?\d+(?:\.\d+)?),\s*EMA_20:\s*(?P<ema20>-?\d+(?:\.\d+)?),\s*EMA_9:\s*(?P<ema9>-?\d+(?:\.\d+)?)
#     \s*-\s*
#     (?P<timestamp>\d{14})
#     $
#     """,
#     re.VERBOSE,
# )

pattern = re.compile(
    r"""
    ^
    (?P<symbol>[A-Z]+(?:\.[A-Z]+)?)\s*-\s*MA\s+Alert\s*-\s*(?P<alert>\d+)\s*-\s*
    price:\s*(?P<price>-?\d+(?:\.\d+)?)
    \s*-\s*
    SMA_20:\s*(?P<sma20>-?\d+(?:\.\d+)?),\s*EMA_20:\s*(?P<ema20>-?\d+(?:\.\d+)?),\s*EMA_9:\s*(?P<ema9>-?\d+(?:\.\d+)?)
    \s*-\s*
    (?P<timestamp>\d{14})
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)

def build_ma_alert_pattern(symbol: str) -> re.Pattern:
    sym = re.escape(symbol)  # handles dots like BRK.B
    return re.compile(
        rf"""
        ^
        (?P<symbol>{sym})\s*-\s*MA\s+Alert\s*-\s*(?P<alert>\d+)\s*-\s*
        price:\s*(?P<price>-?\d+(?:\.\d+)?)
        \s*-\s*
        SMA_20:\s*(?P<sma20>-?\d+(?:\.\d+)?),\s*EMA_20:\s*(?P<ema20>-?\d+(?:\.\d+)?),\s*EMA_9:\s*(?P<ema9>-?\d+(?:\.\d+)?)
        \s*-\s*
        (?P<timestamp>\d{14})
        $
        """,
        re.VERBOSE,
    )

# pattern = build_ma_alert_pattern("SPX")

# print(pattern)

IMAP_SERVER   = "imap.gmail.com"
SENDER_EMAIL  = "noreply@tradingview.com"
POLL_INTERVAL = 1
processed_uids: Set[str] = set()

# ──────────────────────────────────────────────────────────────────────────────
# AUTHENTICATION
# ──────────────────────────────────────────────────────────────────────────────
load_dotenv()
username = os.getenv("GMAIL_USERNAME")
password = os.getenv("GMAIL_PASSWORD")

def connect_to_mailbox() -> imaplib.IMAP4_SSL:
    imap = imaplib.IMAP4_SSL(IMAP_SERVER)
    imap.login(username, password)
    return imap

# ──────────────────────────────────────────────────────────────────────────────
# EMAIL-FETCH HELPERS
# ──────────────────────────────────────────────────────────────────────────────
def _search_date_clause(date_yyyymmdd: Optional[str] = None) -> str:   # ← CHANGED
    if date_yyyymmdd:
        try:
            dt = datetime.strptime(date_yyyymmdd, "%Y%m%d")
        except ValueError:
            print(f"[WARN] Bad date '{date_yyyymmdd}', defaulting to today.")
            dt = datetime.now()
    else:
        dt = datetime.now()
    return dt.strftime("%d-%b-%Y")

def fetch_email_uids(
    imap: imaplib.IMAP4_SSL,
    date_yyyymmdd: Optional[str] = None        # ← CHANGED
) -> List[bytes]:                              # ← CHANGED
    imap.select("inbox")
    search_date = _search_date_clause(date_yyyymmdd)
    status, data = imap.search(None, f'(FROM "{SENDER_EMAIL}" ON {search_date})')
    if status != "OK":
        print(f"[ERROR] IMAP search failed: {status}")
        return []
    return data[0].split()

def fetch_message_body(imap: imaplib.IMAP4_SSL, uid: bytes) -> Optional[str]:  # ← CHANGED
    status, msg_data = imap.fetch(uid, "(RFC822)")
    if status != "OK":
        print(f"[ERROR] fetch UID {uid.decode()}: {status}")
        return None
    for resp in msg_data:
        if isinstance(resp, tuple):
            msg = email.message_from_bytes(resp[1])
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain" and "attachment" not in str(part.get('Content-Disposition')):
                        return (part.get_payload(decode=True) or b"").decode(errors="ignore")
            else:
                return (msg.get_payload(decode=True) or b"").decode(errors="ignore")
    return None

# ──────────────────────────────────────────────────────────────────────────────
# PROCESSING & FILE OUTPUT  (unchanged)
# ──────────────────────────────────────────────────────────────────────────────
def extract_matching_lines(body: Optional[str]) -> List[str]:
    if not body:
        return []
    return [ln.strip() for ln in body.splitlines() if pattern.match(ln.strip())]

def append_to_consolidated(lines: List[str], date_suffix: str) -> None:
    if not lines: return
    with open(f"price_alerts_consolidated_{date_suffix}.txt", "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

def save_to_symbol_files(lines: List[str], date_suffix: str) -> None:
    for line in lines:
        m = pattern.match(line)
        if not m: continue
        symbol = m.group("symbol")
        with open(f"{symbol}_price_{date_suffix}.txt", "w", encoding="utf-8") as f:
            f.write(line + "\n")
        print(f"[INFO] Updated {symbol}_Renko_{date_suffix}.txt")

# ─── helpers ────────────────────────────────────────────────────────────────
def _extract_symbol(line: str) -> str:
    """
    Assumes each alert line starts with the symbol, e.g.  'AAPL, 189.42, …'
    Adapt this splitter if your format differs.
    """
    return line.split(",")[0].strip().upper()

def monitor_price_alerts(date_filter: Optional[str] = None) -> None:   # ← CHANGED
    print(f"🔍 Monitoring e-mails from {SENDER_EMAIL} …")
    while True:
        try:
            if date_filter is None or date_filter.strip() == "":
                date_suffix = datetime.now().strftime("%Y%m%d")
            else:
                date_suffix = date_filter
            imap = connect_to_mailbox()
            for uid in fetch_email_uids(imap, date_filter):
                uid_str = uid.decode()
                if uid_str in processed_uids:
                    continue
                lines = extract_matching_lines(fetch_message_body(imap, uid))
                if lines:
                    append_to_consolidated(lines, date_suffix)
                    save_to_symbol_files(lines, date_suffix)
                    print(f"[INFO] UID {uid_str}: saved {len(lines)} line(s).")
                processed_uids.add(uid_str)
            imap.close(); imap.logout()
        except Exception as exc:
            print(f"[ERROR] {exc}")
        print(f"⏳ Sleeping {POLL_INTERVAL} s …\n")
        time.sleep(POLL_INTERVAL)


# if __name__ == "__main__":
#     monitor_renko_alerts()        # supply YYYYMMDD if you want a specific date
