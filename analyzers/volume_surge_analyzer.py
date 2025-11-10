"""
Volume Surge Analyzer

Looks for markets with unusually high volume relative to other markets.
High volume often indicates increased interest and potential price movement.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength
from trade_manager import Side


logger = logging.getLogger(__name__)


class VolumeSurgeAnalyzer(BaseAnalyzer):
    """
    Analyzes markets for volume surge opportunities.
    
    High volume markets with favorable prices present good trading opportunities.
    """

    def get_name(self) -> str:
        return "Volume Surge Analyzer"

    def get_description(self) -> str:
        return "Finds high-volume markets with price opportunities"

    def get_default_config(self) -> Dict[str, Any]:
        return {
            "min_volume": 500,  # High volume threshold
            "very_high_volume": 1500,  # Very high volume for HIGH confidence
            "favorable_low": 30,  # Buy YES if price < this with high volume
            "favorable_high": 70,  # Buy NO if price > this with high volume
            "min_edge_cents": 8,  # Minimum edge
        }

    def _setup(self) -> None:
        """Apply default config values."""
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for volume surge opportunities.

        Args:
            markets: List of market data dictionaries

        Returns:
            List of volume surge opportunities
        """
        # First, calculate average volume to identify surges
        volumes = [m.get("volume", 0) for m in markets]
        avg_volume = sum(volumes) / len(volumes) if volumes else 0
        
        opportunities = []

        for market in markets:
            opportunity = self._analyze_single_market(market, avg_volume)
            if opportunity:
                opportunities.append(opportunity)

        logger.info(
            f"VolumeSurgeAnalyzer found {len(opportunities)} opportunities "
            f"out of {len(markets)} markets (avg_volume: {avg_volume:.0f})"
        )

        return opportunities

    def _analyze_single_market(self, market: Dict[str, Any], avg_volume: float) -> Opportunity | None:
        """Analyze a single market for volume surge opportunities."""
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "Unknown Market")
        last_price = market.get("last_price", 0)
        volume = market.get("volume", 0)

        # Must have significant volume
        if volume < self.config["min_volume"]:
            return None

        # Volume must be significantly above average
        volume_multiplier = volume / avg_volume if avg_volume > 0 else 0
        if volume_multiplier < 2.0:  # At least 2x average
            return None

        side = None
        confidence = None
        strength = None
        estimated_edge_cents = 0

        # High volume + low price = opportunity (crowd might be wrong)
        if last_price < self.config["favorable_low"]:
            side = Side.YES
            edge_from_price = self.config["favorable_low"] - last_price
            volume_boost = min(volume_multiplier / 2, 10)  # Cap at 10
            estimated_edge_cents = edge_from_price + volume_boost
            
            if volume >= self.config["very_high_volume"]:
                strength = OpportunityStrength.HARD
                confidence = ConfidenceLevel.HIGH
            else:
                strength = OpportunityStrength.SOFT
                confidence = ConfidenceLevel.MEDIUM

        # High volume + high price = opportunity (potential bubble)
        elif last_price > self.config["favorable_high"]:
            side = Side.NO
            edge_from_price = last_price - self.config["favorable_high"]
            volume_boost = min(volume_multiplier / 2, 10)  # Cap at 10
            estimated_edge_cents = edge_from_price + volume_boost
            
            if volume >= self.config["very_high_volume"]:
                strength = OpportunityStrength.HARD
                confidence = ConfidenceLevel.HIGH
            else:
                strength = OpportunityStrength.SOFT
                confidence = ConfidenceLevel.MEDIUM
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
            f"Volume surge: {side.name} at {last_price}¢ "
            f"(volume: {volume:,} = {volume_multiplier:.1f}x avg, edge: {estimated_edge_cents:.1f}¢). "
            f"High volume suggests strong interest, price may be inefficient."
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
                "avg_volume": avg_volume,
                "volume_multiplier": volume_multiplier,
                "strategy": "volume_surge",
                "recommended_side": side.value,
            },
        )

        return opportunity
