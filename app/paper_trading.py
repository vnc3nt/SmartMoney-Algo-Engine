from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import ROUND_DOWN, Decimal
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.base import (
    AsyncSessionFactory,
    PortfolioModel,
    StrategyModel,
    OpenPositionModel,
    TradeHistoryModel,
    PerformanceSnapshotModel,
    TradeSide,
)
from app.strategies import Signal, SignalSide, MarketDataProvider


class PaperTradingManager:
    """Receives strategy signals and simulates isolated paper trades."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        market_data: MarketDataProvider,
        slippage_bps: int = 10,
    ) -> None:
        self._session_factory = session_factory
        self._market_data = market_data
        self._slippage_bps = slippage_bps

    async def process_signals(self, signals: Sequence[Signal]) -> None:
        if not signals:
            return

        async with self._session_factory() as session:
            async with session.begin():
                for signal in signals:
                    strategy = await self._require_strategy(session, signal.strategy_key)
                    portfolio = await self._require_portfolio(session, strategy.id)

                    if signal.side == SignalSide.BUY:
                        await self._execute_buy(session, strategy, portfolio, signal)
                    elif signal.side == SignalSide.SELL:
                        await self._execute_sell(session, strategy, portfolio, signal)

                await session.flush()

        touched_strategy_keys = {signal.strategy_key for signal in signals}
        for strategy_key in touched_strategy_keys:
            await self.snapshot_daily_equity(strategy_key)

    async def snapshot_daily_equity(self, strategy_key: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                strategy = await self._require_strategy(session, strategy_key)
                portfolio = await self._require_portfolio(session, strategy.id)

                positions = await self._get_open_positions(session, portfolio.id)
                market_value = Decimal("0")
                for position in positions:
                    last_price = await self._market_data.get_last_price(position.ticker)
                    position.last_mark_price = last_price
                    position.market_value = (position.quantity * last_price).quantize(Decimal("0.0001"))
                    market_value += position.market_value

                equity = (portfolio.cash_balance + market_value).quantize(Decimal("0.0001"))
                portfolio.equity_value = equity

                snapshot_day = date.today()
                previous_snapshot = await session.scalar(
                    select(PerformanceSnapshotModel)
                    .where(PerformanceSnapshotModel.portfolio_id == portfolio.id)
                    .where(PerformanceSnapshotModel.snapshot_date < snapshot_day)
                    .order_by(PerformanceSnapshotModel.snapshot_date.desc())
                    .limit(1)
                )

                previous_equity = previous_snapshot.equity_value if previous_snapshot else portfolio.starting_cash
                daily_pnl = (equity - previous_equity).quantize(Decimal("0.0001"))
                total_return_pct = (
                    ((equity - portfolio.starting_cash) / portfolio.starting_cash) * Decimal("100")
                ).quantize(Decimal("0.000001"))

                existing = await session.scalar(
                    select(PerformanceSnapshotModel).where(
                        PerformanceSnapshotModel.portfolio_id == portfolio.id,
                        PerformanceSnapshotModel.snapshot_date == snapshot_day,
                    )
                )

                if existing is None:
                    session.add(
                        PerformanceSnapshotModel(
                            portfolio_id=portfolio.id,
                            strategy_id=strategy.id,
                            snapshot_date=snapshot_day,
                            cash_balance=portfolio.cash_balance,
                            market_value=market_value,
                            equity_value=equity,
                            open_positions_count=len(positions),
                            daily_pnl=daily_pnl,
                            total_return_pct=total_return_pct,
                        )
                    )
                else:
                    existing.cash_balance = portfolio.cash_balance
                    existing.market_value = market_value
                    existing.equity_value = equity
                    existing.open_positions_count = len(positions)
                    existing.daily_pnl = daily_pnl
                    existing.total_return_pct = total_return_pct

    async def _execute_buy(
        self,
        session: AsyncSession,
        strategy: StrategyModel,
        portfolio: PortfolioModel,
        signal: Signal,
    ) -> None:
        executed_price = self._apply_slippage(signal.signal_price, TradeSide.BUY)
        budget = (portfolio.cash_balance * signal.allocation_fraction).quantize(Decimal("0.0001"))
        quantity = (budget / executed_price).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)

        if quantity <= Decimal("0"):
            return

        gross_notional = (quantity * executed_price).quantize(Decimal("0.0001"))
        if gross_notional > portfolio.cash_balance:
            return

        slippage_amount = ((executed_price - signal.signal_price) * quantity).quantize(Decimal("0.0001"))
        portfolio.cash_balance = (portfolio.cash_balance - gross_notional).quantize(Decimal("0.0001"))

        position = await session.scalar(
            select(OpenPositionModel).where(
                OpenPositionModel.portfolio_id == portfolio.id,
                OpenPositionModel.ticker == signal.ticker,
            )
        )

        if position is None:
            session.add(
                OpenPositionModel(
                    portfolio_id=portfolio.id,
                    strategy_id=strategy.id,
                    ticker=signal.ticker,
                    quantity=quantity,
                    average_entry_price=executed_price,
                    last_mark_price=executed_price,
                    market_value=gross_notional,
                )
            )
        else:
            new_total_qty = position.quantity + quantity
            new_avg = (
                ((position.quantity * position.average_entry_price) + gross_notional) / new_total_qty
            ).quantize(Decimal("0.00000001"))
            position.quantity = new_total_qty
            position.average_entry_price = new_avg
            position.last_mark_price = executed_price
            position.market_value = (new_total_qty * executed_price).quantize(Decimal("0.0001"))

        session.add(
            TradeHistoryModel(
                portfolio_id=portfolio.id,
                strategy_id=strategy.id,
                ticker=signal.ticker,
                side=TradeSide.BUY.value,
                quantity=quantity,
                signal_price=signal.signal_price,
                executed_price=executed_price,
                gross_notional=gross_notional,
                slippage_amount=slippage_amount,
                fees=Decimal("0"),
                realized_pnl=None,
                reason=signal.reason,
                executed_at=datetime.now(timezone.utc),
            )
        )

    async def _execute_sell(
        self,
        session: AsyncSession,
        strategy: StrategyModel,
        portfolio: PortfolioModel,
        signal: Signal,
    ) -> None:
        position = await session.scalar(
            select(OpenPositionModel).where(
                OpenPositionModel.portfolio_id == portfolio.id,
                OpenPositionModel.ticker == signal.ticker,
            )
        )

        if position is None:
            return

        executed_price = self._apply_slippage(signal.signal_price, TradeSide.SELL)
        quantity = position.quantity
        gross_notional = (quantity * executed_price).quantize(Decimal("0.0001"))
        slippage_amount = ((signal.signal_price - executed_price) * quantity).quantize(Decimal("0.0001"))
        realized_pnl = (
            (executed_price - position.average_entry_price) * quantity
        ).quantize(Decimal("0.0001"))

        portfolio.cash_balance = (portfolio.cash_balance + gross_notional).quantize(Decimal("0.0001"))

        session.add(
            TradeHistoryModel(
                portfolio_id=portfolio.id,
                strategy_id=strategy.id,
                ticker=signal.ticker,
                side=TradeSide.SELL.value,
                quantity=quantity,
                signal_price=signal.signal_price,
                executed_price=executed_price,
                gross_notional=gross_notional,
                slippage_amount=slippage_amount,
                fees=Decimal("0"),
                realized_pnl=realized_pnl,
                reason=signal.reason,
                executed_at=datetime.now(timezone.utc),
            )
        )

        await session.delete(position)

    async def _require_strategy(self, session: AsyncSession, strategy_key: str) -> StrategyModel:
        strategy = await session.scalar(
            select(StrategyModel).where(StrategyModel.strategy_key == strategy_key)
        )
        if strategy is None:
            raise ValueError(f"Unknown strategy: {strategy_key}")
        return strategy

    async def _require_portfolio(self, session: AsyncSession, strategy_id: UUID) -> PortfolioModel:
        portfolio = await session.scalar(
            select(PortfolioModel).where(PortfolioModel.strategy_id == strategy_id)
        )
        if portfolio is None:
            raise ValueError(f"Missing portfolio for strategy_id={strategy_id}")
        return portfolio

    async def _get_open_positions(
        self,
        session: AsyncSession,
        portfolio_id: UUID,
    ) -> list[OpenPositionModel]:
        return list(
            (
                await session.execute(
                    select(OpenPositionModel).where(OpenPositionModel.portfolio_id == portfolio_id)
                )
            ).scalars()
        )

    def _apply_slippage(self, raw_price: Decimal, side: TradeSide) -> Decimal:
        bps = Decimal(self._slippage_bps) / Decimal("10000")
        factor = Decimal("1") + bps if side == TradeSide.BUY else Decimal("1") - bps
        return (raw_price * factor).quantize(Decimal("0.00000001"))