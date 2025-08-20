from __future__ import annotations

import argparse, os, re, sys, time, json
from dataclasses import dataclass, field, asdict
from math import floor
from typing import Optional, Dict, Any, List, Iterable, Callable, Tuple, Literal
from datetime import datetime
from src.common.trends import Trend, trend_of
from src.assets.options import OptionContract
from env_utils import get_env_value

@dataclass
class StockConfig:

    def __init__(
        self,
        sym : str = None,
        broker_name : Optional[str] = "alpaca",
        webhook : Optional[str] = "https://webhooks.traderspost.io/trading/webhook/b51fa9de-30a3-4d36-b54f-923039ba0787/14b9c2da8d949b21dd124d197c230431"
        
    ) -> None:
        self.sym = sym
        
        if broker_name == None:
            self.broker_name = self.get_broker_name_from_env()
        else:
            self.broker_name = broker_name
        
        if webhook == None:
            self.webhook = self.get_webhook_from_env()
        else:
            self.webhook = webhook

        self.is_bocked = False

    def get_broker_name_from_env(self) -> str:
        return get_env_value(f"BROKER_{self.sym}")
    def get_broker_name(self) -> str:
        return self.broker_name
    def set_broker_name(self, sym, broker_name) -> None:
        self.broker_name = broker_name
    def set_broker_name(self) -> None:
        self.broker_name = self.get_broker_name_from_env(self.sym)
    
    def get_webhook_from_env(self) -> str:
        broker_name = self.get_broker_name_from_env(self.sym)
        return get_env_value(f"WEBHOOK_{broker_name.upper()}")
    def get_webhook(self) -> str:
        return self.webhook
    def set_webhook(self, webhook) -> None:
        self.webhook = webhook
    def set_webhook(self) -> None:
        self.webhook = self.get_broker_name_from_env(self.sym)
    
    def get_is_blocked(self) -> bool:
        return self.is_bocked
    def set_is_blocked(self, is_blocked):
        self.is_bocked = is_blocked
