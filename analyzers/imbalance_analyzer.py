"""
Imbalance Analyzer

Detects orderbook imbalances that may indicate:
- Informed flow (one-sided order interest)
- Potential mispricings
- Liquidity gaps
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength


logger = logging.getLogger(__name__)


class ImbalanceAnalyzer(BaseAnalyzer):
    """
    Analyzes orderbook depth imbalances.

    Flags markets with:
    - Much deeper liquidity on one side
    - Very thin liquidity on one side (potential for price impact)
    - Asymmetric order flow that may indicate informed trading
    """

    def get_name(self) -> str:
        return "Imbalance Analyzer"

    def get_description(self) -> str:
        return (
            "Detects orderbook imbalances with one-sided liquidity "
            "that may indicate informed flow or mispricing"
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            # Hard opportunity thresholds (strict requirements)
            "hard_min_imbalance_ratio": 3.0,  # Min ratio of depth for hard (e.g., 3:1)
            "hard_strong_imbalance_ratio": 5.0,  # Strong imbalance threshold for hard
            "hard_min_total_liquidity": 100,  # Minimum combined liquidity for hard (contracts)
            "hard_max_thin_side_liquidity": 50,  # Max contracts on thin side for hard
            # Soft opportunity thresholds (relaxed requirements)
            "soft_min_imbalance_ratio": 2.0,  # Min ratio of depth for soft (e.g., 2:1)
            "soft_strong_imbalance_ratio": 3.5,  # Strong imbalance threshold for soft
            "soft_min_total_liquidity": 50,  # Minimum combined liquidity for soft (contracts)
            "soft_max_thin_side_liquidity": 100,  # Max contracts on thin side for soft
        }

    def _setup(self) -> None:
        """Apply default config values."""
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for orderbook imbalances.

        Args:
            markets: List of market data dictionaries with orderbook data

        Returns:
            List of imbalance-based opportunities
        """
        opportunities = []

        for market in markets:
            # Skip markets without orderbook data
            if "orderbook" not in market:
                continue

            opportunity = self._analyze_imbalance(market)
            if opportunity:
                opportunities.append(opportunity)

        logger.info(
            f"ImbalanceAnalyzer found {len(opportunities)} opportunities "
            f"out of {len(markets)} markets"
        )

        return opportunities

    def _analyze_imbalance(self, market: Dict[str, Any]) -> Opportunity | None:
        """Analyze a single market for orderbook imbalance."""
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "Unknown Market")
        orderbook = market.get("orderbook", {})

        # Calculate total liquidity on each side
        yes_depth = self._calculate_depth(orderbook.get("yes", []))
        no_depth = self._calculate_depth(orderbook.get("no", []))

        if yes_depth == 0 and no_depth == 0:
            logger.debug(f"[IMBALANCE] {ticker}: No liquidity in orderbook")
            return None

        # Avoid division by zero
        if yes_depth == 0:
            yes_depth = 1
        if no_depth == 0:
            no_depth = 1

        total_depth = yes_depth + no_depth

        # Calculate imbalance ratio
        yes_no_ratio = yes_depth / no_depth
        no_yes_ratio = no_depth / yes_depth
        max_ratio = max(yes_no_ratio, no_yes_ratio)

        # Log the calculated metrics for this market
        logger.info(
            f"[IMBALANCE] {ticker}: yes_depth={yes_depth}, no_depth={no_depth}, "
            f"ratio={max_ratio:.1f}:1"
        )

        # Determine which side has more depth
        if yes_depth > no_depth:
            heavy_side = "yes"
            thin_side = "no"
            imbalance_ratio = yes_no_ratio
            thin_depth = no_depth
        else:
            heavy_side = "no"
            thin_side = "yes"
            imbalance_ratio = no_yes_ratio
            thin_depth = yes_depth

        # Determine opportunity strength (HARD or SOFT) and confidence
        strength = None
        confidence = None
        is_very_thin = False

        # Check hard thresholds first
        hard_min_liq = self.config["hard_min_total_liquidity"]
        hard_min_imb = self.config["hard_min_imbalance_ratio"]
        hard_strong_imb = self.config["hard_strong_imbalance_ratio"]
        hard_max_thin = self.config["hard_max_thin_side_liquidity"]

        if total_depth >= hard_min_liq and max_ratio >= hard_min_imb:
            strength = OpportunityStrength.HARD
            is_very_thin = thin_depth <= hard_max_thin

            if imbalance_ratio >= hard_strong_imb and is_very_thin:
                confidence = ConfidenceLevel.HIGH
            elif imbalance_ratio >= hard_strong_imb or is_very_thin:
                confidence = ConfidenceLevel.MEDIUM
            else:
                confidence = ConfidenceLevel.LOW

        # Otherwise check soft thresholds
        else:
            soft_min_liq = self.config["soft_min_total_liquidity"]
            soft_min_imb = self.config["soft_min_imbalance_ratio"]
            soft_strong_imb = self.config["soft_strong_imbalance_ratio"]
            soft_max_thin = self.config["soft_max_thin_side_liquidity"]

            if total_depth >= soft_min_liq and max_ratio >= soft_min_imb:
                strength = OpportunityStrength.SOFT
                is_very_thin = thin_depth <= soft_max_thin

                if imbalance_ratio >= soft_strong_imb and is_very_thin:
                    confidence = ConfidenceLevel.HIGH
                elif imbalance_ratio >= soft_strong_imb or is_very_thin:
                    confidence = ConfidenceLevel.MEDIUM
                else:
                    confidence = ConfidenceLevel.LOW
            else:
                logger.info(
                    f"[IMBALANCE] {ticker}: Imbalance not significant enough "
                    f"(ratio={max_ratio:.1f}, min soft={self.config['soft_min_imbalance_ratio']:.1f})"
                )
                return None

        # Get current price
        current_price = market.get("yes_price")
        if current_price is None:
            yes_bid_data = self._get_best_bid(orderbook, "yes")
            if yes_bid_data:
                current_price = yes_bid_data[0]
            else:
                current_price = 50  # Default fallback

        # Estimate edge based on imbalance
        # Heavy liquidity on one side may indicate:
        # - Informed flow pushing price in that direction
        # - Or market makers providing liquidity against uninformed flow
        # Conservative edge estimate: 2-5 cents
        estimated_edge_cents = min(5.0, imbalance_ratio * 0.5)

        estimated_edge_percent = (estimated_edge_cents / current_price) * 100 if current_price > 0 else 0

        # Build reasoning
        reasoning = (
            f"Orderbook imbalance: {imbalance_ratio:.1f}:1 ratio "
            f"({heavy_side} side: {yes_depth if heavy_side == 'yes' else no_depth} contracts, "
            f"{thin_side} side: {thin_depth} contracts). "
        )

        if is_very_thin:
            reasoning += f"Very thin liquidity on {thin_side} side may indicate informed flow or mispricing."
        else:
            reasoning += f"Heavy {heavy_side} side liquidity may indicate directional bias."

        opportunity = Opportunity(
            opportunity_type=OpportunityType.IMBALANCE,
            confidence=confidence,
            strength=strength,
            timestamp=datetime.now(),
            market_tickers=[ticker],
            market_titles=[title],
            market_urls=[self._make_market_url(ticker)],
            current_prices={ticker: current_price},
            estimated_edge_cents=estimated_edge_cents,
            estimated_edge_percent=estimated_edge_percent,
            reasoning=reasoning,
            additional_data={
                "yes_depth": yes_depth,
                "no_depth": no_depth,
                "total_depth": total_depth,
                "imbalance_ratio": imbalance_ratio,
                "heavy_side": heavy_side,
                "thin_side": thin_side,
                "is_very_thin": is_very_thin,
                "current_price": current_price,
            },
        )

        return opportunity

    def _calculate_depth(self, bids: List[List]) -> int:
        """
        Calculate total depth from a list of bids.

        Args:
            bids: List of [price, quantity] pairs

        Returns:
            Total quantity available
        """
        if bids is None:
            return 0
        return sum(bid[1] for bid in bids)


if __name__ == "__main__":
    # Simple test with mock data
    logging.basicConfig(level=logging.INFO)

    mock_markets = [
        {
            "ticker": "IMB-1",
            "title": "Market with heavy YES imbalance",
            "yes_price": 55,
            "orderbook": {
                "yes": [[55, 500], [54, 300]],  # 800 total
                "no": [[45, 100]],  # 100 total (8:1 ratio)
            },
        },
        {
            "ticker": "IMB-2",
            "title": "Market with heavy NO imbalance and very thin YES",
            "yes_price": 30,
            "orderbook": {
                "yes": [[30, 20]],  # Very thin!
                "no": [[70, 200], [68, 150]],  # 350 total (17.5:1 ratio!)
            },
        },
        {
            "ticker": "IMB-3",
            "title": "Balanced market",
            "yes_price": 50,
            "orderbook": {
                "yes": [[50, 200]],
                "no": [[50, 200]],  # Balanced (1:1 ratio)
            },
        },
    ]

    analyzer = ImbalanceAnalyzer()
    opportunities = analyzer.analyze(mock_markets)

    print(f"\nFound {len(opportunities)} opportunities:\n")
    for opp in opportunities:
        print(opp)
        print(f"  Additional data: {opp.additional_data}\n")
