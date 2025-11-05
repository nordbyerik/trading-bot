"""
Bollinger Bands Analyzer

Tracks price volatility using Bollinger Bands and identifies opportunities
when prices touch or exceed the bands, signaling potential reversals.
"""

import logging
import math
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength


logger = logging.getLogger(__name__)


class BollingerBandsAnalyzer(BaseAnalyzer):
    """
    Analyzes Bollinger Bands to identify extreme price movements.

    Bollinger Bands consist of:
    - Middle Band: Simple Moving Average (SMA)
    - Upper Band: SMA + (standard deviation × multiplier)
    - Lower Band: SMA - (standard deviation × multiplier)

    When price touches or exceeds bands, it may signal a reversal opportunity.
    """

    def _setup(self) -> None:
        """Initialize price history tracking."""
        # Store price history: {ticker: deque([price1, price2, ...])}
        self.price_history: Dict[str, deque] = {}

        # Apply default config
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def get_name(self) -> str:
        return "Bollinger Bands Analyzer"

    def get_description(self) -> str:
        return (
            "Tracks Bollinger Bands to identify when prices reach extreme "
            "levels, signaling potential mean reversion opportunities"
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            "period": 20,  # Standard BB period
            "std_dev_multiplier": 2.0,  # Standard deviation multiplier
            # Hard opportunity thresholds (strict requirements)
            "hard_band_touch_threshold": 0.5,  # How close to band (cents) to trigger for hard
            "hard_extreme_multiplier": 2.5,  # For extreme signals for hard
            "hard_min_edge_cents": 3,  # Minimum expected edge to report for hard
            # Soft opportunity thresholds (relaxed requirements)
            "soft_band_touch_threshold": 1.0,  # How close to band (cents) to trigger for soft
            "soft_extreme_multiplier": 2.2,  # For extreme signals for soft
            "soft_min_edge_cents": 2,  # Minimum expected edge to report for soft
        }

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for Bollinger Band opportunities.

        Args:
            markets: List of market data dictionaries

        Returns:
            List of Bollinger Band opportunities
        """
        opportunities = []

        for market in markets:
            ticker = market.get("ticker", "UNKNOWN")

            # Get current price
            current_price = self._get_market_price(market)
            if current_price is None:
                continue

            # Update price history
            if ticker not in self.price_history:
                self.price_history[ticker] = deque(maxlen=self.config["period"])
                # Try to pre-warm from historical candlesticks
                self._try_prewarm_from_candlesticks(market, ticker)

            self.price_history[ticker].append(current_price)

            # Check for Bollinger Band opportunities
            opportunity = self._check_bands_signal(market, ticker)
            if opportunity:
                opportunities.append(opportunity)

        logger.info(
            f"BollingerBandsAnalyzer found {len(opportunities)} opportunities "
            f"out of {len(markets)} markets"
        )

        return opportunities

    def _get_market_price(self, market: Dict[str, Any]) -> Optional[float]:
        """Extract current price from market data."""
        # Try yes_price first
        price = market.get("yes_price")

        # If not available, try orderbook
        if price is None and "orderbook" in market:
            yes_bid_data = self._get_best_bid(market["orderbook"], "yes")
            if yes_bid_data:
                price = yes_bid_data[0]

        return price

    def _calculate_bands(
        self, prices: deque
    ) -> Optional[tuple[float, float, float, float]]:
        """
        Calculate Bollinger Bands.

        Returns:
            Tuple of (middle_band, upper_band, lower_band, std_dev) or None
        """
        if len(prices) < self.config["period"]:
            return None

        price_list = list(prices)

        # Calculate middle band (SMA)
        middle_band = sum(price_list) / len(price_list)

        # Calculate standard deviation
        variance = sum((p - middle_band) ** 2 for p in price_list) / len(price_list)
        std_dev = math.sqrt(variance)

        # Calculate upper and lower bands
        multiplier = self.config["std_dev_multiplier"]
        upper_band = middle_band + (std_dev * multiplier)
        lower_band = middle_band - (std_dev * multiplier)

        return middle_band, upper_band, lower_band, std_dev

    def _check_bands_signal(
        self, market: Dict[str, Any], ticker: str
    ) -> Optional[Opportunity]:
        """Check if price is at or beyond Bollinger Bands."""
        history = self.price_history.get(ticker)
        if not history or len(history) < self.config["period"]:
            logger.debug(f"[BB] {ticker}: Insufficient history ({len(history) if history else 0}/{self.config['period']} points)")
            return None

        # Calculate bands
        bands = self._calculate_bands(history)
        if bands is None:
            logger.debug(f"[BB] {ticker}: Could not calculate bands")
            return None

        middle_band, upper_band, lower_band, std_dev = bands
        current_price = history[-1]

        # Log the calculated metrics for this market
        logger.info(
            f"[BB] {ticker}: price={current_price:.1f}¢, "
            f"lower={lower_band:.1f}¢, middle={middle_band:.1f}¢, upper={upper_band:.1f}¢, "
            f"std_dev={std_dev:.1f}¢"
        )

        # Determine opportunity strength (HARD or SOFT), signal type, and confidence
        strength = None
        signal_type = None
        direction = None
        confidence = None
        distance_from_band = 0

        # Check hard thresholds first
        hard_threshold = self.config["hard_band_touch_threshold"]
        hard_extreme_multiplier = self.config["hard_extreme_multiplier"]
        hard_extreme_upper = middle_band + (std_dev * hard_extreme_multiplier)
        hard_extreme_lower = middle_band - (std_dev * hard_extreme_multiplier)

        # Check upper band (overbought)
        if current_price >= upper_band - hard_threshold:
            strength = OpportunityStrength.HARD
            signal_type = "upper_band_touch"
            direction = "down"
            distance_from_band = current_price - upper_band
            if current_price >= hard_extreme_upper:
                confidence = ConfidenceLevel.MEDIUM
            else:
                confidence = ConfidenceLevel.LOW

        # Check lower band (oversold)
        elif current_price <= lower_band + hard_threshold:
            strength = OpportunityStrength.HARD
            signal_type = "lower_band_touch"
            direction = "up"
            distance_from_band = lower_band - current_price
            if current_price <= hard_extreme_lower:
                confidence = ConfidenceLevel.MEDIUM
            else:
                confidence = ConfidenceLevel.LOW

        # Otherwise check soft thresholds
        else:
            soft_threshold = self.config["soft_band_touch_threshold"]
            soft_extreme_multiplier = self.config["soft_extreme_multiplier"]
            soft_extreme_upper = middle_band + (std_dev * soft_extreme_multiplier)
            soft_extreme_lower = middle_band - (std_dev * soft_extreme_multiplier)

            # Check upper band (overbought)
            if current_price >= upper_band - soft_threshold:
                strength = OpportunityStrength.SOFT
                signal_type = "upper_band_touch"
                direction = "down"
                distance_from_band = current_price - upper_band
                if current_price >= soft_extreme_upper:
                    confidence = ConfidenceLevel.MEDIUM
                else:
                    confidence = ConfidenceLevel.LOW

            # Check lower band (oversold)
            elif current_price <= lower_band + soft_threshold:
                strength = OpportunityStrength.SOFT
                signal_type = "lower_band_touch"
                direction = "up"
                distance_from_band = lower_band - current_price
                if current_price <= soft_extreme_lower:
                    confidence = ConfidenceLevel.MEDIUM
                else:
                    confidence = ConfidenceLevel.LOW
            else:
                # Price within bands, no signal
                logger.info(f"[BB] {ticker}: Price within bands, no opportunity")
                return None

        # Estimate edge: distance from current price to middle band
        # Conservative: expect partial reversion (60% of the way back)
        distance_to_middle = abs(current_price - middle_band)
        estimated_edge_cents = distance_to_middle * 0.6

        # Filter out low-edge opportunities based on strength
        min_edge = self.config[f"{strength.value}_min_edge_cents"]
        if estimated_edge_cents < min_edge:
            logger.info(
                f"[BB] {ticker}: Edge too low ({estimated_edge_cents:.1f}¢ < {min_edge}¢ min for {strength.value})"
            )
            return None

        estimated_edge_percent = (estimated_edge_cents / current_price) * 100 if current_price > 0 else 0

        # Calculate %B (where price is relative to bands)
        # %B = (Price - Lower Band) / (Upper Band - Lower Band)
        band_width = upper_band - lower_band
        percent_b = (current_price - lower_band) / band_width if band_width > 0 else 0.5

        # Build reasoning
        title = market.get("title", "Unknown Market")
        reasoning = (
            f"Price at {current_price:.1f}¢ touched {signal_type.replace('_', ' ')}. "
            f"BB(±{self.config['std_dev_multiplier']}σ): "
            f"{lower_band:.1f}¢ / {middle_band:.1f}¢ / {upper_band:.1f}¢. "
            f"Expected mean reversion {direction}."
        )

        opportunity = Opportunity(
            opportunity_type=OpportunityType.MOMENTUM_FADE,
            confidence=confidence,
            strength=strength,
            timestamp=datetime.now(),
            market_tickers=[ticker],
            market_titles=[title],
            market_urls=[self._make_market_url(ticker)],
            current_prices={ticker: current_price},
            estimated_edge_cents=estimated_edge_cents,
            estimated_edge_percent=estimated_edge_percent,
            reasoning=reasoning,
            additional_data={
                "signal_type": signal_type,
                "direction": direction,
                "current_price": current_price,
                "middle_band": middle_band,
                "upper_band": upper_band,
                "lower_band": lower_band,
                "std_dev": std_dev,
                "percent_b": percent_b,
                "distance_from_band": distance_from_band,
                "distance_to_middle": distance_to_middle,
                "band_width": band_width,
                "price_history": list(history),
            },
        )

        return opportunity

    def _try_prewarm_from_candlesticks(self, market: Dict[str, Any], ticker: str) -> None:
        """Pre-warm price history from candlesticks data."""
        if not self.kalshi_client:
            return

        lookback_hours = self.config["period"] + 5
        candlesticks = self._fetch_market_candlesticks(
            market, lookback_hours=lookback_hours, period_interval=60
        )

        if not candlesticks:
            return

        prices = self._extract_prices_from_candlesticks(candlesticks, "yes_ask_close")

        if len(prices) >= self.config["period"]:
            for price in prices:
                self.price_history[ticker].append(price)
            logger.info(
                f"Pre-warmed Bollinger Bands history for {ticker} with {len(prices)} candlesticks"
            )

    def clear_history(self) -> None:
        """Clear all price history."""
        self.price_history.clear()
        logger.info("Bollinger Bands history cleared")

    def get_history_stats(self) -> Dict[str, Any]:
        """Get statistics about tracked price history."""
        return {
            "markets_tracked": len(self.price_history),
            "total_observations": sum(len(h) for h in self.price_history.values()),
        }
