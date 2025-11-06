#!/usr/bin/env python3
"""
Kalshi Market Maker Bot

Provides two-sided liquidity to capture spreads.
Features:
- Inventory management
- Dynamic spread adjustment
- Risk limits
- Profit/loss tracking
- Automatic requoting
"""

import logging
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from kalshi_client import KalshiDataClient

logger = logging.getLogger(__name__)


@dataclass
class Quote:
    """Represents a two-sided market maker quote."""
    ticker: str
    fair_value: float  # In cents
    bid_price: int  # YES buy price in cents
    ask_price: int  # NO buy price in cents (to sell YES at 100-ask_price)
    size: int  # Contracts per side
    bid_order_id: Optional[str] = None
    ask_order_id: Optional[str] = None


@dataclass
class Position:
    """Track position in a market."""
    ticker: str
    yes_contracts: int = 0  # Net YES position
    no_contracts: int = 0   # Net NO position
    avg_yes_cost: float = 0.0  # Average cost per YES contract
    avg_no_cost: float = 0.0   # Average cost per NO contract
    realized_pnl: float = 0.0  # Realized profit/loss

    @property
    def net_position(self) -> int:
        """Net position (YES - NO)."""
        return self.yes_contracts - self.no_contracts

    @property
    def total_pairs(self) -> int:
        """Number of complete pairs (guaranteed profit)."""
        return min(self.yes_contracts, self.no_contracts)

    @property
    def inventory_skew(self) -> float:
        """How skewed is inventory (-1 to +1, 0 = balanced)."""
        total = self.yes_contracts + self.no_contracts
        if total == 0:
            return 0.0
        return (self.yes_contracts - self.no_contracts) / total


