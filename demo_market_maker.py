#!/usr/bin/env python3
"""
Market Maker Bot Demo (Dry Run)

Shows what the market maker would do WITHOUT placing real orders.
Safe to run - just calculates and displays quotes.
"""

import logging
from kalshi_client import KalshiDataClient

logging.basicConfig(level=logging.INFO, format='%(message)s')

print("=" * 80)
print("MARKET MAKER BOT - DRY RUN DEMO")
print("=" * 80)
print("\nThis demo shows what quotes the bot would place")
print("WITHOUT actually placing real orders.\n")

# Create client
client = KalshiDataClient.from_env()

# Find markets with wide spreads
print("1. Finding markets with wide spreads...")
print("-" * 80)

markets = client.get_all_open_markets(max_markets=100)

candidates = []
for m in markets[:30]:
    ticker = m.get('ticker')
    title = m.get('title', '')

    try:
        ob_response = client.get_orderbook(ticker)
        ob = ob_response.get('orderbook', {})

        yes_bids = ob.get('yes')
        no_bids = ob.get('no')

        if yes_bids and no_bids:
            yes_best = yes_bids[-1][0]
            no_best = no_bids[-1][0]
            total = yes_best + no_best
            spread = 100 - total

            if spread >= 25:  # 25¢+ spread
                candidates.append({
                    'ticker': ticker,
                    'title': title,
                    'yes_bid': yes_best,
                    'no_bid': no_best,
                    'spread': spread
                })
    except:
        continue

# Sort by spread (widest first)
candidates.sort(key=lambda x: x['spread'], reverse=True)

print(f"\nFound {len(candidates)} markets with spreads >= 25¢:\n")

for i, market in enumerate(candidates[:10], 1):
    print(f"{i}. {market['ticker'][:50]}")
    print(f"   Title: {market['title'][:70]}...")
    print(f"   Current: YES bid={market['yes_bid']}¢, NO bid={market['no_bid']}¢")
    print(f"   Spread: {market['spread']:.0f}¢ 💰\n")

if not candidates:
    print("No wide spread markets found!")
    exit(0)

# Pick the widest spread market to demo
target = candidates[0]

print("\n" + "=" * 80)
print(f"2. Market Maker Analysis: {target['ticker']}")
print("=" * 80)

ticker = target['ticker']
yes_bid = target['yes_bid']
no_bid = target['no_bid']
spread = target['spread']

print(f"\nCurrent Market State:")
print(f"  YES best bid: {yes_bid}¢")
print(f"  NO best bid: {no_bid}¢")
print(f"  Spread: {spread:.0f}¢")

# Calculate fair value
implied_from_yes = yes_bid
implied_from_no = 100 - no_bid
fair_value = (implied_from_yes + implied_from_no) / 2

print(f"\nFair Value Calculation:")
print(f"  Implied from YES bid: {implied_from_yes}¢")
print(f"  Implied from NO bid: {implied_from_no}¢")
print(f"  Fair value (midpoint): {fair_value:.1f}¢")

# Market maker quote
mm_spread = 15.0  # 15¢ spread (much tighter than current!)
half_spread = mm_spread / 2

mm_bid = int(fair_value - half_spread)  # Buy YES
mm_ask_no = int(100 - fair_value - half_spread)  # Buy NO (sells YES at fair+half)

print(f"\n" + "=" * 80)
print("3. Market Maker Quote (what bot would place):")
print("=" * 80)

print(f"\nQuote Parameters:")
print(f"  Target spread: {mm_spread}¢")
print(f"  Quote size: 10 contracts per side")

print(f"\nOrders to Place:")
print(f"  1️⃣  BUY {10} YES at {mm_bid}¢")
print(f"      (Limit order: action='buy', side='yes', yes_price={mm_bid})")

print(f"\n  2️⃣  BUY {10} NO at {mm_ask_no}¢")
print(f"      (Limit order: action='buy', side='no', no_price={mm_ask_no})")
print(f"      → This is equivalent to SELLING YES at {100-mm_ask_no}¢")

print(f"\n" + "=" * 80)
print("4. Profit Calculation (if both orders fill):")
print("=" * 80)

cost_yes = mm_bid
cost_no = mm_ask_no
total_cost = cost_yes + cost_no
payout = 100  # One side pays $1
profit = payout - total_cost
profit_pct = (profit / total_cost) * 100

print(f"\nPer Contract Pair:")
print(f"  Cost of YES: {cost_yes}¢")
print(f"  Cost of NO: {cost_no}¢")
print(f"  Total cost: {total_cost}¢")
print(f"  Payout (one pays): {payout}¢")
print(f"  Profit: {profit}¢ ({profit_pct:.1f}% return)")

print(f"\nFor {10} Contracts:")
print(f"  Total cost: ${total_cost * 10 / 100:.2f}")
print(f"  Total profit: ${profit * 10 / 100:.2f}")

# Compare to current market
current_spread_value = spread / 2  # Could capture half the spread
mm_profit_value = profit

print(f"\n" + "=" * 80)
print("5. Comparison:")
print("=" * 80)
print(f"  Current market spread: {spread:.0f}¢")
print(f"  Our tighter spread: {mm_spread:.0f}¢")
print(f"  Profit per pair: {profit:.0f}¢")
print(f"  We improve liquidity by {spread - mm_spread:.0f}¢!")

print(f"\n" + "=" * 80)
print("6. Risk Management:")
print("=" * 80)
print(f"  Max position limit: 50 total contracts")
print(f"  Max inventory skew: 60% (stop if too imbalanced)")
print(f"  Spread widening: Increase spread by 50% if inventory skewed >30%")
print(f"  Requote interval: Every 120 seconds")

print(f"\n" + "=" * 80)
print("DEMO SUMMARY")
print("=" * 80)
print(f"✅ Found {len(candidates)} profitable markets")
print(f"✅ Bot would quote {mm_bid}¢/{100-mm_ask_no}¢ (current: {yes_bid}¢/{100-no_bid}¢)")
print(f"✅ Potential profit: {profit}¢ per pair ({profit_pct:.1f}% return)")
print(f"✅ Improves market liquidity by tightening spread")
print(f"\n💡 To run for real:")
print(f"   python market_maker_bot.py")
print(f"   (Will place actual orders - use with caution!)")
print("=" * 80)
