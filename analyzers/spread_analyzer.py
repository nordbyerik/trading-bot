"""
Spread Analyzer

Identifies markets with wide bid-ask spreads that may present
market-making or liquidity provision opportunities.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength


logger = logging.getLogger(__name__)


class SpreadAnalyzer(BaseAnalyzer):
    """
    Analyzes bid-ask spreads in prediction markets.

    Wide spreads indicate:
    - Low liquidity
    - Potential market-making opportunities
    - Possible inefficiencies
    """

    def get_name(self) -> str:
        return "Spread Analyzer"

    def get_description(self) -> str:
        return (
            "Identifies markets with wide bid-ask spreads that may present "
            "market-making opportunities"
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            # Hard opportunity thresholds (strict requirements)
            "hard_min_spread_cents": 10,  # Minimum spread to flag as hard (in cents)
            "hard_wide_spread_cents": 20,  # Spread considered "wide" for hard
            "hard_very_wide_spread_cents": 30,  # Spread considered "very wide" for hard
            # Soft opportunity thresholds (relaxed requirements)
            "soft_min_spread_cents": 5,  # Minimum spread to flag as soft (in cents)
            "soft_wide_spread_cents": 10,  # Spread considered "wide" for soft
            "soft_very_wide_spread_cents": 15,  # Spread considered "very wide" for soft
            "min_volume": 0,  # Minimum market volume to consider
        }

    def _setup(self) -> None:
        """Apply default config values."""
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for wide spreads.

        Args:
            markets: List of market data dictionaries with orderbook data

        Returns:
            List of spread-based opportunities
        """
        opportunities = []

        for market in markets:
            # Skip markets without orderbook data
            if "orderbook" not in market:
                continue

            opportunity = self._analyze_single_market(market)
            if opportunity:
                opportunities.append(opportunity)

        logger.info(
            f"SpreadAnalyzer found {len(opportunities)} opportunities "
            f"out of {len(markets)} markets"
        )

        return opportunities

    def _analyze_single_market(self, market: Dict[str, Any]) -> Opportunity | None:
        """Analyze a single market for spread opportunities."""
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "Unknown Market")
        orderbook = market.get("orderbook", {})

        # Get best bids
        yes_bid_data = self._get_best_bid(orderbook, "yes")
        no_bid_data = self._get_best_bid(orderbook, "no")

        if not yes_bid_data or not no_bid_data:
            logger.debug(f"[SPREAD] {ticker}: Missing orderbook data")
            return None

        yes_bid, yes_qty = yes_bid_data
        no_bid, no_qty = no_bid_data

        # Calculate spread
        spread = self._calculate_spread(yes_bid, no_bid)

        # Log the calculated metrics for this market
        logger.info(
            f"[SPREAD] {ticker}: yes_bid={yes_bid:.0f}¢ (qty={yes_qty}), "
            f"no_bid={no_bid:.0f}¢ (qty={no_qty}), spread={spread:.1f}¢"
        )

        # Filter by volume if configured
        volume = market.get("volume", 0)
        if volume < self.config["min_volume"]:
            logger.debug(f"[SPREAD] {ticker}: Volume too low ({volume} < {self.config['min_volume']})")
            return None

        # Determine opportunity strength (HARD or SOFT) and confidence
        strength = None
        confidence = None

        # Check if it meets hard thresholds first
        hard_min = self.config["hard_min_spread_cents"]
        if spread >= hard_min:
            strength = OpportunityStrength.HARD
            hard_wide = self.config["hard_wide_spread_cents"]
            hard_very_wide = self.config["hard_very_wide_spread_cents"]

            if spread >= hard_very_wide:
                confidence = ConfidenceLevel.HIGH
            elif spread >= hard_wide:
                confidence = ConfidenceLevel.MEDIUM
            else:
                confidence = ConfidenceLevel.LOW

        # Otherwise check if it meets soft thresholds
        else:
            soft_min = self.config["soft_min_spread_cents"]
            if spread >= soft_min:
                strength = OpportunityStrength.SOFT
                soft_wide = self.config["soft_wide_spread_cents"]
                soft_very_wide = self.config["soft_very_wide_spread_cents"]

                if spread >= soft_very_wide:
                    confidence = ConfidenceLevel.HIGH
                elif spread >= soft_wide:
                    confidence = ConfidenceLevel.MEDIUM
                else:
                    confidence = ConfidenceLevel.LOW
            else:
                # Doesn't meet either threshold
                logger.info(
                    f"[SPREAD] {ticker}: Spread too narrow ({spread:.1f}¢ < {soft_min}¢ soft min, "
                    f"{hard_min}¢ hard min)"
                )
                return None

        # Calculate estimated edge
        # For market making, you can potentially capture half the spread
        estimated_edge_cents = spread / 2

        # Calculate as percentage of capital deployed
        # Assume you'd buy at mid-price
        mid_price = (yes_bid + no_bid) / 2 + spread / 2
        estimated_edge_percent = (estimated_edge_cents / mid_price) * 100 if mid_price > 0 else 0

        # Create reasoning
        reasoning = (
            f"Wide spread of {spread:.1f}¢ "
            f"(Yes: {yes_bid:.0f}¢ x {yes_qty}, No: {no_bid:.0f}¢ x {no_qty}). "
            f"Potential market-making opportunity."
        )

        # Build opportunity
        opportunity = Opportunity(
            opportunity_type=OpportunityType.WIDE_SPREAD,
            confidence=confidence,
            strength=strength,
            timestamp=datetime.now(),
            market_tickers=[ticker],
            market_titles=[title],
            market_urls=[self._make_market_url(ticker)],
            current_prices={
                f"{ticker}_yes_bid": yes_bid,
                f"{ticker}_no_bid": no_bid,
            },
            estimated_edge_cents=estimated_edge_cents,
            estimated_edge_percent=estimated_edge_percent,
            reasoning=reasoning,
            additional_data={
                "spread_cents": spread,
                "yes_bid_qty": yes_qty,
                "no_bid_qty": no_qty,
                "volume": volume,
                "mid_price": mid_price,
            },
        )

        return opportunity


if __name__ == "__main__":
    # Simple test with mock data
    logging.basicConfig(level=logging.INFO)

    # Mock market data
    mock_markets = [
        {
            "ticker": "TEST-2025-01-01",
            "title": "Test market with wide spread",
            "volume": 1000,
            "orderbook": {
                "yes": [[30, 100], [25, 50]],  # Best yes bid: 30¢
                "no": [[40, 100], [35, 50]],   # Best no bid: 40¢
            },
        },
        {
            "ticker": "TEST-2025-01-02",
            "title": "Test market with narrow spread",
            "volume": 5000,
            "orderbook": {
                "yes": [[48, 200]],  # Best yes bid: 48¢
                "no": [[50, 200]],   # Best no bid: 50¢
            },
        },
    ]

    analyzer = SpreadAnalyzer()
    opportunities = analyzer.analyze(mock_markets)

    print(f"\nFound {len(opportunities)} opportunities:\n")
    for opp in opportunities:
        print(opp)
        print(f"  Additional data: {opp.additional_data}\n")
