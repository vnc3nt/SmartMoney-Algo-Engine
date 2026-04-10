from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Protocol, Sequence

from app.base import ExecutionFrequency, SignalSide, TradeSide


@dataclass(frozen=True)
class InsiderEvent:
    ticker: str
    insider_role: str
    transaction_type: str
    shares: int
    price: Decimal
    filed_at: datetime

    @property
    def usd_notional(self) -> Decimal:
        return Decimal(self.shares) * self.price


@dataclass(frozen=True)
class VolumeSpike:
    ticker: str
    close: Decimal
    previous_close: Decimal
    current_volume: int
    avg_volume_20: int
    observed_at: datetime

    @property
    def volume_ratio(self) -> Decimal:
        return Decimal(self.current_volume) / Decimal(max(self.avg_volume_20, 1))


@dataclass(frozen=True)
class Signal:
    strategy_key: str
    ticker: str
    side: SignalSide
    signal_price: Decimal
    created_at: datetime
    reason: str
    confidence: Decimal = Decimal("0.50")
    allocation_fraction: Decimal = Decimal("0.10")


class MarketDataProvider:
    """Mock provider for market and insider data."""

    async def get_recent_ceo_buys(self) -> list[InsiderEvent]:
        # TODO: Replace with SEC Form 4 / insider API integration.
        return [
            InsiderEvent(
                ticker="NVDA",
                insider_role="CEO",
                transaction_type="BUY",
                shares=25000,
                price=Decimal("912.50"),
                filed_at=datetime.now(timezone.utc) - timedelta(hours=3),
            ),
            InsiderEvent(
                ticker="MSFT",
                insider_role="CEO",
                transaction_type="BUY",
                shares=4000,
                price=Decimal("421.20"),
                filed_at=datetime.now(timezone.utc) - timedelta(hours=4),
            ),
        ]

    async def get_unusual_volume_candidates(self) -> list[VolumeSpike]:
        # TODO: Replace with Polygon / IEX / Alpaca / TwelveData websocket + intraday bars.
        return [
            VolumeSpike(
                ticker="NVDA",
                close=Decimal("918.10"),
                previous_close=Decimal("905.00"),
                current_volume=4_800_000,
                avg_volume_20=1_300_000,
                observed_at=datetime.now(timezone.utc),
            ),
            VolumeSpike(
                ticker="AAPL",
                close=Decimal("201.80"),
                previous_close=Decimal("202.10"),
                current_volume=3_100_000,
                avg_volume_20=1_700_000,
                observed_at=datetime.now(timezone.utc),
            ),
        ]

    async def get_last_price(self, ticker: str) -> Decimal:
        # TODO: Replace with real-time quote API.
        mock_prices: dict[str, Decimal] = {
            "NVDA": Decimal("919.40"),
            "MSFT": Decimal("424.75"),
            "AAPL": Decimal("200.90"),
        }
        return mock_prices.get(ticker, Decimal("100.00"))


class SignalStore(Protocol):
    async def record(self, signal: Signal) -> None: ...
    async def recent(self, strategy_key: str, since: datetime) -> list[Signal]: ...


