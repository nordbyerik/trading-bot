"""
Arbitrage Analyzer

Identifies arbitrage opportunities across related markets including:
- YES bid + NO bid > 100¢ in same market (risk-free profit)
- Price inconsistencies across related markets
- Complementary market arbitrage
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Tuple

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength


logger = logging.getLogger(__name__)


class ArbitrageAnalyzer(BaseAnalyzer):
    """
    Detects arbitrage opportunities in prediction markets.

    Strategies:
    1. Simple arbitrage: YES bid + NO bid > 100 (shouldn't happen but worth checking)
    2. Cross-market arbitrage: Related markets with inconsistent prices
    3. Complementary events: If A and B are mutually exclusive and exhaustive,
       their prices should sum to 100¢
    """

    def get_name(self) -> str:
        return "Arbitrage Analyzer"

    def get_description(self) -> str:
        return (
            "Identifies arbitrage opportunities across related markets and "
            "within individual markets (YES vs NO pricing)"
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            # Hard opportunity thresholds (strict requirements)
            "hard_min_arb_cents": 2,  # Minimum arbitrage profit to flag as hard (in cents)
            # Soft opportunity thresholds (relaxed requirements)
            "soft_min_arb_cents": 1,  # Minimum arbitrage profit to flag as soft (in cents)
            "transaction_cost_cents": 1,  # Estimated transaction costs per side
        }

    def _setup(self) -> None:
        """Apply default config values."""
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for arbitrage opportunities.

        Args:
            markets: List of market data dictionaries with orderbook data

        Returns:
            List of arbitrage opportunities
        """
        opportunities = []

        # Check each market for simple YES/NO arbitrage
        for market in markets:
            simple_arb = self._check_simple_arbitrage(market)
            if simple_arb:
                opportunities.append(simple_arb)

        # Check for cross-market arbitrage in same event
        cross_market_arbs = self._check_cross_market_arbitrage(markets)
        opportunities.extend(cross_market_arbs)

        logger.info(
            f"ArbitrageAnalyzer found {len(opportunities)} opportunities "
            f"out of {len(markets)} markets"
        )

        return opportunities

    def _check_simple_arbitrage(self, market: Dict[str, Any]) -> Opportunity | None:
        """
        Check for simple arbitrage within a single market.

        If you can buy YES at one price and NO at another, and YES + NO < 100,
        that's risk-free profit.
        """
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "Unknown Market")
        orderbook = market.get("orderbook", {})

        # Get best bids
        yes_bid_data = self._get_best_bid(orderbook, "yes")
        no_bid_data = self._get_best_bid(orderbook, "no")

        if not yes_bid_data or not no_bid_data:
            logger.debug(f"[ARB] {ticker}: Missing orderbook data")
            return None

        yes_bid, yes_qty = yes_bid_data
        no_bid, no_qty = no_bid_data

        # For arbitrage, we'd sell to both YES and NO bids
        # Total received = yes_bid + no_bid
        # Cost = 100¢ (we need to hold the position until resolution)
        # Profit = (yes_bid + no_bid) - 100

        total_bids = yes_bid + no_bid
        profit_cents = total_bids - 100

        # Account for transaction costs
        transaction_cost = self.config["transaction_cost_cents"] * 2  # Two transactions
        net_profit = profit_cents - transaction_cost

        # Log the calculated metrics for this market
        logger.info(
            f"[ARB] {ticker}: yes_bid={yes_bid:.0f}¢, no_bid={no_bid:.0f}¢, "
            f"total={total_bids:.0f}¢, net_profit={net_profit:.1f}¢"
        )

        # Determine opportunity strength (HARD or SOFT)
        strength = None
        confidence = None

        hard_min_arb = self.config["hard_min_arb_cents"]
        if net_profit >= hard_min_arb:
            strength = OpportunityStrength.HARD
            # This is a high-confidence opportunity if it exists
            confidence = ConfidenceLevel.HIGH if net_profit >= 5 else ConfidenceLevel.MEDIUM
        else:
            soft_min_arb = self.config["soft_min_arb_cents"]
            if net_profit >= soft_min_arb:
                strength = OpportunityStrength.SOFT
                confidence = ConfidenceLevel.MEDIUM if net_profit >= 1.5 else ConfidenceLevel.LOW
            else:
                logger.info(f"[ARB] {ticker}: No arbitrage opportunity (net_profit={net_profit:.1f}¢)")
                return None

        # Calculate position size based on available liquidity
        max_contracts = min(yes_qty, no_qty)

        reasoning = (
            f"Simple arbitrage: YES bid ({yes_bid:.0f}¢) + NO bid ({no_bid:.0f}¢) = "
            f"{total_bids:.0f}¢ > 100¢. "
            f"Net profit: {net_profit:.1f}¢ per contract. "
            f"Max contracts: {max_contracts}"
        )

        edge_percent = (net_profit / 100) * 100  # Percent return on capital

        opportunity = Opportunity(
            opportunity_type=OpportunityType.ARBITRAGE,
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
            estimated_edge_cents=net_profit,
            estimated_edge_percent=edge_percent,
            reasoning=reasoning,
            additional_data={
                "yes_bid": yes_bid,
                "no_bid": no_bid,
                "total_bids": total_bids,
                "gross_profit": profit_cents,
                "transaction_costs": transaction_cost,
                "max_contracts": max_contracts,
            },
        )

        return opportunity

    def _check_cross_market_arbitrage(
        self, markets: List[Dict[str, Any]]
    ) -> List[Opportunity]:
        """
        Check for arbitrage across related markets.

        For example, if markets are mutually exclusive outcomes of the same event,
        their prices should sum to approximately 100¢.
        """
        opportunities = []

        # Group markets by event_ticker
        markets_by_event: Dict[str, List[Dict]] = {}
        for market in markets:
            event_ticker = market.get("event_ticker")
            if event_ticker:
                if event_ticker not in markets_by_event:
                    markets_by_event[event_ticker] = []
                markets_by_event[event_ticker].append(market)

        # Check events with multiple markets
        for event_ticker, event_markets in markets_by_event.items():
            if len(event_markets) < 2:
                continue

            # Check if markets might be mutually exclusive
            # This is a heuristic - in reality, we'd need event metadata
            arb_opp = self._check_mutually_exclusive_markets(event_markets)
            if arb_opp:
                opportunities.append(arb_opp)

        return opportunities

    def _check_mutually_exclusive_markets(
        self, markets: List[Dict[str, Any]]
    ) -> Opportunity | None:
        """
        Check if mutually exclusive markets have inconsistent pricing.

        If markets are mutually exclusive and exhaustive, the sum of their
        YES prices should be approximately 100¢.
        """
        # Get prices for all markets
        prices = []
        tickers = []
        titles = []

        for market in markets:
            ticker = market.get("ticker")
            title = market.get("title", "")

            # Try to get price from orderbook or yes_price
            price = market.get("yes_price")
            if price is None and "orderbook" in market:
                yes_bid_data = self._get_best_bid(market["orderbook"], "yes")
                if yes_bid_data:
                    price = yes_bid_data[0]

            if price is not None and ticker:
                prices.append(price)
                tickers.append(ticker)
                titles.append(title)

        if len(prices) < 2:
            return None

        # Calculate sum of prices
        total_price = sum(prices)

        # If prices sum to significantly more than 100, there might be arbitrage
        # (though in practice, Kalshi markets may not be perfectly mutually exclusive)
        # We're looking for cases where you could buy all outcomes for < 100¢

        # More conservatively, look for cases where prices sum to < 90 or > 110
        if 90 <= total_price <= 110:
            return None

        if total_price > 110:
            # Markets are overpriced - could short all of them
            # But shorting on Kalshi is limited, so skip this
            return None

        # total_price < 90: Could buy all outcomes for less than 100¢
        profit_cents = 100 - total_price
        transaction_cost = self.config["transaction_cost_cents"] * len(prices)
        net_profit = profit_cents - transaction_cost

        # Determine opportunity strength (HARD or SOFT)
        strength = None
        confidence = None

        hard_min_arb = self.config["hard_min_arb_cents"]
        if net_profit >= hard_min_arb:
            strength = OpportunityStrength.HARD
            # Lower confidence since we're not certain markets are mutually exclusive
            confidence = ConfidenceLevel.LOW
        else:
            soft_min_arb = self.config["soft_min_arb_cents"]
            if net_profit >= soft_min_arb:
                strength = OpportunityStrength.SOFT
                confidence = ConfidenceLevel.LOW
            else:
                return None

        reasoning = (
            f"Potential cross-market arbitrage: {len(prices)} related markets "
            f"with total price {total_price:.0f}¢ < 100¢. "
            f"Net profit: {net_profit:.1f}¢ if markets are mutually exclusive and exhaustive."
        )

        edge_percent = (net_profit / total_price) * 100 if total_price > 0 else 0

        urls = [self._make_market_url(t) for t in tickers]
        prices_dict = {ticker: price for ticker, price in zip(tickers, prices)}

        opportunity = Opportunity(
            opportunity_type=OpportunityType.ARBITRAGE,
            confidence=confidence,
            strength=strength,
            timestamp=datetime.now(),
            market_tickers=tickers,
            market_titles=titles,
            market_urls=urls,
            current_prices=prices_dict,
            estimated_edge_cents=net_profit,
            estimated_edge_percent=edge_percent,
            reasoning=reasoning,
            additional_data={
                "total_price": total_price,
                "num_markets": len(prices),
                "individual_prices": prices,
                "transaction_costs": transaction_cost,
            },
        )

        return opportunity


