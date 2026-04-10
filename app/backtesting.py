# app/backtesting.py
"""
Backtesting Engine for SmartMoney Algo-Engine.

Loads historical OHLCV data via yfinance and simulates strategy execution
day-by-day without real-time delays, writing results to the existing database.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pandas as pd
import yfinance as yf
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.enums import SignalSide
from app.models import (
    OpenPositionModel,
    PerformanceSnapshotModel,
    PortfolioModel,
    StrategyModel,
    TradeHistoryModel,
)
from app.paper_trading import PaperTradingManager
from app.strategies import (
    InMemorySignalStore,
    MarketDataProvider,
    Signal,
    StrategyALegalInsider,
    StrategyBUnusualVolume,
    VolumeSpike,
)


# ---------------------------------------------------------------------------
# Historical market data provider
# ---------------------------------------------------------------------------

class BacktestMarketDataProvider(MarketDataProvider):
    """
    Market data provider backed by pre-loaded historical OHLCV DataFrames.

    The provider maintains a ``current_date`` cursor that advances during the
    simulation loop; all price / volume queries are bounded to data available
    up to (and including) that date.
    """

    def __init__(
        self,
        historical_data: dict[str, pd.DataFrame],
        current_date: date | None = None,
    ) -> None:
        # Skip the live finnhub setup from the parent class
        self.finnhub_client = None
        self._historical_data = historical_data
        self._current_date: date = current_date or date.today()

    def set_current_date(self, current_date: date) -> None:
        self._current_date = current_date

    @property
    def current_date(self) -> date:
        return self._current_date

    async def get_last_price(self, ticker: str) -> Decimal:
        if ticker not in self._historical_data:
            return Decimal("100.00")
        df = self._historical_data[ticker]
        available = df[df.index.date <= self._current_date]
        if available.empty:
            return Decimal("100.00")
        return Decimal(str(float(available["Close"].iloc[-1])))

    async def get_unusual_volume_candidates_for_date(self, target_date: date) -> list[VolumeSpike]:
        """Return volume spikes detectable on *target_date* given historical data."""
        spikes: list[VolumeSpike] = []
        for ticker, df in self._historical_data.items():
            try:
                available = df[df.index.date <= target_date]
                if len(available) < 6:
                    continue
                curr_row = available.iloc[-1]
                prev_row = available.iloc[-2]
                window_5 = available.iloc[-6:-1]

                current_volume = int(curr_row["Volume"])
                close = Decimal(str(float(curr_row["Close"])))
                previous_close = Decimal(str(float(prev_row["Close"])))
                avg_volume_5 = int(window_5["Volume"].mean())

                volume_ratio = Decimal(current_volume) / Decimal(max(avg_volume_5, 1))
                if volume_ratio >= Decimal("1.50"):
                    spikes.append(
                        VolumeSpike(
                            ticker=ticker,
                            close=close,
                            previous_close=previous_close,
                            current_volume=current_volume,
                            avg_volume_5=avg_volume_5,
                            observed_at=datetime.combine(
                                target_date, datetime.min.time()
                            ).replace(tzinfo=timezone.utc),
                        )
                    )
            except Exception:
                continue
        return spikes


# ---------------------------------------------------------------------------
# Backtest-aware strategy variants
# ---------------------------------------------------------------------------

class BacktestStrategyBUnusualVolume(StrategyBUnusualVolume):
    """Volume strategy that reads from historical data instead of live feeds."""

    def __init__(self, market_data: BacktestMarketDataProvider) -> None:
        super().__init__(market_data)
        self._backtest_provider = market_data

    async def analyze_data(self) -> list[VolumeSpike]:
        return await self._backtest_provider.get_unusual_volume_candidates_for_date(
            self._backtest_provider.current_date
        )


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
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
    daily_snapshots: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# BacktestRunner
# ---------------------------------------------------------------------------

class BacktestRunner:
    """
    Orchestrates a historical backtest for a given strategy.

    Steps
    -----
    1. Download OHLCV data for the full date range via yfinance.
    2. Reset the strategy's portfolio to starting state.
    3. Iterate over each trading day (Mon–Fri) in the date range.
    4. On each day, run the strategy against historical data and pass any
       signals to ``PaperTradingManager`` with a ``simulated_dt`` so that
       all DB writes use the correct historical timestamp.
    5. Take an equity snapshot for every simulated day.
    6. Return a ``BacktestResult`` summary.
    """

    SUPPORTED_STRATEGIES = {
        "strategy_b_unusualvolume",
    }

    DEFAULT_TICKERS: dict[str, list[str]] = {
        "strategy_b_unusualvolume": ["AAPL", "TSLA", "MSFT", "NVDA", "AMD"],
        "strategy_a_legalinsider": ["AAPL", "TSLA", "MSFT", "NVDA", "AMD", "GOOG", "META"],
        "strategy_ab_combined": ["AAPL", "TSLA", "MSFT", "NVDA", "AMD"],
    }

    def __init__(
        self,
        strategy_key: str,
        session_factory: async_sessionmaker[AsyncSession],
        tickers: list[str] | None = None,
    ) -> None:
        self.strategy_key = strategy_key
        self._session_factory = session_factory
        self.tickers = tickers or self.DEFAULT_TICKERS.get(strategy_key, ["AAPL", "TSLA", "MSFT"])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        start_date: date,
        end_date: date | None = None,
        reset_portfolio: bool = True,
    ) -> BacktestResult:
        """
        Execute the backtest.

        Parameters
        ----------
        start_date:
            First day to simulate (inclusive).
        end_date:
            Last day to simulate (inclusive). Defaults to yesterday to ensure
            complete OHLCV data is available.
        reset_portfolio:
            When *True* (default), clear all existing trades / snapshots /
            open positions for the strategy before running so the backtest
            starts from a clean state.
        """
        end_date = end_date or (date.today() - timedelta(days=1))

        # 1. Load historical data
        historical_data = self._load_historical_data(start_date, end_date)
        if not historical_data:
            raise ValueError(
                f"Could not download historical data for tickers {self.tickers}"
            )

        # 2. Optionally reset portfolio
        if reset_portfolio:
            await self._reset_portfolio()

        # 3. Build simulated market data provider + strategy
        market_data = BacktestMarketDataProvider(historical_data)
        strategy = self._build_strategy(market_data)
        signal_store = InMemorySignalStore()
        trading_manager = PaperTradingManager(
            session_factory=self._session_factory,
            market_data=market_data,
            slippage_bps=10,
        )

        # 4. Main simulation loop
        total_signals = 0
        trading_days = 0
        current = start_date

        while current <= end_date:
            if current.weekday() >= 5:  # Skip Saturday (5) and Sunday (6)
                current += timedelta(days=1)
                continue

            market_data.set_current_date(current)
            simulated_dt = datetime.combine(current, datetime.min.time()).replace(
                tzinfo=timezone.utc
            )

            try:
                analyzed = await strategy.analyze_data()
                signals = await strategy.generate_signals(analyzed)
                for sig in signals:
                    await signal_store.record(sig)

                total_signals += len(signals)

                if signals:
                    await trading_manager.process_signals(signals, simulated_dt=simulated_dt)
                else:
                    # Still take a daily snapshot even on quiet days
                    await trading_manager.snapshot_daily_equity(
                        self.strategy_key,
                        snapshot_date_override=current,
                    )
            except Exception:
                # Log and continue – don't abort the whole backtest on one bad day
                await trading_manager.snapshot_daily_equity(
                    self.strategy_key,
                    snapshot_date_override=current,
                )

            trading_days += 1
            current += timedelta(days=1)

        # 5. Collect results
        return await self._compile_result(start_date, end_date, trading_days, total_signals)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_historical_data(
        self,
        start_date: date,
        end_date: date,
    ) -> dict[str, pd.DataFrame]:
        """Download OHLCV data for all tickers in one batch call."""
        # yfinance end date is exclusive, so add 1 day
        yf_end = (end_date + timedelta(days=1)).isoformat()
        yf_start = start_date.isoformat()

        result: dict[str, pd.DataFrame] = {}
        for ticker in self.tickers:
            try:
                df = yf.download(
                    ticker,
                    start=yf_start,
                    end=yf_end,
                    progress=False,
                    multi_level_names=False,
                )
                if not df.empty:
                    result[ticker] = df
            except Exception:
                continue
        return result

    def _build_strategy(
        self,
        market_data: BacktestMarketDataProvider,
    ) -> StrategyBUnusualVolume:
        """Return the appropriate backtesting strategy variant."""
        if self.strategy_key == "strategy_b_unusualvolume":
            strat = BacktestStrategyBUnusualVolume(market_data)
            # Limit to tickers with available historical data
            strat.VOLUME_SPIKE_TICKERS = self.tickers  # type: ignore[attr-defined]
            return strat
        raise NotImplementedError(
            f"Backtesting for '{self.strategy_key}' is not yet implemented. "
            f"Supported: {list(self.SUPPORTED_STRATEGIES)}"
        )

    async def _reset_portfolio(self) -> None:
        """Clear existing trade history, snapshots, and open positions for this strategy."""
        async with self._session_factory() as session:
            async with session.begin():
                strategy = await session.scalar(
                    select(StrategyModel).where(StrategyModel.strategy_key == self.strategy_key)
                )
                if strategy is None:
                    return

                portfolio = await session.scalar(
                    select(PortfolioModel).where(PortfolioModel.strategy_id == strategy.id)
                )
                if portfolio is None:
                    return

                pid = portfolio.id
                # Delete related rows (cascade would handle this, but being explicit)
                await session.execute(
                    delete(OpenPositionModel).where(OpenPositionModel.portfolio_id == pid)
                )
                await session.execute(
                    delete(TradeHistoryModel).where(TradeHistoryModel.portfolio_id == pid)
                )
                await session.execute(
                    delete(PerformanceSnapshotModel).where(
                        PerformanceSnapshotModel.portfolio_id == pid
                    )
                )
                # Reset portfolio balances
                portfolio.cash_balance = portfolio.starting_cash
                portfolio.equity_value = portfolio.starting_cash

    async def _compile_result(
        self,
        start_date: date,
        end_date: date,
        trading_days: int,
        total_signals: int,
    ) -> BacktestResult:
        """Compute aggregate statistics from the DB after the simulation."""
        async with self._session_factory() as session:
            strategy = await session.scalar(
                select(StrategyModel).where(StrategyModel.strategy_key == self.strategy_key)
            )
            if strategy is None:
                raise ValueError(f"Strategy '{self.strategy_key}' not found")

            portfolio = await session.scalar(
                select(PortfolioModel).where(PortfolioModel.strategy_id == strategy.id)
            )
            if portfolio is None:
                raise ValueError("Portfolio not found")

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

            starting_cash = float(portfolio.starting_cash)
            final_equity = float(portfolio.equity_value)
            total_return = (
                (final_equity - starting_cash) / starting_cash * 100
                if starting_cash > 0
                else 0.0
            )

            # Max drawdown
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

            # Win rate (SELL trades with realized_pnl > 0)
            sell_trades = [t for t in trades if t.realized_pnl is not None]
            winning = sum(1 for t in sell_trades if t.realized_pnl > Decimal("0"))
            win_rate = (winning / len(sell_trades) * 100) if sell_trades else 0.0

            daily_snapshots = [
                {
                    "date": s.snapshot_date.isoformat(),
                    "equity": float(s.equity_value),
                    "cash": float(s.cash_balance),
                    "market_value": float(s.market_value),
                    "daily_pnl": float(s.daily_pnl),
                    "total_return_pct": float(s.total_return_pct),
                }
                for s in snapshots
            ]

            return BacktestResult(
                strategy_key=self.strategy_key,
                start_date=start_date,
                end_date=end_date,
                tickers=self.tickers,
                total_trading_days=trading_days,
                total_signals=total_signals,
                total_trades=len(trades),
                starting_cash=starting_cash,
                final_equity=final_equity,
                total_return_pct=round(total_return, 4),
                max_drawdown_pct=round(max_dd, 4),
                win_rate_pct=round(win_rate, 4),
                daily_snapshots=daily_snapshots,
            )
