# Kalshi Market Maker Bot Guide

## Overview

The Market Maker Bot provides two-sided liquidity on Kalshi markets to capture bid-ask spreads. It's designed to be profitable on illiquid markets with wide spreads.

## How It Works

### The Core Strategy

On Kalshi, you can't directly "sell" contracts you don't own. Instead, market making works through the mathematical relationship:

**YES + NO = $1.00 (100¢)**

This means:
- **Buying YES at 30¢** is equivalent to **selling NO at 70¢**
- **Buying NO at 70¢** is equivalent to **selling YES at 30¢**

### Market Making Mechanics

To quote a market with fair value 40¢ and 10¢ spread:

```python
# Quote: 35¢ bid / 45¢ ask (10¢ spread)

# Order 1: BUY YES at 35¢ (the bid)
create_order(action="buy", side="yes", yes_price=35)

# Order 2: BUY NO at 55¢ (equivalent to selling YES at 45¢)
create_order(action="buy", side="no", no_price=55)

# If both fill:
# - Cost: 35¢ + 55¢ = 90¢
# - Payout: 100¢ (one contract pays $1)
# - Profit: 10¢ per pair (11.1% return)
```

## Real Example from Demo

**Market:** KXMVENFLMULTIGAMEEXTENDED-S2025...
**Current Spread:** 76¢ (YES bid: 1¢, NO bid: 23¢)

**Bot's Quote:** 31¢ / 47¢ (15¢ spread)
- Order 1: Buy 10 YES at 31¢
- Order 2: Buy 10 NO at 53¢ (sells YES at 47¢)

**If both fill:**
- Cost: 31¢ + 53¢ = 84¢
- Payout: 100¢
- **Profit: 16¢ per pair (19% return!)**

**For 10 contracts:** $1.60 profit on $8.40 invested

## Key Features

### 1. Inventory Management
```python
# Track positions
Position(
    yes_contracts=15,
    no_contracts=10,
    total_pairs=10,        # Min(YES, NO) = guaranteed profit
    inventory_skew=0.20    # (15-10)/(15+10) = 20% long YES
)
```

### 2. Dynamic Spread Adjustment
- **Base spread:** 15¢ (configurable)
- **Inventory skewed > 30%:** Widen spread by 50%
- **Example:** If long YES, quote lower to encourage selling

### 3. Risk Limits
- **Max position:** 50 total contracts per market
- **Max skew:** 60% (stop quoting if too imbalanced)
- **Auto-cancel:** Cancels all quotes on shutdown

### 4. Fair Value Estimation
```python
# From orderbook
yes_best_bid = 48¢  # Implies 48% probability
no_best_bid = 50¢   # Implies 50% probability (100 - 50)

# Fair value = average
fair_value = (48 + 50) / 2 = 49¢

# Adjust for inventory skew
if inventory_skew > 0.1:
    fair_value -= skew * spread
```

## Configuration

```python
bot = MarketMakerBot(
    client=client,
    base_spread_cents=15.0,        # 15¢ total spread
    quote_size=10,                 # 10 contracts per side
    max_position=50,               # Max 50 total contracts
    max_inventory_skew=0.6,        # 60% max imbalance
    requote_interval_seconds=120   # Requote every 2 min
)
```

### Parameter Guide

**base_spread_cents:**
- Wider = more profit per trade, but fewer fills
- Narrower = more fills, but less profit per trade
- Recommended: 10-20¢ for illiquid markets

**quote_size:**
- Smaller = less risk, more frequent trading
- Larger = more profit per fill, more capital needed
- Recommended: 5-20 contracts

**max_position:**
- Limits total exposure per market
- Recommended: 50-100 contracts

**max_inventory_skew:**
- Stop quoting if inventory gets too imbalanced
- Prevents runaway long/short exposure
- Recommended: 0.5-0.7 (50-70%)

## Usage

### Dry Run (Safe - No Real Orders)

```bash
python demo_market_maker.py
```

This shows what the bot WOULD do without placing orders.

### Live Trading (Places Real Orders!)

```python
from kalshi_client import KalshiDataClient
from market_maker_bot import MarketMakerBot

# Create client
client = KalshiDataClient.from_env()

# Create bot
bot = MarketMakerBot(
    client=client,
    base_spread_cents=15.0,
    quote_size=5
)

# Find wide spread markets
markets = client.get_all_open_markets(max_markets=100)
# ... filter for wide spreads ...

# Run bot
bot.run(tickers=selected_tickers, duration_seconds=3600)
```

## Profit Potential

Based on real Kalshi data analysis:

### Current Market Conditions (Nov 2025)

**Markets with spreads > 70¢:** ~10 found in sample
**Example spreads:** 73¢, 76¢, 77¢, 78¢, 79¢

**Profit scenarios:**

| Market Spread | Your Spread | Cost | Profit/Pair | Return |
|---------------|-------------|------|-------------|--------|
| 73¢ | 15¢ | 85¢ | 15¢ | 17.6% |
| 76¢ | 15¢ | 84¢ | 16¢ | 19.0% |
| 79¢ | 15¢ | 83¢ | 17¢ | 20.5% |

