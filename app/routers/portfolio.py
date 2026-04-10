from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    StrategyModel,
    PortfolioModel,
    OpenPositionModel,
    TradeHistoryModel,
    PerformanceSnapshotModel,
)
from app.dependencies import get_session
from app.enums import ExecutionFrequency, SignalSide, TradeSide

router = APIRouter(prefix="/api/v1", tags=["portfolio"])

@router.get("/portfolios/{strategy_key}/equity-curve")
async def get_equity_curve(
    strategy_key: str,
    period: str = "1M",   # "1W" | "1M" | "3M" | "ALL"
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Equity-Kurve für Chart (tägl. Snapshots)."""
    strategy = await session.scalar(
        select(StrategyModel).where(StrategyModel.strategy_key == strategy_key)
    )
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    cutoff = {
        "1W": date.today() - timedelta(days=7),
        "1M": date.today() - timedelta(days=30),
        "3M": date.today() - timedelta(days=90),
    }.get(period, date(2000, 1, 1))

    rows = (await session.execute(
        select(PerformanceSnapshotModel)
        .join(PortfolioModel, PerformanceSnapshotModel.portfolio_id == PortfolioModel.id)
        .where(PortfolioModel.strategy_id == strategy.id)
        .where(PerformanceSnapshotModel.snapshot_date >= cutoff)
        .order_by(PerformanceSnapshotModel.snapshot_date)
    )).scalars().all()

    return [
        {
            "date": r.snapshot_date.isoformat(),
            "equity": float(r.equity_value),
            "cash": float(r.cash_balance),
            "market_value": float(r.market_value),
            "daily_pnl": float(r.daily_pnl),
            "total_return_pct": float(r.total_return_pct),
        }
        for r in rows
    ]


@router.get("/portfolios/{strategy_key}/trades")
async def get_trade_history(
    strategy_key: str,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Letzte N Trades einer Strategie."""
    strategy = await session.scalar(
        select(StrategyModel).where(StrategyModel.strategy_key == strategy_key)
    )
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    rows = (await session.execute(
        select(TradeHistoryModel)
        .where(TradeHistoryModel.strategy_id == strategy.id)
        .order_by(TradeHistoryModel.executed_at.desc())
        .limit(limit)
    )).scalars().all()

    return [
        {
            "ticker": r.ticker,
            "side": r.side,
            "quantity": float(r.quantity),
            "executed_price": float(r.executed_price),
            "gross_notional": float(r.gross_notional),
            "realized_pnl": float(r.realized_pnl) if r.realized_pnl else None,
            "executed_at": r.executed_at.isoformat(),
            "reason": r.reason,
        }
        for r in rows
    ]


@router.get("/portfolios/{strategy_key}/positions")
async def get_open_positions(
    strategy_key: str,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Aktuelle offene Positionen."""
    strategy = await session.scalar(
        select(StrategyModel).where(StrategyModel.strategy_key == strategy_key)
    )
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    portfolio = await session.scalar(
        select(PortfolioModel).where(PortfolioModel.strategy_id == strategy.id)
    )

    rows = (await session.execute(
        select(OpenPositionModel).where(OpenPositionModel.portfolio_id == portfolio.id)
    )).scalars().all()

    return [
        {
            "ticker": r.ticker,
            "quantity": float(r.quantity),
            "average_entry_price": float(r.average_entry_price),
            "last_mark_price": float(r.last_mark_price) if r.last_mark_price else None,
            "market_value": float(r.market_value) if r.market_value else None,
            "opened_at": r.opened_at.isoformat(),
        }
        for r in rows
    ]