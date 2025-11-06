"""
Recency Bias Analyzer

Exploits novice traders' tendency to overweight recent information and underweight
base rates. Detects markets where recent price moves have likely overshot fair value
due to recency bias, creating mean reversion opportunities.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import statistics

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength


logger = logging.getLogger(__name__)


class RecencyBiasAnalyzer(BaseAnalyzer):
    """
    Analyzes markets for recency bias exploitation opportunities.

    Novice traders commonly exhibit recency bias:
    - Overreact to breaking news
    - Extrapolate short-term trends
    - Ignore base rates and historical context
    - Create momentum that eventually reverts

    This analyzer detects:
    - Sharp moves followed by stagnation (overshooting)
    - Prices that deviate significantly from recent average
    - Volume spikes that fade (FOMO buying that exhausts)
    """

    def get_name(self) -> str:
        return "Recency Bias Analyzer"

    def get_description(self) -> str:
        return (
            "Detects markets where novices have overreacted to recent news, "
            "creating mean reversion opportunities by exploiting recency bias"
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            # Hard opportunity thresholds
            "hard_min_deviation_pct": 25.0,  # 25% deviation from mean
            "hard_min_spike_hours": 12,  # Spike occurred in last 12 hours
            "hard_stagnation_threshold": 0.05,  # Price movement < 5% after spike

            # Soft opportunity thresholds
            "soft_min_deviation_pct": 15.0,  # 15% deviation from mean
            "soft_min_spike_hours": 24,  # Spike occurred in last 24 hours
            "soft_stagnation_threshold": 0.08,  # Price movement < 8% after spike

            # Analysis parameters
            "lookback_hours": 72,  # Look at past 3 days for context
            "recent_window_hours": 6,  # Define "recent" as last 6 hours
            "min_data_points": 10,  # Minimum candles needed for analysis
            "min_volume": 50,  # Minimum volume threshold
        }

    def _setup(self) -> None:
        """Apply default config values."""
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for recency bias opportunities.

        Args:
            markets: List of market data dictionaries with orderbook data

        Returns:
            List of recency bias opportunities
        """
        opportunities = []
        now = datetime.now(timezone.utc)

        for market in markets:
            opportunity = self._analyze_single_market(market, now)
            if opportunity:
                opportunities.append(opportunity)

        logger.info(
            f"RecencyBiasAnalyzer found {len(opportunities)} opportunities "
            f"out of {len(markets)} markets"
        )

        return opportunities

    def _analyze_single_market(
        self, market: Dict[str, Any], now: datetime
    ) -> Optional[Opportunity]:
        """Analyze a single market for recency bias opportunities."""
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "Unknown Market")
        volume = market.get("volume", 0)

        # Check volume threshold
        if volume < self.config["min_volume"]:
            return None

        # Fetch historical data
        candlesticks = self._fetch_market_candlesticks(
            market,
            lookback_hours=self.config["lookback_hours"],
            period_interval=60  # 1-hour candles
        )

        if not candlesticks or len(candlesticks) < self.config["min_data_points"]:
            return None

        # Extract prices and timestamps
        prices = self._extract_prices_from_candlesticks(candlesticks, "yes_ask_close")
        if not prices or len(prices) < self.config["min_data_points"]:
            return None

        # Convert to fractions
        prices = [p / 100.0 for p in prices]

        # Perform recency bias analysis
        # Try HARD thresholds first
        hard_result = self._detect_recency_bias(
            prices,
            min_deviation_pct=self.config["hard_min_deviation_pct"],
            min_spike_hours=self.config["hard_min_spike_hours"],
            stagnation_threshold=self.config["hard_stagnation_threshold"]
        )

        if hard_result:
            strength = OpportunityStrength.HARD
            result = hard_result
        else:
            # Try SOFT thresholds
            soft_result = self._detect_recency_bias(
                prices,
                min_deviation_pct=self.config["soft_min_deviation_pct"],
                min_spike_hours=self.config["soft_min_spike_hours"],
                stagnation_threshold=self.config["soft_stagnation_threshold"]
            )

            if soft_result:
                strength = OpportunityStrength.SOFT
                result = soft_result
            else:
                return None

        # Extract analysis results
        current_price = result["current_price"]
        mean_price = result["mean_price"]
        deviation_pct = result["deviation_pct"]
        spike_direction = result["spike_direction"]
        stagnation = result["stagnation"]

        # Calculate confidence
        confidence = self._calculate_confidence(deviation_pct, stagnation)

        # Calculate estimated edge (expected reversion)
        estimated_edge_cents = self._calculate_edge(current_price, mean_price, deviation_pct)
        estimated_edge_percent = (
            (estimated_edge_cents / (current_price * 100)) * 100 if current_price > 0 else 0
        )

        reasoning = (
            f"Recency bias detected: Price {spike_direction} {deviation_pct:.1f}% from "
            f"{self.config['lookback_hours']}h mean (current: {current_price:.2f}, "
            f"mean: {mean_price:.2f}). "
            f"Momentum has stagnated ({stagnation:.1f}% movement in recent hours), "
            f"suggesting novice overreaction. Expected mean reversion."
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
                "current_price": round(current_price, 4),
                "mean_price": round(mean_price, 4),
                "deviation_pct": round(deviation_pct, 2),
                "spike_direction": spike_direction,
                "stagnation_pct": round(stagnation * 100, 2),
                "analysis_type": "recency_bias",
                "exploit_type": "novice_overreaction_to_news",
            },
        )

        logger.info(
            f"[RECENCY] {ticker}: {deviation_pct:.1f}% {spike_direction} deviation, "
            f"stagnated {stagnation*100:.1f}% (Strength: {strength.value})"
        )

        return opportunity

    def _detect_recency_bias(
        self,
        prices: List[float],
        min_deviation_pct: float,
        min_spike_hours: int,
        stagnation_threshold: float
    ) -> Optional[Dict[str, Any]]:
        """
        Detect recency bias patterns in price series.

        Returns analysis dict if pattern found, None otherwise.
        """
        if len(prices) < 3:
            return None

        current_price = prices[-1]

        # Calculate mean price over the lookback period
        # Exclude the most recent window to get "historical" mean
        recent_window_size = max(1, int(self.config["recent_window_hours"]))
        if len(prices) <= recent_window_size:
            return None

        historical_prices = prices[:-recent_window_size]
        mean_price = statistics.mean(historical_prices)

        if mean_price == 0:
            return None

        # Calculate deviation from mean
        deviation = current_price - mean_price
        deviation_pct = abs(deviation / mean_price) * 100

        # Check if deviation meets threshold
        if deviation_pct < min_deviation_pct:
            return None

        # Determine spike direction
        spike_direction = "spiked up" if deviation > 0 else "dropped"

        # Check for stagnation: has momentum faded?
        # Look at price movement in the recent window
        recent_prices = prices[-recent_window_size:]
        if len(recent_prices) < 2:
            return None

        recent_start = recent_prices[0]
        recent_end = recent_prices[-1]
        recent_movement = abs(recent_end - recent_start) / recent_start if recent_start > 0 else 0

        # Stagnation means recent movement is small
        if recent_movement > stagnation_threshold:
            # Still moving significantly, not stagnated yet
            return None

        return {
            "current_price": current_price,
            "mean_price": mean_price,
            "deviation_pct": deviation_pct,
            "spike_direction": spike_direction,
            "stagnation": recent_movement,
        }

    def _calculate_confidence(self, deviation_pct: float, stagnation: float) -> ConfidenceLevel:
        """
        Calculate confidence based on deviation magnitude and stagnation.

        Larger deviation + more stagnation = higher confidence in reversion
        """
        # Score deviation
        if deviation_pct >= 30:
            deviation_score = 3
        elif deviation_pct >= 20:
            deviation_score = 2
        else:
            deviation_score = 1

        # Score stagnation (lower = better)
        if stagnation <= 0.03:  # < 3% movement
            stagnation_score = 3
        elif stagnation <= 0.06:  # < 6% movement
            stagnation_score = 2
        else:
            stagnation_score = 1

        total_score = deviation_score + stagnation_score

        if total_score >= 5:
            return ConfidenceLevel.HIGH
        elif total_score >= 3:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW

    def _calculate_edge(
        self, current_price: float, mean_price: float, deviation_pct: float
    ) -> float:
        """
        Calculate estimated edge in cents.

        Assumes partial reversion to mean.
        """
        # Calculate the gap to close
        gap = abs(current_price - mean_price) * 100  # Convert to cents

        # Assume we can capture some fraction of the reversion
        # More extreme deviations warrant higher reversion expectations
        if deviation_pct >= 30:
            reversion_factor = 0.6  # Expect 60% reversion
        elif deviation_pct >= 20:
            reversion_factor = 0.5  # Expect 50% reversion
        else:
            reversion_factor = 0.4  # Expect 40% reversion

        edge_cents = gap * reversion_factor

        return edge_cents


if __name__ == "__main__":
    # Simple test
    logging.basicConfig(level=logging.INFO)

    analyzer = RecencyBiasAnalyzer()
    print(f"Analyzer: {analyzer.get_name()}")
    print(f"Description: {analyzer.get_description()}")
    print(f"Config: {analyzer.config}")
