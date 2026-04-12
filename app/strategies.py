from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Protocol, Sequence
import os
import logging
from uuid import uuid4

import yfinance as yf
import finnhub
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.enums import ExecutionFrequency, SignalSide, TradeSide
from app.models import StrategySignalModel

logger = logging.getLogger(__name__)


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
class NewsEvent:
    ticker: str
    headline: str
    summary: str
    source: str
    published_at: datetime
    url: str | None = None


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
    NEWS_WATCH_TICKERS = ["AAPL", "TSLA", "MSFT", "NVDA", "AMD", "META", "GOOG"]
    MIN_INSIDER_TRANSACTION_USD = Decimal("1000000")  # Only track insider trades > $1M

    def __init__(self) -> None:
        self.finnhub_client = None
        api_key = os.getenv("FINNHUB_API_KEY")
        if api_key:
            try:
                self.finnhub_client = finnhub.Client(api_key=api_key)
            except Exception:
                logger.exception("Finnhub client initialization failed")

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
                logger.exception("Insider fetch failed for ticker=%s", ticker)
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
                logger.exception("Unusual volume fetch failed for ticker=%s", ticker)
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
            logger.exception("Price fetch failed for ticker=%s", ticker)
            return Decimal("100.00")

    async def get_company_news(
        self,
        ticker: str,
        from_dt: datetime,
        to_dt: datetime,
    ) -> list[NewsEvent]:
        """Fetch company news with robust parsing and deterministic fallback."""
        if self.finnhub_client is None:
            return self._mock_news_for_ticker(ticker=ticker, observed_at=to_dt)

        from_str = from_dt.date().isoformat()
        to_str = to_dt.date().isoformat()
        try:
            raw_items = await asyncio.to_thread(
                self.finnhub_client.company_news,
                ticker,
                _from=from_str,
                to=to_str,
            )
        except (RuntimeError, ValueError, TypeError):
            return self._mock_news_for_ticker(ticker=ticker, observed_at=to_dt)

        if not isinstance(raw_items, list):
            return self._mock_news_for_ticker(ticker=ticker, observed_at=to_dt)

        parsed: list[NewsEvent] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            event = self._parse_news_event(ticker=ticker, payload=item)
            if event is not None:
                parsed.append(event)
        return parsed

    def _parse_news_event(self, ticker: str, payload: dict[str, Any]) -> NewsEvent | None:
        headline_raw = payload.get("headline", "")
        summary_raw = payload.get("summary", "")
        if not isinstance(headline_raw, str) or not headline_raw.strip():
            return None
        if not isinstance(summary_raw, str):
            summary_raw = ""

        timestamp_raw = payload.get("datetime")
        published_at = datetime.now(timezone.utc)
        if isinstance(timestamp_raw, (int, float)):
            try:
                published_at = datetime.fromtimestamp(timestamp_raw, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                published_at = datetime.now(timezone.utc)

        source_raw = payload.get("source", "unknown")
        source = source_raw if isinstance(source_raw, str) and source_raw else "unknown"

        url_raw = payload.get("url")
        url = url_raw if isinstance(url_raw, str) and url_raw else None

        return NewsEvent(
            ticker=ticker,
            headline=headline_raw.strip(),
            summary=summary_raw.strip(),
            source=source.strip(),
            published_at=published_at,
            url=url,
        )

    def _mock_news_for_ticker(self, ticker: str, observed_at: datetime) -> list[NewsEvent]:
        mock_headlines: dict[str, tuple[str, str]] = {
            "AAPL": ("Apple guidance raised after record profits", "Management raised guidance for next quarter."),
            "TSLA": ("Tesla faces lawsuit over autopilot safety claims", "Regulatory scrutiny intensified this week."),
            "MSFT": ("Microsoft reports strong cloud growth", "Azure demand beat analyst expectations."),
        }
        headline, summary = mock_headlines.get(
            ticker,
            ("Company update: neutral market commentary", "No material sentiment shift detected."),
        )
        return [
            NewsEvent(
                ticker=ticker,
                headline=headline,
                summary=summary,
                source="mock-feed",
                published_at=observed_at,
                url=None,
            )
        ]


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


class DatabaseSignalStore:
    """Persistent signal store for cross-strategy correlation across restarts."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(self, signal: Signal) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                session.add(
                    StrategySignalModel(
                        id=uuid4(),
                        strategy_key=signal.strategy_key,
                        ticker=signal.ticker,
                        side=signal.side.value,
                        signal_price=signal.signal_price,
                        confidence=signal.confidence,
                        allocation_fraction=signal.allocation_fraction,
                        reason=signal.reason,
                        created_at=signal.created_at,
                    )
                )

    async def recent(self, strategy_key: str, since: datetime) -> list[Signal]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(StrategySignalModel)
                    .where(StrategySignalModel.strategy_key == strategy_key)
                    .where(StrategySignalModel.created_at >= since)
                    .order_by(StrategySignalModel.created_at.desc())
                )
            ).scalars().all()

            return [
                Signal(
                    strategy_key=row.strategy_key,
                    ticker=row.ticker,
                    side=SignalSide(row.side),
                    signal_price=row.signal_price,
                    created_at=row.created_at,
                    reason=row.reason,
                    confidence=row.confidence,
                    allocation_fraction=row.allocation_fraction,
                )
                for row in rows
            ]


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


class StrategyCNewsSentiment(BaseStrategy):
    strategy_key = "strategy_c_newssentiment"
    name = "Strategy_C_NewsSentiment"

    POSITIVE_KEYWORDS: dict[str, Decimal] = {
        "guidance raised": Decimal("2.0"),
        "record profits": Decimal("2.0"),
        "beats expectations": Decimal("1.8"),
        "strong growth": Decimal("1.5"),
        "buyback": Decimal("1.2"),
        "upgraded": Decimal("1.0"),
    }
    NEGATIVE_KEYWORDS: dict[str, Decimal] = {
        "lawsuit": Decimal("-2.2"),
        "guidance cut": Decimal("-2.0"),
        "misses expectations": Decimal("-1.8"),
        "regulatory probe": Decimal("-1.7"),
        "fraud": Decimal("-2.5"),
        "downgraded": Decimal("-1.0"),
    }
    SENTIMENT_BUY_THRESHOLD = Decimal("1.5")
    SENTIMENT_SELL_THRESHOLD = Decimal("-1.5")

    @property
    def execution_frequency(self) -> ExecutionFrequency:
        return ExecutionFrequency.M1

    async def analyze_data(self) -> dict[str, list[NewsEvent]]:
        now = datetime.now(timezone.utc)
        from_dt = now - timedelta(hours=24)
        ticker_tasks = [
            self.market_data.get_company_news(ticker=ticker, from_dt=from_dt, to_dt=now)
            for ticker in self.market_data.NEWS_WATCH_TICKERS
        ]
        fetched = await asyncio.gather(*ticker_tasks)
        return {
            ticker: news_items
            for ticker, news_items in zip(self.market_data.NEWS_WATCH_TICKERS, fetched, strict=True)
        }

    async def generate_signals(self, analyzed_data: dict[str, list[NewsEvent]]) -> list[Signal]:
        now = datetime.now(timezone.utc)
        signals: list[Signal] = []

        for ticker, news_items in analyzed_data.items():
            score = self._score_news_items(news_items)
            if score == Decimal("0"):
                continue

            side: SignalSide | None = None
            confidence = Decimal("0.55")
            if score >= self.SENTIMENT_BUY_THRESHOLD:
                side = SignalSide.BUY
                confidence = min(Decimal("0.92"), Decimal("0.60") + (score / Decimal("10")))
            elif score <= self.SENTIMENT_SELL_THRESHOLD:
                side = SignalSide.SELL
                confidence = min(Decimal("0.92"), Decimal("0.60") + (abs(score) / Decimal("10")))

            if side is None:
                continue

            signal_price = await self.market_data.get_last_price(ticker)
            signals.append(
                Signal(
                    strategy_key=self.strategy_key,
                    ticker=ticker,
                    side=side,
                    signal_price=signal_price,
                    created_at=now,
                    confidence=confidence.quantize(Decimal("0.01")),
                    allocation_fraction=Decimal("0.08"),
                    reason=f"News sentiment score={score} from {len(news_items)} article(s)",
                )
            )

        return signals

    def _score_news_items(self, news_items: list[NewsEvent]) -> Decimal:
        aggregate = Decimal("0")
        for item in news_items:
            text = f"{item.headline} {item.summary}".lower()
            item_score = Decimal("0")
            for phrase, weight in self.POSITIVE_KEYWORDS.items():
                if phrase in text:
                    item_score += weight
            for phrase, weight in self.NEGATIVE_KEYWORDS.items():
                if phrase in text:
                    item_score += weight
            aggregate += item_score
        return aggregate


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
