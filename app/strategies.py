from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Protocol, Sequence
import os

import yfinance as yf
import finnhub

from app.enums import ExecutionFrequency, SignalSide, TradeSide


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
    avg_volume_5: int
    observed_at: datetime

    @property
    def volume_ratio(self) -> Decimal:
        return Decimal(self.current_volume) / Decimal(max(self.avg_volume_5, 1))


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
    """Fetch real market data using yfinance and Finnhub."""

    VOLUME_SPIKE_TICKERS = ["AAPL", "TSLA", "MSFT", "NVDA", "AMD"]
    INSIDER_WATCH_TICKERS = ["AAPL", "TSLA", "MSFT", "NVDA", "AMD", "GOOG", "META"]
    MIN_INSIDER_TRANSACTION_USD = Decimal("1000000")  # Only track insider trades > $1M

    def __init__(self) -> None:
        self.finnhub_client = None
        api_key = os.getenv("FINNHUB_API_KEY")
        if api_key:
            try:
                self.finnhub_client = finnhub.Client(api_key=api_key)
            except Exception:
                pass

    async def get_recent_ceo_buys(self) -> list[InsiderEvent]:
        """Fetch recent CEO insider buys from Finnhub."""
        if not self.finnhub_client:
            return []

        events = []
        now = datetime.now(timezone.utc)

        for ticker in self.INSIDER_WATCH_TICKERS:
            try:
                # Finnhub insider transactions endpoint
                transactions = self.finnhub_client.insider_transactions(ticker)

                if not transactions or "data" not in transactions:
                    continue

                for txn in transactions["data"]:
                    # Filter for CEO buys from last 7 days
                    filing_date = datetime.fromisoformat(txn.get("filingDate", "").replace("Z", "+00:00"))
                    if (now - filing_date).days > 7:
                        continue

                    # Only CEO/President level transactions
                    person_relation = txn.get("personRelation", [])
                    if not any(r in person_relation for r in ["CEO", "President", "Chief"]):
                        continue

                    # Only BUY transactions
                    transaction_type = txn.get("transactionType", "")
                    if transaction_type != "Buy":
                        continue

                    # Get transaction value
                    shares = Decimal(str(txn.get("shares", 0)))
                    price = Decimal(str(txn.get("price", 0)))
                    notional = shares * price

                    # Only significant transactions
                    if notional < self.MIN_INSIDER_TRANSACTION_USD:
                        continue

                    events.append(
                        InsiderEvent(
                            ticker=ticker,
                            insider_role=txn.get("personRelation", ["Unknown"])[0],
                            transaction_type="BUY",
                            shares=int(shares),
                            price=price,
                            filed_at=filing_date,
                        )
                    )
            except Exception:
                # Skip ticker on API error
                continue

        return events

    async def get_unusual_volume_candidates(self) -> list[VolumeSpike]:
        """Fetch last 5 days of volume data and detect spikes (>150%)."""
        spikes = []
        now = datetime.now(timezone.utc)

        for ticker in self.VOLUME_SPIKE_TICKERS:
            try:
                # Fetch last 5 days of OHLCV data
                data = yf.download(ticker, period="5d", progress=False, multi_level_names=False)

                if data.empty or len(data) < 2:
                    continue

                # Get last two rows: previous and current
                prev_row = data.iloc[-2]
                curr_row = data.iloc[-1]

                current_volume = int(curr_row["Volume"])
                close = Decimal(str(curr_row["Close"]))
                previous_close = Decimal(str(prev_row["Close"]))

                # Average volume of last 5 days
                avg_volume_5 = int(data["Volume"].mean())

                # Detect spike: current volume > 150% of 5-day average
                volume_ratio = Decimal(current_volume) / Decimal(max(avg_volume_5, 1))
                if volume_ratio >= Decimal("1.50"):
                    spikes.append(
                        VolumeSpike(
                            ticker=ticker,
                            close=close,
                            previous_close=previous_close,
                            current_volume=current_volume,
                            avg_volume_5=avg_volume_5,
                            observed_at=now,
                        )
                    )
            except Exception:
                # Skip ticker if data fetch fails
                continue

        return spikes

    async def get_last_price(self, ticker: str) -> Decimal:
        """Fetch the last available price for a ticker."""
        try:
            data = yf.download(ticker, period="1d", progress=False, multi_level_names=False)
            if data.empty:
                return Decimal("100.00")
            return Decimal(str(data["Close"].iloc[-1]))
        except Exception:
            return Decimal("100.00")


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
            # Signal for significant insider CEO buys (>$2.5M notional)
            if event.usd_notional >= Decimal("2500000"):
                signals.append(
                    Signal(
                        strategy_key=self.strategy_key,
                        ticker=event.ticker,
                        side=SignalSide.BUY,
                        signal_price=event.price,
                        created_at=now,
                        confidence=Decimal("0.82"),
                        allocation_fraction=Decimal("0.05"),
                        reason=f"Insider CEO buy: {event.insider_role} purchased {event.shares} shares at ${event.price}",
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
            # Signal when volume > 150% of 5-day average
            if spike.volume_ratio >= Decimal("1.50"):
                signals.append(
                    Signal(
                        strategy_key=self.strategy_key,
                        ticker=spike.ticker,
                        side=SignalSide.BUY,
                        signal_price=spike.close,
                        created_at=spike.observed_at,
                        confidence=Decimal("0.75"),
                        reason=(
                            f"Volume spike: {spike.current_volume} vs avg {spike.avg_volume_5} "
                            f"(ratio={spike.volume_ratio.quantize(Decimal('0.01'))})"
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