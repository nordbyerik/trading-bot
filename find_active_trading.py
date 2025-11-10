#!/usr/bin/env python3
"""
Find markets with ACTUAL trading activity
"""

from datetime import datetime, timedelta
from kalshi_client import KalshiDataClient

client = KalshiDataClient()

print("\n" + "="*80)
print("FINDING ACTIVELY TRADED MARKETS")
print("="*80 + "\n")

# Strategy 1: Look for markets with open interest > 0
print("Strategy 1: Markets with Open Interest > 0")
print("-" * 80)

markets = client.get_all_open_markets(max_markets=500, status="open")
print(f"Fetched {len(markets)} total markets\n")

active_markets = []
for market in markets:
    ticker = market.get("ticker")
    
    # Get details
    try:
        details = client.get_market(ticker)
        
        open_interest = details.get("open_interest", 0)
        volume = details.get("volume", 0)
        last_price = details.get("last_price", 0)
        
        if open_interest > 0 and last_price > 0:
            active_markets.append({
                "ticker": ticker,
                "title": details.get("title", "")[:50],
                "open_interest": open_interest,
                "volume": volume,
                "last_price": last_price,
                "status": details.get("status"),
            })
            
            if len(active_markets) >= 10:
                break
    except:
        pass

print(f"Found {len(active_markets)} markets with open interest!\n")

for i, m in enumerate(active_markets[:5]):
    print(f"\n{i+1}. {m['ticker']}")
    print(f"   Title: {m['title']}...")
    print(f"   Open Interest: {m['open_interest']:,}")
    print(f"   Volume: {m['volume']:,}")
    print(f"   Last Price: {m['last_price']}¢")
    print(f"   Status: {m['status']}")
    
    # NOW CHECK THE ORDERBOOK
    print(f"   Checking orderbook...")
    try:
        ob_response = client.get_orderbook(m['ticker'])
        ob = ob_response.get("orderbook", {})
        
        yes_orders = ob.get("yes")
        no_orders = ob.get("no")
        
        if yes_orders and no_orders:
            print(f"   ✓ ORDERBOOK HAS DATA!")
            print(f"     YES: {len(yes_orders)} orders, best: {yes_orders[0]}") 
            print(f"     NO:  {len(no_orders)} orders, best: {no_orders[0]}")
        else:
            print(f"   ❌ Orderbook still null (yes={yes_orders}, no={no_orders})")
    except Exception as e:
        print(f"   Error: {e}")

if not active_markets:
    print("\n⚠️  NO MARKETS WITH OPEN INTEREST FOUND")
    print("\nThis suggests Kalshi currently has no active trading.")
    print("Possible reasons:")
    print("  - Markets may only trade during certain hours")
    print("  - No live events happening right now")
    print("  - We're between market cycles")

print("\n" + "="*80)
