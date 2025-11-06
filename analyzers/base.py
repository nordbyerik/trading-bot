"""
Base Analyzer Interface

Defines the common interface and data structures for all market analyzers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import time
import logging

if TYPE_CHECKING:
    from kalshi_client import KalshiDataClient

logger = logging.getLogger(__name__)


class ConfidenceLevel(Enum):
    """Confidence level for identified opportunities."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OpportunityStrength(Enum):
    """Strength of opportunity based on threshold requirements."""
    SOFT = "soft"  # Relaxed requirements - more opportunities but lower quality
    HARD = "hard"  # Strict requirements - fewer but higher quality opportunities


class OpportunityType(Enum):
    """Types of trading opportunities."""
    ARBITRAGE = "arbitrage"
    WIDE_SPREAD = "wide_spread"
    MISPRICING = "mispricing"
    MOMENTUM_FADE = "momentum_fade"
    CORRELATION_BREAK = "correlation_break"
    IMBALANCE = "imbalance"


@dataclass
class Opportunity:
    """Represents a trading opportunity identified by an analyzer."""

    # Core identification
    opportunity_type: OpportunityType
    confidence: ConfidenceLevel
    strength: OpportunityStrength  # HARD (strict requirements) or SOFT (relaxed)
    timestamp: datetime

    # Market information
    market_tickers: List[str]
    market_titles: List[str]
    market_urls: List[str]

    # Opportunity details
    current_prices: Dict[str, float]  # ticker -> price in cents
    estimated_edge_cents: float  # Expected profit in cents
    estimated_edge_percent: float  # Expected profit as percentage

    # Explanation
    reasoning: str  # Human-readable explanation
    additional_data: Dict[str, Any]  # Extra analyzer-specific data

    def to_dict(self) -> Dict[str, Any]:
        """Convert opportunity to dictionary for serialization."""
        return {
            "type": self.opportunity_type.value,
            "confidence": self.confidence.value,
            "strength": self.strength.value,
            "timestamp": self.timestamp.isoformat(),
            "markets": {
                "tickers": self.market_tickers,
                "titles": self.market_titles,
                "urls": self.market_urls,
            },
            "prices": self.current_prices,
            "edge": {
                "cents": self.estimated_edge_cents,
                "percent": self.estimated_edge_percent,
            },
            "reasoning": self.reasoning,
            "additional_data": self.additional_data,
        }

    def __str__(self) -> str:
        """String representation for console output."""
        markets_str = ", ".join(self.market_tickers)
        return (
            f"[{self.opportunity_type.value.upper()}] "
            f"[{self.strength.value.upper()}] "
            f"({self.confidence.value}) "
            f"{markets_str} - "
            f"Edge: {self.estimated_edge_cents:.1f}¢ ({self.estimated_edge_percent:.1f}%) - "
            f"{self.reasoning}"
        )


