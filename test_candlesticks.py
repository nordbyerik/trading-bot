#!/usr/bin/env python3
"""Test candlestick API endpoint"""

import time
from kalshi_client import KalshiDataClient

client = KalshiDataClient()

# Get one market with good volume
markets = client.get_all_open_markets(max_markets=5, status="open", min_volume=100)

if markets:
    market = markets[0]
    ticker = market.get("ticker")
    series_ticker = market.get("series_ticker")
    
    if not series_ticker:
        series_ticker = ticker.split("-")[0]
    
    print(f"Testing market: {ticker}")
    print(f"Series: {series_ticker}")
    print(f"Volume: {market.get('volume')}")
    print(f"Last Price: {market.get('last_price')}¢\n")
    
    # Try different time ranges
    end_ts = int(time.time())
    
    for hours in [24, 72, 168]:  # 1 day, 3 days, 1 week
        start_ts = end_ts - (hours * 3600)
        
        print(f"Trying {hours} hour lookback...")
        try:
            result = client.get_market_candlesticks(
                series_ticker=series_ticker,
                market_ticker=ticker,
                start_ts=start_ts,
                end_ts=end_ts,
                period_interval=60
            )
            
            candles = result.get("candlesticks", [])
            print(f"  Got {len(candles)} candlesticks")
            
            if candles:
                first = candles[0]
                print(f"  First candle keys: {first.keys()}")
                print(f"  Sample: ts={first.get('ts')}, open={first.get('yes_ask_open')}, close={first.get('yes_ask_close')}\n")
                break
        except Exception as e:
            print(f"  Error: {e}\n")
else:
    print("No markets found!")
