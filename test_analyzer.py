#!/usr/bin/env python3
"""
Test script for individual analyzers
"""

import logging
import sys
from analyzers.arbitrage_analyzer import ArbitrageAnalyzer

logging.basicConfig(level=logging.INFO, format='%(message)s')

print("=" * 70)
print("TESTING: ArbitrageAnalyzer")
print("=" * 70)

# Test data with simple arbitrage
mock_markets = [
    {
        "ticker": "ARB-SIMPLE",
        "title": "Market with simple arbitrage",
        "event_ticker": "EVENT-1",
        "orderbook": {
            "yes": [[55, 100]],  # YES bid: 55¢
            "no": [[50, 100]],   # NO bid: 50¢
            # 55 + 50 = 105 > 100 (3¢ profit after costs!)
        },
    },
    {
        "ticker": "ARB-CROSS-1",
        "title": "Market A in event 2",
        "event_ticker": "EVENT-2",
        "yes_price": 30,
    },
    {
        "ticker": "ARB-CROSS-2",
        "title": "Market B in event 2",
        "event_ticker": "EVENT-2",
        "yes_price": 35,
    },
    {
        "ticker": "ARB-CROSS-3",
        "title": "Market C in event 2",
        "event_ticker": "EVENT-2",
        "yes_price": 20,
    },
    # Total for EVENT-2: 30 + 35 + 20 = 85 < 100 (potential 15¢ profit - costs)
]

print("\nTest Data:")
print("-" * 70)
print(f"Market 1: {mock_markets[0]['ticker']} - YES bid: 55¢, NO bid: 50¢")
print(f"  Expected: Simple arbitrage (55+50=105 > 100)")
print(f"\nMarket Group (EVENT-2): 3 markets with prices: 30¢, 35¢, 20¢")
print(f"  Total: 85¢ < 100¢")
print(f"  Expected: Cross-market arbitrage opportunity")

print("\n" + "=" * 70)
print("Running Analyzer...")
print("=" * 70 + "\n")

analyzer = ArbitrageAnalyzer()
opportunities = analyzer.analyze(mock_markets)

print("\n" + "=" * 70)
print(f"RESULTS: Found {len(opportunities)} opportunities")
print("=" * 70 + "\n")

for i, opp in enumerate(opportunities, 1):
    print(f"Opportunity #{i}:")
    print("-" * 70)
    print(f"Type: {opp.opportunity_type}")
    print(f"Confidence: {opp.confidence}")
    print(f"Strength: {opp.strength}")
    print(f"Markets: {', '.join(opp.market_tickers)}")
    print(f"Edge: {opp.estimated_edge_cents:.2f}¢ ({opp.estimated_edge_percent:.2f}%)")
    print(f"Reasoning: {opp.reasoning}")
    print(f"Additional Data: {opp.additional_data}")
    print()

if len(opportunities) == 0:
    print("❌ NO OPPORTUNITIES FOUND - Something may be wrong!")
    sys.exit(1)
else:
    print(f"✅ ArbitrageAnalyzer working correctly! Found {len(opportunities)} opportunities.")
    sys.exit(0)
