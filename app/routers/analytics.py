# app/routers/analytics.py
"""
Analytics & Strategy Leaderboard endpoints.

Computes performance metrics (returns, win rate, max drawdown) across all
active strategies and returns them sorted by all-time total return.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_session
from app.models import (
    PerformanceSnapshotModel,
    PortfolioModel,
    StrategyModel,
    TradeHistoryModel,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


# ---------------------------------------------------------------------------
# Pure computation helpers
# ---------------------------------------------------------------------------

def _total_return_for_window(
    snapshots: list[PerformanceSnapshotModel],
    portfolio: PortfolioModel,
    cutoff: date,
) -> float:
    """
    Percentage return from *cutoff* to the most recent snapshot.

    If there is no snapshot on or before *cutoff*, the starting_cash is used
    as the reference equity so that long backtests still report correct
    all-time figures.
    """
    if not snapshots:
        return 0.0

    latest_equity = float(snapshots[-1].equity_value)

    # Find reference equity at or just before cutoff
    reference: float | None = None
    for s in snapshots:
        if s.snapshot_date <= cutoff:
            reference = float(s.equity_value)
        else:
            break

    if reference is None:
        # No snapshot before cutoff – use starting cash
        reference = float(portfolio.starting_cash)

    if reference <= 0:
        return 0.0

    return round((latest_equity - reference) / reference * 100, 4)


def _win_rate(trades: list[TradeHistoryModel]) -> float:
    """Percentage of SELL trades with positive realized_pnl."""
    closed = [t for t in trades if t.realized_pnl is not None]
    if not closed:
        return 0.0
    winning = sum(1 for t in closed if t.realized_pnl > Decimal("0"))
    return round(winning / len(closed) * 100, 4)


def _max_drawdown(snapshots: list[PerformanceSnapshotModel]) -> float:
    """Greatest percentage drop from a running peak equity."""
    peak = 0.0
    max_dd = 0.0
    for s in snapshots:
        eq = float(s.equity_value)
        if eq > peak:
            peak = eq
        elif peak > 0:
            dd = (peak - eq) / peak * 100
            if dd > max_dd:
                max_dd = dd
    return round(max_dd, 4)


# ---------------------------------------------------------------------------
# Leaderboard endpoint
# ---------------------------------------------------------------------------

@router.get("/leaderboard")
async def get_leaderboard(
    sort_by: str = "return_all",
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """
    Return all active strategies ranked by performance.

    Each entry includes:

    * ``return_1d`` / ``return_1w`` / ``return_1m`` / ``return_1y`` / ``return_all`` – total
      return (%) for each time window.
    * ``win_rate`` – percentage of closed trades with positive PnL.
    * ``max_drawdown`` – largest peak-to-trough drawdown (%).
    * Basic strategy and portfolio metadata.

    Query parameter ``sort_by`` (default ``return_all``) controls the sort
    column.  Descending order is always applied.
    """
    today = date.today()
    cutoffs: dict[str, date] = {
        "return_1d": today - timedelta(days=1),
        "return_1w": today - timedelta(days=7),
        "return_1m": today - timedelta(days=30),
        "return_1y": today - timedelta(days=365),
        "return_all": date(2000, 1, 1),
    }

    strategies = (
        await session.execute(
            select(StrategyModel).where(StrategyModel.is_active == True)  # noqa: E712
        )
    ).scalars().all()

    leaderboard: list[dict[str, Any]] = []

    for strategy in strategies:
        portfolio = await session.scalar(
            select(PortfolioModel).where(PortfolioModel.strategy_id == strategy.id)
        )
        if portfolio is None:
            continue

        snapshots = (
            await session.execute(
                select(PerformanceSnapshotModel)
                .where(PerformanceSnapshotModel.portfolio_id == portfolio.id)
                .order_by(PerformanceSnapshotModel.snapshot_date)
            )
        ).scalars().all()

        trades = (
            await session.execute(
                select(TradeHistoryModel).where(
                    TradeHistoryModel.portfolio_id == portfolio.id
                )
            )
        ).scalars().all()

        returns = {
            key: _total_return_for_window(list(snapshots), portfolio, cutoff)
            for key, cutoff in cutoffs.items()
        }
        wr = _win_rate(list(trades))
        mdd = _max_drawdown(list(snapshots))

        leaderboard.append(
            {
                "strategy_key": strategy.strategy_key,
                "name": strategy.name,
                "execution_frequency": strategy.execution_frequency,
                "portfolio_id": str(portfolio.id),
                "starting_cash": float(portfolio.starting_cash),
                "equity_value": float(portfolio.equity_value),
                "cash_balance": float(portfolio.cash_balance),
                "return_1d": returns["return_1d"],
                "return_1w": returns["return_1w"],
                "return_1m": returns["return_1m"],
                "return_1y": returns["return_1y"],
                "return_all": returns["return_all"],
                "win_rate": wr,
                "max_drawdown": mdd,
                "total_trades": len(trades),
                "snapshot_count": len(snapshots),
            }
        )

    # Sort descending by the requested metric (default: return_all)
    valid_sort_keys = {"return_1d", "return_1w", "return_1m", "return_1y", "return_all", "win_rate"}
    sort_key = sort_by if sort_by in valid_sort_keys else "return_all"
    leaderboard.sort(key=lambda x: x.get(sort_key, 0), reverse=True)

    return leaderboard


@router.get("/strategy/{strategy_key}/metrics")
async def get_strategy_metrics(
    strategy_key: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """
    Detailed metrics for a single strategy, covering all time windows.
    """
    from fastapi import HTTPException

    strategy = await session.scalar(
        select(StrategyModel).where(StrategyModel.strategy_key == strategy_key)
    )
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    portfolio = await session.scalar(
        select(PortfolioModel).where(PortfolioModel.strategy_id == strategy.id)
    )
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    today = date.today()
    cutoffs: dict[str, date] = {
        "return_1d": today - timedelta(days=1),
        "return_1w": today - timedelta(days=7),
        "return_1m": today - timedelta(days=30),
        "return_1y": today - timedelta(days=365),
        "return_all": date(2000, 1, 1),
    }

    snapshots = (
        await session.execute(
            select(PerformanceSnapshotModel)
            .where(PerformanceSnapshotModel.portfolio_id == portfolio.id)
            .order_by(PerformanceSnapshotModel.snapshot_date)
        )
    ).scalars().all()

    trades = (
        await session.execute(
            select(TradeHistoryModel).where(TradeHistoryModel.portfolio_id == portfolio.id)
        )
    ).scalars().all()

    returns = {
        key: _total_return_for_window(list(snapshots), portfolio, cutoff)
        for key, cutoff in cutoffs.items()
    }

    return {
        "strategy_key": strategy_key,
        "name": strategy.name,
        "equity_value": float(portfolio.equity_value),
        "starting_cash": float(portfolio.starting_cash),
        **returns,
        "win_rate": _win_rate(list(trades)),
        "max_drawdown": _max_drawdown(list(snapshots)),
        "total_trades": len(trades),
    }
