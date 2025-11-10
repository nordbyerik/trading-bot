#!/usr/bin/env python3
"""
Find the MOST liquid markets - top volume
"""

from kalshi_client import KalshiDataClient

client = KalshiDataClient.from_env()

print("\n" + "="*80)
print("FINDING HIGHEST VOLUME MARKETS")
print("="*80 + "\n")

# Fetch as many as possible
markets = client.get_all_open_markets(max_markets=1000, status="open")

print(f"Fetched {len(markets)} markets\n")
print("Getting details for top markets by volume...")

# Get details for all
market_details = []
for m in markets[:500]:  # Check first 500
    ticker = m.get("ticker")
    try:
        details = client.get_market(ticker)
        volume = details.get("volume", 0)
        open_interest = details.get("open_interest", 0)
        
        if volume > 0 or open_interest > 0:
            market_details.append({
                "ticker": ticker,
                "title": details.get("title", "")[:40],
                "volume": volume,
                "open_interest": open_interest,
                "last_price": details.get("last_price", 0),
            })
    except:
        pass

# Sort by volume
market_details.sort(key=lambda x: x["volume"], reverse=True)

print(f"\nTOP 10 MARKETS BY VOLUME:")
print(f"{'='*80}\n")

for i, m in enumerate(market_details[:10]):
    print(f"{i+1}. Volume: {m['volume']:,} | OI: {m['open_interest']:,} | Price: {m['last_price']}¢")
    print(f"   {m['ticker']}")
    print(f"   {m['title']}...\n")

# Now check orderbooks for these top markets
print(f"\n{'='*80}")
print("CHECKING ORDERBOOKS FOR TOP 5 MARKETS")
print(f"{'='*80}\n")

for i, m in enumerate(market_details[:5]):
    ticker = m['ticker']
    print(f"\n{i+1}. {ticker}")
    print(f"   Volume: {m['volume']:,}, OI: {m['open_interest']:,}")
    
    try:
        # Try with depth parameter
        ob_response = client.get_orderbook(ticker, use_auth=True)
        ob = ob_response.get("orderbook", {})
        
        yes_orders = ob.get("yes")
        no_orders = ob.get("no")
        
        if yes_orders:
            print(f"   ✓✓✓ YES ORDERBOOK: {len(yes_orders)} levels")
            for j, level in enumerate(yes_orders[:3]):
                print(f"       Level {j+1}: {level[0]}¢ x {level[1]} contracts")
        else:
            print(f"   ❌ YES orderbook null")
            
        if no_orders:
            print(f"   ✓✓✓ NO ORDERBOOK: {len(no_orders)} levels")
            for j, level in enumerate(no_orders[:3]):
                print(f"       Level {j+1}: {level[0]}¢ x {level[1]} contracts")
        else:
            print(f"   ❌ NO orderbook null")
            
    except Exception as e:
        print(f"   Error: {e}")

print(f"\n{'='*80}\n")
