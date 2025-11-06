#!/usr/bin/env python3
"""
Test if authentication is required/helpful for orderbook data
"""

import logging
import json
from kalshi_client import KalshiDataClient

logging.basicConfig(level=logging.WARNING)

# Test with authenticated client
print("=" * 80)
print("TESTING ORDERBOOK ACCESS WITH AND WITHOUT AUTHENTICATION")
print("=" * 80)

auth_client = KalshiDataClient.from_env()
public_client = KalshiDataClient()

# Get a market
print("\nFetching a market...")
markets = auth_client.get_all_open_markets(max_markets=10, min_volume=100)

if not markets:
    print("No markets found")
else:
    ticker = markets[0]['ticker']
    print(f"Testing with: {ticker}")
    print(f"Market yes_bid from API: {markets[0].get('yes_bid')}¢")
    print(f"Market no_bid from API: {markets[0].get('no_bid')}¢")

    print("\n" + "-" * 80)
    print("1. ORDERBOOK WITH AUTHENTICATION:")
    print("-" * 80)
    try:
        orderbook_auth = auth_client.get_orderbook(ticker, use_auth=True)
        print(json.dumps(orderbook_auth, indent=2))
    except Exception as e:
        print(f"ERROR: {e}")

    print("\n" + "-" * 80)
    print("2. ORDERBOOK WITHOUT AUTHENTICATION:")
    print("-" * 80)
    try:
        orderbook_public = public_client.get_orderbook(ticker, use_auth=False)
        print(json.dumps(orderbook_public, indent=2))
    except Exception as e:
        print(f"ERROR: {e}")

    print("\n" + "=" * 80)
    print("COMPARISON:")
    print("=" * 80)

    auth_ob = orderbook_auth.get('orderbook', {})
    pub_ob = orderbook_public.get('orderbook', {})

    print(f"Authenticated YES bids: {auth_ob.get('yes')}")
    print(f"Public YES bids: {pub_ob.get('yes')}")
    print(f"\nAuthenticated NO bids: {auth_ob.get('no')}")
    print(f"Public NO bids: {pub_ob.get('no')}")

    if auth_ob == pub_ob:
        print("\n✓ Same data with and without auth")
        if auth_ob.get('yes') is None and auth_ob.get('no') is None:
            print("  → This market has NO ORDERBOOK DATA (empty/inactive)")
    else:
        print("\n⚡ DIFFERENT data with auth!")
