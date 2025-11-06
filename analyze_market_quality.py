#!/usr/bin/env python3
"""
Analyze the REAL state of Kalshi markets for market making viability.
"""

from kalshi_client import KalshiDataClient

def analyze_market_quality():
    """Show the distribution of spreads and liquidity."""
    client = KalshiDataClient.from_env()

    print("Analyzing Kalshi Market Quality...")
    print("=" * 80)

    markets = client.get_all_open_markets(max_markets=200)

    spread_distribution = {
        '0-10¢': [],
        '10-25¢': [],
        '25-50¢': [],
        '50-75¢': [],
        '75-100¢': []
    }

    total_analyzed = 0
    no_liquidity = 0

    for market in markets:
        ticker = market.get('ticker')
        title = market.get('title', 'N/A')
        volume = market.get('volume', 0)

        ob_response = client.get_orderbook(ticker)
        if ob_response.get('error'):
            continue

        orderbook = ob_response.get('orderbook', {})
        yes_bids = orderbook.get('yes', [])
        no_bids = orderbook.get('no', [])

        if not yes_bids or not no_bids:
            no_liquidity += 1
            continue

        total_analyzed += 1

        yes_best = yes_bids[-1][0]
        no_best = no_bids[-1][0]
        spread = 100 - yes_best - no_best

        market_data = {
            'ticker': ticker,
            'title': title[:50],
            'spread': spread,
            'yes': yes_best,
            'no': no_best,
            'volume': volume
        }

        if spread <= 10:
            spread_distribution['0-10¢'].append(market_data)
        elif spread <= 25:
            spread_distribution['10-25¢'].append(market_data)
        elif spread <= 50:
            spread_distribution['25-50¢'].append(market_data)
        elif spread <= 75:
            spread_distribution['50-75¢'].append(market_data)
        else:
            spread_distribution['75-100¢'].append(market_data)

    print(f"Total markets analyzed: {total_analyzed}")
    print(f"Markets with no liquidity (one-sided): {no_liquidity}")
    print()

    print("SPREAD DISTRIBUTION:")
    print("-" * 80)
    for category, markets_list in spread_distribution.items():
        count = len(markets_list)
        percentage = (count / total_analyzed * 100) if total_analyzed > 0 else 0
        print(f"{category:15} {count:4} markets ({percentage:5.1f}%)")

        if count > 0 and count <= 3:
            print("  Examples:")
            for m in markets_list[:3]:
                print(f"    {m['title']}")
                print(f"    Spread: {m['spread']:.0f}¢, Volume: ${m['volume']/100:.2f}")
        print()

    print("=" * 80)
    print("🚨 REALITY CHECK:")
    print()

    tight_count = len(spread_distribution['0-10¢']) + len(spread_distribution['10-25¢'])
    if tight_count == 0:
        print("  ❌ NO liquid markets with tight spreads (<25¢)")
        print("  ❌ Market making on Kalshi is HIGH RISK")
        print()
        print("  Why this matters:")
        print("  - Wide spreads = low liquidity = hard to fill both sides")
        print("  - You WILL get stuck with one-sided positions")
        print("  - You'll be gambling, not market making")
        print()
        print("  The 'profit' you saw (16¢ on 84¢) assumes BOTH sides fill.")
        print("  Reality: You'll likely only fill one side and be exposed to event risk.")
    else:
        print(f"  ✅ Found {tight_count} markets with tight spreads - these are tradeable!")

    print("=" * 80)

if __name__ == "__main__":
    analyze_market_quality()
