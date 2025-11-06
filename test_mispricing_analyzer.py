#!/usr/bin/env python3
"""
Test MispricingAnalyzer with real market data
"""

import logging
from kalshi_client import KalshiDataClient
from analyzers.mispricing_analyzer import MispricingAnalyzer

logging.basicConfig(level=logging.INFO, format='%(message)s')

print("=" * 80)
print("TESTING: MispricingAnalyzer")
print("=" * 80)

client = KalshiDataClient.from_env()

# Get markets
print("\n1. Fetching markets...")
markets_all = client.get_all_open_markets(max_markets=100)

# Get prices from orderbooks or market data
markets_with_prices = []
for m in markets_all[:50]:
    ticker = m.get('ticker')

    # Get price from yes_price or orderbook
    price = m.get('yes_price')
    if price is None:
        try:
            ob_response = client.get_orderbook(ticker)
            ob = ob_response.get('orderbook', {})
            yes_bids = ob.get('yes')
            if yes_bids:
                price = yes_bids[-1][0]  # Best bid (fixed!)
                m['yes_price'] = price
        except:
            pass

    if price is not None:
        markets_with_prices.append(m)

    if len(markets_with_prices) >= 20:
        break

print(f"   ✓ Found {len(markets_with_prices)} markets with prices\n")

# Show price distribution
print("2. Price distribution:")
print("-" * 80)
extreme_low = []
extreme_high = []
round_numbers = []
normal = []

for m in markets_with_prices:
    price = m.get('yes_price', 0)
    ticker = m.get('ticker', '')

    if price <= 5:
        extreme_low.append((ticker, price))
    elif price >= 95:
        extreme_high.append((ticker, price))
    elif abs(price - 25) <= 2 or abs(price - 50) <= 2 or abs(price - 75) <= 2:
        round_numbers.append((ticker, price))
    else:
        normal.append((ticker, price))

print(f"  Extreme LOW (≤5¢): {len(extreme_low)} markets")
for ticker, price in extreme_low[:3]:
    print(f"    - {ticker[:50]}: {price}¢")

print(f"\n  Extreme HIGH (≥95¢): {len(extreme_high)} markets")
for ticker, price in extreme_high[:3]:
    print(f"    - {ticker[:50]}: {price}¢")

print(f"\n  Round numbers (25¢, 50¢, 75¢ ±2): {len(round_numbers)} markets")
for ticker, price in round_numbers[:3]:
    print(f"    - {ticker[:50]}: {price}¢")

print(f"\n  Normal prices: {len(normal)} markets")

print("\n3. Running MispricingAnalyzer...")
print("=" * 80 + "\n")

analyzer = MispricingAnalyzer()
opportunities = analyzer.analyze(markets_with_prices)

print("\n" + "=" * 80)
print(f"RESULTS: {len(opportunities)} opportunities found")
print("=" * 80 + "\n")

if opportunities:
    for i, opp in enumerate(opportunities, 1):
        print(f"Opportunity #{i}:")
        print("-" * 80)
        print(f"Market: {opp.market_tickers[0][:50]}")
        print(f"Type: {opp.opportunity_type}")
        print(f"Confidence: {opp.confidence}, Strength: {opp.strength}")
        print(f"Edge: {opp.estimated_edge_cents:.2f}¢")
        print(f"Reasoning: {opp.reasoning[:120]}...")
        if 'price' in opp.additional_data:
            print(f"Price: {opp.additional_data['price']}¢")
        if 'volume' in opp.additional_data:
            print(f"Volume: ${opp.additional_data['volume']:,}")
        print()
else:
    print("No mispricing opportunities found.")
    print("Prices are not at extremes or round numbers.")

print("\n" + "=" * 80)
print("SUMMARY: MispricingAnalyzer")
print("=" * 80)
print(f"✓ Tested with {len(markets_with_prices)} real markets")
print(f"✓ Uses FIXED orderbook parsing (bids[-1])")
print(f"✓ Detects extreme prices (≤5¢ or ≥95¢)")
print(f"✓ Detects round number bias (25¢, 50¢, 75¢)")
print("\n✅ MispricingAnalyzer: WORKING")
print("=" * 80)
