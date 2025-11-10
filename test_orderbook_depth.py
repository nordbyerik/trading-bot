#!/usr/bin/env python3
"""
Test orderbook with depth parameter and check API directly
"""

import requests
from kalshi_client import KalshiDataClient

client = KalshiDataClient()

# Get a market with open interest
markets = client.get_all_open_markets(max_markets=100, status="open")

# Find one with open interest
target_ticker = None
for m in markets:
    details = client.get_market(m.get("ticker"))
    if details.get("open_interest", 0) > 0:
        target_ticker = details.get("ticker")
        print(f"Testing market: {target_ticker}")
        print(f"  Open Interest: {details.get('open_interest'):,}")
        print(f"  Volume: {details.get('volume'):,}")
        print(f"  Last Price: {details.get('last_price')}¢")
        break

if not target_ticker:
    print("No markets with open interest found!")
    exit(1)

print(f"\n{'='*80}")
print("Testing different orderbook API calls")
print(f"{'='*80}\n")

# Test 1: Regular call
print("Test 1: Regular orderbook call")
print("-" * 80)
url1 = f"https://api.elections.kalshi.com/trade-api/v2/markets/{target_ticker}/orderbook"
r1 = requests.get(url1)
print(f"URL: {url1}")
print(f"Status: {r1.status_code}")
print(f"Response: {r1.text}\n")

# Test 2: With depth parameter
print("Test 2: With depth parameter")
print("-" * 80)
url2 = f"https://api.elections.kalshi.com/trade-api/v2/markets/{target_ticker}/orderbook?depth=10"
r2 = requests.get(url2)
print(f"URL: {url2}")
print(f"Status: {r2.status_code}")
print(f"Response: {r2.text}\n")

# Test 3: Check if there's a trades endpoint
print("Test 3: Recent trades endpoint")
print("-" * 80)
url3 = f"https://api.elections.kalshi.com/trade-api/v2/markets/trades?ticker={target_ticker}&limit=5"
r3 = requests.get(url3)
print(f"URL: {url3}")
print(f"Status: {r3.status_code}")
print(f"Response: {r3.text[:500]}...\n")

# Test 4: Try a completely different market category (not NFL)
print("\nTest 4: Trying non-NFL markets")
print("-" * 80)

# Get markets from different series
all_series = set()
for m in markets[:200]:
    series = m.get("series_ticker")
    if series:
        all_series.add(series)

print(f"Found {len(all_series)} different series")
print(f"Series: {list(all_series)[:10]}")

# Try to find non-NFL markets
for series in all_series:
    if "NFL" not in series:
        print(f"\nTrying series: {series}")
        try:
            series_markets = [m for m in markets if m.get("series_ticker") == series][:3]
            for m in series_markets:
                ticker = m.get("ticker")
                ob = client.get_orderbook(ticker).get("orderbook", {})
                if ob.get("yes") or ob.get("no"):
                    print(f"  ✓ FOUND ORDERBOOK DATA in {ticker}!")
                    print(f"    YES: {ob.get('yes')}")
                    print(f"    NO: {ob.get('no')}")
                    break
        except:
            pass
