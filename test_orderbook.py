#!/usr/bin/env python3
"""Test script to verify orderbook data from KalshiClient"""

import logging
from kalshi_client import KalshiDataClient

logging.basicConfig(level=logging.INFO)

client = KalshiDataClient()

# Get a few markets
print("Fetching markets...")
markets_response = client.get_markets(status="open", limit=5)
markets = markets_response.get("markets", [])

print(f"\nFound {len(markets)} markets\n")

for market in markets:
    ticker = market.get("ticker")
    title = market.get("title", "")

    print(f"\n{'='*80}")
    print(f"Market: {ticker}")
    print(f"Title: {title[:60]}...")
    print(f"Last Price: {market.get('last_price', 'N/A')}¢")
    print(f"Volume: {market.get('volume', 'N/A')}")

    # Get orderbook
    try:
        orderbook = client.get_orderbook(ticker)
        print(f"\nOrderbook structure: {orderbook.keys()}")

        yes_orders = orderbook.get("yes", [])
        no_orders = orderbook.get("no", [])

        print(f"\nYES side: {len(yes_orders)} orders")
        if yes_orders:
            print("  Top 3 YES orders:")
            for i, order in enumerate(yes_orders[:3]):
                print(f"    {i+1}. Price: {order[0]}¢, Quantity: {order[1]}")

        print(f"\nNO side: {len(no_orders)} orders")
        if no_orders:
            print("  Top 3 NO orders:")
            for i, order in enumerate(no_orders[:3]):
                print(f"    {i+1}. Price: {order[0]}¢, Quantity: {order[1]}")

        # Calculate spread if we have both sides
        if yes_orders and no_orders:
            best_yes_bid = yes_orders[0][0]
            best_no_bid = no_orders[0][0]
            spread = 100 - (best_yes_bid + best_no_bid)
            print(f"\nSpread: {spread}¢ (YES: {best_yes_bid}¢ + NO: {best_no_bid}¢ = {best_yes_bid + best_no_bid}¢)")

    except Exception as e:
        print(f"Error fetching orderbook: {e}")

print("\n" + "="*80)
print("Test complete!")
