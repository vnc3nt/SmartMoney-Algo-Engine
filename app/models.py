# app/models.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey,
    Integer, Numeric, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.base import Base

TRADES_SCHEMA = "trades"


class StrategyModel(Base):
    __tablename__ = "strategies"
    __table_args__ = {"schema": TRADES_SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True)
    strategy_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_frequency: Mapped[str] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PortfolioModel(Base):
    __tablename__ = "portfolios"
    __table_args__ = {"schema": TRADES_SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True)
    strategy_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{TRADES_SCHEMA}.strategies.id", ondelete="CASCADE"),
        unique=True, index=True,
    )
    base_currency: Mapped[str] = mapped_column(String(10), default="USD", server_default="USD")
    starting_cash: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("100000.0000"))
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("100000.0000"))
    equity_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("100000.0000"))
    slippage_bps: Mapped[int] = mapped_column(Integer, default=10, server_default="10")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OpenPositionModel(Base):
    __tablename__ = "open_positions"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "ticker", name="uq_open_positions_portfolio_ticker"),
        {"schema": TRADES_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{TRADES_SCHEMA}.portfolios.id", ondelete="CASCADE"), index=True,
    )
    strategy_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{TRADES_SCHEMA}.strategies.id", ondelete="CASCADE"), index=True,
    )
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    average_entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    last_mark_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    market_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TradeHistoryModel(Base):
    __tablename__ = "trade_history"
    __table_args__ = {"schema": TRADES_SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True)
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{TRADES_SCHEMA}.portfolios.id", ondelete="CASCADE"), index=True,
    )
    strategy_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{TRADES_SCHEMA}.strategies.id", ondelete="CASCADE"), index=True,
    )
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    signal_price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    executed_price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    gross_notional: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    slippage_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    fees: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PerformanceSnapshotModel(Base):
    __tablename__ = "performance_snapshots"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "snapshot_date", name="uq_performance_snapshot_daily"),
        {"schema": TRADES_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{TRADES_SCHEMA}.portfolios.id", ondelete="CASCADE"), index=True,
    )
    strategy_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{TRADES_SCHEMA}.strategies.id", ondelete="CASCADE"), index=True,
    )
    snapshot_date: Mapped[date] = mapped_column(Date)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    market_value: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    equity_value: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    open_positions_count: Mapped[int] = mapped_column(Integer, default=0)
    daily_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    total_return_pct: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())