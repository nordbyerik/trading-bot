#!/usr/bin/env python3
"""
Deep dive into orderbook API - let's see EXACTLY what's coming back
"""

import json
import logging
from kalshi_client import KalshiDataClient

logging.basicConfig(level=logging.DEBUG)

client = KalshiDataClient()

print("\n" + "="*80)
print("DEEP ORDERBOOK INVESTIGATION")
print("="*80 + "\n")

# Get a variety of markets
print("Fetching markets...")
markets = client.get_all_open_markets(max_markets=100, status="open")

print(f"Got {len(markets)} markets total\n")

# Try different market types
test_cases = [
    ("High volume markets", lambda m: m.get("volume", 0) > 1000),
    ("Medium volume markets", lambda m: 500 < m.get("volume", 0) <= 1000),
    ("Low volume markets", lambda m: 100 < m.get("volume", 0) <= 500),
    ("Any volume markets", lambda m: m.get("volume", 0) > 0),
]

for test_name, filter_fn in test_cases:
    print(f"\n{'='*80}")
    print(f"Testing: {test_name}")
    print(f"{'='*80}\n")
    
    matching_markets = [m for m in markets if filter_fn(m)][:5]
    
    if not matching_markets:
        print(f"No markets found for {test_name}")
        continue
    
    print(f"Found {len(matching_markets)} markets, testing first 5...\n")
    
    for i, market in enumerate(matching_markets[:5]):
        ticker = market.get("ticker")
        volume = market.get("volume", 0)
        last_price = market.get("last_price")
        
        print(f"\nMarket {i+1}: {ticker}")
        print(f"  Volume: {volume:,}")
        print(f"  Last Price: {last_price}¢")
        
        # Get raw orderbook
        try:
            response = client.get_orderbook(ticker, use_auth=False)
            
            print(f"\n  RAW API RESPONSE:")
            print(f"  " + "-"*76)
            print(json.dumps(response, indent=4))
            print(f"  " + "-"*76)
            
            # Check the structure
            if "orderbook" in response:
                ob = response["orderbook"]
                print(f"\n  Orderbook structure:")
                print(f"    Keys: {ob.keys() if isinstance(ob, dict) else 'NOT A DICT'}")
                
                if isinstance(ob, dict):
                    for key in ob.keys():
                        value = ob[key]
                        print(f"    {key}: {type(value).__name__} = {value}")
            
            # Try with auth
            print(f"\n  Trying with authentication...")
            auth_response = client.get_orderbook(ticker, use_auth=True)
            
            if auth_response != response:
                print(f"  DIFFERENT WITH AUTH!")
                print(json.dumps(auth_response, indent=4))
            else:
                print(f"  Same response with auth")
            
            break  # Found a working one, stop
            
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()

print("\n" + "="*80)
print("Investigation complete!")
print("="*80)
