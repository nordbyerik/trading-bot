#!/usr/bin/env python3
"""Find markets with active orderbooks."""

import json
from kalshi_client import KalshiDataClient

client = KalshiDataClient()

# Fetch more markets
print("Fetching markets...")
markets = client.get_all_open_markets(max_markets=200, status="open")

print(f"Fetched {len(markets)} total markets\n")

# Filter out multivariate markets
regular_markets = [m for m in markets if not m.get("ticker", "").startswith("KXMV")]
multi_markets = [m for m in markets if m.get("ticker", "").startswith("KXMV")]

print(f"Regular markets: {len(regular_markets)}")
print(f"Multivariate markets: {len(multi_markets)}")

if regular_markets:
    print(f"\nChecking first 5 regular markets for orderbook data...")

    markets_with_orders = []
    for i, market in enumerate(regular_markets[:10]):
        ticker = market.get("ticker")
        volume = market.get("volume", 0)

        try:
            orderbook_response = client.get_orderbook(ticker)
            orderbook = orderbook_response.get("orderbook", {})

            yes_orders = orderbook.get("yes") or []
            no_orders = orderbook.get("no") or []

            has_orders = len(yes_orders) > 0 or len(no_orders) > 0

            print(f"\n{i+1}. {ticker}")
            print(f"   Volume: {volume:,}")
            print(f"   YES orders: {len(yes_orders)}")
            print(f"   NO orders: {len(no_orders)}")

            if has_orders:
                markets_with_orders.append(ticker)
                print(f"   ✓ HAS ORDERBOOK DATA")
                print(f"   Title: {market.get('title', '')[:60]}")
                if yes_orders:
                    print(f"   Best YES bid: {yes_orders[0]}")
                if no_orders:
                    print(f"   Best NO bid: {no_orders[0]}")
            else:
                print(f"   ✗ Empty orderbook")

        except Exception as e:
            print(f"   Error: {e}")

    print(f"\n\nSummary: {len(markets_with_orders)} out of 10 checked have orderbook data")

    if markets_with_orders:
        print(f"\nMarkets with orders: {markets_with_orders}")
else:
    print("\nNo regular markets found!")