if __name__ == "__main__":
    # Simple test with mock data
    logging.basicConfig(level=logging.INFO)

    mock_markets = [
        {
            "ticker": "ARB-SIMPLE",
            "title": "Market with simple arbitrage",
            "event_ticker": "EVENT-1",
            "orderbook": {
                "yes": [[55, 100]],
                "no": [[50, 100]],  # 55 + 50 = 105 > 100 (arbitrage!)
            },
        },
        {
            "ticker": "ARB-CROSS-1",
            "title": "Market A in event 2",
            "event_ticker": "EVENT-2",
            "yes_price": 30,
        },
        {
            "ticker": "ARB-CROSS-2",
            "title": "Market B in event 2",
            "event_ticker": "EVENT-2",
            "yes_price": 35,
        },
        {
            "ticker": "ARB-CROSS-3",
            "title": "Market C in event 2",
            "event_ticker": "EVENT-2",
            "yes_price": 20,
        },
        # Total for EVENT-2: 30 + 35 + 20 = 85 < 100 (potential arbitrage)
    ]

    analyzer = ArbitrageAnalyzer()
    opportunities = analyzer.analyze(mock_markets)

    print(f"\nFound {len(opportunities)} opportunities:\n")
    for opp in opportunities:
        print(opp)
        print(f"  Additional data: {opp.additional_data}\n")
