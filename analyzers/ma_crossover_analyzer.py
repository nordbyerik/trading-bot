"""
Moving Average Crossover Analyzer

Tracks short-term and long-term moving averages of market prices
and identifies bullish/bearish crossover opportunities.
"""

import logging
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength


logger = logging.getLogger(__name__)


class MovingAverageCrossoverAnalyzer(BaseAnalyzer):
    """
    Analyzes price moving averages and identifies crossover opportunities.

    This analyzer tracks short-term (fast) and long-term (slow) moving averages.
    When the fast MA crosses above the slow MA, it signals a bullish opportunity.
    When the fast MA crosses below the slow MA, it signals a bearish opportunity.
    """

    def _setup(self) -> None:
        """Initialize price history tracking."""
        # Store price history: {ticker: deque([price1, price2, ...])}
        self.price_history: Dict[str, deque] = {}

        # Track previous MA states for crossover detection
        self.previous_ma_state: Dict[str, Dict[str, float]] = {}

        # Apply default config
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def get_name(self) -> str:
        return "Moving Average Crossover Analyzer"

    def get_description(self) -> str:
        return (
            "Tracks short-term and long-term moving averages and identifies "
            "bullish/bearish crossover signals"
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            "fast_period": 3,  # Short-term MA period
            "slow_period": 7,  # Long-term MA period
            # Hard opportunity thresholds (strict requirements)
            "hard_min_separation_cents": 2,  # Minimum MA separation to signal for hard
            "hard_min_edge_cents": 3,  # Minimum expected edge to report for hard
            # Soft opportunity thresholds (relaxed requirements)
            "soft_min_separation_cents": 1,  # Minimum MA separation to signal for soft
            "soft_min_edge_cents": 2,  # Minimum expected edge to report for soft
        }

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for MA crossover opportunities.

        Args:
            markets: List of market data dictionaries

        Returns:
            List of MA crossover opportunities
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
                self.price_history[ticker] = deque(maxlen=self.config["slow_period"])
                # Try to pre-warm from historical candlesticks
                self._try_prewarm_from_candlesticks(market, ticker)

            self.price_history[ticker].append(current_price)

            # Check for crossover opportunities
            opportunity = self._check_for_crossover(market, ticker)
            if opportunity:
                opportunities.append(opportunity)

        logger.info(
            f"MovingAverageCrossoverAnalyzer found {len(opportunities)} opportunities "
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

    def _calculate_ma(self, prices: deque, period: int) -> Optional[float]:
        """Calculate moving average for given period."""
        if len(prices) < period:
            return None

        # Use the last 'period' prices
        recent_prices = list(prices)[-period:]
        return sum(recent_prices) / period

    def _check_for_crossover(
        self, market: Dict[str, Any], ticker: str
    ) -> Optional[Opportunity]:
        """Check if MAs have crossed over."""
        history = self.price_history.get(ticker)
        if not history or len(history) < self.config["slow_period"]:
            logger.debug(
                f"[MA] {ticker}: Insufficient history "
                f"({len(history) if history else 0}/{self.config['slow_period']} points)"
            )
            return None

        # Calculate current MAs
        fast_ma = self._calculate_ma(history, self.config["fast_period"])
        slow_ma = self._calculate_ma(history, self.config["slow_period"])

        if fast_ma is None or slow_ma is None:
            logger.debug(f"[MA] {ticker}: Could not calculate MAs")
            return None

        current_price = history[-1]

        # Log the calculated metrics for this market
        logger.info(
            f"[MA] {ticker}: price={current_price:.1f}¢, "
            f"fast_ma={fast_ma:.1f}¢, slow_ma={slow_ma:.1f}¢"
        )

        # Get previous MA state
        prev_state = self.previous_ma_state.get(ticker, {})
        prev_fast = prev_state.get("fast_ma")
        prev_slow = prev_state.get("slow_ma")

        # Store current state for next iteration
        self.previous_ma_state[ticker] = {
            "fast_ma": fast_ma,
            "slow_ma": slow_ma,
        }

        # Need previous state to detect crossover
        if prev_fast is None or prev_slow is None:
            logger.debug(f"[MA] {ticker}: No previous MA state for crossover detection")
            return None

        # Detect crossover
        crossover_type = None

        # Bullish crossover: fast MA crosses above slow MA
        if prev_fast <= prev_slow and fast_ma > slow_ma:
            crossover_type = "bullish"
            direction = "up"
        # Bearish crossover: fast MA crosses below slow MA
        elif prev_fast >= prev_slow and fast_ma < slow_ma:
            crossover_type = "bearish"
            direction = "down"
        else:
            logger.info(f"[MA] {ticker}: No crossover detected")
            return None

        # Check if separation is significant enough and determine strength
        ma_separation = abs(fast_ma - slow_ma)

        # Get current price
        current_price = history[-1]

        # Estimate edge based on MA separation and trend strength
        # Conservative: assume we can capture a portion of the momentum
        estimated_edge_cents = ma_separation * 1.5

        # Determine opportunity strength (HARD or SOFT) and confidence
        strength = None
        confidence = None

        # Check hard thresholds first
        hard_min_sep = self.config["hard_min_separation_cents"]
        hard_min_edge = self.config["hard_min_edge_cents"]

        if ma_separation >= hard_min_sep and estimated_edge_cents >= hard_min_edge:
            strength = OpportunityStrength.HARD
            if ma_separation >= 5:
                confidence = ConfidenceLevel.MEDIUM
            elif ma_separation >= 3:
                confidence = ConfidenceLevel.MEDIUM
            else:
                confidence = ConfidenceLevel.LOW

        # Otherwise check soft thresholds
        else:
            soft_min_sep = self.config["soft_min_separation_cents"]
            soft_min_edge = self.config["soft_min_edge_cents"]

            if ma_separation >= soft_min_sep and estimated_edge_cents >= soft_min_edge:
                strength = OpportunityStrength.SOFT
                if ma_separation >= 3:
                    confidence = ConfidenceLevel.MEDIUM
                else:
                    confidence = ConfidenceLevel.LOW
            else:
                logger.info(
                    f"[MA] {ticker}: MA separation too small ({ma_separation:.1f}¢) "
                    f"or edge too low ({estimated_edge_cents:.1f}¢)"
                )
                return None

        estimated_edge_percent = (estimated_edge_cents / current_price) * 100 if current_price > 0 else 0

        # Build reasoning
        title = market.get("title", "Unknown Market")
        reasoning = (
            f"{crossover_type.capitalize()} MA crossover detected. "
            f"Fast MA ({self.config['fast_period']}p): {fast_ma:.1f}¢, "
            f"Slow MA ({self.config['slow_period']}p): {slow_ma:.1f}¢. "
            f"Trend suggests price movement {direction}."
        )

        opportunity = Opportunity(
            opportunity_type=OpportunityType.MISPRICING,  # Using existing type
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
                "crossover_type": crossover_type,
                "direction": direction,
                "fast_ma": fast_ma,
                "slow_ma": slow_ma,
                "ma_separation": ma_separation,
                "current_price": current_price,
                "price_history": list(history),
            },
        )

        return opportunity

    def _try_prewarm_from_candlesticks(self, market: Dict[str, Any], ticker: str) -> None:
        """Pre-warm price history from candlesticks data."""
        if not self.kalshi_client:
            return

        lookback_hours = self.config["slow_period"] + 5
        candlesticks = self._fetch_market_candlesticks(
            market, lookback_hours=lookback_hours, period_interval=60
        )

        if not candlesticks:
            return

        prices = self._extract_prices_from_candlesticks(candlesticks, "yes_ask_close")

        if len(prices) >= self.config["slow_period"]:
            for price in prices:
                self.price_history[ticker].append(price)
            logger.info(
                f"Pre-warmed MA Crossover history for {ticker} with {len(prices)} candlesticks"
            )

    def clear_history(self) -> None:
        """Clear all price history."""
        self.price_history.clear()
        self.previous_ma_state.clear()
        logger.info("MA history cleared")

    def get_history_stats(self) -> Dict[str, Any]:
        """Get statistics about tracked price history."""
        return {
            "markets_tracked": len(self.price_history),
            "total_observations": sum(len(h) for h in self.price_history.values()),
        }
