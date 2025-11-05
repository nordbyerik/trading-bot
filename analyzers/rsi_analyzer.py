"""
RSI (Relative Strength Index) Analyzer

Tracks the Relative Strength Index of market prices to identify
overbought and oversold conditions that may signal reversals.
"""

import logging
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength


logger = logging.getLogger(__name__)


class RSIAnalyzer(BaseAnalyzer):
    """
    Analyzes RSI (Relative Strength Index) to identify reversal opportunities.

    RSI ranges from 0-100:
    - Above 70: Overbought (potential sell/fade opportunity)
    - Below 30: Oversold (potential buy opportunity)
    - 50: Neutral
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
        return "RSI Analyzer"

    def get_description(self) -> str:
        return (
            "Tracks Relative Strength Index (RSI) to identify overbought "
            "and oversold conditions signaling potential reversals"
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            "rsi_period": 14,  # Standard RSI period
            # Hard opportunity thresholds (strict requirements)
            "hard_overbought_threshold": 70,  # RSI above this = overbought for hard
            "hard_oversold_threshold": 30,  # RSI below this = oversold for hard
            "hard_extreme_overbought": 80,  # Very strong signal for hard
            "hard_extreme_oversold": 20,  # Very strong signal for hard
            "hard_min_edge_cents": 3,  # Minimum expected edge to report for hard
            # Soft opportunity thresholds (relaxed requirements)
            "soft_overbought_threshold": 65,  # RSI above this = overbought for soft
            "soft_oversold_threshold": 35,  # RSI below this = oversold for soft
            "soft_extreme_overbought": 75,  # Very strong signal for soft
            "soft_extreme_oversold": 25,  # Very strong signal for soft
            "soft_min_edge_cents": 2,  # Minimum expected edge to report for soft
        }

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for RSI-based opportunities.

        Args:
            markets: List of market data dictionaries

        Returns:
            List of RSI-based opportunities
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
                # Need period + 1 for RSI calculation
                self.price_history[ticker] = deque(maxlen=self.config["rsi_period"] + 1)
                # Try to pre-warm from historical candlesticks
                self._try_prewarm_from_candlesticks(market, ticker)

            self.price_history[ticker].append(current_price)

            # Check for RSI opportunities
            opportunity = self._check_rsi_signal(market, ticker)
            if opportunity:
                opportunities.append(opportunity)

        logger.info(
            f"RSIAnalyzer found {len(opportunities)} opportunities "
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

    def _calculate_rsi(self, prices: deque) -> Optional[float]:
        """
        Calculate RSI based on price history.

        RSI = 100 - (100 / (1 + RS))
        where RS = Average Gain / Average Loss
        """
        if len(prices) < self.config["rsi_period"] + 1:
            return None

        # Convert to list for easier indexing
        price_list = list(prices)

        # Calculate price changes
        changes = []
        for i in range(1, len(price_list)):
            changes.append(price_list[i] - price_list[i - 1])

        # Need at least rsi_period changes
        if len(changes) < self.config["rsi_period"]:
            return None

        # Take the last rsi_period changes
        recent_changes = changes[-self.config["rsi_period"]:]

        # Separate gains and losses
        gains = [max(0, change) for change in recent_changes]
        losses = [abs(min(0, change)) for change in recent_changes]

        # Calculate average gain and loss
        avg_gain = sum(gains) / len(gains)
        avg_loss = sum(losses) / len(losses)

        # Avoid division by zero
        if avg_loss == 0:
            return 100.0  # Maximum RSI when no losses

        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def _check_rsi_signal(
        self, market: Dict[str, Any], ticker: str
    ) -> Optional[Opportunity]:
        """Check if RSI indicates an opportunity."""
        history = self.price_history.get(ticker)
        if not history or len(history) < self.config["rsi_period"] + 1:
            logger.debug(
                f"[RSI] {ticker}: Insufficient history "
                f"({len(history) if history else 0}/{self.config['rsi_period'] + 1} points)"
            )
            return None

        # Calculate RSI
        rsi = self._calculate_rsi(history)
        if rsi is None:
            logger.debug(f"[RSI] {ticker}: Could not calculate RSI")
            return None

        current_price = history[-1]

        # Log the calculated metrics for this market
        logger.info(f"[RSI] {ticker}: price={current_price:.1f}¢, rsi={rsi:.1f}")

        # Determine opportunity strength (HARD or SOFT), signal type, and confidence
        strength = None
        signal_type = None
        direction = None
        confidence = None

        # Check hard thresholds first
        hard_overbought = self.config["hard_overbought_threshold"]
        hard_oversold = self.config["hard_oversold_threshold"]
        hard_extreme_overbought = self.config["hard_extreme_overbought"]
        hard_extreme_oversold = self.config["hard_extreme_oversold"]

        # Overbought condition - expect price to fall
        if rsi >= hard_overbought:
            strength = OpportunityStrength.HARD
            signal_type = "overbought"
            direction = "down"
            if rsi >= hard_extreme_overbought:
                confidence = ConfidenceLevel.MEDIUM
            else:
                confidence = ConfidenceLevel.LOW

        # Oversold condition - expect price to rise
        elif rsi <= hard_oversold:
            strength = OpportunityStrength.HARD
            signal_type = "oversold"
            direction = "up"
            if rsi <= hard_extreme_oversold:
                confidence = ConfidenceLevel.MEDIUM
            else:
                confidence = ConfidenceLevel.LOW

        # Otherwise check soft thresholds
        else:
            soft_overbought = self.config["soft_overbought_threshold"]
            soft_oversold = self.config["soft_oversold_threshold"]
            soft_extreme_overbought = self.config["soft_extreme_overbought"]
            soft_extreme_oversold = self.config["soft_extreme_oversold"]

            # Overbought condition - expect price to fall
            if rsi >= soft_overbought:
                strength = OpportunityStrength.SOFT
                signal_type = "overbought"
                direction = "down"
                if rsi >= soft_extreme_overbought:
                    confidence = ConfidenceLevel.MEDIUM
                else:
                    confidence = ConfidenceLevel.LOW

            # Oversold condition - expect price to rise
            elif rsi <= soft_oversold:
                strength = OpportunityStrength.SOFT
                signal_type = "oversold"
                direction = "up"
                if rsi <= soft_extreme_oversold:
                    confidence = ConfidenceLevel.MEDIUM
                else:
                    confidence = ConfidenceLevel.LOW
            else:
                # Neutral zone
                logger.info(f"[RSI] {ticker}: RSI in neutral zone, no opportunity")
                return None

        # Estimate edge based on distance from neutral (50)
        # More extreme RSI = larger expected reversal
        rsi_distance = abs(rsi - 50)
        estimated_edge_cents = (rsi_distance / 50) * 15  # Scale to reasonable range

        # Filter out low-edge opportunities based on strength
        min_edge = self.config[f"{strength.value}_min_edge_cents"]
        if estimated_edge_cents < min_edge:
            logger.info(
                f"[RSI] {ticker}: Edge too low ({estimated_edge_cents:.1f}¢ < {min_edge}¢ min for {strength.value})"
            )
            return None

        estimated_edge_percent = (estimated_edge_cents / current_price) * 100 if current_price > 0 else 0

        # Build reasoning
        title = market.get("title", "Unknown Market")
        reasoning = (
            f"RSI at {rsi:.1f} indicates {signal_type} condition. "
            f"Expected mean reversion {direction}. "
            f"(Period: {self.config['rsi_period']})"
        )

        opportunity = Opportunity(
            opportunity_type=OpportunityType.MOMENTUM_FADE,  # RSI reversal is a type of fade
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
                "rsi": rsi,
                "signal_type": signal_type,
                "direction": direction,
                "current_price": current_price,
                "rsi_period": self.config["rsi_period"],
                "price_history": list(history),
            },
        )

        return opportunity

    def _try_prewarm_from_candlesticks(self, market: Dict[str, Any], ticker: str) -> None:
        """
        Try to pre-warm price history from candlesticks data.

        This allows the analyzer to start producing signals immediately
        instead of waiting to accumulate enough observations.
        """
        if not self.kalshi_client:
            return

        # Fetch enough history to calculate RSI
        # Use hourly candlesticks to get sufficient data points
        lookback_hours = self.config["rsi_period"] + 5  # Extra buffer
        candlesticks = self._fetch_market_candlesticks(
            market,
            lookback_hours=lookback_hours,
            period_interval=60  # 1-hour intervals
        )

        if not candlesticks:
            logger.debug(f"No candlesticks available for {ticker}, will accumulate data manually")
            return

        # Extract closing prices from candlesticks
        prices = self._extract_prices_from_candlesticks(candlesticks, "yes_ask_close")

        if len(prices) >= self.config["rsi_period"]:
            # Populate price history (deque will auto-limit to maxlen)
            for price in prices:
                self.price_history[ticker].append(price)
            logger.info(
                f"Pre-warmed RSI history for {ticker} with {len(prices)} candlesticks"
            )
        else:
            logger.debug(
                f"Insufficient candlesticks for {ticker} "
                f"(got {len(prices)}, need {self.config['rsi_period']})"
            )

    def clear_history(self) -> None:
        """Clear all price history."""
        self.price_history.clear()
        logger.info("RSI history cleared")

    def get_history_stats(self) -> Dict[str, Any]:
        """Get statistics about tracked price history."""
        return {
            "markets_tracked": len(self.price_history),
            "total_observations": sum(len(h) for h in self.price_history.values()),
        }
