#!/usr/bin/env python3
"""Test script to verify orderbook data from KalshiClient - with debug output"""

import logging
import json
from kalshi_client import KalshiDataClient

logging.basicConfig(level=logging.INFO)

client = KalshiDataClient()

# Get markets with volume
print("Fetching markets with volume...")
markets = client.get_all_open_markets(max_markets=20, status="open", min_volume=100)

print(f"\nFound {len(markets)} markets with volume >= 100\n")

if not markets:
    print("No markets with volume found. Fetching any markets...")
    markets_response = client.get_markets(status="open", limit=5)
    markets = markets_response.get("markets", [])

for i, market in enumerate(markets[:3]):
    ticker = market.get("ticker")
    title = market.get("title", "")
    volume = market.get("volume", 0)
    last_price = market.get("last_price")

    print(f"\n{'='*80}")
    print(f"Market {i+1}: {ticker}")
    print(f"Title: {title[:60]}...")
    print(f"Last Price: {last_price}¢")
    print(f"Volume: {volume}")

    # Get orderbook
    try:
        orderbook_response = client.get_orderbook(ticker)
        print(f"\n=== RAW ORDERBOOK RESPONSE ===")
        print(json.dumps(orderbook_response, indent=2)[:500] + "...")

        # Try to extract orderbook data
        if "orderbook" in orderbook_response:
            orderbook = orderbook_response["orderbook"]
            print(f"\n=== NESTED ORDERBOOK ===")
            print(f"Keys in nested orderbook: {orderbook.keys()}")

            yes_orders = orderbook.get("yes", [])
            no_orders = orderbook.get("no", [])

            print(f"\nYES side: {len(yes_orders)} orders")
            if yes_orders:
                print("  Top 3 YES orders:")
                for j, order in enumerate(yes_orders[:3]):
                    print(f"    {j+1}. {order}")

            print(f"\nNO side: {len(no_orders)} orders")
            if no_orders:
                print("  Top 3 NO orders:")
                for j, order in enumerate(no_orders[:3]):
                    print(f"    {j+1}. {order}")

    except Exception as e:
        print(f"Error fetching orderbook: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "="*80)
print("Test complete!")
