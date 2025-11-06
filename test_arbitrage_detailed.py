#!/usr/bin/env python3
"""
Show detailed analysis of what ArbitrageAnalyzer checks
"""

import logging
from kalshi_client import KalshiDataClient
from analyzers.arbitrage_analyzer import ArbitrageAnalyzer

# Enable detailed logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

print("=" * 80)
print("DETAILED ARBITRAGE ANALYSIS ON REAL MARKETS")
print("=" * 80)

client = KalshiDataClient.from_env()

# Get markets
markets = client.get_all_open_markets(max_markets=30, min_volume=100)
print(f"\n✓ Fetched {len(markets)} markets\n")

# Prepare data
markets_with_data = []
print("Markets being analyzed:")
print("-" * 80)

for i, market in enumerate(markets[:20], 1):
    ticker = market.get('ticker')
    yes_bid = market.get('yes_bid', 0)
    no_bid = market.get('no_bid', 0)

    # Try orderbook first
    try:
        orderbook_response = client.get_orderbook(ticker)
        orderbook = orderbook_response.get('orderbook', {})

        # Get bids from orderbook if available
        if orderbook.get('yes'):
            yes_bid = orderbook['yes'][0][0]
        if orderbook.get('no'):
            no_bid = orderbook['no'][0][0]
    except:
        pass

    # Only include if we have both bids
    if yes_bid > 0 and no_bid > 0:
        # Construct orderbook
        market['orderbook'] = {
            'yes': [[yes_bid, 100]],
            'no': [[no_bid, 100]]
        }
        markets_with_data.append(market)

        total = yes_bid + no_bid
        profit = total - 100 - 2  # minus transaction costs

        status = ""
        if profit >= 2:
            status = "🚨 ARBITRAGE!"
        elif profit >= 0:
            status = "⚡ Small profit"
        elif total >= 98:
            status = "✓ Fair"
        else:
            status = "📉 Wide spread"

        print(f"{i:2d}. YES:{yes_bid:3d}¢ + NO:{no_bid:3d}¢ = {total:3d}¢ (profit:{profit:+3.0f}¢) {status}")
        print(f"    {ticker[:65]}")

print(f"\n{len(markets_with_data)} markets with complete bid data")

# Run analyzer
print("\n" + "=" * 80)
print("Running ArbitrageAnalyzer...")
print("=" * 80 + "\n")

analyzer = ArbitrageAnalyzer()
opportunities = analyzer.analyze(markets_with_data)

print("\n" + "=" * 80)
print(f"FINAL RESULTS: {len(opportunities)} arbitrage opportunities")
print("=" * 80)

if opportunities:
    for opp in opportunities:
        print(f"\n🎯 FOUND: {opp.reasoning}")
else:
    print("\n✓ No arbitrage found - markets are efficiently priced!")
    print("  The analyzer correctly checked all markets and found")
    print("  that YES bid + NO bid never exceeds 100¢ + transaction costs")
