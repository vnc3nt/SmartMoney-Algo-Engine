"""Database seeding script for initial strategies and portfolios."""

import asyncio
import os
from decimal import Decimal
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models import StrategyAllocationModel, StrategyModel, PortfolioModel, TRADES_SCHEMA

# Load environment variables
load_dotenv()

# Database URL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/smartmoney"
)


async def seed_database():
    """Initialize database with base strategies and portfolios."""
    engine = create_async_engine(DATABASE_URL, echo=False)

    # Create async session factory
    async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            # Ensure schema exists
            await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {TRADES_SCHEMA}"))

        async with async_session_maker() as session:
            async with session.begin():
                # Check if strategies already exist
                existing_strategies = await session.execute(
                    select(StrategyModel)
                )
                if existing_strategies.scalars().first():
                    print("✓ Strategies already exist, skipping seed")
                    return

                # Define the 4 base strategies
                strategies = [
                    StrategyModel(
                        id=uuid4(),
                        strategy_key="strategy_a_legalinsider",
                        name="Strategy A: Legal Insider",
                        description="Trades based on CEO insider buy signals from Finnhub",
                        execution_frequency="1d",
                        is_active=True,
                    ),
                    StrategyModel(
                        id=uuid4(),
                        strategy_key="strategy_b_unusualvolume",
                        name="Strategy B: Unusual Volume",
                        description="Trades based on volume spikes >150% using yfinance data",
                        execution_frequency="1m",
                        is_active=True,
                    ),
                    StrategyModel(
                        id=uuid4(),
                        strategy_key="strategy_ab_combined",
                        name="Strategy AB: Combined",
                        description="Combines signals from Strategy A and B for higher confidence",
                        execution_frequency="1h",
                        is_active=True,
                    ),
                    StrategyModel(
                        id=uuid4(),
                        strategy_key="strategy_c_newssentiment",
                        name="Strategy C: News Sentiment",
                        description="Trades on fast sentiment shifts from real-time company news",
                        execution_frequency="1m",
                        is_active=True,
                    ),
                ]

                session.add_all(strategies)
                await session.flush()

                # Create portfolios for each strategy
                portfolios = [
                    PortfolioModel(
                        id=uuid4(),
                        strategy_id=strategies[0].id,
                        base_currency="USD",
                        starting_cash=Decimal("100000.0000"),
                        cash_balance=Decimal("100000.0000"),
                        equity_value=Decimal("100000.0000"),
                        slippage_bps=10,
                    ),
                    PortfolioModel(
                        id=uuid4(),
                        strategy_id=strategies[1].id,
                        base_currency="USD",
                        starting_cash=Decimal("100000.0000"),
                        cash_balance=Decimal("100000.0000"),
                        equity_value=Decimal("100000.0000"),
                        slippage_bps=10,
                    ),
                    PortfolioModel(
                        id=uuid4(),
                        strategy_id=strategies[2].id,
                        base_currency="USD",
                        starting_cash=Decimal("100000.0000"),
                        cash_balance=Decimal("100000.0000"),
                        equity_value=Decimal("100000.0000"),
                        slippage_bps=10,
                    ),
                    PortfolioModel(
                        id=uuid4(),
                        strategy_id=strategies[3].id,
                        base_currency="USD",
                        starting_cash=Decimal("100000.0000"),
                        cash_balance=Decimal("100000.0000"),
                        equity_value=Decimal("100000.0000"),
                        slippage_bps=10,
                    ),
                ]

                session.add_all(portfolios)
                allocations = [
                    StrategyAllocationModel(
                        id=uuid4(),
                        strategy_id=strategy.id,
                        allocation_fraction=Decimal("0.100000"),
                        is_auto_managed=True,
                    )
                    for strategy in strategies
                ]
                session.add_all(allocations)
                await session.commit()

                print(
                    f"✓ Seeded {len(strategies)} strategies, {len(portfolios)} portfolios, "
                    f"and {len(allocations)} allocation records"
                )
                for strategy, portfolio in zip(strategies, portfolios):
                    print(f"  - {strategy.name} (ID: {strategy.id})")

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_database())
    print("\n✓ Database seeding completed successfully!")
