#!/usr/bin/env python3
"""Quick script to inspect a single market's data structure."""

import json
from kalshi_client import KalshiDataClient

client = KalshiDataClient()

# Fetch one market
markets = client.get_all_open_markets(max_markets=1, status="open", min_volume=100)

if markets:
    market = markets[0]
    ticker = market.get("ticker")

    print(f"Market ticker: {ticker}")
    print(f"\nMarket data:")
    print(json.dumps(market, indent=2, default=str))

    # Fetch orderbook
    print(f"\n\nFetching orderbook for {ticker}...")
    orderbook_response = client.get_orderbook(ticker)
    print(f"\nOrderbook response:")
    print(json.dumps(orderbook_response, indent=2, default=str))
else:
    print("No markets found!")
