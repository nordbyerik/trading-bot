"""
Momentum Fade Analyzer

Detects sudden price movements that may indicate overreactions,
providing fade opportunities (betting against recent momentum).
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength


logger = logging.getLogger(__name__)


class MomentumFadeAnalyzer(BaseAnalyzer):
    """
    Analyzes price momentum and identifies potential fade opportunities.

    This analyzer tracks price changes over time and flags markets where
    rapid price movements may indicate overreaction.
    """

    def _setup(self) -> None:
        """Initialize price history tracking."""
        # Store historical prices: {ticker: [(timestamp, price), ...]}
        self.price_history: Dict[str, List[tuple[datetime, float]]] = {}

        # Apply default config
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def get_name(self) -> str:
        return "Momentum Fade Analyzer"

    def get_description(self) -> str:
        return (
            "Tracks price changes over time and identifies sudden moves "
            "that may indicate overreaction (fade opportunities)"
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            # Hard opportunity thresholds (strict requirements)
            "hard_min_price_change_cents": 10,  # Minimum price change to flag for hard
            "hard_large_price_change_cents": 20,  # "Large" price change threshold for hard
            # Soft opportunity thresholds (relaxed requirements)
            "soft_min_price_change_cents": 5,  # Minimum price change to flag for soft
            "soft_large_price_change_cents": 12,  # "Large" price change threshold for soft
            "lookback_periods": 3,  # Number of historical observations to keep
            "min_history_required": 2,  # Minimum history before flagging
        }

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for momentum fade opportunities.

        Args:
            markets: List of market data dictionaries

        Returns:
            List of momentum fade opportunities
        """
        opportunities = []
        current_time = datetime.now()

        for market in markets:
            ticker = market.get("ticker", "UNKNOWN")

            # Get current price
            current_price = self._get_market_price(market)
            if current_price is None:
                continue

            # Update price history
            if ticker not in self.price_history:
                self.price_history[ticker] = []
                # Try to pre-warm from historical candlesticks
                self._try_prewarm_from_candlesticks(market, ticker)

            self.price_history[ticker].append((current_time, current_price))

            # Keep only recent history
            max_history = self.config["lookback_periods"]
            if len(self.price_history[ticker]) > max_history:
                self.price_history[ticker] = self.price_history[ticker][-max_history:]

            # Check for fade opportunities
            opportunity = self._check_for_fade(market, ticker, current_price)
            if opportunity:
                opportunities.append(opportunity)

        logger.info(
            f"MomentumFadeAnalyzer found {len(opportunities)} opportunities "
            f"out of {len(markets)} markets"
        )

        return opportunities

    def _get_market_price(self, market: Dict[str, Any]) -> Optional[float]:
        """Extract current price from market data."""
        # Try yes_price first
        price = market.get("yes_price")

        # If not available, try orderbook
        if price is None and "orderbook" in market:
            yes_bid_data = self._get_best_bid(market["orderbook"], "yes")
            if yes_bid_data:
                price = yes_bid_data[0]

        return price

    def _check_for_fade(
        self, market: Dict[str, Any], ticker: str, current_price: float
    ) -> Opportunity | None:
        """Check if market has momentum that should be faded."""
        history = self.price_history.get(ticker, [])

        # Need minimum history
        min_history = self.config["min_history_required"]
        if len(history) < min_history + 1:  # +1 for current price
            logger.debug(
                f"[MOMENTUM] {ticker}: Insufficient history "
                f"({len(history)}/{min_history + 1} points)"
            )
            return None

        # Get previous price
        previous_time, previous_price = history[-2]  # Second to last

        # Calculate price change
        price_change = current_price - previous_price
        abs_change = abs(price_change)

        # Log the calculated metrics for this market
        logger.info(
            f"[MOMENTUM] {ticker}: prev_price={previous_price:.0f}¢, "
            f"current_price={current_price:.0f}¢, change={price_change:+.1f}¢ (abs={abs_change:.1f}¢)"
        )

        # Determine opportunity strength (HARD or SOFT) and confidence
        strength = None
        confidence = None

        # Check hard thresholds first
        hard_min = self.config["hard_min_price_change_cents"]
        if abs_change >= hard_min:
            strength = OpportunityStrength.HARD
            hard_large = self.config["hard_large_price_change_cents"]
            if abs_change >= hard_large:
                confidence = ConfidenceLevel.MEDIUM
            else:
                confidence = ConfidenceLevel.LOW
        else:
            # Check soft thresholds
            soft_min = self.config["soft_min_price_change_cents"]
            if abs_change >= soft_min:
                strength = OpportunityStrength.SOFT
                soft_large = self.config["soft_large_price_change_cents"]
                if abs_change >= soft_large:
                    confidence = ConfidenceLevel.MEDIUM
                else:
                    confidence = ConfidenceLevel.LOW
            else:
                logger.info(
                    f"[MOMENTUM] {ticker}: Price change too small "
                    f"({abs_change:.1f}¢ < {soft_min}¢ soft min)"
                )
                return None

        # Determine direction
        direction = "up" if price_change > 0 else "down"

        # For fade: bet against the direction
        # If price went up, we expect it to come down
        # If price went down, we expect it to come up
        fade_direction = "down" if direction == "up" else "up"

        # Estimate edge: assume partial mean reversion
        # Conservative: 30-50% of the move reverts
        estimated_edge_cents = abs_change * 0.4

        # Calculate as percentage
        estimated_edge_percent = (estimated_edge_cents / current_price) * 100 if current_price > 0 else 0

        # Build reasoning
        title = market.get("title", "Unknown Market")
        time_diff = (datetime.now() - previous_time).total_seconds() / 60  # minutes

        reasoning = (
            f"Price moved {direction} by {abs_change:.0f}¢ "
            f"({previous_price:.0f}¢ → {current_price:.0f}¢) "
            f"in {time_diff:.1f} minutes. "
            f"Potential overreaction - fade opportunity ({fade_direction})."
        )

        opportunity = Opportunity(
            opportunity_type=OpportunityType.MOMENTUM_FADE,
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
                "current_price": current_price,
                "previous_price": previous_price,
                "price_change": price_change,
                "abs_change": abs_change,
                "direction": direction,
                "fade_direction": fade_direction,
                "time_diff_minutes": time_diff,
                "price_history": [p for _, p in history],
            },
        )

        return opportunity

    def _try_prewarm_from_candlesticks(self, market: Dict[str, Any], ticker: str) -> None:
        """Pre-warm price history from candlesticks data."""
        if not self.kalshi_client:
            return

        lookback_hours = self.config["lookback_periods"] + 2
        candlesticks = self._fetch_market_candlesticks(
            market, lookback_hours=lookback_hours, period_interval=60
        )

        if not candlesticks:
            return

        # Extract prices with timestamps
        for candle in candlesticks:
            price = candle.get("yes_ask_close")
            timestamp = candle.get("ts")
            if price is not None and timestamp is not None:
                # Convert Unix timestamp to datetime
                from datetime import datetime
                dt = datetime.fromtimestamp(timestamp)
                self.price_history[ticker].append((dt, float(price)))

        if self.price_history[ticker]:
            logger.info(
                f"Pre-warmed Momentum Fade history for {ticker} with {len(self.price_history[ticker])} candlesticks"
            )

    def clear_history(self) -> None:
        """Clear all price history."""
        self.price_history.clear()
        logger.info("Price history cleared")

    def get_history_stats(self) -> Dict[str, Any]:
        """Get statistics about tracked price history."""
        return {
            "markets_tracked": len(self.price_history),
            "total_observations": sum(len(h) for h in self.price_history.values()),
        }


if __name__ == "__main__":
    # Simple test with mock data
    logging.basicConfig(level=logging.INFO)

    import time

    analyzer = MomentumFadeAnalyzer()

    # Simulate multiple polling rounds
    print("=== Round 1 ===")
    markets_r1 = [
        {"ticker": "MOM-1", "title": "Market 1", "yes_price": 50},
        {"ticker": "MOM-2", "title": "Market 2", "yes_price": 30},
    ]
    opps1 = analyzer.analyze(markets_r1)
    print(f"Found {len(opps1)} opportunities (expected: 0 - no history yet)\n")

    time.sleep(0.1)

    print("=== Round 2 ===")
    markets_r2 = [
        {"ticker": "MOM-1", "title": "Market 1", "yes_price": 52},  # Small change
        {"ticker": "MOM-2", "title": "Market 2", "yes_price": 45},  # Large change!
    ]
    opps2 = analyzer.analyze(markets_r2)
    print(f"Found {len(opps2)} opportunities:\n")
    for opp in opps2:
        print(opp)
        print(f"  Additional data: {opp.additional_data}\n")

    print(f"History stats: {analyzer.get_history_stats()}")