**Conservative estimate:**
- 5 markets with 75¢ avg spread
- Quote 15¢ spread
- 10 contracts per side
- Both sides fill once per day

**Daily profit:** 5 markets × 10 contracts × 16¢ = $8.00/day
**Monthly profit:** ~$240

## Risks & Considerations

### 1. Adverse Selection
- Smart traders may pick off your quotes when they have information
- **Mitigation:** Widen spreads, use smaller sizes

### 2. Inventory Risk
- You might accumulate one-sided positions
- **Mitigation:** Max skew limits, dynamic spread adjustment

### 3. Event Risk
- Sudden news can move markets sharply
- **Mitigation:** Monitor news, use stop losses, limit per-market exposure

### 4. Execution Risk
- One side fills but not the other (directional exposure)
- **Mitigation:** Tight spreads increase both-sided fills

### 5. Capital Requirements
- Need sufficient capital to hold positions
- **Rule of thumb:** $500-1000 minimum per market

## Best Practices

### 1. Start Small
- Begin with 1-2 markets
- Use small quote sizes (5-10 contracts)
- Monitor closely

### 2. Focus on Wide Spreads
- Target spreads > 30¢
- More room for profit
- Less competition

### 3. Monitor Inventory
- Keep positions balanced
- Close out skewed positions
- Don't let inventory build up

### 4. Track Performance
```python
# Use bot's built-in stats
bot.print_stats()

# Outputs:
# - Position by market
# - Realized P&L
# - Fees paid
# - Net profit
```

### 5. Risk Management Rules
- Never risk > 10% of capital on one market
- Set daily loss limits
- Take breaks if losing

## Advanced Strategies

### 1. Dynamic Sizing
```python
# Size quotes based on spread width
if spread > 50:
    quote_size = 20  # Larger size for wide spreads
else:
    quote_size = 5   # Smaller for tighter
```

### 2. Fair Value from Multiple Sources
```python
# Combine orderbook + last price + fundamentals
fair_from_ob = calculate_from_orderbook()
fair_from_last = market['last_price']
fair = 0.7 * fair_from_ob + 0.3 * fair_from_last
```

### 3. Correlation Hedging
```python
# If long YES on Market A
# And Markets A & B are correlated
# Quote tighter on Market B to hedge
```

### 4. Time-Based Adjustments
```python
# Wider spreads near expiration (more risk)
# Tighter spreads mid-day (more liquidity)
time_to_expiry = get_time_to_expiry(market)
if time_to_expiry < 3600:  # < 1 hour
    spread *= 1.5
```

## Kalshi-Specific Considerations

### Liquidity Incentive Program
Kalshi pays rebates for providing liquidity!
- Check current program terms
- May receive payments for resting orders
- Improves economics further

### Market Types
- **Single events:** Easier to price
- **Parlays (multi-leg):** Harder to price, often wider spreads
- **Sports:** Fast-moving, need quick requotes
- **Politics:** Slow-moving, stable quotes

### API Rate Limits
- Respect Kalshi's rate limits
- Bot includes rate limiting (1s between markets)
- Don't spam orders

## Monitoring & Debugging

### Logs
```
2025-11-06 12:00:00 - INFO - Quote placed: 31¢/47¢ (spread=15.0¢)
2025-11-06 12:00:30 - INFO - Position updated: YES=10, NO=8, pairs=8
2025-11-06 12:01:00 - INFO - Inventory skew: +0.11 (11% long YES)
```

### Key Metrics to Watch
1. **Fill rate:** % of quotes that fill
2. **Avg profit per pair:** Should match spread - fees
3. **Inventory turnover:** How fast you complete pairs
4. **Win rate:** % of pairs that profit

## Troubleshooting

**"No wide spread markets found"**
- Markets may be more efficient at certain times
- Try during off-hours (night, weekends)
- Look at parlay/multi-leg markets

**"Position limit reached"**
- Close out existing positions
- Increase max_position limit
- Focus on fewer markets

**"Inventory too skewed"**
- Bot stopped quoting to prevent runaway exposure
- Manually close skewed positions
- Adjust max_inventory_skew setting

**"Failed to place quote"**
- Check API authentication
- Check rate limits
- Check order parameters (price must be 1-99)

## Next Steps

1. **Run demo:** `python demo_market_maker.py`
2. **Paper trade:** Log what WOULD happen without orders
3. **Start tiny:** 1 market, 5 contracts, watch for 1 hour
4. **Scale gradually:** Add markets and size as comfortable
5. **Automate:** Run on schedule (cron job, cloud server)

## Support

**Documentation:**
- Kalshi API: https://docs.kalshi.com
- Market Making Guide: This file

**Code Files:**
- `market_maker_bot.py` - Main bot implementation
- `demo_market_maker.py` - Dry run demo
- `kalshi_client.py` - API client with auth

---

**DISCLAIMER:** This bot places real orders and risks real money. Use at your own risk. Start small, monitor closely, and never risk more than you can afford to lose. Past performance does not guarantee future results.

**Good luck and happy market making! 🚀**
