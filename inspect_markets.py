#!/usr/bin/env python3
"""
Inspect actual market data structure
"""

import logging
import json
from kalshi_client import KalshiDataClient

logging.basicConfig(level=logging.WARNING)

client = KalshiDataClient.from_env()

# Get some markets
print("Fetching markets...")
markets = client.get_all_open_markets(max_markets=5, min_volume=1000)

if markets:
    print(f"\n=== MARKET SAMPLE (first market) ===\n")
    print(json.dumps(markets[0], indent=2))

    # Try getting orderbook
    ticker = markets[0]['ticker']
    print(f"\n=== ORDERBOOK for {ticker} ===\n")
    orderbook_response = client.get_orderbook(ticker, use_auth=True)
    print(json.dumps(orderbook_response, indent=2))
