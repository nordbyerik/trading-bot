#!/usr/bin/env python3
"""
Test analyzers with REAL market data from Kalshi API (with volume filter)
"""

import logging
import sys
from kalshi_client import KalshiDataClient
from analyzers.arbitrage_analyzer import ArbitrageAnalyzer

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

print("=" * 80)
print("TESTING ARBITRAGE ANALYZER WITH REAL KALSHI MARKET DATA")
print("=" * 80)

# Create client (with auth if available, otherwise public)
try:
    client = KalshiDataClient.from_env()
    print("\n✓ Using authenticated client")
except:
    client = KalshiDataClient()
    print("\n✓ Using public (non-authenticated) client")

# Fetch real markets with volume
print("\n1. Fetching markets with volume from Kalshi API...")
print("-" * 80)

try:
    # Get more markets and filter by volume
    all_markets = client.get_all_open_markets(max_markets=100, min_volume=1000)

    # Sort by volume
    all_markets.sort(key=lambda m: m.get('volume', 0), reverse=True)

    # Take top 15
    markets = all_markets[:15]

    print(f"✓ Fetched {len(markets)} markets with volume >= $1,000")

    # Show what we got
    if markets:
        print(f"\nTop markets by volume:")
        for i, m in enumerate(markets[:10], 1):
            print(f"  {i}. {m.get('ticker', 'N/A')[:60]}")
            print(f"     Title: {m.get('title', 'N/A')[:70]}...")
            print(f"     Volume: ${m.get('volume', 0):,}")
            print(f"     Yes Price: {m.get('yes_price', 'N/A')}¢")

except Exception as e:
    print(f"✗ Failed to fetch markets: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Fetch orderbook data for each market
print(f"\n2. Fetching orderbook data for {len(markets)} markets...")
print("-" * 80)

markets_with_orderbooks = []
for i, market in enumerate(markets, 1):
    ticker = market.get('ticker')
    try:
        # Get orderbook with auth if available
        try:
            orderbook_response = client.get_orderbook(ticker, use_auth=True)
        except:
            orderbook_response = client.get_orderbook(ticker, use_auth=False)

        orderbook = orderbook_response.get('orderbook', {})
        market['orderbook'] = orderbook
        markets_with_orderbooks.append(market)

        # Show orderbook summary for first few
        if i <= 5:
            yes_bids = orderbook.get('yes', [])
            no_bids = orderbook.get('no', [])
            yes_best = yes_bids[0][0] if yes_bids else None
            no_best = no_bids[0][0] if no_bids else None
            total = (yes_best or 0) + (no_best or 0)
            print(f"  {ticker[:55]}:")
            print(f"    YES bid: {yes_best}¢, NO bid: {no_best}¢, Sum: {total}¢")
            if yes_best and no_best:
                if total > 100:
                    print(f"    ⚡ POTENTIAL ARBITRAGE! {total - 100}¢ gross profit")
                elif total < 98:
                    print(f"    ⚠ Wide spread ({100 - total}¢ gap)")

    except Exception as e:
        logger.debug(f"Failed to get orderbook for {ticker}: {e}")
        continue

print(f"\n✓ Successfully fetched orderbooks for {len(markets_with_orderbooks)} markets")

# Run the analyzer on real data
print("\n3. Running ArbitrageAnalyzer on real market data...")
print("=" * 80 + "\n")

analyzer = ArbitrageAnalyzer()
opportunities = analyzer.analyze(markets_with_orderbooks)

print("\n" + "=" * 80)
print(f"RESULTS: Found {len(opportunities)} opportunities in {len(markets_with_orderbooks)} markets")
print("=" * 80 + "\n")

if len(opportunities) > 0:
    for i, opp in enumerate(opportunities, 1):
        print(f"Opportunity #{i}:")
        print("-" * 80)
        print(f"Type: {opp.opportunity_type}")
        print(f"Confidence: {opp.confidence}")
        print(f"Strength: {opp.strength}")
        print(f"Markets: {', '.join(opp.market_tickers)}")
        print(f"Titles: {opp.market_titles[0][:70]}...")
        print(f"Edge: {opp.estimated_edge_cents:.2f}¢ ({opp.estimated_edge_percent:.2f}%)")
        print(f"Reasoning: {opp.reasoning}")
        print(f"Additional Data: {opp.additional_data}")
        print()
else:
    print("No arbitrage opportunities found in current markets.")
    print("This is expected - true arbitrage is rare in liquid, efficient markets!")

print("\n" + "=" * 80)
print(f"✅ ArbitrageAnalyzer successfully tested with REAL market data")
print(f"   Analyzed {len(markets_with_orderbooks)} real markets with volume")
print(f"   Found {len(opportunities)} opportunities")
print("=" * 80)
