# app/settings.py
from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv()  # lädt .env, bevor os.environ gelesen wird


@dataclass(frozen=True)
class Settings:
    database_url: str
    app_name: str = "SmartMoney Algo-Engine"
    default_starting_cash: Decimal = Decimal("100000.00")
    slippage_bps: int = 10


def load_settings() -> Settings:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL ist nicht gesetzt. "
            "Lege eine .env-Datei an oder exportiere die Variable."
        )
    return Settings(database_url=url)