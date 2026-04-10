from __future__ import annotations

from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI

from app.base import AsyncSessionFactory, settings
from app.strategies import (
    BaseStrategy,
    ExecutionFrequency,
    InMemorySignalStore,
    MarketDataProvider,
    SignalStore,
    StrategyABCombined,
    StrategyALegalInsider,
    StrategyBUnusualVolume,
)
from app.paper_trading import PaperTradingManager


class StrategyOrchestrator:
    """Coordinates strategy runs and trade execution."""

    def __init__(
        self,
        strategies: dict[str, BaseStrategy],
        signal_store: SignalStore,
        trading_manager: PaperTradingManager,
    ) -> None:
        self.strategies = strategies
        self.signal_store = signal_store
        self.trading_manager = trading_manager

    async def run_strategy(self, strategy_key: str) -> None:
        strategy = self.strategies[strategy_key]
        signals = await strategy.run(self.signal_store)
        await self.trading_manager.process_signals(signals)

    async def snapshot_all(self) -> None:
        for strategy_key in self.strategies:
            await self.trading_manager.snapshot_daily_equity(strategy_key)


def build_trigger(freq: ExecutionFrequency):
    if freq == ExecutionFrequency.M1:
        return IntervalTrigger(minutes=1)
    if freq == ExecutionFrequency.H1:
        return CronTrigger(minute=0)
    if freq == ExecutionFrequency.D1:
        return CronTrigger(hour=22, minute=5)
    raise ValueError(f"Unsupported frequency: {freq}")


market_data = MarketDataProvider()
signal_store = InMemorySignalStore()

strategy_a = StrategyALegalInsider(market_data)
strategy_b = StrategyBUnusualVolume(market_data)
strategy_ab = StrategyABCombined(market_data, signal_store)

strategy_registry: dict[str, BaseStrategy] = {
    strategy_a.strategy_key: strategy_a,
    strategy_b.strategy_key: strategy_b,
    strategy_ab.strategy_key: strategy_ab,
}

trading_manager = PaperTradingManager(
    session_factory=AsyncSessionFactory,
    market_data=market_data,
    slippage_bps=10,
)

orchestrator = StrategyOrchestrator(
    strategies=strategy_registry,
    signal_store=signal_store,
    trading_manager=trading_manager,
)

scheduler = AsyncIOScheduler(timezone="UTC")


@asynccontextmanager
async def lifespan(_: FastAPI):
    for strategy in strategy_registry.values():
        scheduler.add_job(
            orchestrator.run_strategy,
            trigger=build_trigger(strategy.execution_frequency),
            args=[strategy.strategy_key],
            id=strategy.strategy_key,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=30,
        )

    scheduler.add_job(
        orchestrator.snapshot_all,
        trigger=CronTrigger(hour=23, minute=59),
        id="daily_equity_snapshots",
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)

