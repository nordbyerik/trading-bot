"""
Volume Trend Analyzer

Tracks trading volume patterns and identifies unusual volume spikes
that may indicate significant market moves or smart money activity.
"""

import logging
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength


logger = logging.getLogger(__name__)


class VolumeTrendAnalyzer(BaseAnalyzer):
    """
    Analyzes trading volume trends and identifies anomalies.

    Volume analysis helps identify:
    - Volume spikes (unusual interest)
    - Volume + price divergence
    - Volume exhaustion (potential reversals)
    - Accumulation/distribution patterns

    Volume is derived from orderbook depth and bid/ask quantities.
    """

    def _setup(self) -> None:
        """Initialize volume history tracking."""
        # Store volume history: {ticker: deque([volume1, volume2, ...])}
        self.volume_history: Dict[str, deque] = {}

        # Store price history for correlation: {ticker: deque([price1, price2, ...])}
        self.price_history: Dict[str, deque] = {}

        # Apply default config
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def get_name(self) -> str:
        return "Volume Trend Analyzer"

    def get_description(self) -> str:
        return (
            "Tracks trading volume patterns and identifies unusual spikes, "
            "divergences, and accumulation/distribution signals"
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            "lookback_period": 10,  # Periods to track
            # Hard opportunity thresholds (strict requirements)
            "hard_volume_spike_multiplier": 2.0,  # Volume > avg × multiplier for hard
            "hard_extreme_spike_multiplier": 3.0,  # Very unusual volume for hard
            "hard_min_volume_threshold": 100,  # Minimum volume to consider for hard
            "hard_min_edge_cents": 3,  # Minimum expected edge to report for hard
            # Soft opportunity thresholds (relaxed requirements)
            "soft_volume_spike_multiplier": 1.5,  # Volume > avg × multiplier for soft
            "soft_extreme_spike_multiplier": 2.5,  # Very unusual volume for soft
            "soft_min_volume_threshold": 50,  # Minimum volume to consider for soft
            "soft_min_edge_cents": 2,  # Minimum expected edge to report for soft
        }

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for volume-based opportunities.

        Args:
            markets: List of market data dictionaries

        Returns:
            List of volume-based opportunities
        """
        opportunities = []

        for market in markets:
            ticker = market.get("ticker", "UNKNOWN")

            # Get current price and volume
            current_price = self._get_market_price(market)
            current_volume = self._get_market_volume(market)

            if current_price is None or current_volume is None:
                continue

            # Update histories
            if ticker not in self.volume_history:
                self.volume_history[ticker] = deque(maxlen=self.config["lookback_period"])
                self.price_history[ticker] = deque(maxlen=self.config["lookback_period"])
                # Try to pre-warm from historical candlesticks (gets real volume data!)
                self._try_prewarm_from_candlesticks(market, ticker)

            self.volume_history[ticker].append(current_volume)
            self.price_history[ticker].append(current_price)

            # Check for volume opportunities
            opportunity = self._check_volume_signal(market, ticker)
            if opportunity:
                opportunities.append(opportunity)

        logger.info(
            f"VolumeTrendAnalyzer found {len(opportunities)} opportunities "
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

    def _get_market_volume(self, market: Dict[str, Any]) -> Optional[float]:
        """
        Extract volume from market data.

        Volume is estimated from orderbook depth (total quantity available).
        """
        orderbook = market.get("orderbook")
        if not orderbook:
            return None

        # Sum all quantities on both sides (handle None values)
        yes_bids = orderbook.get("yes") or []
        no_bids = orderbook.get("no") or []
        yes_volume = sum(qty for price, qty in yes_bids)
        no_volume = sum(qty for price, qty in no_bids)

        total_volume = yes_volume + no_volume

        return float(total_volume) if total_volume > 0 else None

    def _calculate_average_volume(self, volumes: deque) -> float:
        """Calculate average volume from history."""
        if not volumes:
            return 0.0
        return sum(volumes) / len(volumes)

    def _check_volume_signal(
        self, market: Dict[str, Any], ticker: str
    ) -> Optional[Opportunity]:
        """Check if volume indicates an opportunity."""
        vol_hist = self.volume_history.get(ticker)
        price_hist = self.price_history.get(ticker)

        # Need minimum history
        if not vol_hist or not price_hist or len(vol_hist) < 3:
            logger.debug(
                f"[VOLUME] {ticker}: Insufficient history "
                f"({len(vol_hist) if vol_hist else 0} volume points, {len(price_hist) if price_hist else 0} price points, need 3)"
            )
            return None

        current_volume = vol_hist[-1]
        current_price = price_hist[-1]

        # Calculate average volume (excluding current)
        if len(vol_hist) > 1:
            avg_volume = self._calculate_average_volume(list(vol_hist)[:-1])
        else:
            return None

        # Avoid division by zero
        if avg_volume == 0:
            logger.debug(f"[VOLUME] {ticker}: Average volume is zero")
            return None

        # Calculate volume ratio
        volume_ratio = current_volume / avg_volume

        # Log the calculated metrics for this market
        logger.info(
            f"[VOLUME] {ticker}: price={current_price:.0f}¢, "
            f"current_volume={current_volume:.0f}, avg_volume={avg_volume:.0f}, ratio={volume_ratio:.2f}x"
        )

        # Determine opportunity strength (HARD or SOFT)
        strength = None
        signal_type = None
        direction = None
        confidence = ConfidenceLevel.LOW

        # Check hard thresholds first
        hard_min_vol = self.config["hard_min_volume_threshold"]
        hard_spike_mult = self.config["hard_volume_spike_multiplier"]
        hard_extreme_mult = self.config["hard_extreme_spike_multiplier"]

        if current_volume >= hard_min_vol:
            spike_multiplier = hard_spike_mult
            extreme_multiplier = hard_extreme_mult
            strength = OpportunityStrength.HARD
        else:
            # Check soft thresholds
            soft_min_vol = self.config["soft_min_volume_threshold"]
            soft_spike_mult = self.config["soft_volume_spike_multiplier"]
            soft_extreme_mult = self.config["soft_extreme_spike_multiplier"]

            if current_volume >= soft_min_vol:
                spike_multiplier = soft_spike_mult
                extreme_multiplier = soft_extreme_mult
                strength = OpportunityStrength.SOFT
            else:
                return None

        # Volume spike detected
        if volume_ratio >= spike_multiplier:
            # Check price movement for context
            if len(price_hist) >= 2:
                prev_price = price_hist[-2]
                price_change = current_price - prev_price

                # Volume spike with price increase
                if price_change > 2:
                    signal_type = "volume_spike_bullish"
                    direction = "up"
                # Volume spike with price decrease
                elif price_change < -2:
                    signal_type = "volume_spike_bearish"
                    direction = "down"
                # Volume spike without clear direction (accumulation)
                else:
                    signal_type = "volume_spike_neutral"
                    direction = "unknown"

                # Extreme volume = higher confidence
                if volume_ratio >= extreme_multiplier:
                    confidence = ConfidenceLevel.MEDIUM
                else:
                    confidence = ConfidenceLevel.LOW
            else:
                return None

        # Volume divergence: Price moving but volume decreasing (exhaustion)
        elif len(vol_hist) >= 3 and len(price_hist) >= 3:
            prev_volume = vol_hist[-2]
            older_volume = vol_hist[-3]
            prev_price = price_hist[-2]
            older_price = price_hist[-3]

            # Volume is declining
            volume_declining = current_volume < prev_volume < older_volume

            # But price is still moving
            price_moving_up = current_price > prev_price > older_price
            price_moving_down = current_price < prev_price < older_price

            if volume_declining and price_moving_up:
                signal_type = "volume_divergence_bearish"
                direction = "down"  # Expect reversal
                confidence = ConfidenceLevel.LOW
            elif volume_declining and price_moving_down:
                signal_type = "volume_divergence_bullish"
                direction = "up"  # Expect reversal
                confidence = ConfidenceLevel.LOW

        if signal_type is None:
            logger.info(f"[VOLUME] {ticker}: No significant volume signal detected")
            return None

        # Estimate edge based on volume strength and signal type
        if "spike" in signal_type:
            # Volume spikes suggest momentum continuation
            estimated_edge_cents = min((volume_ratio - 1) * 2, 12)
        else:
            # Divergence suggests reversal
            estimated_edge_cents = 5.0

        # Filter out low-edge opportunities based on strength
        min_edge = self.config[f"{strength.value}_min_edge_cents"]
        if estimated_edge_cents < min_edge:
            logger.info(
                f"[VOLUME] {ticker}: Edge too low ({estimated_edge_cents:.1f}¢ < {min_edge}¢ min for {strength.value})"
            )
            return None

        estimated_edge_percent = (estimated_edge_cents / current_price) * 100 if current_price > 0 else 0

        # Build reasoning
        title = market.get("title", "Unknown Market")
        reasoning = (
            f"{signal_type.replace('_', ' ').title()}: "
            f"Volume at {current_volume:.0f} ({volume_ratio:.1f}× avg). "
        )

        if direction != "unknown":
            reasoning += f"Expected movement {direction}."
        else:
            reasoning += "Unusual activity detected."

        opportunity = Opportunity(
            opportunity_type=OpportunityType.IMBALANCE,  # Volume-based signals
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
                "current_volume": current_volume,
                "average_volume": avg_volume,
                "volume_ratio": volume_ratio,
                "current_price": current_price,
                "volume_history": list(vol_hist),
                "price_history": list(price_hist),
            },
        )

        return opportunity

    def _try_prewarm_from_candlesticks(self, market: Dict[str, Any], ticker: str) -> None:
        """
        Pre-warm volume and price history from candlesticks data.

        This is particularly valuable for volume analysis as it provides
        actual trade volume instead of estimated orderbook depth.
        """
        if not self.kalshi_client:
            return

        lookback_hours = self.config["lookback_period"] + 3
        candlesticks = self._fetch_market_candlesticks(
            market, lookback_hours=lookback_hours, period_interval=60
        )

        if not candlesticks:
            return

        prices = self._extract_prices_from_candlesticks(candlesticks, "yes_ask_close")
        volumes = self._extract_volumes_from_candlesticks(candlesticks)

        if len(prices) >= self.config["lookback_period"] and len(volumes) >= self.config["lookback_period"]:
            for price, volume in zip(prices, volumes):
                self.price_history[ticker].append(price)
                self.volume_history[ticker].append(volume)
            logger.info(
                f"Pre-warmed Volume Trend history for {ticker} with {len(prices)} candlesticks (actual volume data)"
            )

    def clear_history(self) -> None:
        """Clear all history."""
        self.volume_history.clear()
        self.price_history.clear()
        logger.info("Volume history cleared")

    def get_history_stats(self) -> Dict[str, Any]:
        """Get statistics about tracked history."""
        return {
            "markets_tracked": len(self.volume_history),
            "total_volume_observations": sum(len(h) for h in self.volume_history.values()),
            "total_price_observations": sum(len(h) for h in self.price_history.values()),
        }
