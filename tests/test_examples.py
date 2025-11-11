#!/usr/bin/env python3
"""
Examples of using the Kalshi orderbook functionality

This script demonstrates how to properly use the orderbook API with the
KalshiDataClient, including handling empty orderbooks and authentication.
"""

from kalshi_client import KalshiDataClient
import logging

logging.basicConfig(level=logging.INFO)


def example_basic_orderbook():
    """Example 1: Basic orderbook fetching without authentication"""
    print("\n" + "="*80)
    print("Example 1: Basic Orderbook Fetching")
    print("="*80)

    # Create client without authentication
    client = KalshiDataClient()

    # Get a market
    markets = client.get_markets(status="open", limit=1)
    ticker = markets['markets'][0]['ticker']

    # Fetch orderbook
    response = client.get_orderbook(ticker)

    # Extract orderbook data (handles null values automatically)
    orderbook = response.get("orderbook", {})
    yes_orders = orderbook.get("yes", [])
    no_orders = orderbook.get("no", [])

    print(f"\nMarket: {ticker}")
    print(f"YES orders: {len(yes_orders)}")
    print(f"NO orders: {len(no_orders)}")

    # Process orders if they exist
    if yes_orders:
        print("\nTop YES bids:")
        for price, quantity in yes_orders[:3]:
            print(f"  {price}¢ x {quantity} contracts")

    if no_orders:
        print("\nTop NO bids:")
        for price, quantity in no_orders[:3]:
            print(f"  {price}¢ x {quantity} contracts")

    if not yes_orders and not no_orders:
        print("\n⚠️  No active orders in this market")


def example_authenticated_orderbook():
    """Example 2: Orderbook fetching with authentication"""
    print("\n" + "="*80)
    print("Example 2: Authenticated Orderbook Fetching")
    print("="*80)

    try:
        # Create authenticated client from environment variables
        client = KalshiDataClient.from_env()

        # Get a market
        markets = client.get_markets(status="open", limit=1)
        ticker = markets['markets'][0]['ticker']

        # Fetch orderbook with authentication
        response = client.get_orderbook(ticker, use_auth=True)

        orderbook = response.get("orderbook", {})
        yes_orders = orderbook.get("yes", [])
        no_orders = orderbook.get("no", [])

        print(f"\nMarket: {ticker}")
        print(f"YES orders: {len(yes_orders)}")
        print(f"NO orders: {len(no_orders)}")

    except ValueError as e:
        print(f"\n⚠️  Authentication required: {e}")
        print("Set KALSHI_API_KEY_ID and KALSHI_PRIV_KEY environment variables")


def example_orderbook_depth():
    """Example 3: Using the depth parameter"""
    print("\n" + "="*80)
    print("Example 3: Orderbook Depth Parameter")
    print("="*80)

    client = KalshiDataClient()

    markets = client.get_markets(status="open", limit=1)
    ticker = markets['markets'][0]['ticker']

    # Fetch full orderbook
    full_response = client.get_orderbook(ticker, depth=0)
    full_orderbook = full_response.get("orderbook", {})

    # Fetch limited orderbook (top 5 levels)
    limited_response = client.get_orderbook(ticker, depth=5)
    limited_orderbook = limited_response.get("orderbook", {})

    print(f"\nMarket: {ticker}")
    print(f"Full depth - YES: {len(full_orderbook.get('yes', []))}, NO: {len(full_orderbook.get('no', []))}")
    print(f"Top 5 depth - YES: {len(limited_orderbook.get('yes', []))}, NO: {len(limited_orderbook.get('no', []))}")


def example_calculate_spread():
    """Example 4: Calculate bid-ask spread from orderbook"""
    print("\n" + "="*80)
    print("Example 4: Calculate Spread from Orderbook")
    print("="*80)

    client = KalshiDataClient()

    # Get markets and look for one with orders
    markets = client.get_all_open_markets(max_markets=100, status="open")

    for market in markets:
        ticker = market.get('ticker')

        response = client.get_orderbook(ticker)
        orderbook = response.get("orderbook", {})
        yes_orders = orderbook.get("yes", [])
        no_orders = orderbook.get("no", [])

        if yes_orders and no_orders:
            # Calculate spread
            # In Kalshi, a YES bid at X¢ is equivalent to a NO ask at (100-X)¢
            best_yes_bid = yes_orders[0][0]  # Price in cents
            best_no_bid = no_orders[0][0]

            # The spread is the difference between the implied prices
            # YES bid + NO bid should equal 100 in a perfectly efficient market
            spread = 100 - (best_yes_bid + best_no_bid)

            print(f"\nMarket: {ticker}")
            print(f"Title: {market.get('title', '')[:60]}...")
            print(f"Best YES bid: {best_yes_bid}¢")
            print(f"Best NO bid: {best_no_bid}¢")
            print(f"Implied YES ask: {100 - best_no_bid}¢")
            print(f"Implied NO ask: {100 - best_yes_bid}¢")
            print(f"Spread: {spread}¢")

            break
    else:
        print("\n⚠️  No markets with active orderbooks found")
        print("This is normal - many markets may not have active orders")


def example_monitor_orderbook():
    """Example 5: Monitor orderbook for changes"""
    print("\n" + "="*80)
    print("Example 5: Monitor Orderbook (Single Check)")
    print("="*80)

    client = KalshiDataClient(cache_ttl=0)  # Disable caching for monitoring

    markets = client.get_markets(status="open", limit=1)
    ticker = markets['markets'][0]['ticker']

    print(f"\nMonitoring market: {ticker}")

    # In a real application, you would loop this
    response = client.get_orderbook(ticker)
    orderbook = response.get("orderbook", {})
    yes_orders = orderbook.get("yes", [])
    no_orders = orderbook.get("no", [])

    print(f"Snapshot - YES: {len(yes_orders)} orders, NO: {len(no_orders)} orders")

    if yes_orders:
        print(f"  Best YES bid: {yes_orders[0][0]}¢ x {yes_orders[0][1]}")
    if no_orders:
        print(f"  Best NO bid: {no_orders[0][0]}¢ x {no_orders[0][1]}")

    print("\n💡 In a real monitoring application, you would:")
    print("   - Use a loop with sleep intervals")
    print("   - Compare orderbook snapshots to detect changes")
    print("   - Set cache_ttl=0 to always get fresh data")
    print("   - Consider rate limits (default: 20 req/sec)")


def main():
    """Run all examples"""
    print("\n" + "#"*80)
    print("#  Kalshi Orderbook Usage Examples")
    print("#"*80)

    example_basic_orderbook()
    example_authenticated_orderbook()
    example_orderbook_depth()
    example_calculate_spread()
    example_monitor_orderbook()

    print("\n" + "="*80)
    print("Examples complete!")
    print("="*80)


if __name__ == "__main__":
    main()
