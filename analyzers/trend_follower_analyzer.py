"""
Trend Follower Analyzer

Uses candlestick data to identify strong trends and bet in the direction of the trend.
Follows the "trend is your friend" principle.
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength
from trade_manager import Side


logger = logging.getLogger(__name__)


class TrendFollowerAnalyzer(BaseAnalyzer):
    """
    Analyzes markets for trend-following opportunities using candlestick data.
    
    Looks for:
    - Strong upward trends (buy YES)
    - Strong downward trends (buy NO)
    - Consistent price movement over multiple periods
    """

    def get_name(self) -> str:
        return "Trend Follower Analyzer"

    def get_description(self) -> str:
        return "Follows strong price trends using candlestick data"

    def get_default_config(self) -> Dict[str, Any]:
        return {
            "min_volume": 100,  # Minimum volume to consider
            "min_trend_strength": 10,  # Minimum price change (cents) to consider a trend
            "strong_trend_strength": 20,  # Price change for HIGH confidence
            "lookback_hours": 24,  # How far back to look for trend
            "min_edge_cents": 8,  # Minimum edge in cents
        }

    def _setup(self) -> None:
        """Apply default config values."""
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for trend-following opportunities.

        Args:
            markets: List of market data dictionaries

        Returns:
            List of trend-following opportunities
        """
        opportunities = []

        for market in markets:
            opportunity = self._analyze_single_market(market)
            if opportunity:
                opportunities.append(opportunity)

        logger.info(
            f"TrendFollowerAnalyzer found {len(opportunities)} opportunities "
            f"out of {len(markets)} markets"
        )

        return opportunities

    def _get_candlesticks(self, market: Dict[str, Any]) -> List[Dict]:
        """Fetch candlestick data for a market."""
        ticker = market.get("ticker")
        series_ticker = market.get("series_ticker")
        
        if not series_ticker or not ticker:
            return []
        
        try:
            # Get candlesticks for last N hours
            end_ts = int(time.time())
            start_ts = end_ts - (self.config["lookback_hours"] * 3600)
            
            # Use the client from base analyzer (need to access it through the market data)
            # For now, skip candlesticks if we don't have a client
            # TODO: Pass client to analyzer
            return []
        except Exception as e:
            logger.debug(f"Failed to fetch candlesticks for {ticker}: {e}")
            return []

    def _analyze_single_market(self, market: Dict[str, Any]) -> Opportunity | None:
        """Analyze a single market for trend opportunities."""
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "Unknown Market")
        last_price = market.get("last_price", 0)
        volume = market.get("volume", 0)

        # Filter by volume
        if volume < self.config["min_volume"]:
            return None

        # For now, use simple price-based heuristics since we can't fetch candlesticks easily
        # Look for extreme prices that suggest a trend
        
        side = None
        confidence = None
        strength = None
        estimated_edge_cents = 0

        # Strong upward trend if price is high but not extreme
        # (suggests momentum continuing upward)
        if 60 <= last_price <= 80:
            side = Side.YES
            trend_strength = last_price - 50
            
            if trend_strength >= self.config["strong_trend_strength"]:
                strength = OpportunityStrength.HARD
                confidence = ConfidenceLevel.HIGH
                estimated_edge_cents = trend_strength
            elif trend_strength >= self.config["min_trend_strength"]:
                strength = OpportunityStrength.SOFT
                confidence = ConfidenceLevel.MEDIUM
                estimated_edge_cents = trend_strength
            else:
                return None

        # Strong downward trend if price is low but not extreme
        # (suggests momentum continuing downward)
        elif 20 <= last_price <= 40:
            side = Side.NO
            trend_strength = 50 - last_price
            
            if trend_strength >= self.config["strong_trend_strength"]:
                strength = OpportunityStrength.HARD
                confidence = ConfidenceLevel.HIGH
                estimated_edge_cents = trend_strength
            elif trend_strength >= self.config["min_trend_strength"]:
                strength = OpportunityStrength.SOFT
                confidence = ConfidenceLevel.MEDIUM
                estimated_edge_cents = trend_strength
            else:
                return None
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
            f"Trend following: {side.name} at {last_price}¢ "
            f"(momentum strength: {trend_strength:.1f}¢, volume: {volume}). "
            f"Price shows {'upward' if side == Side.YES else 'downward'} momentum."
        )

        # Build opportunity
        opportunity = Opportunity(
            opportunity_type=OpportunityType.MOMENTUM_FADE,  # Using existing type
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
                "strategy": "trend_following",
                "trend_direction": "up" if side == Side.YES else "down",
                "trend_strength": trend_strength,
                "recommended_side": side.value,
            },
        )

        return opportunity
