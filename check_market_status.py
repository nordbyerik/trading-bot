#!/usr/bin/env python3
"""
Check the actual status of these markets - are they really tradeable?
"""

import json
from datetime import datetime
from kalshi_client import KalshiDataClient

client = KalshiDataClient()

print("\n" + "="*80)
print("DETAILED MARKET STATUS CHECK")
print("="*80 + "\n")

# Get markets
markets = client.get_all_open_markets(max_markets=20, status="open")

print(f"Checking {len(markets)} 'open' markets...\n")

for i, market in enumerate(markets[:10]):
    ticker = market.get("ticker")
    
    print(f"\n{'='*80}")
    print(f"Market {i+1}: {ticker}")
    print(f"{'='*80}")
    
    # Get detailed market info
    try:
        details = client.get_market(ticker)
        
        print(f"\nKey Fields:")
        print(f"  Ticker:        {details.get('ticker')}")
        print(f"  Title:         {details.get('title', 'N/A')[:60]}...")
        print(f"  Status:        {details.get('status')}")
        print(f"  Result:        {details.get('result')}")
        print(f"  Volume:        {details.get('volume', 0):,}")
        print(f"  Open Interest: {details.get('open_interest', 0):,}")
        print(f"  Last Price:    {details.get('last_price')}¢")
        
        # Check timestamps
        close_ts = details.get('close_time')
        expiry_ts = details.get('expiration_time')
        
        if close_ts:
            close_dt = datetime.fromisoformat(close_ts.replace('Z', '+00:00'))
            now = datetime.now(close_dt.tzinfo)
            print(f"  Close Time:    {close_dt}")
            print(f"  Time to close: {close_dt - now}")
            
            if close_dt < now:
                print(f"  ⚠️  MARKET ALREADY CLOSED!")
        
        if expiry_ts:
            expiry_dt = datetime.fromisoformat(expiry_ts.replace('Z', '+00:00'))
            print(f"  Expiry Time:   {expiry_dt}")
        
        # Trading details
        print(f"\nTrading Info:")
        print(f"  Can Close Early: {details.get('can_close_early')}")
        print(f"  Open Interest:   {details.get('open_interest', 0)}")
        print(f"  Previous Yes Bid: {details.get('previous_yes_bid')}¢")
        print(f"  Previous Yes Ask: {details.get('previous_yes_ask')}¢")
        print(f"  Previous No Bid:  {details.get('previous_no_bid')}¢")
        print(f"  Previous No Ask:  {details.get('previous_no_ask')}¢")
        
        # Get orderbook
        print(f"\nOrderbook Check:")
        ob_response = client.get_orderbook(ticker)
        ob = ob_response.get("orderbook", {})
        
        yes_orders = ob.get("yes")
        no_orders = ob.get("no")
        
        if yes_orders is None and no_orders is None:
            print(f"  ❌ Orderbook is NULL")
            print(f"  Likely reason: Market closed or no active orders")
        else:
            print(f"  ✓ Has orderbook data!")
            print(f"    YES: {len(yes_orders) if yes_orders else 0} orders")
            print(f"    NO:  {len(no_orders) if no_orders else 0} orders")
        
    except Exception as e:
        print(f"  ERROR: {e}")
    
    if i >= 4:  # Check first 5
        break

print(f"\n{'='*80}\n")
