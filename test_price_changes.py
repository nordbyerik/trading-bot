#!/usr/bin/env python3
"""
Test if market prices actually change over time
"""

import logging
import time
from kalshi_client import KalshiDataClient

logging.basicConfig(level=logging.INFO)

client = KalshiDataClient()

print("Fetching initial market prices...")
markets_initial = client.get_all_open_markets(max_markets=20, status="open", min_volume=100)

# Store initial prices
initial_prices = {}
for m in markets_initial:
    ticker = m.get("ticker")
    price = m.get("last_price")
    volume = m.get("volume")
    initial_prices[ticker] = {"price": price, "volume": volume}

print(f"Tracking {len(markets_initial)} markets...")
print(f"Waiting 30 seconds to check for price changes...\n")

time.sleep(30)

print("Fetching updated market prices...")
markets_updated = client.get_all_open_markets(max_markets=20, status="open", min_volume=100)

# Check for changes
changes_found = 0
for m in markets_updated:
    ticker = m.get("ticker")
    new_price = m.get("last_price")
    new_volume = m.get("volume")
    
    if ticker in initial_prices:
        old_price = initial_prices[ticker]["price"]
        old_volume = initial_prices[ticker]["volume"]
        
        if new_price != old_price or new_volume != old_volume:
            changes_found += 1
            print(f"✓ CHANGE: {ticker[:40]}")
            print(f"  Price: {old_price}¢ → {new_price}¢ (Δ{new_price - old_price if old_price and new_price else 'N/A'})")
            print(f"  Volume: {old_volume} → {new_volume} (Δ{new_volume - old_volume})\n")

print(f"\n{'='*80}")
print(f"Results: {changes_found} markets changed out of {len(initial_prices)} tracked")
print(f"{'='*80}\n")

if changes_found == 0:
    print("⚠️  No price changes detected!")
    print("This means markets are not actively trading right now.")
    print("For backtesting with live data, we need to either:")
    print("  1. Wait for active trading hours")
    print("  2. Use historical candlestick data")
    print("  3. Find more liquid markets")
