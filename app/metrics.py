"""Performance metrics calculation module."""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TradeHistoryModel, PerformanceSnapshotModel, PortfolioModel


class PerformanceMetrics:
    """Calculate trading performance KPIs."""

    @staticmethod
    async def calculate_roi(
        session: AsyncSession,
        portfolio_id: str,
    ) -> Decimal:
        """Return on Investment as percentage."""
        portfolio = await session.scalar(
            select(PortfolioModel).where(PortfolioModel.id == portfolio_id)
        )
        if not portfolio:
            return Decimal("0")

        if portfolio.starting_cash <= Decimal("0"):
            return Decimal("0")

        roi = (
            (portfolio.equity_value - portfolio.starting_cash) / portfolio.starting_cash * Decimal("100")
        ).quantize(Decimal("0.01"))
        return roi

    @staticmethod
    async def calculate_win_rate(
        session: AsyncSession,
        strategy_id: str,
    ) -> Decimal:
        """Percentage of trades with positive PnL."""
        trades = (
            await session.execute(
                select(TradeHistoryModel)
                .where(TradeHistoryModel.strategy_id == strategy_id)
                .where(TradeHistoryModel.realized_pnl.isnot(None))
            )
        ).scalars().all()

        if not trades:
            return Decimal("0")

        winning_trades = sum(1 for trade in trades if trade.realized_pnl > Decimal("0"))
        win_rate = (Decimal(winning_trades) / Decimal(len(trades)) * Decimal("100")).quantize(Decimal("0.01"))
        return win_rate

    @staticmethod
    async def calculate_max_drawdown(
        session: AsyncSession,
        portfolio_id: str,
    ) -> Decimal:
        """Maximum percentage loss from peak equity."""
        snapshots = (
            await session.execute(
                select(PerformanceSnapshotModel)
                .where(PerformanceSnapshotModel.portfolio_id == portfolio_id)
                .order_by(PerformanceSnapshotModel.snapshot_date)
            )
        ).scalars().all()

        if len(snapshots) < 2:
            return Decimal("0")

        peak_equity = Decimal("0")
        max_drawdown = Decimal("0")

        for snapshot in snapshots:
            if snapshot.equity_value > peak_equity:
                peak_equity = snapshot.equity_value
            else:
                drawdown = (
                    (peak_equity - snapshot.equity_value) / peak_equity * Decimal("100")
                ).quantize(Decimal("0.01"))
                if drawdown > max_drawdown:
                    max_drawdown = drawdown

        return max_drawdown

    @staticmethod
    async def calculate_sharpe_ratio(
        session: AsyncSession,
        portfolio_id: str,
        risk_free_rate: Decimal = Decimal("0.04"),  # 4% annual
    ) -> Decimal:
        """Sharpe Ratio for portfolio (annual approximation)."""
        snapshots = (
            await session.execute(
                select(PerformanceSnapshotModel)
                .where(PerformanceSnapshotModel.portfolio_id == portfolio_id)
                .order_by(PerformanceSnapshotModel.snapshot_date)
            )
        ).scalars().all()

        if len(snapshots) < 2:
            return Decimal("0")

        # Calculate daily returns
        daily_returns = []
        for i in range(1, len(snapshots)):
            prev_equity = snapshots[i - 1].equity_value
            curr_equity = snapshots[i].equity_value
            if prev_equity > Decimal("0"):
                daily_return = (curr_equity - prev_equity) / prev_equity
                daily_returns.append(daily_return)

        if not daily_returns:
            return Decimal("0")

        # Calculate mean and std dev
        mean_return = sum(daily_returns) / Decimal(len(daily_returns))
        variance = sum((r - mean_return) ** 2 for r in daily_returns) / Decimal(len(daily_returns))
        std_dev = variance.sqrt() if variance > Decimal("0") else Decimal("0")

        if std_dev == Decimal("0"):
            return Decimal("0")

        # Annualize (assuming 252 trading days per year)
        daily_risk_free = risk_free_rate / Decimal("252")
        excess_return = (mean_return - daily_risk_free) * Decimal("252")
        annualized_std = std_dev * Decimal("252").sqrt()

        sharpe_ratio = (excess_return / annualized_std).quantize(Decimal("0.01")) if annualized_std > Decimal("0") else Decimal("0")
        return sharpe_ratio

    @staticmethod
    async def get_all_metrics(
        session: AsyncSession,
        portfolio_id: str,
        strategy_id: str,
    ) -> dict[str, Decimal]:
        """Get all key metrics for a portfolio."""
        return {
            "roi": await PerformanceMetrics.calculate_roi(session, portfolio_id),
            "win_rate": await PerformanceMetrics.calculate_win_rate(session, strategy_id),
            "max_drawdown": await PerformanceMetrics.calculate_max_drawdown(session, portfolio_id),
            "sharpe_ratio": await PerformanceMetrics.calculate_sharpe_ratio(session, portfolio_id),
        }
