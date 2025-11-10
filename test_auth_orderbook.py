#!/usr/bin/env python3
"""Test orderbook fetching with authentication"""

import logging
from kalshi_client import KalshiDataClient

logging.basicConfig(level=logging.INFO)

# Create client with authentication
client = KalshiDataClient.from_env()

print("Fetching markets with volume...")
markets = client.get_all_open_markets(max_markets=10, status="open", min_volume=100)
print(f"Found {len(markets)} markets\n")

found_orderbooks = 0
for i, market in enumerate(markets[:5]):
    ticker = market.get("ticker")
    title = market.get("title", "")
    volume = market.get("volume", 0)

    print(f"\n{'='*80}")
    print(f"Market {i+1}: {ticker}")
    print(f"Title: {title[:50]}...")
    print(f"Volume: {volume}")

    # Try WITHOUT auth first
    try:
        orderbook_response = client.get_orderbook(ticker, use_auth=False)
        orderbook = orderbook_response.get("orderbook", {})
        yes_orders = orderbook.get("yes")
        no_orders = orderbook.get("no")

        if yes_orders and no_orders:
            found_orderbooks += 1
            print(f"✓ Orderbook (NO AUTH): YES={len(yes_orders)} orders, NO={len(no_orders)} orders")
            if yes_orders:
                print(f"  Best YES: {yes_orders[0][0]}¢ x {yes_orders[0][1]}")
            if no_orders:
                print(f"  Best NO: {no_orders[0][0]}¢ x {no_orders[0][1]}")
        else:
            print(f"✗ Orderbook (NO AUTH): Empty (yes={yes_orders}, no={no_orders})")
    except Exception as e:
        print(f"✗ Error (NO AUTH): {e}")

    # Try WITH auth
    try:
        orderbook_response = client.get_orderbook(ticker, use_auth=True)
        orderbook = orderbook_response.get("orderbook", {})
        yes_orders = orderbook.get("yes")
        no_orders = orderbook.get("no")

        if yes_orders and no_orders:
            found_orderbooks += 1
            print(f"✓ Orderbook (WITH AUTH): YES={len(yes_orders)} orders, NO={len(no_orders)} orders")
            if yes_orders:
                print(f"  Best YES: {yes_orders[0][0]}¢ x {yes_orders[0][1]}")
            if no_orders:
                print(f"  Best NO: {no_orders[0][0]}¢ x {no_orders[0][1]}")
        else:
            print(f"✗ Orderbook (WITH AUTH): Empty (yes={yes_orders}, no={no_orders})")
    except Exception as e:
        print(f"✗ Error (WITH AUTH): {e}")

print(f"\n{'='*80}")
print(f"Found {found_orderbooks} orderbooks with data out of {min(5, len(markets))} markets checked")
