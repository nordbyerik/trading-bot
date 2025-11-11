"""
Price Extreme Mean Reversion Analyzer

Exploits overconfidence at price extremes - markets priced very high or very low
often revert to more reasonable levels.

Strategy:
- Markets at <5¢: Overconfident bears → Buy YES (contrarian)
- Markets at >95¢: Overconfident bulls → Buy NO (contrarian)
- Markets at extremes have asymmetric risk/reward

Key insight: Extreme prices represent overconfidence and often revert
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from .base import (
    BaseAnalyzer,
    Opportunity,
    OpportunityType,
    ConfidenceLevel,
    OpportunityStrength,
)

logger = logging.getLogger(__name__)


class PriceExtremeReversionAnalyzer(BaseAnalyzer):
    """Identifies mean reversion opportunities at price extremes."""

    def get_name(self) -> str:
        return "Price Extreme Reversion Analyzer"

    def get_description(self) -> str:
        return (
            "Identifies mean reversion opportunities when markets are priced at extremes - "
            "contrarian bets against overconfidence"
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            # Hard opportunity thresholds (most extreme)
            "hard_low_price": 3,  # <= 3¢ is extremely underpriced
            "hard_high_price": 97,  # >= 97¢ is extremely overpriced
            "hard_min_volume": 100,  # Need some liquidity
            # Soft opportunity thresholds
            "soft_low_price": 5,  # <= 5¢ is underpriced
            "soft_high_price": 95,  # >= 95¢ is overpriced
            "soft_min_volume": 10,  # Lower volume OK
            # General settings
            "min_open_interest": 10,  # Need some market activity
            "max_close_hours": 48,  # Don't trade markets closing >48hrs away
        }

    def _setup(self) -> None:
        """Apply default config values."""
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze multiple markets for price extreme opportunities.

        Args:
            markets: List of market dictionaries

        Returns:
            List of all found opportunities
        """
        opportunities = []

        for market in markets:
            try:
                opportunity = self._analyze_single_market(market)
                if opportunity:
                    opportunities.append(opportunity)
            except Exception as e:
                ticker = market.get("ticker", "UNKNOWN")
                logger.error(f"Error analyzing {ticker}: {e}")

        logger.info(
            f"{self.get_name()} found {len(opportunities)} opportunities "
            f"out of {len(markets)} markets"
        )
        return opportunities

    def _analyze_single_market(self, market: Dict[str, Any]) -> Optional[Opportunity]:
        """
        Analyze a single market for price extreme opportunities.

        Args:
            market: Market data

        Returns:
            Opportunity if found, None otherwise
        """
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "Unknown Market")
        last_price = market.get("last_price")
        volume = market.get("volume", 0)
        open_interest = market.get("open_interest", 0)

        # Skip if no price
        if last_price is None:
            return None

        # Filter by open interest
        if open_interest < self.config["min_open_interest"]:
            return None

        # Determine if this is a hard or soft opportunity
        hard_low = self.config["hard_low_price"]
        hard_high = self.config["hard_high_price"]
        soft_low = self.config["soft_low_price"]
        soft_high = self.config["soft_high_price"]

        strength = None
        confidence = None
        suggested_side = None
        extreme_type = None

        # Check for HARD opportunities (most extreme)
        if last_price <= hard_low and volume >= self.config["hard_min_volume"]:
            strength = OpportunityStrength.HARD
            suggested_side = "yes"  # Buy YES on underpriced markets
            extreme_type = "extreme_low"

            # Lower price = higher confidence in reversion
            if last_price <= 1:
                confidence = ConfidenceLevel.HIGH
            elif last_price <= 2:
                confidence = ConfidenceLevel.MEDIUM
            else:
                confidence = ConfidenceLevel.LOW

        elif last_price >= hard_high and volume >= self.config["hard_min_volume"]:
            strength = OpportunityStrength.HARD
            suggested_side = "no"  # Buy NO on overpriced markets
            extreme_type = "extreme_high"

            # Higher price = higher confidence in reversion
            if last_price >= 99:
                confidence = ConfidenceLevel.HIGH
            elif last_price >= 98:
                confidence = ConfidenceLevel.MEDIUM
            else:
                confidence = ConfidenceLevel.LOW

        # Check for SOFT opportunities
        elif last_price <= soft_low and volume >= self.config["soft_min_volume"]:
            strength = OpportunityStrength.SOFT
            suggested_side = "yes"
            extreme_type = "low"

            if last_price <= 3:
                confidence = ConfidenceLevel.MEDIUM
            else:
                confidence = ConfidenceLevel.LOW

        elif last_price >= soft_high and volume >= self.config["soft_min_volume"]:
            strength = OpportunityStrength.SOFT
            suggested_side = "no"
            extreme_type = "high"

            if last_price >= 97:
                confidence = ConfidenceLevel.MEDIUM
            else:
                confidence = ConfidenceLevel.LOW

        else:
            # Price not extreme enough
            return None

        # Calculate edge based on extreme level
        # More extreme = higher edge
        if extreme_type in ["extreme_low", "low"]:
            # Distance from low threshold
            distance_from_threshold = soft_low - last_price
            estimated_edge_cents = 5.0 + (distance_from_threshold * 2)  # 5-15¢
        else:  # high or extreme_high
            # Distance from high threshold
            distance_from_threshold = last_price - soft_high
            estimated_edge_cents = 5.0 + (distance_from_threshold * 2)  # 5-15¢

        estimated_edge_cents = min(estimated_edge_cents, 20.0)  # Cap at 20¢

        # Calculate edge as percentage
        estimated_edge_percent = (estimated_edge_cents / last_price) * 100 if last_price > 0 else 0

        # Build rationale
        if extreme_type in ["extreme_low", "low"]:
            reasoning = (
                f"Market extremely underpriced at {last_price}¢ "
                f"(threshold: {soft_low if strength == OpportunityStrength.SOFT else hard_low}¢). "
                f"Contrarian YES bet exploits overconfident bears. "
                f"Asymmetric payoff: max loss {last_price}¢, potential gain {100-last_price}¢. "
                f"Volume: {volume:,}, OI: {open_interest:,}"
            )
        else:
            reasoning = (
                f"Market extremely overpriced at {last_price}¢ "
                f"(threshold: {soft_high if strength == OpportunityStrength.SOFT else hard_high}¢). "
                f"Contrarian NO bet exploits overconfident bulls. "
                f"Asymmetric payoff: max loss {100-last_price}¢, potential gain {last_price}¢. "
                f"Volume: {volume:,}, OI: {open_interest:,}"
            )

        logger.info(
            f"[EXTREME] {ticker}: Found {strength.value} opportunity - "
            f"{extreme_type} at {last_price}¢, suggesting {suggested_side.upper()} "
            f"(vol={volume}, oi={open_interest})"
        )

        # Create opportunity
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
            },
            estimated_edge_cents=estimated_edge_cents,
            estimated_edge_percent=estimated_edge_percent,
            reasoning=reasoning,
            additional_data={
                "extreme_type": extreme_type,
                "suggested_side": suggested_side,  # TradeManager looks for this!
                "volume": volume,
                "open_interest": open_interest,
                "last_price": last_price,
            },
        )

        return opportunity
