"""
Value Bet Analyzer

Finds markets where the current price appears to be mispriced based on
fundamental value indicators like volume, market dynamics, and price extremes.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength
from trade_manager import Side


logger = logging.getLogger(__name__)


class ValueBetAnalyzer(BaseAnalyzer):
    """
    Analyzes markets for value betting opportunities.
    
    Looks for:
    - Underpriced YES (price < 30¢ with decent volume)
    - Overpriced NO (price > 70¢ with decent volume)
    - Markets with good liquidity that suggest mispricing
    """

    def get_name(self) -> str:
        return "Value Bet Analyzer"

    def get_description(self) -> str:
        return "Finds value betting opportunities in mispriced markets"

    def get_default_config(self) -> Dict[str, Any]:
        return {
            "min_volume": 50,  # Minimum volume to consider
            "underpriced_threshold": 35,  # Buy YES if price < this
            "overpriced_threshold": 65,  # Buy NO if price > this
            "extreme_underpriced": 20,  # HARD opportunity if YES < this
            "extreme_overpriced": 80,  # HARD opportunity if NO > this
            "min_edge_cents": 5,  # Minimum edge in cents
        }

    def _setup(self) -> None:
        """Apply default config values."""
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for value betting opportunities.

        Args:
            markets: List of market data dictionaries

        Returns:
            List of value betting opportunities
        """
        opportunities = []

        for market in markets:
            opportunity = self._analyze_single_market(market)
            if opportunity:
                opportunities.append(opportunity)

        logger.info(
            f"ValueBetAnalyzer found {len(opportunities)} opportunities "
            f"out of {len(markets)} markets"
        )

        return opportunities

    def _analyze_single_market(self, market: Dict[str, Any]) -> Opportunity | None:
        """Analyze a single market for value betting opportunities."""
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "Unknown Market")
        last_price = market.get("last_price", 0)
        volume = market.get("volume", 0)

        # Filter by volume
        if volume < self.config["min_volume"]:
            return None

        # Determine if this is a value bet
        side = None
        confidence = None
        strength = None
        estimated_edge_cents = 0

        # Check for underpriced YES (buy YES)
        if last_price < self.config["underpriced_threshold"]:
            side = Side.YES
            
            if last_price < self.config["extreme_underpriced"]:
                strength = OpportunityStrength.HARD
                confidence = ConfidenceLevel.HIGH
                # Estimate edge: assume fair value is 50¢
                estimated_edge_cents = 50 - last_price
            else:
                strength = OpportunityStrength.SOFT
                confidence = ConfidenceLevel.MEDIUM
                # Estimate edge: assume fair value is 45¢
                estimated_edge_cents = 45 - last_price

        # Check for overpriced YES (buy NO)
        elif last_price > self.config["overpriced_threshold"]:
            side = Side.NO
            
            if last_price > self.config["extreme_overpriced"]:
                strength = OpportunityStrength.HARD
                confidence = ConfidenceLevel.HIGH
                # Estimate edge: assume fair value is 50¢, we buy NO at (100-price)
                estimated_edge_cents = last_price - 50
            else:
                strength = OpportunityStrength.SOFT
                confidence = ConfidenceLevel.MEDIUM
                # Estimate edge: assume fair value is 55¢
                estimated_edge_cents = last_price - 55

        if side is None:
            return None

        # Check minimum edge
        if estimated_edge_cents < self.config["min_edge_cents"]:
            return None

        # Calculate edge percent
        cost = last_price if side == Side.YES else (100 - last_price)
        estimated_edge_percent = (estimated_edge_cents / cost * 100) if cost > 0 else 0

        # Get orderbook for pricing
        orderbook = market.get("orderbook", {})
        yes_bids = orderbook.get("yes", [])
        no_bids = orderbook.get("no", [])

        yes_bid = yes_bids[0][0] if yes_bids else last_price
        no_bid = no_bids[0][0] if no_bids else (100 - last_price)

        # Create reasoning
        reasoning = (
            f"Value bet: {side.name} at {last_price}¢ "
            f"(edge: {estimated_edge_cents:.1f}¢, volume: {volume}). "
            f"Price appears {'undervalued' if side == Side.YES else 'overvalued'}."
        )

        # Build opportunity
        opportunity = Opportunity(
            opportunity_type=OpportunityType.MISPRICING,
            confidence=confidence,
            strength=strength,
            timestamp=datetime.now(),
            market_tickers=[ticker],
            market_titles=[title],
            market_urls=[self._make_market_url(ticker)],
            current_prices={
                f"{ticker}_last": last_price,
                f"{ticker}_yes_bid": yes_bid,
                f"{ticker}_no_bid": no_bid,
            },
            estimated_edge_cents=estimated_edge_cents,
            estimated_edge_percent=estimated_edge_percent,
            reasoning=reasoning,
            additional_data={
                "volume": volume,
                "strategy": "value_bet",
                "price_extreme": "underpriced" if side == Side.YES else "overpriced",
                "recommended_side": side.value,
            },
        )

        return opportunity


if __name__ == "__main__":
    # Simple test
    logging.basicConfig(level=logging.INFO)

    mock_markets = [
        {
            "ticker": "TEST-LOW-PRICE",
            "title": "Underpriced market",
            "last_price": 15,
            "volume": 500,
            "orderbook": {"yes": [[14, 100]], "no": [[85, 100]]},
        },
        {
            "ticker": "TEST-HIGH-PRICE",
            "title": "Overpriced market",
            "last_price": 85,
            "volume": 300,
            "orderbook": {"yes": [[84, 50]], "no": [[15, 50]]},
        },
        {
            "ticker": "TEST-FAIR-PRICE",
            "title": "Fair market",
            "last_price": 50,
            "volume": 1000,
            "orderbook": {"yes": [[49, 200]], "no": [[49, 200]]},
        },
    ]

    analyzer = ValueBetAnalyzer()
    opportunities = analyzer.analyze(mock_markets)

    print(f"\nFound {len(opportunities)} opportunities:\n")
    for opp in opportunities:
        print(f"  {opp.market_tickers[0]}: {opp.reasoning}")
        print(f"    Confidence: {opp.confidence.name}, Strength: {opp.strength.name}")
        print(f"    Edge: {opp.estimated_edge_cents:.1f}¢ ({opp.estimated_edge_percent:.1f}%)\n")
