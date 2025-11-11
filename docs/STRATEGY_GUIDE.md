# Trading Strategy Guide

Complete guide to trading strategies, analyzers, and execution system for the Kalshi trading bot.

## Table of Contents
- [System Architecture](#system-architecture)
- [Available Analyzers](#available-analyzers)
- [Trade Manager](#trade-manager)
- [Simulation & Testing](#simulation--testing)
- [Novice Exploitation Strategies](#novice-exploitation-strategies)
- [Market Making Strategy](#market-making-strategy)
- [Risk Management](#risk-management)

---

## System Architecture

The trading system consists of several components working together:

```
┌─────────────────┐
│  Kalshi Client  │  Fetches market data & orderbooks
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Analyzers     │  Identify trading opportunities
│  (13+ types)    │  - Spread, Mispricing, RSI, etc.
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Trade Manager   │  Makes trading decisions
│                 │  - Evaluates opportunities
│                 │  - Manages positions & P&L
│                 │  - Applies risk management
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Simulator     │  Tests strategies over time
│                 │  - Backtests on historical data
│                 │  - Simulates live trading
│                 │  - Tracks performance metrics
└─────────────────┘
```

---

## Available Analyzers

Each analyzer outputs `Opportunity` objects with:
- Confidence level (LOW/MEDIUM/HIGH)
- Strength (SOFT/HARD)
- Estimated edge in cents and percentage
- Reasoning and market details

### Core Market Analyzers
- **spread_analyzer**: Wide bid-ask spreads (market-making opportunities)
- **mispricing_analyzer**: Prices that don't match fundamentals
- **arbitrage_analyzer**: Cross-market arbitrage opportunities
- **imbalance_analyzer**: Order book depth imbalances

### Technical Indicators
- **rsi_analyzer**: RSI-based overbought/oversold signals (requires 14+ historical data points)
- **bollinger_bands_analyzer**: Bollinger bands breakouts
- **macd_analyzer**: MACD trend signals
- **ma_crossover_analyzer**: Moving average crossovers

### Behavioral/Advanced
- **momentum_fade_analyzer**: Fade strong momentum moves
- **theta_decay_analyzer**: Time decay opportunities (near expiration)
- **correlation_analyzer**: Correlation breaks between related markets
- **volume_trend_analyzer**: Volume-based signals
- **price_extreme_reversion_analyzer**: Contrarian bets on extreme prices (<5¢ or >95¢)
- **orderbook_depth_analyzer**: Order flow imbalance signals

### Novice Exploitation (Advanced)
- **event_volatility_analyzer**: Fade FOMO spikes after breaking news
- **recency_bias_analyzer**: Bet against extrapolation of short-term trends
- **psychological_levels_analyzer**: Exploit biases at round numbers, lottery tickets, etc.
- **liquidity_trap_analyzer**: Exploit thin orderbooks with tight spreads

---

## Trade Manager

The trade manager is the bridge between analysis and execution.

### Core Features

**1. Opportunity Evaluation**
Filters opportunities based on:
- Minimum confidence/strength thresholds
- Minimum edge requirements
- Available capital
- Max position limits

**2. Position Management**
- Opens positions with configurable sizing
- Tracks open and closed positions
- Calculates real-time P&L (realized + unrealized)
- Maintains complete trade history

**3. Risk Management**
- Stop losses (default: 20%)
- Take profit targets (default: 50%)
- Maximum position limits
- Portfolio risk controls

**4. Position Sizing Methods**
- `fixed`: Fixed dollar amount per trade
- `confidence_scaled`: Scale by opportunity confidence
- `kelly`: Kelly criterion based on edge

### Configuration

```python
from trade_manager import TradeManager, TradeManagerConfig
from analyzers.base import ConfidenceLevel, OpportunityStrength

config = TradeManagerConfig(
    initial_capital=10000.0,       # Starting cash ($100 in cents)
    max_position_size=1000.0,      # Max per position ($10)
    max_portfolio_risk=0.5,        # Max fraction of capital at risk

    min_confidence=ConfidenceLevel.MEDIUM,  # Filter threshold
    min_strength=OpportunityStrength.HARD,  # Filter threshold
    min_edge_cents=5.0,            # Minimum edge required
    min_edge_percent=2.0,          # Minimum edge % required

    stop_loss_percent=20.0,        # Stop loss trigger
    take_profit_percent=50.0,      # Take profit trigger
    max_positions=10,              # Max concurrent positions

    position_sizing_method="fixed",  # or "kelly" or "confidence_scaled"
    base_position_size=500.0       # Base size for fixed method
)

manager = TradeManager(config)
```

### Usage

```python
# Evaluate if we should trade on an opportunity
should_trade, reason = manager.should_trade(opportunity)

# Execute a trade
if should_trade:
    position = manager.execute_trade(opportunity, side=Side.YES)

# Update prices for all positions
manager.update_position_prices(market_prices)

# Check and trigger stop losses / take profits
closed_ids = manager.check_stops_and_targets(market_prices)

# Get portfolio metrics
summary = manager.get_portfolio_summary()
manager.print_summary()
```

---

## Simulation & Testing

The simulator runs the trade manager with real Kalshi data using fake money to test strategies over time.

### Quick Start

**Option 1: Use the preset runner (recommended)**

```bash
# Quick test (3 cycles)
python3 run_simulation.py --mode test --cycles 3

# Conservative strategy for 30 minutes
python3 run_simulation.py --mode conservative --minutes 30

# Aggressive strategy for 1 hour
python3 run_simulation.py --mode aggressive --minutes 60

# Technical analysis strategy
python3 run_simulation.py --mode technical --minutes 45

# With equity curve plot
python3 run_simulation.py --mode conservative --minutes 30 --plot
```

**Option 2: Use the simulator directly**

```bash
# Run for 2 hours with custom settings
python3 simulator.py --hours 2 --capital 100 --interval 60 --analyzers spread,mispricing,rsi

# Run for 10 cycles
python3 simulator.py --cycles 10 --max-markets 50

# Continuous mode (Ctrl+C to stop)
python3 simulator.py --continuous --interval 120
```

### Simulation Modes

**Conservative** (High quality, fewer trades)
- Min confidence: HIGH
- Min strength: HARD
- Min edge: 10¢ / 5%
- Max positions: 5
- Analyzers: spread, mispricing, arbitrage

**Aggressive** (More trades, higher risk)
- Min confidence: MEDIUM
- Min strength: SOFT
- Min edge: 3¢ / 2%
- Max positions: 10
- Analyzers: spread, mispricing, rsi, imbalance, momentum_fade

**Technical** (Technical indicators only)
- Min confidence: MEDIUM
- Min edge: 5¢
- Max positions: 8
- Analyzers: rsi, macd, bollinger_bands, ma_crossover

### How It Works

Each simulation cycle:
1. **Fetch Market Data** - Gets current markets and orderbooks from Kalshi
2. **Update Positions** - Updates prices for all open positions
3. **Check Stops** - Triggers stop losses and take profit targets
4. **Run Analyzers** - Identifies trading opportunities
5. **Evaluate & Trade** - Filters opportunities and executes trades
6. **Take Snapshot** - Records portfolio state for performance tracking
7. **Sleep** - Waits until next cycle

### Performance Metrics

After simulation:
- Total return and max drawdown
- Win rate, average win/loss, profit factor
- Opportunity conversion rate
- Detailed rejection reason analysis
- Equity curve visualization (optional)

---

## Novice Exploitation Strategies

Advanced analyzers designed to identify and exploit common behavioral biases and mistakes made by novice prediction market traders.

### 1. Event Volatility Crush

**Concept**: Similar to IV crush in options, prediction market prices spike before major events then normalize afterward.

**What Novices Do Wrong:**
- Buy into price spikes driven by breaking news
- Extrapolate short-term momentum indefinitely
- Use market orders during high volatility

**How We Exploit It:**
- Detect 15-20%+ price move in 24-48 hours with 2-3x volume spike
- Wait for stagnation (momentum exhausted)
- Fade the move (take opposite side)

**Example:**
```
Market: "Team wins championship"
- Star player injury news
- Price crashes 35¢ → 15¢ in 6 hours (3x volume)
- Stagnates at 13-16¢ for 12 hours
- OPPORTUNITY: Price likely overshot, expect reversion to 20-25¢
```

**Configuration:**
```yaml
event_volatility:
  hard_min_price_change_pct: 20.0
  hard_min_volume_spike: 3.0
  hard_hours_lookback: 24
```

### 2. Enhanced Theta Decay

**Concept**: Prices should converge toward 0 or 1 as expiration approaches. Novices hold uncertain positions (30-70¢) too close to expiration.

**What Novices Do Wrong:**
- Don't understand exponential decay in final hours
- Panic sell at terrible prices
- Don't price weekend/overnight gap risk

**How We Exploit It:**
- **Panic Zone Detection**: Final 6 hours where novices make worst decisions
- **Dead Cat Bounce**: Irrational spikes against convergence trend
- **Sure Thing Trap**: Markets at 94¢ with 3 hours left (novices won't sell)

**Example:**
```
Market: "Bill passes by Friday 5pm"
Thursday 11am: 48¢ (still uncertain - should be converging)
Friday 11am: 52¢ (6 hours left, IN PANIC ZONE)
- OPPORTUNITY: Take informed directional bet
- Novices will panic in next 2-4 hours
- Edge multiplier: 2x in panic zone
```

**Configuration:**
```yaml
theta_decay:
  panic_zone_hours: 6.0
  panic_multiplier: 2.0
  dead_cat_bounce_threshold: 0.10
```

### 3. Recency Bias

**Concept**: Novices overweight recent information and underweight base rates.

**What Novices Do Wrong:**
- See 2-day uptrend, assume it continues forever
- Ignore historical context
- React to each news item like it's the most important ever

**How We Exploit It:**
- Calculate historical mean (exclude recent window)
- Identify sharp deviation from mean
- Wait for stagnation confirmation
- Bet on partial mean reversion (40-60%)

**Example:**
```
Market: "Election poll prediction"
Days 1-3: Steady at 55¢ (mean = 55¢)
Day 4: New poll! Spikes to 75¢ (36% deviation)
Day 4 (6 hours later): Still at 73-76¢ (stagnated)

Analysis:
- 20¢ deviation from recent mean
- Likely overreaction to single data point
- Expected partial reversion: 50% × 20¢ = 10¢
- TRADE: Sell at 75¢, expect drop to 65-68¢
```

### 4. Psychological Levels

**Four Types of Psychological Bias:**

**A. Lottery Ticket Bias (1-5¢)**
- Novices think: "It's only 2¢, might as well buy"
- Reality: 2¢ = 49:1 implied odds, true odds might be 1000:1
- Exploit: Sell lottery tickets at inflated prices

**B. Sure Thing Trap (95-99¢)**
- Novices think: "I want the full dollar, won't sell at 98¢"
- Reality: Tying up $98 for $2 = poor return
- Exploit: Buy "sure things" at 96-98¢ (near-certain 2-4¢ edge)

**C. Round Number Clustering (25¢, 50¢, 75¢)**
- Novices place limit orders at exact round numbers
- Creates artificial support/resistance
- Exploit: Provide liquidity just inside the cluster

**D. 50¢ Anchoring (Special Case)**
- Novices think: "50/50 odds = 50¢ fair price"
- Reality: True fair value might be 45¢ or 55¢
- Exploit: Take informed directional position

### 5. Liquidity Traps

**Concept**: Novices see tight spread, don't check depth, get terrible fills.

**What Novices Do Wrong:**
- Only look at spread, ignore depth
- Use market orders without checking size
- Don't calculate price impact

**How We Exploit It:**
- Detect tight spread (< 5¢) but thin depth (< 100 contracts)
- Provide liquidity at premium vs. market
- Capture novice market orders at favorable prices

**Example:**
```
Market: 45¢ bid / 48¢ ask (3¢ spread - looks tight!)
But order book has only 20-25 contracts per level

Novice wants to buy 100 contracts with market order:
- Average fill: 49.4¢ (not 48¢!)
- Price impact: 2.9% slippage

Our Strategy:
- Offer 100 contracts at 49¢ (limit order)
- Better than their market order execution
- We earn 1¢ premium
```

### Strategy Combinations

Often markets exhibit multiple novice behaviors at once:

**Example: Panic Zone + Psychological Level**
```
Market: 48¢, 4 hours to expiration
- In panic zone (< 6 hours)
- At 50¢ anchor point
- DOUBLE EXPLOIT: Panic + anchoring bias
- Edge multiplier: 2x (panic) + psychological resistance
```

---

## Market Making Strategy

The Market Maker Bot provides two-sided liquidity on Kalshi markets to capture bid-ask spreads.

### How It Works

**Core Concept:**
On Kalshi, YES + NO = $1.00 (100¢)

This means:
- Buying YES at 30¢ = Selling NO at 70¢
- Buying NO at 70¢ = Selling YES at 30¢

**Market Making Mechanics:**
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

### Real Example

**Market:** Wide spread (YES bid: 1¢, NO bid: 23¢ = 76¢ total spread)
**Bot's Quote:** 31¢ / 47¢ (15¢ spread)

- Order 1: Buy 10 YES at 31¢
- Order 2: Buy 10 NO at 53¢

**If both fill:**
- Cost: 31¢ + 53¢ = 84¢
- Payout: 100¢
- **Profit: 16¢ per pair (19% return!)**
- For 10 contracts: $1.60 profit on $8.40 invested

### Key Features

**1. Inventory Management**
```python
Position(
    yes_contracts=15,
    no_contracts=10,
    total_pairs=10,        # Min(YES, NO) = guaranteed profit
    inventory_skew=0.20    # (15-10)/(15+10) = 20% long YES
)
```

**2. Dynamic Spread Adjustment**
- Base spread: 15¢ (configurable)
- Inventory skewed > 30%: Widen spread by 50%
- If long YES, quote lower to encourage selling

**3. Risk Limits**
- Max position: 50 total contracts per market
- Max skew: 60% (stop quoting if too imbalanced)
- Auto-cancel: Cancels all quotes on shutdown

### Configuration

```python
from market_maker_bot import MarketMakerBot

bot = MarketMakerBot(
    client=client,
    base_spread_cents=15.0,        # 15¢ total spread
    quote_size=10,                 # 10 contracts per side
    max_position=50,               # Max 50 total contracts
    max_inventory_skew=0.6,        # 60% max imbalance
    requote_interval_seconds=120   # Requote every 2 min
)
```

**Parameter Guide:**
- **base_spread_cents**: Wider = more profit per trade, fewer fills (10-20¢ recommended)
- **quote_size**: Smaller = less risk, more frequent trading (5-20 contracts)
- **max_position**: Limits total exposure per market (50-100 contracts)
- **max_inventory_skew**: Stop quoting if too imbalanced (0.5-0.7 recommended)

### Profit Potential

Based on real Kalshi data:

**Markets with spreads > 70¢:** ~10 markets found

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

### Best Practices

1. **Start Small**: Begin with 1-2 markets, 5-10 contract sizes
2. **Focus on Wide Spreads**: Target spreads > 30¢
3. **Monitor Inventory**: Keep positions balanced
4. **Track Performance**: Use bot's built-in stats
5. **Risk Management**: Never risk > 10% of capital on one market

### Kalshi-Specific Considerations

**Liquidity Incentive Program:**
- Kalshi pays rebates for providing liquidity
- Check current program terms
- May receive payments for resting orders

**Market Types:**
- Single events: Easier to price
- Parlays (multi-leg): Harder to price, wider spreads
- Sports: Fast-moving, need quick requotes
- Politics: Slow-moving, stable quotes

---

## Risk Management

### Key Principles

**1. Never Chase Moves**
- Wait for stagnation confirmation
- Don't catch falling knives
- Patience is essential

**2. Position Sizing**
- Theta decay near expiration = higher risk
- Psychological levels = medium risk
- Liquidity provision = lower risk (market-making)

**3. Time Horizon**
- Panic zone = minutes to hours
- Event volatility = hours to days
- Psychological levels = days to weeks

**4. Confirmation Signals**
- One analyzer = investigate
- Two analyzers = strong signal
- Three+ analyzers = highest confidence

### Trade Manager Risk Controls

- **Stop losses**: Default 20%, configurable
- **Take profit targets**: Default 50%, configurable
- **Maximum positions**: Limit concurrent exposure
- **Portfolio risk**: Max fraction of capital at risk
- **Minimum edge**: Filter low-quality opportunities

### Avoiding Counter-Exploitation

**Don't become the novice:**
- Always check order book depth before trading
- Calculate expected fill price, not just spread
- Don't FOMO into analyzer signals
- Remember: Markets can stay irrational longer than you can stay solvent
- These are edges, not guarantees

### Risk Management Rules

- Never risk > 10% of capital on one market
- Set daily loss limits
- Take breaks if losing
- Track actual vs. estimated edge
- Iterate and improve continuously

---

## Configuration Guide

### Aggressive Mode (More Opportunities)

```yaml
# Use SOFT thresholds
event_volatility:
  soft_min_price_change_pct: 15.0

theta_decay:
  soft_hours_to_expiration: 48.0

recency_bias:
  soft_min_deviation_pct: 15.0

# Trade manager
trade_manager:
  min_confidence: MEDIUM
  min_strength: SOFT
  min_edge_cents: 3.0
  max_positions: 10
```

### Conservative Mode (Higher Quality)

```yaml
# Use HARD thresholds only
event_volatility:
  hard_min_price_change_pct: 20.0
  hard_min_volume_spike: 3.0

theta_decay:
  hard_hours_to_expiration: 24.0
  panic_multiplier: 2.0

# Trade manager
trade_manager:
  min_confidence: HIGH
  min_strength: HARD
  min_edge_cents: 10.0
  max_positions: 5
```

### Balanced Mode (Recommended)

Enable both HARD and SOFT thresholds, prioritize by strength:
- HARD opportunities = immediate action
- SOFT opportunities = watchlist

---

## Testing and Validation

### Backtesting Approach
1. Run simulation on closed markets (if historical data available)
2. Identify which patterns had highest success rate
3. Calibrate thresholds based on historical data
4. Test edge estimates against actual outcomes

### Paper Trading
1. Log all opportunities without real trades (use simulator)
2. Track hypothetical P&L
3. Identify which exploits work best in live markets
4. Refine configuration

### Live Trading (When Ready)
1. Start with smallest position sizes
2. Focus on highest confidence signals only
3. Track actual vs. estimated edge
4. Iterate and improve

---

## Disclaimer

**Educational and Research Purpose:**
This system identifies patterns in market data. All trading involves risk. Past patterns do not guarantee future results.

**Market Evolution:**
As more traders become aware of these patterns, some may become less exploitable. Continuous monitoring and adaptation required.

**Regulatory Compliance:**
Ensure all trading activities comply with relevant regulations and platform terms of service.

**IMPORTANT:** These strategies place real orders and risk real money when used live. Use at your own risk. Start small, monitor closely, and never risk more than you can afford to lose.
