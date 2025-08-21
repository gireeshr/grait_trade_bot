import argparse
import os
import sys
import time
import datetime as _dt
from dotenv import load_dotenv
from multiprocessing import Process

# Add the "src" directory to the module search path.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.common.trading_engine import TradingEngine
from src.common.price_alerts import monitor_price_alerts

def main():
    # args = parse_args()
    # if args.date:
    #     try:
    #         pnl_date = _dt.datetime.strptime(args.date, "%Y-%m-%d").date()
    #     except ValueError:
    #         print("ERROR: --date must be in YYYY-MM-DD format.")
    #         sys.exit(1)
    # else:
    #     pnl_date = None

    # Assuming main.py is in trading_bot/ (project root), load .env from the same directory.
    dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
    load_dotenv(dotenv_path=dotenv_path)
    
    parse_time = int(os.getenv("PARSE_TIME", 10))

    parser = argparse.ArgumentParser(
        description="Run the trading bot with optional email fetch date."
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Input date in YYYYMMDD format (e.g., 20230512). If not provided, today's date is used.",
    )
    args = parser.parse_args()

    # Set the input date variable. This variable may be used when fetching emails.
    input_date = args.date  # Could be None if not provided

    is_debug_on = True

    if (not is_debug_on):
        renko_alert_process = Process(target=monitor_price_alerts, args=(input_date,))
        renko_alert_process.start()
        
        print(f"\nSleeping for {parse_time} seconds to complete alert parsing...\n")
        time.sleep(parse_time)

    # Initialize and run the trading engine

    engine = TradingEngine()  # adjust interval as needed 
    
    engine.run()


if __name__ == "__main__":
    main()
