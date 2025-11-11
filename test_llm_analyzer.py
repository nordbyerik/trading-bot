#!/usr/bin/env python3
"""
Test script for LLM Reasoning Analyzer

Tests the LLM analyzer with real Kalshi markets to see Claude's analysis.
"""

import os
import logging
from kalshi_client import KalshiDataClient
from analyzers.llm_reasoning_analyzer import LLMReasoningAnalyzer

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def main():
    """Test the LLM reasoning analyzer."""
    print("=" * 80)
    print("LLM REASONING ANALYZER TEST")
    print("=" * 80)
    print()

    # Check for API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ERROR: ANTHROPIC_API_KEY environment variable not set")
        print()
        print("To use the LLM analyzer, you need a Claude API key:")
        print("1. Get a key from: https://console.anthropic.com/")
        print("2. Export it: export ANTHROPIC_API_KEY='your-key-here'")
        print()
        return

    print("✅ ANTHROPIC_API_KEY found")
    print()

    # Initialize client
    print("Initializing Kalshi client...")
    client = KalshiDataClient()

    # Initialize analyzer with config
    analyzer_config = {
        "max_markets_per_cycle": 3,  # Analyze up to 3 markets
        "model": "claude-3-5-haiku-20241022",  # Use Haiku for cost
        "min_market_value": 10,  # Min volume threshold
        "priority_types": [
            "legislation",
            "politics",
            "sports_rules",
            "weather",
            "celebrity",
        ]
    }

    print("Initializing LLM Reasoning Analyzer...")
    analyzer = LLMReasoningAnalyzer(config=analyzer_config, kalshi_client=client)
    print()

    # Fetch markets
    print("Fetching open markets...")
    markets = client.get_all_open_markets(max_markets=20, status="open", min_volume=10)
    print(f"Fetched {len(markets)} markets")
    print()

    # Enrich with orderbooks (needed by some logic)
    print("Enriching markets with orderbooks...")
    enriched_markets = []
    for market in markets[:20]:  # Limit to 20 to avoid too many API calls
        ticker = market.get("ticker")
        try:
            orderbook_response = client.get_orderbook(ticker)
            market["orderbook"] = orderbook_response.get("orderbook", {})
            enriched_markets.append(market)
        except Exception as e:
            logger.debug(f"Failed to fetch orderbook for {ticker}: {e}")

    print(f"Enriched {len(enriched_markets)} markets")
    print()

    # Show some market samples
    print("Sample markets to analyze:")
    print("-" * 80)
    for i, market in enumerate(enriched_markets[:5]):
        title = market.get("title", "No title")
        ticker = market.get("ticker", "")
        price = market.get("last_price", 0)
        volume = market.get("volume", 0)
        print(f"{i+1}. [{ticker}] {title}")
        print(f"   Price: {price}¢, Volume: {volume}")
    print("-" * 80)
    print()

    # Run analyzer
    print("Running LLM analyzer (this will make API calls to Claude)...")
    print()

    opportunities = analyzer.analyze(enriched_markets)

    print()
    print("=" * 80)
    print(f"RESULTS: Found {len(opportunities)} opportunities")
    print("=" * 80)
    print()

    if not opportunities:
        print("No opportunities found. This could mean:")
        print("- Markets don't have significant mispricing according to Claude")
        print("- Markets don't meet the criteria for analysis")
        print("- Claude couldn't identify edge in the current markets")
        print()
    else:
        for i, opp in enumerate(opportunities):
            print(f"Opportunity {i+1}:")
            print(f"  Market: {opp.market_titles[0]}")
            print(f"  Ticker: {opp.market_tickers[0]}")
            print(f"  Confidence: {opp.confidence.value}")
            print(f"  Strength: {opp.strength.value}")
            print(f"  Current Price: {opp.current_prices[opp.market_tickers[0]]}¢")
            print(f"  Edge: {opp.estimated_edge_cents:.1f}¢ ({opp.estimated_edge_percent:.1f}%)")
            print(f"  Suggested Side: {opp.additional_data.get('llm_suggested_side', 'N/A')}")
            print(f"  LLM Fair Value: {opp.additional_data.get('llm_fair_value', 'N/A')}¢")
            print(f"  Market Type: {opp.additional_data.get('market_type', 'N/A')}")
            print(f"  Reasoning:")
            for line in opp.reasoning.split('\n'):
                if line.strip():
                    print(f"    {line}")
            print()

    # Print cost summary
    print("=" * 80)
    print("API USAGE SUMMARY")
    print("=" * 80)
    print(f"Total API calls: {analyzer.total_api_calls}")
    print(f"Input tokens: {analyzer.total_input_tokens}")
    print(f"Output tokens: {analyzer.total_output_tokens}")

    if analyzer.total_api_calls > 0:
        # Claude Haiku pricing: $0.25 per M input tokens, $1.25 per M output tokens
        input_cost = (analyzer.total_input_tokens / 1_000_000) * 0.25
        output_cost = (analyzer.total_output_tokens / 1_000_000) * 1.25
        total_cost = input_cost + output_cost
        print(f"Estimated cost: ${total_cost:.4f}")
        print(f"  Input: ${input_cost:.4f}")
        print(f"  Output: ${output_cost:.4f}")
    print()


if __name__ == "__main__":
    main()
