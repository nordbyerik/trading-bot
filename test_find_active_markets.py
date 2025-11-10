#!/usr/bin/env python3
"""Find markets with active orderbooks"""

import logging
from kalshi_client import KalshiDataClient

logging.basicConfig(level=logging.WARNING)

client = KalshiDataClient()

# Try different strategies to find active markets
print("Strategy 1: Markets with high volume...")
markets = client.get_all_open_markets(max_markets=50, status="open", min_volume=1000)
print(f"Found {len(markets)} markets with volume >= 1000")

markets_with_orderbooks = 0
for market in markets[:10]:
    ticker = market.get("ticker")
    try:
        orderbook_response = client.get_orderbook(ticker)
        orderbook = orderbook_response.get("orderbook", {})

        yes_orders = orderbook.get("yes")
        no_orders = orderbook.get("no")

        if yes_orders and no_orders:
            markets_with_orderbooks += 1
            print(f"\n✓ Found market with orderbook: {ticker}")
            print(f"  Title: {market.get('title', '')[:50]}...")
            print(f"  Volume: {market.get('volume', 0)}")
            print(f"  YES orders: {len(yes_orders)}, NO orders: {len(no_orders)}")
            if yes_orders:
                print(f"  Best YES: {yes_orders[0][0]}¢ x {yes_orders[0][1]}")
            if no_orders:
                print(f"  Best NO: {no_orders[0][0]}¢ x {no_orders[0][1]}")
    except Exception as e:
        continue

print(f"\n{'='*80}")
print(f"Result: Found {markets_with_orderbooks} markets with active orderbooks out of {len(markets[:10])} checked")

# Try looking at all open markets without volume filter
print(f"\n{'='*80}")
print("Strategy 2: Any open markets (no volume filter)...")
markets2 = client.get_all_open_markets(max_markets=100, status="open")
print(f"Found {len(markets2)} total open markets")

# Sample a few from different positions
sample_indices = [0, len(markets2)//4, len(markets2)//2, 3*len(markets2)//4, len(markets2)-1]
sample_indices = [i for i in sample_indices if i < len(markets2)]

markets_with_orderbooks2 = 0
for i in sample_indices:
    if i >= len(markets2):
        continue
    market = markets2[i]
    ticker = market.get("ticker")
    try:
        orderbook_response = client.get_orderbook(ticker)
        orderbook = orderbook_response.get("orderbook", {})

        yes_orders = orderbook.get("yes")
        no_orders = orderbook.get("no")

        if yes_orders and no_orders:
            markets_with_orderbooks2 += 1
            print(f"\n✓ Market {i}: {ticker}")
            print(f"  Volume: {market.get('volume', 0)}, Last price: {market.get('last_price')}¢")
            print(f"  YES orders: {len(yes_orders)}, NO orders: {len(no_orders)}")
    except Exception as e:
        print(f"\n✗ Market {i}: {ticker} - Error: {e}")

print(f"\n{'='*80}")
print(f"Result: Found {markets_with_orderbooks2} markets with active orderbooks out of {len(sample_indices)} checked")

if markets_with_orderbooks == 0 and markets_with_orderbooks2 == 0:
    print("\n⚠️  WARNING: No markets found with active orderbooks!")
    print("This could mean:")
    print("  1. Orderbooks may require authentication")
    print("  2. The markets currently have no active orders")
    print("  3. The API might be returning different data structure")
