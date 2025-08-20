from __future__ import annotations
import time
from typing import Dict, List

from src.common.price_tracker    import FilePriceTracker
from src.common.webhooks         import send_trade_alert_by_sentiment
from env_utils import get_env_value
from src.common.symbol_info import SymbolInfoManager

class TradingEngine:
    """
    Broker‐agnostic trading engine that:
      1. Reads SYMBOLS, BROKER_<SYM> and WEBHOOK_<BROKER> via SymbolInfoManager.
      2. Initializes FilePriceTracker with each symbol’s webhook.
      3. Keeps each symbol’s broker_name in SymbolInfo for P&L, logging, etc.
    """
    def __init__(self) -> None:
        # 1. Initialize state manager, which loads symbols + broker/webhook from .env
        self.manager = SymbolInfoManager()
        self.symbol_list: List[str] = self.manager.symbols()

        # 2. Load polling & order settings
        self.poll_interval = float(get_env_value('POLL_INTERVAL'))
        self.qty           = int(get_env_value('DEFAULT_QTY'))
        self.blocked_symbols: List[str] = []

        # 3. Build tracker: { symbol: webhook_url }
        symbol_to_webhook: Dict[str, str] = {
            sym: self.manager.get_info(sym).get_webhook_url()
            for sym in self.symbol_list
        }
        self.price_tracker = FilePriceTracker(symbol_to_webhook)

        # 4. Optionally log each symbol’s broker from SymbolInfo
        print("––––– Brokers configured –––––")
        for sym in self.symbol_list:
            broker = self.manager.get_info(sym).get_broker_name()
            print(f"  {sym}: {broker}")
        print("–––––––––––––––––––––––––––––")

    def evaluate_trade(self, symbol: str) -> None:
        """
        Strategy: send trade alerts when price ticks up/down, then call P&L guard.
        """
        # limits = SYMBOL_RULES[symbol]
        # blocked = self._renko_guard_or_flat(
        #     symbol,
        #     max_profit=float(limits["max_profit"]),
        #     max_loss=float(limits["max_loss"])
        # )

        # if not blocked:
        
        if not self.price_tracker.price_changed(symbol):
            return

        new_price = self.price_tracker.current_price(symbol)
        old_price = self.price_tracker.previous_price(symbol) or 0.0

        take_profit_factor_per_trade = 2
        
        # 4. Grab our symbol-info object
        info    = self.manager.get_info(symbol)
        self.manager.update_current_price(symbol, new_price)

        if info.unrealized_pnl >= take_profit_factor_per_trade:
            self.manager.update_realized_pnl(symbol)
            self.manager.set_unrealized_pnl(symbol, 0)
            self.manager.update_is_blocked(symbol)
        else:
            if not info.is_blocked:
                webhook = info.get_webhook_url()
                qty     = info.trade_quantity
                ticker  = info.symbol  # already upper-cased
                
                if new_price > old_price and old_price != 0:
                    # update internal state
                    # self.manager.process_bullish_trade(symbol, new_price)
                    # self.manager.update_is_blocked(symbol)

                    # only send alert if not blocked
                    if info.last_trade_side != "buy" and info.expected_trade_side == "buy":
                        
                        # set is_debug_on to True when debugging
                        is_debug_on = False
                        
                        if(not is_debug_on):
                            send_trade_alert_by_sentiment(
                                webhook_url = webhook,
                                ticker      = ticker,
                                action      = "buy",
                                sentiment   = "bullish",
                                quantity    = qty,
                            )
                        self.manager.update_realized_pnl(symbol)
                        self.manager.update_trade_count(symbol)
                        self.manager.update_last_trade_price(symbol,new_price)
                        self.manager.update_unrealized_pnl(symbol)
                        self.manager.update_last_trade_side(symbol, "buy")
                        self.manager.update_expected_trade_side(symbol, "sell")
                        self.manager.update_is_blocked(symbol)
                        info    = self.manager.get_info(symbol)
                        if info.is_blocked:
                            print("----------------------------------------------------")
                            print(f"symbol {symbol} blocked.")
                            print(f"info.realized_pnl = {info.realized_pnl}")
                            print("----------------------------------------------------")

                            if(not is_debug_on):
                                send_trade_alert_by_sentiment(
                                            webhook_url = webhook,
                                            ticker      = ticker,
                                            action      = "exit"
                                        )
                    else:
                        self.manager.update_unrealized_pnl(symbol)
                        self.manager.update_last_trade_side(symbol, "buy")
                
                # 6. On bearish tick
                elif new_price < old_price and old_price != 0:
                    # self.manager.process_bearish_trade(symbol, new_price)
                    self.manager.update_is_blocked(symbol)

                    # only send alert if not blocked
                    if info.last_trade_side != "sell" and info.expected_trade_side == "sell":
                        
                        # set is_debug_on to True when debugging
                        is_debug_on = False

                        if(not is_debug_on):
                            send_trade_alert_by_sentiment(
                                webhook_url = webhook,
                                ticker      = ticker,
                                action      = "sell",
                                sentiment   = "bearish",
                                quantity    = qty,
                            )
                        self.manager.update_realized_pnl(symbol)
                        self.manager.update_trade_count(symbol)
                        self.manager.update_last_trade_price(symbol,new_price)
                        self.manager.update_unrealized_pnl(symbol)
                        self.manager.update_last_trade_side(symbol, "sell")
                        self.manager.update_expected_trade_side(symbol, "buy")
                        self.manager.update_is_blocked(symbol)
                        info    = self.manager.get_info(symbol)
                        if info.is_blocked:
                            print("----------------------------------------------------")
                            print(f"symbol {symbol} blocked.")
                            print(f"info.realized_pnl = {info.realized_pnl}")
                            print("----------------------------------------------------")

                            if(not is_debug_on):
                                send_trade_alert_by_sentiment(
                                            webhook_url = webhook,
                                            ticker      = ticker,
                                            action      = "exit"
                                        )
                    else:
                        self.manager.update_unrealized_pnl(symbol)
                        self.manager.update_last_trade_side(symbol, "sell")
                # if info.is_blocked:
                #     print("----------------------------------------------------")
                #     print(f"symbol {symbol} blocked.")
                #     print(f"info.realized_pnl = {info.realized_pnl}")
                #     print("----------------------------------------------------")

                #     send_trade_alert_by_sentiment(
                #                 webhook_url = webhook,
                #                 ticker      = ticker,
                #                 action      = "exit"
                #             )
                    
                # 7. Log for debugging
                print(f"[{symbol}] old={old_price:.2f} new={new_price:.2f}")
            else:
                return
    
    def run(self) -> None:
        print(f"Starting trading engine (poll = {self.poll_interval}s)…")
        print("XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
        try:
            while True:
                # 1. Refresh prices
                self.price_tracker.poll()

                # 2. Iterate through all managed symbols
                for symbol in self.manager.symbols():
                    info = self.manager.get_info(symbol)

                    # 3. Skip if this symbol has been blocked
                    if info.is_blocked:
                        continue

                    print(f"\n--- Processing {symbol} ---")
                    self.evaluate_trade(symbol)

                # 4. Wait before next poll
                print(f"\nSleeping {self.poll_interval} seconds…\n")
                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            print("⏹️  Stopped by user.")
