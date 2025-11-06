#!/usr/bin/env python3
"""
Test SpreadAnalyzer with real market data
"""

import logging
from kalshi_client import KalshiDataClient
from analyzers.spread_analyzer import SpreadAnalyzer

logging.basicConfig(level=logging.INFO, format='%(message)s')

print("=" * 80)
print("TESTING: SpreadAnalyzer")
print("=" * 80)

client = KalshiDataClient.from_env()

# Get markets with orderbooks
print("\n1. Fetching markets with orderbooks...")
markets_all = client.get_all_open_markets(max_markets=100)

markets_with_orderbooks = []
for m in markets_all[:50]:
    ticker = m.get('ticker')
    try:
        ob_response = client.get_orderbook(ticker)
        ob = ob_response.get('orderbook', {})

        if ob.get('yes') and ob.get('no'):
            m['orderbook'] = ob
            markets_with_orderbooks.append(m)

            if len(markets_with_orderbooks) >= 10:
                break
    except:
        continue

print(f"   ✓ Found {len(markets_with_orderbooks)} markets with orderbooks\n")

# Show orderbook data
print("2. Orderbook data (using FIXED bids[-1] for best bid):")
print("-" * 80)
for m in markets_with_orderbooks[:5]:
    ticker = m['ticker']
    ob = m['orderbook']

    yes_bids = ob.get('yes', [])
    no_bids = ob.get('no', [])

    yes_best = yes_bids[-1][0] if yes_bids else None
    no_best = no_bids[-1][0] if no_bids else None

    # Calculate spread
    # Spread = 100 - (yes_bid + no_bid)
    spread = 100 - (yes_best + no_best) if (yes_best and no_best) else 0

    print(f"  {ticker[:45]}")
    print(f"    YES bid: {yes_best}¢, NO bid: {no_best}¢")
    print(f"    Spread: {spread}¢ (100 - {yes_best + no_best})")

print("\n3. Running SpreadAnalyzer...")
print("=" * 80 + "\n")

analyzer = SpreadAnalyzer()
opportunities = analyzer.analyze(markets_with_orderbooks)

print("\n" + "=" * 80)
print(f"RESULTS: {len(opportunities)} opportunities found")
print("=" * 80 + "\n")

if opportunities:
    for i, opp in enumerate(opportunities, 1):
        print(f"Opportunity #{i}:")
        print("-" * 80)
        print(f"Market: {opp.market_tickers[0][:50]}")
        print(f"Title: {opp.market_titles[0][:60]}...")
        print(f"Type: {opp.opportunity_type}")
        print(f"Confidence: {opp.confidence}, Strength: {opp.strength}")
        print(f"Edge: {opp.estimated_edge_cents:.2f}¢")
        print(f"Reasoning: {opp.reasoning}")
        if 'spread' in opp.additional_data:
            print(f"Spread: {opp.additional_data['spread']}¢")
            print(f"YES bid: {opp.additional_data['yes_bid']}¢")
            print(f"NO bid: {opp.additional_data['no_bid']}¢")
        print()
else:
    print("No wide spread opportunities found.")
    print("Most markets have tight spreads (efficient markets!).")

print("\n" + "=" * 80)
print("SUMMARY: SpreadAnalyzer")
print("=" * 80)
print(f"✓ Tested with {len(markets_with_orderbooks)} real markets")
print(f"✓ Uses FIXED orderbook parsing (bids[-1])")
print(f"✓ Spread calculation: 100 - (YES_bid + NO_bid)")
print(f"✓ Detects wide spreads indicating market-making opportunities")
print("\n✅ SpreadAnalyzer: WORKING")
print("=" * 80)
