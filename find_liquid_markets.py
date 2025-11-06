#!/usr/bin/env python3
"""
Find LIQUID markets suitable for market making.
Avoid the 70-80¢ spread traps!
"""

from kalshi_client import KalshiDataClient

def find_safe_market_making_opportunities():
    """Find markets with tight spreads and good liquidity."""
    client = KalshiDataClient.from_env()

    print("Finding LIQUID markets suitable for market making...")
    print("=" * 80)

    # Get markets with decent volume
    markets = client.get_all_open_markets(max_markets=200)

    good_markets = []

    for market in markets:
        ticker = market.get('ticker')
        title = market.get('title', 'N/A')
        volume = market.get('volume', 0)

        # Skip low volume markets
        if volume < 1000:  # At least $10 in volume
            continue

        # Get orderbook
        ob_response = client.get_orderbook(ticker)
        if ob_response.get('error'):
            continue

        orderbook = ob_response.get('orderbook', {})
        yes_bids = orderbook.get('yes', [])
        no_bids = orderbook.get('no', [])

        if not yes_bids or not no_bids:
            continue

        # Best prices (remember: ascending order, best is last)
        yes_best = yes_bids[-1][0]
        no_best = no_bids[-1][0]
        spread = 100 - yes_best - no_best

        # Look for TIGHTER spreads (5-25¢)
        # These are more liquid and safer for market making
        if 5 <= spread <= 25:
            # Check depth (how many contracts at best price)
            yes_depth = yes_bids[-1][1]
            no_depth = no_bids[-1][1]

            good_markets.append({
                'ticker': ticker,
                'title': title,
                'spread': spread,
                'yes_best': yes_best,
                'no_best': no_best,
                'yes_depth': yes_depth,
                'no_depth': no_depth,
                'volume': volume
            })

    # Sort by spread (tightest first)
    good_markets.sort(key=lambda x: x['spread'])

    print(f"\nFound {len(good_markets)} LIQUID markets with 5-25¢ spreads:\n")

    for i, m in enumerate(good_markets[:10], 1):
        print(f"{i}. {m['ticker']}")
        print(f"   {m['title'][:70]}...")
        print(f"   Spread: {m['spread']:.0f}¢ (YES: {m['yes_best']:.0f}¢ x {m['yes_depth']}, "
              f"NO: {m['no_best']:.0f}¢ x {m['no_depth']})")
        print(f"   Volume: ${m['volume']/100:.2f}")

        # Calculate potential profit with 2¢ spread
        target_spread = 2
        fair = (m['yes_best'] + (100 - m['no_best'])) / 2
        bid = max(1, int(fair - target_spread/2))
        ask_no = max(1, int(100 - fair - target_spread/2))
        profit = 100 - bid - ask_no

        print(f"   If you quote {bid}¢/{100-ask_no}¢ (2¢ spread): "
              f"{profit}¢ profit = {profit/(bid+ask_no)*100:.1f}% return")
        print()

    print("=" * 80)
    print("💡 These markets are MUCH safer because:")
    print("   - Tighter spreads = more liquid = easier to fill both sides")
    print("   - Higher volume = more traders = less adverse selection risk")
    print("   - Lower profit per trade BUT much higher probability of both filling")
    print("=" * 80)

if __name__ == "__main__":
    find_safe_market_making_opportunities()