class BaseAnalyzer(ABC):
    """Abstract base class for all market analyzers."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, kalshi_client: Optional["KalshiDataClient"] = None):
        """
        Initialize the analyzer.

        Args:
            config: Configuration dictionary for analyzer-specific parameters
            kalshi_client: Optional KalshiDataClient for fetching historical data
        """
        self.config = config or {}
        self.kalshi_client = kalshi_client
        self._setup()

    def _setup(self) -> None:
        """
        Perform analyzer-specific setup.
        Override this method in subclasses if needed.
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """
        Get the name of this analyzer.

        Returns:
            Human-readable analyzer name
        """
        pass

    @abstractmethod
    def get_description(self) -> str:
        """
        Get a description of what this analyzer does.

        Returns:
            Human-readable description
        """
        pass

    def get_default_config(self) -> Dict[str, Any]:
        """
        Get default configuration for this analyzer.

        Returns:
            Dictionary of default config values
        """
        return {}

    @abstractmethod
    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets and identify opportunities.

        Args:
            markets: List of market data dictionaries from Kalshi API

        Returns:
            List of identified opportunities
        """
        pass

    def _make_market_url(self, ticker: str) -> str:
        """
        Create a Kalshi market URL from a ticker.

        Args:
            ticker: Market ticker

        Returns:
            Full URL to the market on Kalshi
        """
        # Extract series ticker from market ticker
        # Market tickers are typically like: SERIES-YYYY-MM-DD-XXX
        # We need to get the series part
        parts = ticker.split("-")
        series_ticker = parts[0] if parts else ticker

        return f"https://kalshi.com/markets/{series_ticker}"

    def _get_best_bid(self, orderbook: Dict, side: str) -> Optional[tuple[float, int]]:
        """
        Get the best bid from an orderbook.

        Args:
            orderbook: Orderbook data from API
            side: 'yes' or 'no'

        Returns:
            Tuple of (price_in_cents, quantity) or None if no bids
        """
        bids = orderbook.get(side, [])
        if not bids:
            return None

        # Bids are [price_in_cents, quantity]
        # Kalshi returns bids sorted in ASCENDING order (lowest first)
        # Best bid (highest price) is the LAST element
        return (bids[-1][0], bids[-1][1])

    def _calculate_spread(self, yes_bid: float, no_bid: float) -> float:
        """
        Calculate the bid-ask spread.

        Args:
            yes_bid: Best yes bid price in cents
            no_bid: Best no bid price in cents

        Returns:
            Spread in cents (100 - yes_bid - no_bid)
        """
        return 100.0 - yes_bid - no_bid

    def _fetch_market_candlesticks(
        self,
        market: Dict[str, Any],
        lookback_hours: int = 24,
        period_interval: int = 60
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch historical candlestick data for a market.

        Args:
            market: Market data dictionary containing ticker and series_ticker
            lookback_hours: How many hours of history to fetch
            period_interval: Candlestick period in minutes (1, 60, or 1440)

        Returns:
            List of candlestick dictionaries sorted by timestamp, or None if unavailable
        """
        if not self.kalshi_client:
            return None

        series_ticker = market.get("series_ticker")
        market_ticker = market.get("ticker")

        if not series_ticker or not market_ticker:
            return None

        try:
            end_ts = int(time.time())
            start_ts = end_ts - (lookback_hours * 3600)

            response = self.kalshi_client.get_market_candlesticks(
                series_ticker=series_ticker,
                market_ticker=market_ticker,
                start_ts=start_ts,
                end_ts=end_ts,
                period_interval=period_interval
            )

            candlesticks = response.get("candlesticks", [])
            # Sort by timestamp to ensure chronological order
            candlesticks.sort(key=lambda x: x.get("ts", 0))

            return candlesticks if candlesticks else None

        except Exception as e:
            logger.debug(f"Could not fetch candlesticks for {market_ticker}: {e}")
            return None

    def _extract_prices_from_candlesticks(
        self,
        candlesticks: List[Dict[str, Any]],
        price_field: str = "yes_ask_close"
    ) -> List[float]:
        """
        Extract price series from candlestick data.

        Args:
            candlesticks: List of candlestick dictionaries
            price_field: Which price field to extract (yes_ask_close, yes_ask_open, etc.)

        Returns:
            List of prices in chronological order
        """
        prices = []
        for candle in candlesticks:
            price = candle.get(price_field)
            if price is not None:
                prices.append(float(price))
        return prices

    def _extract_volumes_from_candlesticks(self, candlesticks: List[Dict[str, Any]]) -> List[float]:
        """
        Extract volume series from candlestick data.

        Args:
            candlesticks: List of candlestick dictionaries

        Returns:
            List of volumes in chronological order
        """
        volumes = []
        for candle in candlesticks:
            volume = candle.get("volume")
            if volume is not None:
                volumes.append(float(volume))
        return volumes

    def __repr__(self) -> str:
        """String representation of the analyzer."""
        return f"{self.__class__.__name__}(config={self.config})"
