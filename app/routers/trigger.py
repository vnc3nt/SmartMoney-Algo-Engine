# app/routers/trigger.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.base import AsyncSessionFactory
from app.strategies import (
    MarketDataProvider,
    StrategyALegalInsider,
    StrategyBUnusualVolume,
    StrategyABCombined,
    InMemorySignalStore,
)
from app.paper_trading import PaperTradingManager

router = APIRouter(prefix="/api", tags=["trigger"])

# Shared instances (in Production: dependency injection)
_market_data = MarketDataProvider()
_signal_store = InMemorySignalStore()
_trading_manager = PaperTradingManager(
    session_factory=AsyncSessionFactory,
    market_data=_market_data,
    slippage_bps=10,
)


class TriggerResponse(BaseModel):
    strategy: str
    signals_generated: int
    signal_tickers: list[str]
    status: str


@router.post("/trigger/{strategy_key}", response_model=TriggerResponse)
async def trigger_strategy(strategy_key: str) -> TriggerResponse:
    """
    Manuell eine Strategie einmal ausführen (für Tests).
    strategy_key: strategy_a_legalinsider | strategy_b_unusualvolume | strategy_ab_combined
    """
    strategies = {
        "strategy_a_legalinsider": StrategyALegalInsider(_market_data),
        "strategy_b_unusualvolume": StrategyBUnusualVolume(_market_data),
        "strategy_ab_combined": StrategyABCombined(_market_data, _signal_store),
    }

    if strategy_key not in strategies:
        raise HTTPException(
            status_code=404,
            detail=f"Unbekannte Strategie: {strategy_key}. "
                   f"Verfügbar: {list(strategies.keys())}",
        )

    strategy = strategies[strategy_key]
    signals = await strategy.run(_signal_store)
    await _trading_manager.process_signals(signals)

    return TriggerResponse(
        strategy=strategy_key,
        signals_generated=len(signals),
        signal_tickers=[s.ticker for s in signals],
        status="ok" if signals else "keine Signale generiert",
    )


@router.get("/status")
async def backend_status() -> dict:
    """Health-Check mit DB-Verbindungstest."""
    from sqlalchemy import text
    from app.base import AsyncSessionFactory

    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("select 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "backend": "SmartMoney Algo-Engine",
        "db": db_status,
        "strategies_available": [
            "strategy_a_legalinsider",
            "strategy_b_unusualvolume",
            "strategy_ab_combined",
        ],
    }