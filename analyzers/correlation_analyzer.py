"""
Correlation Analyzer

Finds related markets and checks if their implied probabilities are consistent.
Flags correlation breaks where logically related outcomes have inconsistent pricing.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength


logger = logging.getLogger(__name__)


class CorrelationAnalyzer(BaseAnalyzer):
    """
    Analyzes correlation and consistency across related markets.

    Checks for logical relationships like:
    - If "Team A wins" is 60%, "Team A wins by 10+" should be <= 60%
    - Related markets in same event should have consistent probabilities
    - Series of ordered outcomes should maintain logical ordering
    """

    def get_name(self) -> str:
        return "Correlation Analyzer"

    def get_description(self) -> str:
        return (
            "Identifies related markets with inconsistent probabilities, "
            "such as subset events priced higher than supersets"
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            # Hard opportunity thresholds (strict requirements)
            "hard_min_inconsistency_cents": 5,  # Minimum price inconsistency to flag for hard
            # Soft opportunity thresholds (relaxed requirements)
            "soft_min_inconsistency_cents": 3,  # Minimum price inconsistency to flag for soft
            "check_same_event": True,  # Check markets in same event
            "check_same_series": True,  # Check markets in same series
        }

    def _setup(self) -> None:
        """Apply default config values."""
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for correlation inconsistencies.

        Args:
            markets: List of market data dictionaries

        Returns:
            List of correlation break opportunities
        """
        opportunities = []

        # Group markets by event and series
        markets_by_event = self._group_by_field(markets, "event_ticker")
        markets_by_series = self._group_by_field(markets, "series_ticker")

        # Check for inconsistencies within events
        if self.config["check_same_event"]:
            for event_ticker, event_markets in markets_by_event.items():
                if len(event_markets) >= 2:
                    event_opps = self._check_related_markets(
                        event_markets, "event", event_ticker
                    )
                    opportunities.extend(event_opps)

        # Check for inconsistencies within series
        if self.config["check_same_series"]:
            for series_ticker, series_markets in markets_by_series.items():
                if len(series_markets) >= 2:
                    series_opps = self._check_related_markets(
                        series_markets, "series", series_ticker
                    )
                    opportunities.extend(series_opps)

        logger.info(
            f"CorrelationAnalyzer found {len(opportunities)} opportunities "
            f"out of {len(markets)} markets"
        )

        return opportunities

    def _group_by_field(
        self, markets: List[Dict[str, Any]], field: str
    ) -> Dict[str, List[Dict]]:
        """Group markets by a specific field."""
        grouped: Dict[str, List[Dict]] = {}
        for market in markets:
            key = market.get(field)
            if key:
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(market)
        return grouped

    def _check_related_markets(
        self, markets: List[Dict[str, Any]], group_type: str, group_id: str
    ) -> List[Opportunity]:
        """
        Check for correlation breaks in related markets.

        Look for patterns like:
        - Subset priced higher than superset
        - Ordered outcomes with inverted probabilities
        """
        opportunities = []

        # Get prices for all markets
        market_data = []
        for market in markets:
            ticker = market.get("ticker")
            title = market.get("title", "")
            price = self._get_market_price(market)

            if ticker and price is not None:
                market_data.append({
                    "ticker": ticker,
                    "title": title,
                    "price": price,
                    "market": market,
                })

        if len(market_data) < 2:
            logger.debug(f"[CORR] {group_type} {group_id}: Insufficient markets for comparison ({len(market_data)} < 2)")
            return opportunities

        # Look for subset/superset relationships through title analysis
        # This is heuristic-based
        for i, market_a in enumerate(market_data):
            for market_b in market_data[i + 1:]:
                opp = self._check_pair_correlation(market_a, market_b, group_type)
                if opp:
                    opportunities.append(opp)

        return opportunities

    def _get_market_price(self, market: Dict[str, Any]) -> Optional[float]:
        """Extract current price from market data."""
        price = market.get("yes_price")
        if price is None and "orderbook" in market:
            yes_bid_data = self._get_best_bid(market["orderbook"], "yes")
            if yes_bid_data:
                price = yes_bid_data[0]
        return price

    def _check_pair_correlation(
        self, market_a: Dict, market_b: Dict, group_type: str
    ) -> Opportunity | None:
        """Check if two markets have a correlation break."""
        title_a = market_a["title"].lower()
        title_b = market_b["title"].lower()
        price_a = market_a["price"]
        price_b = market_b["price"]

        # Log the comparison
        logger.debug(
            f"[CORR] Comparing: '{market_a['ticker']}' ({price_a:.0f}¢) vs '{market_b['ticker']}' ({price_b:.0f}¢)"
        )

        # Heuristic: Look for subset/superset keywords
        # Common patterns:
        # - "at least X" vs "exactly X"
        # - "over X" vs "X to Y"
        # - "wins" vs "wins by 10+"

        subset_keywords = [
            ("at least", "exactly"),
            ("over", "under"),
            ("more than", "less than"),
            ("wins by", "wins"),
            (">", "="),
            (">=", "="),
        ]

        # Check if one market might be a subset of another
        relationship = None
        for superset_kw, subset_kw in subset_keywords:
            if superset_kw in title_a and subset_kw in title_b:
                relationship = ("a_superset", superset_kw, subset_kw)
                break
            elif superset_kw in title_b and subset_kw in title_a:
                relationship = ("b_superset", superset_kw, subset_kw)
                break

        if not relationship:
            logger.debug(f"[CORR] No subset/superset relationship detected between {market_a['ticker']} and {market_b['ticker']}")
            return None

        # Check if probabilities are inconsistent
        # Subset should have <= probability of superset
        if relationship[0] == "a_superset":
            # A is superset, B is subset
            if price_b > price_a:
                inconsistency = price_b - price_a
            else:
                logger.info(
                    f"[CORR] {market_a['ticker']} / {market_b['ticker']}: Consistent pricing "
                    f"(superset {price_a:.0f}¢ >= subset {price_b:.0f}¢)"
                )
                return None  # Consistent
        else:
            # B is superset, A is subset
            if price_a > price_b:
                inconsistency = price_a - price_b
            else:
                logger.info(
                    f"[CORR] {market_a['ticker']} / {market_b['ticker']}: Consistent pricing "
                    f"(superset {price_b:.0f}¢ >= subset {price_a:.0f}¢)"
                )
                return None  # Consistent

        # Log the inconsistency found
        logger.info(
            f"[CORR] {market_a['ticker']} / {market_b['ticker']}: Inconsistency detected! "
            f"Subset priced {inconsistency:.1f}¢ higher than superset"
        )

        # Determine opportunity strength (HARD or SOFT) and confidence
        strength = None
        confidence = None

        # Check hard thresholds first
        hard_min = self.config["hard_min_inconsistency_cents"]
        if inconsistency >= hard_min:
            strength = OpportunityStrength.HARD
            if inconsistency >= 15:
                confidence = ConfidenceLevel.HIGH
            elif inconsistency >= 8:
                confidence = ConfidenceLevel.MEDIUM
            else:
                confidence = ConfidenceLevel.LOW
        else:
            # Check soft thresholds
            soft_min = self.config["soft_min_inconsistency_cents"]
            if inconsistency >= soft_min:
                strength = OpportunityStrength.SOFT
                if inconsistency >= 10:
                    confidence = ConfidenceLevel.MEDIUM
                else:
                    confidence = ConfidenceLevel.LOW
            else:
                logger.info(
                    f"[CORR] {market_a['ticker']} / {market_b['ticker']}: Inconsistency too small "
                    f"({inconsistency:.1f}¢ < {soft_min}¢ soft min)"
                )
                return None

        # Estimate edge as the inconsistency
        estimated_edge_cents = inconsistency / 2  # Conservative
        estimated_edge_percent = (estimated_edge_cents / min(price_a, price_b)) * 100

        reasoning = (
            f"Correlation break in {group_type}: "
            f"'{market_a['title']}' ({price_a:.0f}¢) vs "
            f"'{market_b['title']}' ({price_b:.0f}¢). "
            f"Subset event priced {inconsistency:.0f}¢ higher than superset."
        )

        opportunity = Opportunity(
            opportunity_type=OpportunityType.CORRELATION_BREAK,
            confidence=confidence,
            strength=strength,
            timestamp=datetime.now(),
            market_tickers=[market_a["ticker"], market_b["ticker"]],
            market_titles=[market_a["title"], market_b["title"]],
            market_urls=[
                self._make_market_url(market_a["ticker"]),
                self._make_market_url(market_b["ticker"]),
            ],
            current_prices={
                market_a["ticker"]: price_a,
                market_b["ticker"]: price_b,
            },
            estimated_edge_cents=estimated_edge_cents,
            estimated_edge_percent=estimated_edge_percent,
            reasoning=reasoning,
            additional_data={
                "inconsistency_cents": inconsistency,
                "relationship": relationship[0],
                "keywords": (relationship[1], relationship[2]),
                "group_type": group_type,
            },
        )

        return opportunity


if __name__ == "__main__":
    # Simple test with mock data
    logging.basicConfig(level=logging.INFO)

    mock_markets = [
        {
            "ticker": "CORR-1",
            "title": "Team A wins",
            "yes_price": 55,
            "event_ticker": "GAME-1",
        },
        {
            "ticker": "CORR-2",
            "title": "Team A wins by at least 10 points",
            "yes_price": 60,  # Inconsistent! Should be <= 55
            "event_ticker": "GAME-1",
        },
        {
            "ticker": "CORR-3",
            "title": "Temperature over 80 degrees",
            "yes_price": 40,
            "series_ticker": "TEMP",
        },
        {
            "ticker": "CORR-4",
            "title": "Temperature exactly 85 degrees",
            "yes_price": 45,  # Inconsistent! Should be <= 40
            "series_ticker": "TEMP",
        },
    ]

    analyzer = CorrelationAnalyzer()
    opportunities = analyzer.analyze(mock_markets)

    print(f"\nFound {len(opportunities)} opportunities:\n")
    for opp in opportunities:
        print(opp)
        print(f"  Additional data: {opp.additional_data}\n")
