# app/routers/backtest.py
"""
Backtest API endpoints.

Provides an HTTP interface to trigger historical backtests for a given strategy.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtesting import BacktestRunner
from app.base import AsyncSessionFactory
from app.dependencies import get_session

router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    start_date: date = Field(..., description="First day to simulate (YYYY-MM-DD)")
    end_date: date | None = Field(None, description="Last day to simulate (defaults to yesterday)")
    tickers: list[str] | None = Field(None, description="Override ticker list (optional)")
    reset_portfolio: bool = Field(
        True,
        description="Clear existing trade history before running (recommended)",
    )


class BacktestResponse(BaseModel):
    strategy_key: str
    start_date: date
    end_date: date
    tickers: list[str]
    total_trading_days: int
    total_signals: int
    total_trades: int
    starting_cash: float
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    daily_snapshots: list[dict[str, Any]]


_SUPPORTED_STRATEGIES = {
    "strategy_a_legalinsider",
    "strategy_b_unusualvolume",
    "strategy_c_newssentiment",
    "strategy_ab_combined",
}


@router.post("/{strategy_key}", response_model=BacktestResponse)
async def run_backtest(
    strategy_key: str,
    body: BacktestRequest,
    _session: AsyncSession = Depends(get_session),
) -> BacktestResponse:
    """
    Run a historical backtest for the given strategy.

    The backtest loads OHLCV data from yfinance, simulates day-by-day
    execution, and writes results (trade history, equity snapshots) to the
    database.  **Warning**: by default this resets the strategy's portfolio
    before running.
    """
    if strategy_key not in _SUPPORTED_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Backtesting for '{strategy_key}' is not yet supported. "
                f"Supported strategies: {sorted(_SUPPORTED_STRATEGIES)}"
            ),
        )

    if body.end_date and body.end_date <= body.start_date:
        raise HTTPException(
            status_code=422,
            detail="end_date must be after start_date",
        )

    runner = BacktestRunner(
        strategy_key=strategy_key,
        session_factory=AsyncSessionFactory,
        tickers=body.tickers,
    )

    try:
        result = await runner.run(
            start_date=body.start_date,
            end_date=body.end_date,
            reset_portfolio=body.reset_portfolio,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return BacktestResponse(
        strategy_key=result.strategy_key,
        start_date=result.start_date,
        end_date=result.end_date,
        tickers=result.tickers,
        total_trading_days=result.total_trading_days,
        total_signals=result.total_signals,
        total_trades=result.total_trades,
        starting_cash=result.starting_cash,
        final_equity=result.final_equity,
        total_return_pct=result.total_return_pct,
        max_drawdown_pct=result.max_drawdown_pct,
        win_rate_pct=result.win_rate_pct,
        daily_snapshots=result.daily_snapshots,
    )