class MarketMakerBot:
    """
    Automated market maker for Kalshi.

    Strategy:
    1. Post bids on both YES and NO sides
    2. When both fill, capture the spread
    3. Manage inventory by adjusting quotes
    4. Respect risk limits
    """

    def __init__(
        self,
        client: KalshiDataClient,
        base_spread_cents: float = 10.0,
        quote_size: int = 10,
        max_position: int = 100,
        max_inventory_skew: float = 0.5,
        requote_interval_seconds: int = 60,
    ):
        """
        Initialize market maker bot.

        Args:
            client: Authenticated Kalshi client
            base_spread_cents: Base spread to quote (total, bid to ask)
            quote_size: Contracts to quote on each side
            max_position: Maximum total position (YES + NO contracts)
            max_inventory_skew: Max inventory imbalance (0-1, 0.5 = 50% skew allowed)
            requote_interval_seconds: How often to update quotes
        """
        self.client = client
        self.base_spread_cents = base_spread_cents
        self.quote_size = quote_size
        self.max_position = max_position
        self.max_inventory_skew = max_inventory_skew
        self.requote_interval_seconds = requote_interval_seconds

        # Track positions
        self.positions: Dict[str, Position] = {}

        # Track active quotes
        self.active_quotes: Dict[str, Quote] = {}

        # Performance tracking
        self.total_realized_pnl = 0.0
        self.total_fees_paid = 0.0

        logger.info(
            f"MarketMakerBot initialized: spread={base_spread_cents}¢, "
            f"size={quote_size}, max_pos={max_position}"
        )

    def calculate_fair_value(self, ticker: str) -> Optional[float]:
        """
        Estimate fair value for a market.

        Strategy:
        1. Get orderbook
        2. Take midpoint of best bid/ask on each side
        3. Adjust for inventory skew

        Returns:
            Fair value in cents, or None if can't determine
        """
        try:
            ob_response = self.client.get_orderbook(ticker, use_auth=True)
            ob = ob_response.get('orderbook', {})

            yes_bids = ob.get('yes', [])
            no_bids = ob.get('no', [])

            if not yes_bids or not no_bids:
                logger.warning(f"Incomplete orderbook for {ticker}")
                return None

            # Best bids (highest prices willing to pay)
            yes_best_bid = yes_bids[-1][0]  # Fixed: use -1 for best
            no_best_bid = no_bids[-1][0]

            # Calculate fair value from orderbook
            # YES at Y means event has Y% probability
            # NO at N means event has (100-N)% probability
            # Average these for fair value
            implied_from_yes = yes_best_bid
            implied_from_no = 100 - no_best_bid

            fair_value = (implied_from_yes + implied_from_no) / 2

            # Adjust for inventory skew
            position = self.positions.get(ticker)
            if position and abs(position.inventory_skew) > 0.1:
                # Skew fair value to encourage balanced inventory
                # If long YES, quote lower to sell
                # If long NO, quote higher to buy YES
                skew_adjustment = position.inventory_skew * self.base_spread_cents
                fair_value -= skew_adjustment

                logger.info(
                    f"{ticker}: Fair value {fair_value:.1f}¢ "
                    f"(adjusted {skew_adjustment:+.1f}¢ for inventory skew)"
                )

            return fair_value

        except Exception as e:
            logger.error(f"Failed to calculate fair value for {ticker}: {e}")
            return None

    def generate_quote(self, ticker: str, fair_value: float) -> Quote:
        """
        Generate a two-sided quote.

        Args:
            ticker: Market ticker
            fair_value: Fair value estimate in cents

        Returns:
            Quote object with bid and ask prices
        """
        # Widen spread if inventory is skewed
        position = self.positions.get(ticker)
        spread = self.base_spread_cents

        if position and abs(position.inventory_skew) > 0.3:
            # Widen spread by 50% when inventory gets skewed
            spread *= 1.5
            logger.info(f"{ticker}: Widening spread to {spread:.1f}¢ due to inventory skew")

        half_spread = spread / 2

        # Calculate prices
        # Bid: Buy YES at fair - half_spread
        bid_price = max(1, int(fair_value - half_spread))

        # Ask: To "sell YES" at fair + half_spread, we "buy NO" at (100 - fair - half_spread)
        # Example: Sell YES at 52¢ = Buy NO at 48¢ (because 100 - 52 = 48)
        ask_price_yes = fair_value + half_spread  # Where we want to sell YES
        ask_price_no = max(1, int(100 - ask_price_yes))  # Price to buy NO

        # Ensure bid < ask (in YES terms)
        if bid_price >= (100 - ask_price_no):
            logger.warning(
                f"{ticker}: Invalid spread bid={bid_price}, ask={100-ask_price_no}, "
                f"adjusting..."
            )
            bid_price = int((100 - ask_price_no) - 2)

        quote = Quote(
            ticker=ticker,
            fair_value=fair_value,
            bid_price=bid_price,
            ask_price=ask_price_no,
            size=self.quote_size
        )

        logger.info(
            f"{ticker}: Quote {bid_price}¢ / {100-ask_price_no}¢ "
            f"(spread={spread:.1f}¢, fair={fair_value:.1f}¢)"
        )

        return quote

    def can_quote_market(self, ticker: str) -> bool:
        """
        Check if we should quote this market based on risk limits.

        Args:
            ticker: Market ticker

        Returns:
            True if safe to quote
        """
        position = self.positions.get(ticker)
        if not position:
            return True  # No position yet, safe to start

        total_position = position.yes_contracts + position.no_contracts

        # Check position limit
        if total_position >= self.max_position:
            logger.warning(f"{ticker}: Position limit reached ({total_position})")
            return False

        # Check inventory skew
        if abs(position.inventory_skew) > self.max_inventory_skew:
            logger.warning(
                f"{ticker}: Inventory too skewed ({position.inventory_skew:.2f})"
            )
            return False

        return True

    def place_quote(self, quote: Quote) -> Tuple[Optional[str], Optional[str]]:
        """
        Place a two-sided quote in the market.

        Args:
            quote: Quote to place

        Returns:
            Tuple of (bid_order_id, ask_order_id)
        """
        ticker = quote.ticker

        try:
            # Place bid: Buy YES
            logger.info(f"{ticker}: Placing bid - buy {quote.size} YES at {quote.bid_price}¢")
            bid_response = self.client.create_order(
                ticker=ticker,
                action="buy",
                side="yes",
                count=quote.size,
                type="limit",
                yes_price=quote.bid_price
            )
            bid_order_id = bid_response.get('order', {}).get('order_id')

            # Place ask: Buy NO (which is equivalent to selling YES)
            logger.info(
                f"{ticker}: Placing ask - buy {quote.size} NO at {quote.ask_price}¢ "
                f"(sells YES at {100-quote.ask_price}¢)"
            )
            ask_response = self.client.create_order(
                ticker=ticker,
                action="buy",
                side="no",
                count=quote.size,
                type="limit",
                no_price=quote.ask_price
            )
            ask_order_id = ask_response.get('order', {}).get('order_id')

            logger.info(
                f"{ticker}: Quote placed successfully "
                f"(bid={bid_order_id}, ask={ask_order_id})"
            )

            return bid_order_id, ask_order_id

        except Exception as e:
            logger.error(f"{ticker}: Failed to place quote: {e}")
            return None, None

    def cancel_quote(self, quote: Quote) -> None:
        """
        Cancel an existing quote.

        Args:
            quote: Quote to cancel
        """
        try:
            if quote.bid_order_id:
                self.client.cancel_order(quote.bid_order_id)
                logger.info(f"{quote.ticker}: Cancelled bid order {quote.bid_order_id}")

            if quote.ask_order_id:
                self.client.cancel_order(quote.ask_order_id)
                logger.info(f"{quote.ticker}: Cancelled ask order {quote.ask_order_id}")

        except Exception as e:
            logger.error(f"{quote.ticker}: Failed to cancel quote: {e}")

    def update_position(self, ticker: str) -> None:
        """
        Update position from portfolio data.

        Args:
            ticker: Market ticker
        """
        try:
            # Get current portfolio
            portfolio = self.client.get_portfolio()
            positions_data = portfolio.get('portfolio_positions', [])

            # Find this market's position
            position = None
            for pos_data in positions_data:
                if pos_data.get('ticker') == ticker:
                    position = pos_data
                    break

            if position:
                # Update our position tracking
                if ticker not in self.positions:
                    self.positions[ticker] = Position(ticker=ticker)

                pos = self.positions[ticker]
                # Note: Kalshi API position structure may vary, adjust fields as needed
                pos.yes_contracts = position.get('yes_position', 0)
                pos.no_contracts = position.get('no_position', 0)

                logger.info(
                    f"{ticker}: Position updated - "
                    f"YES: {pos.yes_contracts}, NO: {pos.no_contracts}, "
                    f"pairs: {pos.total_pairs}, skew: {pos.inventory_skew:.2f}"
                )

        except Exception as e:
            logger.error(f"{ticker}: Failed to update position: {e}")

    def quote_market(self, ticker: str) -> bool:
        """
        Quote a single market (main entry point).

        Args:
            ticker: Market ticker to quote

        Returns:
            True if successfully quoted
        """
        # Check risk limits
        if not self.can_quote_market(ticker):
            logger.warning(f"{ticker}: Skipping due to risk limits")
            return False

        # Calculate fair value
        fair_value = self.calculate_fair_value(ticker)
        if fair_value is None:
            logger.warning(f"{ticker}: Could not determine fair value")
            return False

        # Generate quote
        quote = self.generate_quote(ticker, fair_value)

        # Cancel existing quote if any
        if ticker in self.active_quotes:
            old_quote = self.active_quotes[ticker]
            self.cancel_quote(old_quote)

        # Place new quote
        bid_id, ask_id = self.place_quote(quote)

        if bid_id and ask_id:
            quote.bid_order_id = bid_id
            quote.ask_order_id = ask_id
            self.active_quotes[ticker] = quote
            return True

        return False

    def run(self, tickers: List[str], duration_seconds: int = 3600) -> None:
        """
        Run market maker bot for specified duration.

        Args:
            tickers: List of market tickers to make markets in
            duration_seconds: How long to run (default 1 hour)
        """
        logger.info(
            f"Starting market maker bot for {len(tickers)} markets, "
            f"duration={duration_seconds}s"
        )

        start_time = time.time()

        while time.time() - start_time < duration_seconds:
            for ticker in tickers:
                try:
                    # Update position
                    self.update_position(ticker)

                    # Requote market
                    self.quote_market(ticker)

                except Exception as e:
                    logger.error(f"{ticker}: Error in main loop: {e}")

                # Rate limiting
                time.sleep(1)

            # Wait before next requote cycle
            logger.info(
                f"Requote cycle complete, sleeping {self.requote_interval_seconds}s..."
            )
            time.sleep(self.requote_interval_seconds)

        # Cleanup: Cancel all quotes
        logger.info("Shutting down, cancelling all quotes...")
        for quote in self.active_quotes.values():
            self.cancel_quote(quote)

        # Print final stats
        self.print_stats()

    def print_stats(self) -> None:
        """Print performance statistics."""
        print("\n" + "=" * 80)
        print("MARKET MAKER BOT - FINAL STATISTICS")
        print("=" * 80)

        print(f"\nPositions:")
        print("-" * 80)
        for ticker, pos in self.positions.items():
            print(f"{ticker[:50]}:")
            print(f"  YES: {pos.yes_contracts} contracts")
            print(f"  NO: {pos.no_contracts} contracts")
            print(f"  Complete pairs: {pos.total_pairs}")
            print(f"  Inventory skew: {pos.inventory_skew:+.2f}")
            print(f"  Realized P&L: ${pos.realized_pnl:.2f}")

        print(f"\nOverall Performance:")
        print("-" * 80)
        print(f"Total Realized P&L: ${self.total_realized_pnl:.2f}")
        print(f"Total Fees Paid: ${self.total_fees_paid:.2f}")
        print(f"Net P&L: ${self.total_realized_pnl - self.total_fees_paid:.2f}")
        print("=" * 80)


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create authenticated client
    client = KalshiDataClient.from_env()

    # Create market maker bot
    bot = MarketMakerBot(
        client=client,
        base_spread_cents=15.0,  # 15¢ spread
        quote_size=5,  # 5 contracts per side
        max_position=50,  # Max 50 total contracts per market
        max_inventory_skew=0.6,  # Allow 60% skew before stopping
        requote_interval_seconds=120  # Requote every 2 minutes
    )

    # Example: Find markets with wide spreads to make in
    print("Finding markets with wide spreads...")
    markets = client.get_all_open_markets(max_markets=100)

    wide_spread_markets = []
    for m in markets[:20]:
        ticker = m.get('ticker')
        try:
            ob_response = client.get_orderbook(ticker)
            ob = ob_response.get('orderbook', {})

            yes_bids = ob.get('yes')
            no_bids = ob.get('no')

            if yes_bids and no_bids:
                yes_best = yes_bids[-1][0]
                no_best = no_bids[-1][0]
                spread = 100 - (yes_best + no_best)

                if spread >= 30:  # 30¢+ spread
                    wide_spread_markets.append(ticker)
                    print(f"  {ticker[:50]}: {spread:.0f}¢ spread")
        except:
            pass

    if wide_spread_markets:
        print(f"\nFound {len(wide_spread_markets)} markets with wide spreads!")
        print("\nStarting market maker bot...")
        print("(Running for 5 minutes as a demo)")

        # Run for 5 minutes
        bot.run(tickers=wide_spread_markets[:3], duration_seconds=300)
    else:
        print("No wide spread markets found to make.")
