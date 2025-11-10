"""
Mean Reversion Analyzer

Bets that extreme prices will revert to the mean (around 50¢).
Looks for overextended markets that are likely to snap back.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength
from trade_manager import Side


logger = logging.getLogger(__name__)


class MeanReversionAnalyzer(BaseAnalyzer):
    """
    Analyzes markets for mean reversion opportunities.
    
    Bets that prices far from 50¢ (the natural equilibrium) will revert back.
    """

    def get_name(self) -> str:
        return "Mean Reversion Analyzer"

    def get_description(self) -> str:
        return "Bets on extreme prices reverting to the mean"

    def get_default_config(self) -> Dict[str, Any]:
        return {
            "min_volume": 200,  # Higher volume for mean reversion
            "extreme_high": 75,  # Buy NO if price >= this
            "extreme_low": 25,  # Buy YES if price <= this
            "very_extreme_high": 85,  # HIGH confidence
            "very_extreme_low": 15,  # HIGH confidence
            "min_edge_cents": 10,  # Need good edge for mean reversion
        }

    def _setup(self) -> None:
        """Apply default config values."""
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for mean reversion opportunities.

        Args:
            markets: List of market data dictionaries

        Returns:
            List of mean reversion opportunities
        """
        opportunities = []

        for market in markets:
            opportunity = self._analyze_single_market(market)
            if opportunity:
                opportunities.append(opportunity)

        logger.info(
            f"MeanReversionAnalyzer found {len(opportunities)} opportunities "
            f"out of {len(markets)} markets"
        )

        return opportunities

    def _analyze_single_market(self, market: Dict[str, Any]) -> Opportunity | None:
        """Analyze a single market for mean reversion opportunities."""
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "Unknown Market")
        last_price = market.get("last_price", 0)
        volume = market.get("volume", 0)

        # Filter by volume - need liquid markets for mean reversion
        if volume < self.config["min_volume"]:
            return None

        side = None
        confidence = None
        strength = None
        estimated_edge_cents = 0

        # Price too high - bet it will come down (buy NO)
        if last_price >= self.config["extreme_high"]:
            side = Side.NO
            # Estimate edge: distance from mean
            distance_from_mean = last_price - 50
            
            if last_price >= self.config["very_extreme_high"]:
                strength = OpportunityStrength.HARD
                confidence = ConfidenceLevel.HIGH
                estimated_edge_cents = distance_from_mean * 0.7  # Expect 70% reversion
            else:
                strength = OpportunityStrength.SOFT
                confidence = ConfidenceLevel.MEDIUM
                estimated_edge_cents = distance_from_mean * 0.5  # Expect 50% reversion

        # Price too low - bet it will come up (buy YES)
        elif last_price <= self.config["extreme_low"]:
            side = Side.YES
            # Estimate edge: distance from mean
            distance_from_mean = 50 - last_price
            
            if last_price <= self.config["very_extreme_low"]:
                strength = OpportunityStrength.HARD
                confidence = ConfidenceLevel.HIGH
                estimated_edge_cents = distance_from_mean * 0.7  # Expect 70% reversion
            else:
                strength = OpportunityStrength.SOFT
                confidence = ConfidenceLevel.MEDIUM
                estimated_edge_cents = distance_from_mean * 0.5  # Expect 50% reversion
        else:
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
            f"Mean reversion: {side.name} at {last_price}¢ "
            f"(edge: {estimated_edge_cents:.1f}¢, volume: {volume}). "
            f"Price is {'too high' if side == Side.NO else 'too low'}, "
            f"expect reversion toward 50¢."
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
                "strategy": "mean_reversion",
                "distance_from_mean": abs(last_price - 50),
                "recommended_side": side.value,
            },
        )

        return opportunity
