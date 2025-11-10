#!/usr/bin/env python3
"""
Test orderbook with authentication - detailed debugging
"""

import os
import json
import logging
from kalshi_client import KalshiDataClient

# Enable detailed logging
logging.basicConfig(level=logging.DEBUG)

print("\n" + "="*80)
print("TESTING AUTHENTICATED ORDERBOOK REQUESTS")
print("="*80 + "\n")

# Check we have credentials
api_key = os.environ.get('KALSHI_API_KEY_ID')
priv_key = os.environ.get('KALSHI_PRIV_KEY')

print(f"API Key ID: {api_key[:20]}..." if api_key else "❌ No API key")
print(f"Private Key: {'✓ Present' if priv_key else '❌ Missing'}\n")

# Create authenticated client
try:
    client = KalshiDataClient.from_env()
    print("✓ Client created with authentication\n")
except Exception as e:
    print(f"❌ Failed to create client: {e}\n")
    exit(1)

# Get a market with open interest
print("Finding market with open interest...")
markets = client.get_all_open_markets(max_markets=50, status="open")

target_market = None
for m in markets:
    ticker = m.get("ticker")
    try:
        details = client.get_market(ticker)
        if details.get("open_interest", 0) > 0:
            target_market = details
            break
    except:
        pass

if not target_market:
    print("No markets with open interest found!")
    exit(1)

ticker = target_market.get("ticker")
print(f"\nTarget Market: {ticker}")
print(f"  Open Interest: {target_market.get('open_interest'):,}")
print(f"  Volume: {target_market.get('volume'):,}")
print(f"  Last Price: {target_market.get('last_price')}¢")

print(f"\n{'='*80}")
print("MAKING AUTHENTICATED ORDERBOOK REQUEST")
print(f"{'='*80}\n")

# Clear cache to ensure fresh request
client.clear_cache()

# Make authenticated request with debug logging
try:
    print("Calling get_orderbook with use_auth=True...")
    response = client.get_orderbook(ticker, use_auth=True)
    
    print(f"\n✓ Response received:")
    print(json.dumps(response, indent=2))
    
    # Check orderbook
    ob = response.get("orderbook", {})
    yes_orders = ob.get("yes")
    no_orders = ob.get("no")
    
    print(f"\nOrderbook Analysis:")
    print(f"  YES orders: {yes_orders}")
    print(f"  NO orders: {no_orders}")
    
    if yes_orders is not None and len(yes_orders) > 0:
        print(f"\n✓✓✓ SUCCESS! Found orderbook data!")
        print(f"  YES side has {len(yes_orders)} levels")
        print(f"  Best YES bid: {yes_orders[0][0]}¢ x {yes_orders[0][1]} contracts")
    elif no_orders is not None and len(no_orders) > 0:
        print(f"\n✓✓✓ SUCCESS! Found orderbook data!")
        print(f"  NO side has {len(no_orders)} levels")
        print(f"  Best NO bid: {no_orders[0][0]}¢ x {no_orders[0][1]} contracts")
    else:
        print(f"\n❌ Orderbook is still null despite authentication")
        print(f"  This means the market truly has no resting limit orders")
        
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()

print(f"\n{'='*80}\n")
