"""
Mispricing Analyzer

Identifies potential mispricings based on:
- Extreme probabilities (very high or very low)
- Round number bias
- Unusual price patterns
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength


logger = logging.getLogger(__name__)


class MispricingAnalyzer(BaseAnalyzer):
    """
    Detects potential mispricings in prediction markets.

    Strategies:
    1. Extreme probabilities: Markets at very high/low prices are often mispriced
    2. Round number bias: Prices clustering at 25¢, 50¢, 75¢ may be lazy estimates
    3. Price-volume anomalies: Low volume at extreme prices
    """

    def get_name(self) -> str:
        return "Mispricing Analyzer"

    def get_description(self) -> str:
        return (
            "Identifies potential mispricings based on extreme probabilities, "
            "round number bias, and anomalous price patterns"
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            # Hard opportunity thresholds (strict requirements)
            "hard_extreme_low_threshold": 5,  # Price below this is "extreme low" for hard (cents)
            "hard_extreme_high_threshold": 95,  # Price above this is "extreme high" for hard (cents)
            "hard_min_volume_for_extreme": 10,  # Min volume to flag extreme prices for hard
            "hard_max_volume_for_round_bias": 500,  # Max volume to flag round number bias for hard
            # Soft opportunity thresholds (relaxed requirements)
            "soft_extreme_low_threshold": 10,  # Price below this is "extreme low" for soft (cents)
            "soft_extreme_high_threshold": 90,  # Price above this is "extreme high" for soft (cents)
            "soft_min_volume_for_extreme": 0,  # Min volume to flag extreme prices for soft
            "soft_max_volume_for_round_bias": 1000,  # Max volume to flag round number bias for soft
            # Shared settings
            "round_numbers": [25, 50, 75],  # Round numbers to check for bias
            "round_number_tolerance": 2,  # Within this many cents counts as "round"
        }

    def _setup(self) -> None:
        """Apply default config values."""
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for potential mispricings.

        Args:
            markets: List of market data dictionaries

        Returns:
            List of mispricing opportunities
        """
        opportunities = []

        for market in markets:
            # Check different mispricing patterns
            extreme_opp = self._check_extreme_prices(market)
            if extreme_opp:
                opportunities.append(extreme_opp)

            round_bias_opp = self._check_round_number_bias(market)
            if round_bias_opp:
                opportunities.append(round_bias_opp)

        logger.info(
            f"MispricingAnalyzer found {len(opportunities)} opportunities "
            f"out of {len(markets)} markets"
        )

        return opportunities

    def _check_extreme_prices(self, market: Dict[str, Any]) -> Opportunity | None:
        """Check for extreme probability mispricings."""
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "Unknown Market")

        # Get last price (could be yes_price from market data or from orderbook)
        last_price = market.get("yes_price")

        # If no yes_price, try to get from orderbook
        if last_price is None and "orderbook" in market:
            orderbook = market["orderbook"]
            yes_bid_data = self._get_best_bid(orderbook, "yes")
            if yes_bid_data:
                last_price = yes_bid_data[0]

        if last_price is None:
            logger.debug(f"[MISPRICING] {ticker}: No price available")
            return None

        volume = market.get("volume", 0)

        # Log the calculated metrics for this market
        logger.info(
            f"[MISPRICING] {ticker}: price={last_price:.0f}¢, volume={volume}"
        )

        # Determine opportunity strength (HARD or SOFT) and check thresholds
        strength = None
        confidence = None
        direction = None
        estimated_edge_cents = 0
        is_extreme_low = False
        is_extreme_high = False

        # Check hard thresholds first
        hard_extreme_low = self.config["hard_extreme_low_threshold"]
        hard_extreme_high = self.config["hard_extreme_high_threshold"]
        hard_min_volume = self.config["hard_min_volume_for_extreme"]

        if (last_price <= hard_extreme_low or last_price >= hard_extreme_high) and volume >= hard_min_volume:
            strength = OpportunityStrength.HARD
            is_extreme_low = last_price <= hard_extreme_low
            is_extreme_high = last_price >= hard_extreme_high

            if is_extreme_low:
                direction = "underpriced"
                estimated_edge_cents = min(10, hard_extreme_low - last_price + 5)
                confidence = ConfidenceLevel.MEDIUM if last_price <= 2 else ConfidenceLevel.LOW
            else:
                direction = "overpriced"
                estimated_edge_cents = min(10, last_price - hard_extreme_high + 5)
                confidence = ConfidenceLevel.MEDIUM if last_price >= 98 else ConfidenceLevel.LOW

        # Otherwise check soft thresholds
        else:
            soft_extreme_low = self.config["soft_extreme_low_threshold"]
            soft_extreme_high = self.config["soft_extreme_high_threshold"]
            soft_min_volume = self.config["soft_min_volume_for_extreme"]

            if (last_price <= soft_extreme_low or last_price >= soft_extreme_high) and volume >= soft_min_volume:
                strength = OpportunityStrength.SOFT
                is_extreme_low = last_price <= soft_extreme_low
                is_extreme_high = last_price >= soft_extreme_high

                if is_extreme_low:
                    direction = "underpriced"
                    estimated_edge_cents = min(8, soft_extreme_low - last_price + 3)
                    confidence = ConfidenceLevel.LOW
                else:
                    direction = "overpriced"
                    estimated_edge_cents = min(8, last_price - soft_extreme_high + 3)
                    confidence = ConfidenceLevel.LOW
            else:
                # Doesn't meet either threshold
                logger.info(
                    f"[MISPRICING] {ticker}: Price not extreme enough "
                    f"(price={last_price:.0f}¢, hard thresholds: <={hard_extreme_low}¢ or >={hard_extreme_high}¢, "
                    f"soft thresholds: <={soft_extreme_low}¢ or >={soft_extreme_high}¢, volume={volume})"
                )
                return None

        estimated_edge_percent = (estimated_edge_cents / last_price) * 100 if last_price > 0 else 0

        reasoning = (
            f"Extreme price of {last_price:.0f}¢ suggests potential {direction}. "
            f"Markets at extreme probabilities are often mispriced. "
            f"Volume: {volume}"
        )

        opportunity = Opportunity(
            opportunity_type=OpportunityType.MISPRICING,
            confidence=confidence,
            strength=strength,
            timestamp=datetime.now(),
            market_tickers=[ticker],
            market_titles=[title],
            market_urls=[self._make_market_url(ticker)],
            current_prices={ticker: last_price},
            estimated_edge_cents=estimated_edge_cents,
            estimated_edge_percent=estimated_edge_percent,
            reasoning=reasoning,
            additional_data={
                "last_price": last_price,
                "volume": volume,
                "extreme_type": "low" if is_extreme_low else "high",
                "direction": direction,
            },
        )

        return opportunity

    def _check_round_number_bias(self, market: Dict[str, Any]) -> Opportunity | None:
        """Check for round number bias."""
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "Unknown Market")

        # Get last price
        last_price = market.get("yes_price")

        if last_price is None and "orderbook" in market:
            orderbook = market["orderbook"]
            yes_bid_data = self._get_best_bid(orderbook, "yes")
            if yes_bid_data:
                last_price = yes_bid_data[0]

        if last_price is None:
            logger.debug(f"[MISPRICING-ROUND] {ticker}: No price available")
            return None

        volume = market.get("volume", 0)

        # Check if price is near a round number
        round_numbers = self.config["round_numbers"]
        tolerance = self.config["round_number_tolerance"]

        nearest_round = None
        for round_num in round_numbers:
            if abs(last_price - round_num) <= tolerance:
                nearest_round = round_num
                break

        if nearest_round is None:
            logger.debug(f"[MISPRICING-ROUND] {ticker}: Price {last_price:.0f}¢ not near any round number")
            return None

        # Log the calculated metrics for this market
        logger.info(
            f"[MISPRICING-ROUND] {ticker}: price={last_price:.0f}¢ near {nearest_round}¢, volume={volume}"
        )

        # Determine opportunity strength (HARD or SOFT) based on volume
        strength = None
        confidence = None
        estimated_edge_cents = 0

        # Check hard thresholds first (stricter volume requirements)
        hard_max_volume = self.config["hard_max_volume_for_round_bias"]
        if volume <= hard_max_volume:
            strength = OpportunityStrength.HARD
            confidence = ConfidenceLevel.LOW
            estimated_edge_cents = 3.0
        else:
            # Check soft thresholds (more relaxed volume requirements)
            soft_max_volume = self.config["soft_max_volume_for_round_bias"]
            if volume <= soft_max_volume:
                strength = OpportunityStrength.SOFT
                confidence = ConfidenceLevel.LOW
                estimated_edge_cents = 2.0
            else:
                # Volume too high even for soft threshold
                logger.info(
                    f"[MISPRICING-ROUND] {ticker}: Volume too high for round number bias "
                    f"(volume={volume}, max soft={soft_max_volume})"
                )
                return None

        estimated_edge_percent = (estimated_edge_cents / last_price) * 100 if last_price > 0 else 0

        reasoning = (
            f"Price of {last_price:.0f}¢ (near {nearest_round}¢) with low volume ({volume}) "
            f"suggests potential round number bias. Market may be inefficiently priced."
        )

        opportunity = Opportunity(
            opportunity_type=OpportunityType.MISPRICING,
            confidence=confidence,
            strength=strength,
            timestamp=datetime.now(),
            market_tickers=[ticker],
            market_titles=[title],
            market_urls=[self._make_market_url(ticker)],
            current_prices={ticker: last_price},
            estimated_edge_cents=estimated_edge_cents,
            estimated_edge_percent=estimated_edge_percent,
            reasoning=reasoning,
            additional_data={
                "last_price": last_price,
                "nearest_round_number": nearest_round,
                "volume": volume,
                "bias_type": "round_number",
            },
        )

        return opportunity


if __name__ == "__main__":
    # Simple test with mock data
    logging.basicConfig(level=logging.INFO)

    mock_markets = [
        {
            "ticker": "EXTREME-LOW",
            "title": "Market with extreme low price",
            "yes_price": 3,
            "volume": 100,
        },
        {
            "ticker": "EXTREME-HIGH",
            "title": "Market with extreme high price",
            "yes_price": 97,
            "volume": 200,
        },
        {
            "ticker": "ROUND-BIAS",
            "title": "Market with round number bias",
            "yes_price": 50,
            "volume": 50,
        },
        {
            "ticker": "NORMAL-MARKET",
            "title": "Normal market",
            "yes_price": 65,
            "volume": 5000,
        },
    ]

    analyzer = MispricingAnalyzer()
    opportunities = analyzer.analyze(mock_markets)

    print(f"\nFound {len(opportunities)} opportunities:\n")
    for opp in opportunities:
        print(opp)
        print(f"  Additional data: {opp.additional_data}\n")
