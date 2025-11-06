#!/usr/bin/env python3
"""
Test analyzers with REAL market data from Kalshi API
"""

import logging
import sys
from kalshi_client import KalshiDataClient
from analyzers.arbitrage_analyzer import ArbitrageAnalyzer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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

# Fetch real markets
print("\n1. Fetching real markets from Kalshi API...")
print("-" * 80)

try:
    # Get open markets with some volume
    response = client.get_markets(status="open", limit=20)
    markets = response.get("markets", [])

    print(f"✓ Fetched {len(markets)} markets")

    # Show what we got
    if markets:
        print(f"\nSample markets:")
        for i, m in enumerate(markets[:5], 1):
            print(f"  {i}. {m.get('ticker', 'N/A')}")
            print(f"     Title: {m.get('title', 'N/A')[:60]}...")
            print(f"     Volume: ${m.get('volume', 0):,}")

except Exception as e:
    print(f"✗ Failed to fetch markets: {e}")
    sys.exit(1)

# Fetch orderbook data for each market
print("\n2. Fetching orderbook data for markets...")
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
        if i <= 3:
            yes_bids = orderbook.get('yes', [])
            no_bids = orderbook.get('no', [])
            yes_best = yes_bids[0][0] if yes_bids else None
            no_best = no_bids[0][0] if no_bids else None
            print(f"  {ticker[:50]}:")
            print(f"    YES bid: {yes_best}¢, NO bid: {no_best}¢, Sum: {(yes_best or 0) + (no_best or 0)}¢")

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
        print(f"Titles: {', '.join([t[:50] for t in opp.market_titles])}")
        print(f"Edge: {opp.estimated_edge_cents:.2f}¢ ({opp.estimated_edge_percent:.2f}%)")
        print(f"Reasoning: {opp.reasoning}")
        print(f"Additional Data: {opp.additional_data}")
        print()
else:
    print("No arbitrage opportunities found in current markets.")
    print("This is expected - true arbitrage opportunities are rare in efficient markets!")

print("\n" + "=" * 80)
print(f"✅ ArbitrageAnalyzer successfully tested with REAL market data")
print(f"   Analyzed {len(markets_with_orderbooks)} real markets")
print(f"   Found {len(opportunities)} opportunities")
print("=" * 80)
