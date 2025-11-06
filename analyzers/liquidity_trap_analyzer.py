"""
Liquidity Trap Analyzer

Detects markets where novice traders fall victim to illiquidity:
- Deceptively tight spreads that widen when you try to trade size
- Low order book depth that leads to slippage
- Markets where small orders move the price significantly
- "Ghost liquidity" where visible orders disappear when approached
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength


logger = logging.getLogger(__name__)


class LiquidityTrapAnalyzer(BaseAnalyzer):
    """
    Analyzes markets for liquidity trap opportunities.

    Novice traders often:
    - See tight bid-ask spread and think "good liquidity"
    - Don't check order book depth
    - Use market orders and get terrible fills
    - Don't understand slippage costs
    - Chase prices in thin markets

    This analyzer detects:
    - Deceptively tight spreads with thin depth
    - Markets where moderate size causes significant price impact
    - Opportunities to provide liquidity at premium
    - Situations where we can exploit novice market orders
    """

    def get_name(self) -> str:
        return "Liquidity Trap Analyzer"

    def get_description(self) -> str:
        return (
            "Detects thin markets where novices get poor fills, creating "
            "opportunities to provide liquidity at premium or exploit slippage"
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            # Hard opportunity thresholds
            "hard_max_spread_cents": 5.0,  # "Tight" spread that looks good
            "hard_max_top_depth": 100,  # But very thin depth (contracts)
            "hard_min_price_impact_pct": 15.0,  # Moving 100 contracts causes 15%+ impact

            # Soft opportunity thresholds
            "soft_max_spread_cents": 8.0,
            "soft_max_top_depth": 200,
            "soft_min_price_impact_pct": 10.0,

            # Analysis parameters
            "test_order_size": 100,  # Simulate order of this size
            "depth_levels_to_check": 3,  # Check top N levels of order book
            "min_volume_for_trap": 25,  # Minimum volume to consider
            "max_volume_threshold": 500,  # Don't flag high-volume markets

            # Premium calculation
            "illiquidity_premium_cents": 3.0,  # Value of providing liquidity
        }

    def _setup(self) -> None:
        """Apply default config values."""
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for liquidity trap opportunities.

        Args:
            markets: List of market data dictionaries with orderbook data

        Returns:
            List of liquidity trap opportunities
        """
        opportunities = []

        for market in markets:
            opportunity = self._analyze_single_market(market)
            if opportunity:
                opportunities.append(opportunity)

        logger.info(
            f"LiquidityTrapAnalyzer found {len(opportunities)} opportunities "
            f"out of {len(markets)} markets"
        )

        return opportunities

    def _analyze_single_market(self, market: Dict[str, Any]) -> Optional[Opportunity]:
        """Analyze a single market for liquidity trap opportunities."""
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "Unknown Market")
        volume = market.get("volume", 0)

        # Check volume thresholds
        if volume < self.config["min_volume_for_trap"]:
            return None

        if volume > self.config["max_volume_threshold"]:
            # Too liquid, not a trap
            return None

        # Get orderbook
        orderbook = market.get("orderbook", {})
        if not orderbook:
            return None

        yes_bids = orderbook.get("yes", [])
        no_bids = orderbook.get("no", [])  # These are actually yes asks

        if not yes_bids or not no_bids:
            return None

        # Calculate spread
        best_yes_bid = yes_bids[0][0] if yes_bids else None
        best_yes_ask = 100 - no_bids[0][0] if no_bids else None

        if best_yes_bid is None or best_yes_ask is None:
            return None

        spread_cents = best_yes_ask - best_yes_bid

        # Analyze depth
        depth_analysis = self._analyze_order_book_depth(yes_bids, no_bids)

        if not depth_analysis:
            return None

        total_yes_depth = depth_analysis["total_yes_depth"]
        total_no_depth = depth_analysis["total_no_depth"]
        min_depth = min(total_yes_depth, total_no_depth)

        # Calculate price impact for a test order
        price_impact_pct = self._calculate_price_impact(
            yes_bids, no_bids, self.config["test_order_size"]
        )

        # Check HARD thresholds
        if (spread_cents <= self.config["hard_max_spread_cents"] and
            min_depth <= self.config["hard_max_top_depth"] and
            price_impact_pct >= self.config["hard_min_price_impact_pct"]):
            strength = OpportunityStrength.HARD
        # Check SOFT thresholds
        elif (spread_cents <= self.config["soft_max_spread_cents"] and
              min_depth <= self.config["soft_max_top_depth"] and
              price_impact_pct >= self.config["soft_min_price_impact_pct"]):
            strength = OpportunityStrength.SOFT
        else:
            return None

        # This is a liquidity trap!
        confidence = self._calculate_confidence(
            spread_cents, min_depth, price_impact_pct
        )

        # Calculate edge
        # We can earn the illiquidity premium + spread + slippage we save
        estimated_edge_cents = self._calculate_edge(
            spread_cents, price_impact_pct
        )
        mid_price = (best_yes_bid + best_yes_ask) / 2.0
        estimated_edge_percent = (estimated_edge_cents / mid_price) * 100 if mid_price > 0 else 0

        reasoning = (
            f"LIQUIDITY TRAP: Spread appears tight ({spread_cents:.1f}¢) but depth is shallow "
            f"(Yes: {total_yes_depth}, No: {total_no_depth} contracts). "
            f"Test order of {self.config['test_order_size']} contracts would cause "
            f"{price_impact_pct:.1f}% price impact. Novices using market orders will get "
            f"terrible fills. Opportunity to provide liquidity at premium or exploit slippage."
        )

        opportunity = Opportunity(
            opportunity_type=OpportunityType.WIDE_SPREAD,
            confidence=confidence,
            strength=strength,
            timestamp=datetime.now(),
            market_tickers=[ticker],
            market_titles=[title],
            market_urls=[self._make_market_url(ticker)],
            current_prices={
                f"{ticker}_bid": best_yes_bid,
                f"{ticker}_ask": best_yes_ask,
            },
            estimated_edge_cents=estimated_edge_cents,
            estimated_edge_percent=estimated_edge_percent,
            reasoning=reasoning,
            additional_data={
                "spread_cents": round(spread_cents, 2),
                "yes_depth": total_yes_depth,
                "no_depth": total_no_depth,
                "price_impact_pct": round(price_impact_pct, 2),
                "test_order_size": self.config["test_order_size"],
                "analysis_type": "liquidity_trap",
                "exploit_type": "illiquidity_premium",
            },
        )

        logger.info(
            f"[LIQ-TRAP] {ticker}: {spread_cents:.1f}¢ spread, depth={min_depth}, "
            f"impact={price_impact_pct:.1f}% (Strength: {strength.value})"
        )

        return opportunity

    def _analyze_order_book_depth(
        self, yes_bids: List[List], no_bids: List[List]
    ) -> Optional[Dict[str, int]]:
        """
        Analyze order book depth.

        Returns dict with total depth on each side, or None if insufficient data.
        """
        levels_to_check = min(
            self.config["depth_levels_to_check"],
            len(yes_bids),
            len(no_bids)
        )

        if levels_to_check == 0:
            return None

        # Sum up quantity across top N levels
        total_yes_depth = sum(level[1] for level in yes_bids[:levels_to_check])
        total_no_depth = sum(level[1] for level in no_bids[:levels_to_check])

        return {
            "total_yes_depth": total_yes_depth,
            "total_no_depth": total_no_depth,
        }

    def _calculate_price_impact(
        self, yes_bids: List[List], no_bids: List[List], order_size: int
    ) -> float:
        """
        Calculate price impact of a market order of given size.

        Simulates "walking the book" to see average fill price vs. best price.

        Returns price impact as percentage.
        """
        if not yes_bids:
            return 0.0

        # Use yes side for calculation (buy order walking through asks)
        # no_bids represent yes asks: [no_price, quantity] -> yes_ask = 100 - no_price
        asks = [[100 - level[0], level[1]] for level in no_bids]

        if not asks:
            return 0.0

        best_ask = asks[0][0]
        remaining_size = order_size
        total_cost = 0.0

        # Walk through the ask levels
        for ask_price, ask_quantity in asks:
            if remaining_size <= 0:
                break

            fill_quantity = min(remaining_size, ask_quantity)
            total_cost += fill_quantity * ask_price
            remaining_size -= fill_quantity

        if remaining_size > 0:
            # Couldn't fill entire order, assume infinite slippage
            return 100.0

        # Calculate average fill price
        avg_fill_price = total_cost / order_size

        # Calculate price impact
        price_impact = ((avg_fill_price - best_ask) / best_ask) * 100

        return price_impact

    def _calculate_confidence(
        self, spread_cents: float, min_depth: int, price_impact_pct: float
    ) -> ConfidenceLevel:
        """
        Calculate confidence based on trap severity.

        Tighter spread + thinner depth + bigger impact = higher confidence
        (More deceptive trap = better opportunity)
        """
        # Score spread (tighter = more deceptive)
        if spread_cents <= 3:
            spread_score = 3
        elif spread_cents <= 5:
            spread_score = 2
        else:
            spread_score = 1

        # Score depth (thinner = worse trap)
        if min_depth <= 50:
            depth_score = 3
        elif min_depth <= 100:
            depth_score = 2
        else:
            depth_score = 1

        # Score impact (higher = worse execution)
        if price_impact_pct >= 20:
            impact_score = 3
        elif price_impact_pct >= 15:
            impact_score = 2
        else:
            impact_score = 1

        total_score = spread_score + depth_score + impact_score

        if total_score >= 7:
            return ConfidenceLevel.HIGH
        elif total_score >= 5:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW

    def _calculate_edge(self, spread_cents: float, price_impact_pct: float) -> float:
        """
        Calculate estimated edge in cents.

        Edge comes from:
        1. Illiquidity premium we can charge
        2. Spread we can capture
        3. Slippage we save vs. novices
        """
        # Base illiquidity premium
        edge = self.config["illiquidity_premium_cents"]

        # Add portion of spread
        edge += spread_cents * 0.5

        # Add value from avoiding slippage
        # Assume novices lose price_impact_pct on their fills
        # We can capture some of that
        slippage_value = price_impact_pct * 0.3  # Conservative: 30% of their slippage
        edge += slippage_value

        return edge


if __name__ == "__main__":
    # Simple test
    logging.basicConfig(level=logging.INFO)

    analyzer = LiquidityTrapAnalyzer()
    print(f"Analyzer: {analyzer.get_name()}")
    print(f"Description: {analyzer.get_description()}")
    print(f"Config: {analyzer.config}")