class InMemorySignalStore:
    """Ephemeral store for signal correlation; persist later if needed."""

    def __init__(self) -> None:
        self._signals: dict[str, list[Signal]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def record(self, signal: Signal) -> None:
        async with self._lock:
            self._signals[signal.strategy_key].append(signal)

    async def recent(self, strategy_key: str, since: datetime) -> list[Signal]:
        async with self._lock:
            return [s for s in self._signals[strategy_key] if s.created_at >= since]


class BaseStrategy(ABC):
    """Abstract trading strategy interface."""

    strategy_key: str
    name: str

    def __init__(self, market_data: MarketDataProvider) -> None:
        self.market_data = market_data

    @property
    @abstractmethod
    def execution_frequency(self) -> ExecutionFrequency:
        """Return scheduling cadence."""

    @abstractmethod
    async def analyze_data(self) -> Any:
        """Fetch and normalize raw inputs."""

    @abstractmethod
    async def generate_signals(self, analyzed_data: Any) -> list[Signal]:
        """Transform analyzed inputs into tradeable signals."""

    async def run(self, signal_store: SignalStore) -> list[Signal]:
        analyzed = await self.analyze_data()
        signals = await self.generate_signals(analyzed)
        for signal in signals:
            await signal_store.record(signal)
        return signals


class StrategyALegalInsider(BaseStrategy):
    strategy_key = "strategy_a_legalinsider"
    name = "Strategy_A_LegalInsider"

    @property
    def execution_frequency(self) -> ExecutionFrequency:
        return ExecutionFrequency.D1

    async def analyze_data(self) -> list[InsiderEvent]:
        events = await self.market_data.get_recent_ceo_buys()
        return [
            event
            for event in events
            if event.insider_role.upper() == "CEO" and event.transaction_type.upper() == "BUY"
        ]

    async def generate_signals(self, analyzed_data: list[InsiderEvent]) -> list[Signal]:
        signals: list[Signal] = []
        now = datetime.now(timezone.utc)

        for event in analyzed_data:
            if event.usd_notional >= Decimal("2500000"):
                signals.append(
                    Signal(
                        strategy_key=self.strategy_key,
                        ticker=event.ticker,
                        side=SignalSide.BUY,
                        signal_price=event.price,
                        created_at=now,
                        confidence=Decimal("0.82"),
                        reason=f"CEO buy detected, notional={event.usd_notional}",
                    )
                )
        return signals


class StrategyBUnusualVolume(BaseStrategy):
    strategy_key = "strategy_b_unusualvolume"
    name = "Strategy_B_UnusualVolume"

    @property
    def execution_frequency(self) -> ExecutionFrequency:
        return ExecutionFrequency.M1

    async def analyze_data(self) -> list[VolumeSpike]:
        return await self.market_data.get_unusual_volume_candidates()

    async def generate_signals(self, analyzed_data: list[VolumeSpike]) -> list[Signal]:
        signals: list[Signal] = []

        for spike in analyzed_data:
            bullish_price_action = spike.close > spike.previous_close
            if spike.volume_ratio >= Decimal("3.0") and bullish_price_action:
                signals.append(
                    Signal(
                        strategy_key=self.strategy_key,
                        ticker=spike.ticker,
                        side=SignalSide.BUY,
                        signal_price=spike.close,
                        created_at=spike.observed_at,
                        confidence=Decimal("0.76"),
                        reason=(
                            f"Volume spike ratio={spike.volume_ratio.quantize(Decimal('0.01'))}, "
                            "positive intraday momentum"
                        ),
                    )
                )
        return signals


class StrategyABCombined(BaseStrategy):
    strategy_key = "strategy_ab_combined"
    name = "Strategy_AB_Combined"

    def __init__(
        self,
        market_data: MarketDataProvider,
        signal_store: SignalStore,
    ) -> None:
        super().__init__(market_data)
        self.signal_store = signal_store

    @property
    def execution_frequency(self) -> ExecutionFrequency:
        return ExecutionFrequency.H1

    async def analyze_data(self) -> dict[str, tuple[Signal, Signal]]:
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=24)

        signals_a = await self.signal_store.recent("strategy_a_legalinsider", since)
        signals_b = await self.signal_store.recent("strategy_b_unusualvolume", since)

        latest_a = {s.ticker: s for s in signals_a if s.side == SignalSide.BUY}
        latest_b = {s.ticker: s for s in signals_b if s.side == SignalSide.BUY}

        overlap: dict[str, tuple[Signal, Signal]] = {}
        for ticker in set(latest_a).intersection(latest_b):
            overlap[ticker] = (latest_a[ticker], latest_b[ticker])

        return overlap

    async def generate_signals(self, analyzed_data: dict[str, tuple[Signal, Signal]]) -> list[Signal]:
        combined: list[Signal] = []
        now = datetime.now(timezone.utc)

        for ticker, (signal_a, signal_b) in analyzed_data.items():
            reference_price = (signal_a.signal_price + signal_b.signal_price) / Decimal("2")
            combined.append(
                Signal(
                    strategy_key=self.strategy_key,
                    ticker=ticker,
                    side=SignalSide.BUY,
                    signal_price=reference_price,
                    created_at=now,
                    confidence=Decimal("0.90"),
                    allocation_fraction=Decimal("0.15"),
                    reason="A and B confirmed the same ticker within 24h",
                )
            )
        return combined