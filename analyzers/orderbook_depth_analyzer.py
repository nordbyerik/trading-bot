"""
Orderbook Depth Imbalance Analyzer

Exploits order flow imbalance - when one side of the orderbook is significantly
heavier than the other, it signals future price movement.

Strategy:
- Calculate total depth (quantity) on YES vs NO sides
- If YES depth >> NO depth → Price likely to rise → Buy YES
- If NO depth >> YES depth → Price likely to fall → Buy NO
- Stronger imbalance = higher confidence

Key insight: Order book depth reveals true demand/supply
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


class OrderbookDepthAnalyzer(BaseAnalyzer):
    """Identifies opportunities based on orderbook depth imbalance."""

    def get_name(self) -> str:
        return "Orderbook Depth Analyzer"

    def get_description(self) -> str:
        return (
            "Identifies opportunities based on orderbook depth imbalance - "
            "heavy order flow on one side suggests price movement"
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            # Hard opportunity thresholds (strict requirements)
            "hard_min_imbalance_ratio": 4.0,  # 4x imbalance for hard
            "hard_min_total_depth": 100,  # Minimum total depth for hard
            # Soft opportunity thresholds (relaxed requirements)
            "soft_min_imbalance_ratio": 2.0,  # 2x imbalance for soft
            "soft_min_total_depth": 50,  # Minimum total depth for soft
            # General settings
            "min_levels": 2,  # Minimum orderbook levels
            "min_price": 10,  # Don't trade below 10¢
            "max_price": 90,  # Don't trade above 90¢
            "min_volume": 0,  # Minimum market volume
        }

    def _setup(self) -> None:
        """Apply default config values."""
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze multiple markets for orderbook imbalance opportunities.

        Args:
            markets: List of market dictionaries with orderbook data

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
        Analyze a single market for orderbook imbalance opportunities.

        Args:
            market: Market data with orderbook

        Returns:
            Opportunity if found, None otherwise
        """
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "Unknown Market")
        last_price = market.get("last_price")
        volume = market.get("volume", 0)

        # Skip if no price
        if last_price is None or last_price <= 0:
            return None

        # Skip if price too extreme
        if last_price < self.config["min_price"] or last_price > self.config["max_price"]:
            logger.debug(
                f"[DEPTH] {ticker}: Price {last_price}¢ outside bounds "
                f"[{self.config['min_price']}¢, {self.config['max_price']}¢]"
            )
            return None

        # Filter by volume
        if volume < self.config["min_volume"]:
            return None

        # Get orderbook
        orderbook = market.get("orderbook", {})
        if not orderbook:
            return None

        yes_orders = orderbook.get("yes", [])
        no_orders = orderbook.get("no", [])

        # Skip if orderbook is empty or insufficient
        if not yes_orders or not no_orders:
            return None

        min_levels = self.config["min_levels"]
        if len(yes_orders) < min_levels or len(no_orders) < min_levels:
            logger.debug(
                f"[DEPTH] {ticker}: Insufficient levels "
                f"(yes={len(yes_orders)}, no={len(no_orders)}, min={min_levels})"
            )
            return None

        # Calculate total depth on each side
        yes_depth = sum(order[1] for order in yes_orders)  # Sum quantities
        no_depth = sum(order[1] for order in no_orders)

        total_depth = yes_depth + no_depth

        # Determine which side is heavier and calculate imbalance
        if yes_depth > no_depth:
            imbalance_ratio = yes_depth / no_depth if no_depth > 0 else float("inf")
            heavy_side = "yes"
            suggested_side = "yes"  # Heavy YES buying → Buy YES
        else:
            imbalance_ratio = no_depth / yes_depth if yes_depth > 0 else float("inf")
            heavy_side = "no"
            suggested_side = "no"  # Heavy NO buying → Buy NO

        # Determine strength (HARD or SOFT) and confidence
        strength = None
        confidence = None

        # Check hard thresholds first
        hard_ratio = self.config["hard_min_imbalance_ratio"]
        hard_depth = self.config["hard_min_total_depth"]

        if imbalance_ratio >= hard_ratio and total_depth >= hard_depth:
            strength = OpportunityStrength.HARD
            # Higher imbalance = higher confidence
            if imbalance_ratio >= hard_ratio * 2:
                confidence = ConfidenceLevel.HIGH
            elif imbalance_ratio >= hard_ratio * 1.5:
                confidence = ConfidenceLevel.MEDIUM
            else:
                confidence = ConfidenceLevel.LOW

        # Check soft thresholds
        else:
            soft_ratio = self.config["soft_min_imbalance_ratio"]
            soft_depth = self.config["soft_min_total_depth"]

            if imbalance_ratio >= soft_ratio and total_depth >= soft_depth:
                strength = OpportunityStrength.SOFT
                # Higher imbalance = higher confidence
                if imbalance_ratio >= soft_ratio * 2.5:
                    confidence = ConfidenceLevel.HIGH
                elif imbalance_ratio >= soft_ratio * 1.5:
                    confidence = ConfidenceLevel.MEDIUM
                else:
                    confidence = ConfidenceLevel.LOW
            else:
                # Doesn't meet thresholds
                logger.debug(
                    f"[DEPTH] {ticker}: Imbalance {imbalance_ratio:.2f}x too weak "
                    f"(hard min: {hard_ratio}x, soft min: {soft_ratio}x)"
                )
                return None

        # Calculate edge based on imbalance
        # Stronger imbalance = higher expected edge
        soft_ratio = self.config["soft_min_imbalance_ratio"]
        edge_multiplier = min(imbalance_ratio / soft_ratio, 3.0)
        estimated_edge_cents = 5.0 * edge_multiplier  # 5-15¢ edge

        # Calculate edge as percentage
        estimated_edge_percent = (estimated_edge_cents / last_price) * 100 if last_price > 0 else 0

        # Build rationale
        reasoning = (
            f"Order book depth heavily favors {heavy_side.upper()} side with "
            f"{imbalance_ratio:.1f}x imbalance "
            f"(YES: {yes_depth} contracts, NO: {no_depth} contracts). "
            f"Strong {heavy_side.upper()} demand suggests price will move favorably for {suggested_side.upper()} positions."
        )

        logger.info(
            f"[DEPTH] {ticker}: Found {strength.value} opportunity - "
            f"{imbalance_ratio:.1f}x imbalance favoring {heavy_side.upper()} "
            f"(yes_depth={yes_depth}, no_depth={no_depth}, price={last_price}¢)"
        )

        # Create opportunity
        opportunity = Opportunity(
            opportunity_type=OpportunityType.IMBALANCE,
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
                "yes_depth": yes_depth,
                "no_depth": no_depth,
                "imbalance_ratio": imbalance_ratio,
                "heavy_side": heavy_side,
                "suggested_side": suggested_side,  # TradeManager looks for this!
                "total_depth": total_depth,
                "volume": volume,
            },
        )

        return opportunity
