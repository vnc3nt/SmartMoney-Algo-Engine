# app/settings.py
from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Settings:
    database_url: str
    app_name: str = "SmartMoney Algo-Engine"
    default_starting_cash: Decimal = Decimal("100000.00")
    slippage_bps: int = 10


def load_settings() -> Settings:
    return Settings(
        database_url=os.environ["DATABASE_URL"],
    )