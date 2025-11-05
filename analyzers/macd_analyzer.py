"""
MACD (Moving Average Convergence Divergence) Analyzer

Tracks MACD indicator to identify momentum shifts and trend changes.
MACD is calculated from the difference between fast and slow EMAs.
"""

import logging
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength


logger = logging.getLogger(__name__)


class MACDAnalyzer(BaseAnalyzer):
    """
    Analyzes MACD (Moving Average Convergence Divergence) indicator.

    MACD Components:
    - MACD Line: 12-period EMA - 26-period EMA
    - Signal Line: 9-period EMA of MACD Line
    - Histogram: MACD Line - Signal Line

    Trading signals:
    - Bullish: MACD crosses above Signal Line
    - Bearish: MACD crosses below Signal Line
    - Divergence: Price and MACD move in opposite directions
    """

    def _setup(self) -> None:
        """Initialize price and MACD history tracking."""
        # Store price history: {ticker: deque([price1, price2, ...])}
        self.price_history: Dict[str, deque] = {}

        # Store MACD values: {ticker: deque([(macd, signal, histogram), ...])}
        self.macd_history: Dict[str, deque] = {}

        # Store EMAs for calculation: {ticker: {'fast_ema': float, 'slow_ema': float, 'signal_ema': float}}
        self.ema_state: Dict[str, Dict[str, float]] = {}

        # Apply default config
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def get_name(self) -> str:
        return "MACD Analyzer"

    def get_description(self) -> str:
        return (
            "Tracks MACD indicator to identify momentum shifts, "
            "trend changes, and crossover signals"
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            "fast_period": 12,  # Fast EMA period
            "slow_period": 26,  # Slow EMA period
            "signal_period": 9,  # Signal line EMA period
            # Hard opportunity thresholds (strict requirements)
            "hard_min_histogram_value": 1.0,  # Minimum histogram value for signal for hard
            "hard_min_edge_cents": 3,  # Minimum expected edge to report for hard
            # Soft opportunity thresholds (relaxed requirements)
            "soft_min_histogram_value": 0.5,  # Minimum histogram value for signal for soft
            "soft_min_edge_cents": 2,  # Minimum expected edge to report for soft
        }

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for MACD opportunities.

        Args:
            markets: List of market data dictionaries

        Returns:
            List of MACD-based opportunities
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
                # Need slow_period for initial EMA calculation
                self.price_history[ticker] = deque(maxlen=self.config["slow_period"] + 20)
                # Try to pre-warm from historical candlesticks
                self._try_prewarm_from_candlesticks(market, ticker)

            self.price_history[ticker].append(current_price)

            # Calculate MACD
            macd_values = self._calculate_macd(ticker)
            if macd_values is None:
                continue

            # Store MACD history
            if ticker not in self.macd_history:
                self.macd_history[ticker] = deque(maxlen=50)

            self.macd_history[ticker].append(macd_values)

            # Check for MACD opportunities
            opportunity = self._check_macd_signal(market, ticker)
            if opportunity:
                opportunities.append(opportunity)

        logger.info(
            f"MACDAnalyzer found {len(opportunities)} opportunities "
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

    def _calculate_ema(
        self, current_price: float, previous_ema: Optional[float], period: int
    ) -> float:
        """
        Calculate Exponential Moving Average.

        EMA = (Price × multiplier) + (Previous EMA × (1 - multiplier))
        where multiplier = 2 / (period + 1)
        """
        multiplier = 2 / (period + 1)

        if previous_ema is None:
            # First EMA is just the current price
            return current_price

        return (current_price * multiplier) + (previous_ema * (1 - multiplier))

    def _calculate_macd(self, ticker: str) -> Optional[Tuple[float, float, float]]:
        """
        Calculate MACD, Signal Line, and Histogram.

        Returns:
            Tuple of (macd_line, signal_line, histogram) or None
        """
        history = self.price_history.get(ticker)
        if not history or len(history) < self.config["slow_period"]:
            return None

        current_price = history[-1]

        # Initialize EMA state if needed
        if ticker not in self.ema_state:
            # Use SMA as starting point for EMAs
            price_list = list(history)
            fast_sma = sum(price_list[-self.config["fast_period"]:]) / self.config["fast_period"]
            slow_sma = sum(price_list[-self.config["slow_period"]:]) / self.config["slow_period"]

            self.ema_state[ticker] = {
                "fast_ema": fast_sma,
                "slow_ema": slow_sma,
                "signal_ema": None,  # Will be calculated from MACD
            }

        # Update EMAs
        state = self.ema_state[ticker]
        fast_ema = self._calculate_ema(current_price, state["fast_ema"], self.config["fast_period"])
        slow_ema = self._calculate_ema(current_price, state["slow_ema"], self.config["slow_period"])

        # Calculate MACD line
        macd_line = fast_ema - slow_ema

        # Calculate signal line (EMA of MACD line)
        signal_line = self._calculate_ema(macd_line, state["signal_ema"], self.config["signal_period"])

        # Calculate histogram
        histogram = macd_line - signal_line

        # Update state
        self.ema_state[ticker] = {
            "fast_ema": fast_ema,
            "slow_ema": slow_ema,
            "signal_ema": signal_line,
        }

        return macd_line, signal_line, histogram

    def _check_macd_signal(
        self, market: Dict[str, Any], ticker: str
    ) -> Optional[Opportunity]:
        """Check if MACD indicates an opportunity."""
        macd_hist = self.macd_history.get(ticker)
        if not macd_hist or len(macd_hist) < 2:
            logger.debug(
                f"[MACD] {ticker}: Insufficient MACD history "
                f"({len(macd_hist) if macd_hist else 0}/2 points)"
            )
            return None

        # Get current and previous MACD values
        current_macd, current_signal, current_histogram = macd_hist[-1]
        prev_macd, prev_signal, prev_histogram = macd_hist[-2]

        current_price = self.price_history[ticker][-1]

        # Log the calculated metrics for this market
        logger.info(
            f"[MACD] {ticker}: price={current_price:.1f}¢, "
            f"macd={current_macd:.2f}, signal={current_signal:.2f}, histogram={current_histogram:.2f}"
        )

        # Estimate edge based on histogram strength and momentum
        # Larger histogram = stronger signal = more potential edge
        histogram_strength = abs(current_histogram)
        estimated_edge_cents = min(histogram_strength * 3, 15)  # Cap at 15 cents

        # Determine opportunity strength (HARD or SOFT), signal type, direction, and confidence
        strength = None
        signal_type = None
        direction = None
        confidence = None

        # Check hard thresholds first
        hard_min_hist = self.config["hard_min_histogram_value"]
        hard_min_edge = self.config["hard_min_edge_cents"]

        # Bullish crossover: MACD crosses above Signal
        if prev_macd <= prev_signal and current_macd > current_signal:
            if current_histogram >= hard_min_hist and estimated_edge_cents >= hard_min_edge:
                strength = OpportunityStrength.HARD
                signal_type = "bullish_crossover"
                direction = "up"
                confidence = ConfidenceLevel.MEDIUM
            else:
                soft_min_hist = self.config["soft_min_histogram_value"]
                soft_min_edge = self.config["soft_min_edge_cents"]
                if current_histogram >= soft_min_hist and estimated_edge_cents >= soft_min_edge:
                    strength = OpportunityStrength.SOFT
                    signal_type = "bullish_crossover"
                    direction = "up"
                    confidence = ConfidenceLevel.LOW

        # Bearish crossover: MACD crosses below Signal
        elif prev_macd >= prev_signal and current_macd < current_signal:
            if abs(current_histogram) >= hard_min_hist and estimated_edge_cents >= hard_min_edge:
                strength = OpportunityStrength.HARD
                signal_type = "bearish_crossover"
                direction = "down"
                confidence = ConfidenceLevel.MEDIUM
            else:
                soft_min_hist = self.config["soft_min_histogram_value"]
                soft_min_edge = self.config["soft_min_edge_cents"]
                if abs(current_histogram) >= soft_min_hist and estimated_edge_cents >= soft_min_edge:
                    strength = OpportunityStrength.SOFT
                    signal_type = "bearish_crossover"
                    direction = "down"
                    confidence = ConfidenceLevel.LOW

        # Strong momentum signals (histogram extremes)
        elif abs(current_histogram) >= hard_min_hist * 2:
            if current_histogram > 0 and current_histogram > prev_histogram:
                if estimated_edge_cents >= hard_min_edge:
                    strength = OpportunityStrength.HARD
                    signal_type = "strong_bullish_momentum"
                    direction = "up"
                    confidence = ConfidenceLevel.MEDIUM
            elif current_histogram < 0 and current_histogram < prev_histogram:
                if estimated_edge_cents >= hard_min_edge:
                    strength = OpportunityStrength.HARD
                    signal_type = "strong_bearish_momentum"
                    direction = "down"
                    confidence = ConfidenceLevel.MEDIUM

        # Check soft thresholds for momentum signals
        elif abs(current_histogram) >= self.config["soft_min_histogram_value"] * 2:
            if current_histogram > 0 and current_histogram > prev_histogram:
                if estimated_edge_cents >= self.config["soft_min_edge_cents"]:
                    strength = OpportunityStrength.SOFT
                    signal_type = "strong_bullish_momentum"
                    direction = "up"
                    confidence = ConfidenceLevel.LOW
            elif current_histogram < 0 and current_histogram < prev_histogram:
                if estimated_edge_cents >= self.config["soft_min_edge_cents"]:
                    strength = OpportunityStrength.SOFT
                    signal_type = "strong_bearish_momentum"
                    direction = "down"
                    confidence = ConfidenceLevel.LOW

        if signal_type is None or strength is None:
            logger.info(f"[MACD] {ticker}: No crossover or strong momentum signal detected")
            return None

        estimated_edge_percent = (estimated_edge_cents / current_price) * 100 if current_price > 0 else 0

        # Build reasoning
        title = market.get("title", "Unknown Market")
        reasoning = (
            f"MACD {signal_type.replace('_', ' ')}: "
            f"MACD={current_macd:.2f}, Signal={current_signal:.2f}, "
            f"Histogram={current_histogram:.2f}. "
            f"Momentum suggests price movement {direction}."
        )

        opportunity = Opportunity(
            opportunity_type=OpportunityType.MOMENTUM_FADE if "crossover" in signal_type else OpportunityType.MISPRICING,
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
                "macd_line": current_macd,
                "signal_line": current_signal,
                "histogram": current_histogram,
                "prev_histogram": prev_histogram,
                "current_price": current_price,
                "histogram_strength": histogram_strength,
            },
        )

        return opportunity

    def _try_prewarm_from_candlesticks(self, market: Dict[str, Any], ticker: str) -> None:
        """Pre-warm price history from candlesticks data."""
        if not self.kalshi_client:
            return

        lookback_hours = self.config["slow_period"] + 10
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
                f"Pre-warmed MACD history for {ticker} with {len(prices)} candlesticks"
            )

    def clear_history(self) -> None:
        """Clear all history."""
        self.price_history.clear()
        self.macd_history.clear()
        self.ema_state.clear()
        logger.info("MACD history cleared")

    def get_history_stats(self) -> Dict[str, Any]:
        """Get statistics about tracked history."""
        return {
            "markets_tracked": len(self.price_history),
            "total_price_observations": sum(len(h) for h in self.price_history.values()),
            "total_macd_observations": sum(len(h) for h in self.macd_history.values()),
        }
