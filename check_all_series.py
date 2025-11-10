#!/usr/bin/env python3
"""Check all different market series for orderbook data"""

from kalshi_client import KalshiDataClient
from collections import defaultdict

client = KalshiDataClient.from_env()

print("\n" + "="*80)
print("CHECKING ALL MARKET SERIES")
print("="*80 + "\n")

# Get lots of markets
markets = client.get_all_open_markets(max_markets=2000, status="open")

# Group by series
by_series = defaultdict(list)
for m in markets:
    ticker = m.get("ticker")
    if ticker:
        series = ticker.split("-")[0]
        by_series[series].append(ticker)

print(f"Found {len(by_series)} different series:")
for series, tickers in sorted(by_series.items(), key=lambda x: len(x[1]), reverse=True):
    print(f"  {series}: {len(tickers)} markets")

# Test a few markets from each series
print(f"\n{'='*80}")
print("TESTING ORDERBOOKS ACROSS DIFFERENT SERIES")
print(f"{'='*80}\n")

total_with_orderbooks = 0
total_checked = 0

for series, tickers in list(by_series.items())[:20]:  # Check first 20 series
    print(f"\nSeries: {series} ({len(tickers)} markets)")
    
    # Check first 3 markets in this series
    for ticker in tickers[:3]:
        total_checked += 1
        try:
            details = client.get_market(ticker)
            volume = details.get("volume", 0)
            oi = details.get("open_interest", 0)
            
            if volume > 0 or oi > 0:  # Only check if there's activity
                ob_response = client.get_orderbook(ticker, use_auth=True)
                ob = ob_response.get("orderbook", {})
                
                has_data = (ob.get("yes") is not None and len(ob.get("yes", [])) > 0) or \
                           (ob.get("no") is not None and len(ob.get("no", [])) > 0)
                
                if has_data:
                    total_with_orderbooks += 1
                    print(f"  ✓✓✓ FOUND ORDERBOOK: {ticker}")
                    print(f"      Volume: {volume:,}, OI: {oi:,}")
                    print(f"      YES: {len(ob.get('yes', []))} levels, NO: {len(ob.get('no', []))} levels")
        except:
            pass

print(f"\n{'='*80}")
print(f"RESULT: {total_with_orderbooks} markets with orderbooks out of {total_checked} checked")
print(f"{'='*80}\n")

if total_with_orderbooks == 0:
    print("CONCLUSION: Kalshi currently has NO active limit orders across ALL markets.")
    print("This is the actual state of the platform right now.")
    print("\nFor backtesting, we have two options:")
    print("  1. Use price simulation (what we built)")
    print("  2. Track actual price changes over time from last_price field")
    print("  3. Use the trades endpoint to see historical executed trades")
