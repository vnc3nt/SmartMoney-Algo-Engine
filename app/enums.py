# app/enums.py
from __future__ import annotations

from enum import Enum


class ExecutionFrequency(str, Enum):
    M1 = "1m"
    H1 = "1h"
    D1 = "1d"


class SignalSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"