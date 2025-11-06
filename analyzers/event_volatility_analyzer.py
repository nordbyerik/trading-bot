"""
Event Volatility Crush Analyzer

Detects markets experiencing volatility crush similar to IV crush in traditional options.
Identifies opportunities where novice traders buy into high volatility without understanding
that prices often normalize after major events.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength


logger = logging.getLogger(__name__)


class EventVolatilityCrushAnalyzer(BaseAnalyzer):
    """
    Analyzes markets for event-driven volatility crush opportunities.

    Similar to IV crush in options:
    - Prices spike before major events (debates, announcements, earnings)
    - Novices FOMO into high volatility positions
    - After event passes, volatility normalizes
    - Smart money fades the move or waits for post-event convergence
    """

    def get_name(self) -> str:
        return "Event Volatility Crush Analyzer"

    def get_description(self) -> str:
        return (
            "Detects markets with recent high volatility and volume spikes "
            "that may normalize after events, exploiting novice FOMO behavior"
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            # Hard opportunity thresholds
            "hard_min_price_change_pct": 20.0,  # 20% move in lookback period
            "hard_min_volume_spike": 3.0,  # 3x average volume
            "hard_hours_lookback": 24,  # Look at past 24 hours

            # Soft opportunity thresholds
            "soft_min_price_change_pct": 15.0,  # 15% move
            "soft_min_volume_spike": 2.0,  # 2x average volume
            "soft_hours_lookback": 48,  # Look at past 48 hours

            # General settings
            "min_volume": 100,  # Minimum volume to consider
            "exclude_near_expiration_hours": 6,  # Ignore markets about to expire
        }

    def _setup(self) -> None:
        """Apply default config values."""
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for volatility crush opportunities.

        Args:
            markets: List of market data dictionaries with orderbook data

        Returns:
            List of volatility crush opportunities
        """
        opportunities = []
        now = datetime.now(timezone.utc)

        for market in markets:
            opportunity = self._analyze_single_market(market, now)
            if opportunity:
                opportunities.append(opportunity)

        logger.info(
            f"EventVolatilityCrushAnalyzer found {len(opportunities)} opportunities "
            f"out of {len(markets)} markets"
        )

        return opportunities

    def _analyze_single_market(
        self, market: Dict[str, Any], now: datetime
    ) -> Optional[Opportunity]:
        """Analyze a single market for volatility crush opportunities."""
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "Unknown Market")

        # Check volume threshold
        volume = market.get("volume", 0)
        if volume < self.config["min_volume"]:
            return None

        # Check if too close to expiration
        expiration_str = market.get("close_time") or market.get("expiration_time")
        if expiration_str:
            expiration = self._parse_datetime(expiration_str)
            if expiration:
                hours_remaining = (expiration - now).total_seconds() / 3600.0
                if 0 < hours_remaining < self.config["exclude_near_expiration_hours"]:
                    logger.debug(
                        f"[VOL-CRUSH] {ticker}: Too close to expiration ({hours_remaining:.1f}h)"
                    )
                    return None

        # Try to fetch historical data to detect volatility
        # Check for HARD opportunity first (24h lookback)
        hard_result = self._check_volatility_crush(
            market,
            lookback_hours=self.config["hard_hours_lookback"],
            min_price_change_pct=self.config["hard_min_price_change_pct"],
            min_volume_spike=self.config["hard_min_volume_spike"]
        )

        if hard_result:
            strength = OpportunityStrength.HARD
            result = hard_result
        else:
            # Try SOFT opportunity (48h lookback, relaxed thresholds)
            soft_result = self._check_volatility_crush(
                market,
                lookback_hours=self.config["soft_hours_lookback"],
                min_price_change_pct=self.config["soft_min_price_change_pct"],
                min_volume_spike=self.config["soft_min_volume_spike"]
            )

            if soft_result:
                strength = OpportunityStrength.SOFT
                result = soft_result
            else:
                return None

        # Extract result data
        price_change_pct = result["price_change_pct"]
        volume_spike = result["volume_spike"]
        current_price = result["current_price"]
        price_direction = result["price_direction"]

        # Determine confidence based on magnitude of move and volume
        confidence = self._calculate_confidence(price_change_pct, volume_spike)

        # Calculate estimated edge
        # The edge comes from fading the move or waiting for normalization
        estimated_edge_cents = self._calculate_edge(price_change_pct, volume_spike)
        estimated_edge_percent = (
            (estimated_edge_cents / (current_price * 100)) * 100 if current_price > 0 else 0
        )

        reasoning = (
            f"Detected {price_change_pct:.1f}% {price_direction} move with {volume_spike:.1f}x "
            f"volume spike. Likely novice FOMO - potential for volatility crush and "
            f"mean reversion after event/hype subsides."
        )

        opportunity = Opportunity(
            opportunity_type=OpportunityType.MOMENTUM_FADE,
            confidence=confidence,
            strength=strength,
            timestamp=datetime.now(),
            market_tickers=[ticker],
            market_titles=[title],
            market_urls=[self._make_market_url(ticker)],
            current_prices={
                ticker: current_price * 100,  # Convert to cents
            },
            estimated_edge_cents=estimated_edge_cents,
            estimated_edge_percent=estimated_edge_percent,
            reasoning=reasoning,
            additional_data={
                "price_change_pct": round(price_change_pct, 2),
                "volume_spike": round(volume_spike, 2),
                "price_direction": price_direction,
                "analysis_type": "event_volatility_crush",
            },
        )

        logger.info(
            f"[VOL-CRUSH] {ticker}: {price_change_pct:.1f}% {price_direction} move, "
            f"{volume_spike:.1f}x volume spike (Strength: {strength.value})"
        )

        return opportunity

    def _check_volatility_crush(
        self,
        market: Dict[str, Any],
        lookback_hours: int,
        min_price_change_pct: float,
        min_volume_spike: float
    ) -> Optional[Dict[str, Any]]:
        """
        Check if a market shows volatility crush signals.

        Returns dict with analysis data if signals found, None otherwise.
        """
        ticker = market.get("ticker")

        # Fetch candlesticks
        candlesticks = self._fetch_market_candlesticks(
            market,
            lookback_hours=lookback_hours,
            period_interval=60  # 1-hour candles
        )

        if not candlesticks or len(candlesticks) < 2:
            return None

        # Extract prices and volumes
        prices = self._extract_prices_from_candlesticks(candlesticks, "yes_ask_close")
        volumes = self._extract_volumes_from_candlesticks(candlesticks)

        if not prices or not volumes or len(prices) < 2 or len(volumes) < 2:
            return None

        # Calculate price change
        start_price = prices[0] / 100.0  # Convert cents to fraction
        current_price = prices[-1] / 100.0
        price_change = abs(current_price - start_price)
        price_change_pct = (price_change / start_price) * 100 if start_price > 0 else 0

        # Determine direction
        if current_price > start_price:
            price_direction = "upward"
        else:
            price_direction = "downward"

        # Calculate volume spike
        # Compare recent volume to historical average
        if len(volumes) >= 4:
            recent_volume = sum(volumes[-2:]) / 2  # Last 2 periods
            historical_volume = sum(volumes[:-2]) / len(volumes[:-2])  # Earlier periods
            volume_spike = recent_volume / historical_volume if historical_volume > 0 else 0
        else:
            # Not enough data for meaningful comparison
            volume_spike = 1.0

        # Check if meets thresholds
        if price_change_pct >= min_price_change_pct and volume_spike >= min_volume_spike:
            return {
                "price_change_pct": price_change_pct,
                "volume_spike": volume_spike,
                "current_price": current_price,
                "price_direction": price_direction,
            }

        return None

    def _calculate_confidence(
        self, price_change_pct: float, volume_spike: float
    ) -> ConfidenceLevel:
        """
        Calculate confidence based on magnitude of move and volume.

        Larger moves with bigger volume spikes = higher confidence in fade opportunity
        """
        # Score price move
        if price_change_pct >= 30:
            price_score = 3
        elif price_change_pct >= 20:
            price_score = 2
        else:
            price_score = 1

        # Score volume spike
        if volume_spike >= 4:
            volume_score = 3
        elif volume_spike >= 2.5:
            volume_score = 2
        else:
            volume_score = 1

        total_score = price_score + volume_score

        if total_score >= 5:
            return ConfidenceLevel.HIGH
        elif total_score >= 3:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW

    def _calculate_edge(self, price_change_pct: float, volume_spike: float) -> float:
        """
        Calculate estimated edge in cents.

        Based on expectation that volatility will normalize and price will partially revert.
        """
        # Assume we can capture some fraction of the recent move
        # More extreme moves with high volume suggest stronger fade opportunity
        reversion_factor = 0.3  # Conservative: expect 30% reversion

        if price_change_pct >= 30 and volume_spike >= 4:
            reversion_factor = 0.5  # Very extreme: 50% reversion expected
        elif price_change_pct >= 20 and volume_spike >= 3:
            reversion_factor = 0.4

        # Edge is the expected reversion in cents
        edge_cents = price_change_pct * reversion_factor

        return edge_cents

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        """Parse ISO 8601 datetime string to timezone-aware datetime."""
        if not value:
            return None
        try:
            if value.endswith("Z"):
                value = value.replace("Z", "+00:00")
            return datetime.fromisoformat(value).astimezone(timezone.utc)
        except (ValueError, AttributeError):
            return None


if __name__ == "__main__":
    # Simple test
    logging.basicConfig(level=logging.INFO)

    analyzer = EventVolatilityCrushAnalyzer()
    print(f"Analyzer: {analyzer.get_name()}")
    print(f"Description: {analyzer.get_description()}")
    print(f"Config: {analyzer.config}")
