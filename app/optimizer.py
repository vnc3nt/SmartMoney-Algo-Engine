from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import (
    AllocationAdjustmentModel,
    StrategyAllocationModel,
    StrategyModel,
)
from app.routers.analytics import get_leaderboard


@dataclass(frozen=True)
class StrategyMetrics:
    strategy_id: Any
    strategy_key: str
    return_30d: Decimal
    max_drawdown: Decimal
    sharpe_like: Decimal
    win_rate: Decimal


class DynamicAllocator:
    """Weekly allocation optimizer based on recent strategy performance."""

    MAX_DRAWDOWN_THRESHOLD = Decimal("15.0")
    HALVING_FACTOR = Decimal("0.5")
    MIN_ALLOCATION = Decimal("0.01")
    MAX_ALLOCATION = Decimal("0.70")

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def run(self) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                metrics = await self._collect_metrics_30d(session)
                if not metrics:
                    return

                receiver = self._select_receiver(metrics)
                if receiver is None:
                    return

                total_reallocated = Decimal("0")
                for metric in metrics:
                    if metric.strategy_key == receiver.strategy_key:
                        continue
                    should_penalize = (
                        metric.return_30d < Decimal("0")
                        or metric.max_drawdown > self.MAX_DRAWDOWN_THRESHOLD
                    )
                    if not should_penalize:
                        continue
                    moved = await self._halve_allocation(
                        session=session,
                        metric=metric,
                        reason=(
                            "Penalty: negative 30d return or excessive max drawdown"
                        ),
                    )
                    total_reallocated += moved

                if total_reallocated <= Decimal("0"):
                    return

                await self._increase_receiver_allocation(
                    session=session,
                    metric=receiver,
                    increment=total_reallocated,
                    reason="Weekly optimization reallocation from underperformers",
                )

    async def _collect_metrics_30d(self, session: AsyncSession) -> list[StrategyMetrics]:
        leaderboard = await get_leaderboard(sort_by="return_1m", session=session)
        strategy_rows = (
            await session.execute(
                select(StrategyModel).where(StrategyModel.is_active == True)  # noqa: E712
            )
        ).scalars().all()
        strategy_id_by_key = {row.strategy_key: row.id for row in strategy_rows}

        metrics: list[StrategyMetrics] = []
        for row in leaderboard:
            strategy_key = str(row.get("strategy_key", ""))
            strategy_id = strategy_id_by_key.get(strategy_key)
            if strategy_id is None:
                continue
            metrics.append(
                StrategyMetrics(
                    strategy_id=strategy_id,
                    strategy_key=strategy_key,
                    return_30d=Decimal(str(row.get("return_1m", 0))).quantize(Decimal("0.0001")),
                    max_drawdown=Decimal(str(row.get("max_drawdown", 0))).quantize(Decimal("0.0001")),
                    sharpe_like=Decimal("0"),
                    win_rate=Decimal(str(row.get("win_rate", 0))).quantize(Decimal("0.0001")),
                )
            )
        return metrics

    def _select_receiver(self, metrics: list[StrategyMetrics]) -> StrategyMetrics | None:
        profitable = [m for m in metrics if m.return_30d > Decimal("0")]
        if not profitable:
            return None
        profitable.sort(key=lambda m: (m.sharpe_like, m.win_rate, m.return_30d), reverse=True)
        return profitable[0]

    async def _halve_allocation(
        self,
        session: AsyncSession,
        metric: StrategyMetrics,
        reason: str,
    ) -> Decimal:
        allocation = await self._get_or_create_allocation(session, metric.strategy_id)
        old_value = Decimal(allocation.allocation_fraction)
        new_value = max(self.MIN_ALLOCATION, (old_value * self.HALVING_FACTOR).quantize(Decimal("0.000001")))
        moved = old_value - new_value
        if moved <= Decimal("0"):
            return Decimal("0")
        allocation.allocation_fraction = new_value
        session.add(
            AllocationAdjustmentModel(
                strategy_id=metric.strategy_id,
                previous_fraction=old_value,
                new_fraction=new_value,
                adjustment_reason=reason,
                metric_return_30d=metric.return_30d,
                metric_max_drawdown=metric.max_drawdown,
                metric_sharpe=metric.sharpe_like,
                metric_win_rate=metric.win_rate,
            )
        )
        return moved

    async def _increase_receiver_allocation(
        self,
        session: AsyncSession,
        metric: StrategyMetrics,
        increment: Decimal,
        reason: str,
    ) -> None:
        allocation = await self._get_or_create_allocation(session, metric.strategy_id)
        old_value = Decimal(allocation.allocation_fraction)
        new_value = min(self.MAX_ALLOCATION, (old_value + increment).quantize(Decimal("0.000001")))
        allocation.allocation_fraction = new_value
        session.add(
            AllocationAdjustmentModel(
                strategy_id=metric.strategy_id,
                previous_fraction=old_value,
                new_fraction=new_value,
                adjustment_reason=reason,
                metric_return_30d=metric.return_30d,
                metric_max_drawdown=metric.max_drawdown,
                metric_sharpe=metric.sharpe_like,
                metric_win_rate=metric.win_rate,
            )
        )

    async def _get_or_create_allocation(
        self,
        session: AsyncSession,
        strategy_id: Any,
    ) -> StrategyAllocationModel:
        allocation = await session.scalar(
            select(StrategyAllocationModel).where(StrategyAllocationModel.strategy_id == strategy_id)
        )
        if allocation is not None:
            return allocation

        allocation = StrategyAllocationModel(
            strategy_id=strategy_id,
            allocation_fraction=Decimal("0.100000"),
            is_auto_managed=True,
        )
        session.add(allocation)
        await session.flush()
        return allocation
