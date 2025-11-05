# Trade Manager & Simulator Architecture

## Overview

The trading system consists of several components working together:

```
┌─────────────────┐
│  Kalshi Client  │  Fetches market data & orderbooks
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Analyzers     │  Identify trading opportunities
│  (13 types)     │  - Spread, Mispricing, RSI, etc.
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
│  (Coming next)  │  - Backtests on historical data
│                 │  - Simulates live trading
│                 │  - Tracks performance metrics
└─────────────────┘
```

## Current Components

### 1. KalshiDataClient (`kalshi_client.py`)
- Fetches market data from Kalshi API
- Handles rate limiting and caching
- No authentication required for public data

### 2. Analyzers (`analyzers/`)
Available analyzers:
- **spread_analyzer**: Wide bid-ask spreads (market-making opportunities)
- **mispricing_analyzer**: Prices that don't match fundamentals
- **arbitrage_analyzer**: Cross-market arbitrage opportunities
- **rsi_analyzer**: RSI-based overbought/oversold signals
- **bollinger_bands_analyzer**: Bollinger bands breakouts
- **macd_analyzer**: MACD trend signals
- **ma_crossover_analyzer**: Moving average crossovers
- **momentum_fade_analyzer**: Fade strong momentum moves
- **correlation_analyzer**: Correlation breaks between related markets
- **imbalance_analyzer**: Order book imbalances
- **volume_trend_analyzer**: Volume-based signals
- **theta_decay_analyzer**: Time decay opportunities

Each analyzer outputs `Opportunity` objects with:
- Confidence level (LOW/MEDIUM/HIGH)
- Strength (SOFT/HARD)
- Estimated edge in cents and percentage
- Reasoning and market details

### 3. Trade Manager (`trade_manager.py`) ✅ NEW

The trade manager is the bridge between analysis and execution:

#### Core Features:
- **Opportunity Evaluation**: Filters opportunities based on:
  - Minimum confidence/strength thresholds
  - Minimum edge requirements
  - Available capital
  - Max position limits

- **Position Management**:
  - Opens positions with configurable sizing
  - Tracks open and closed positions
  - Calculates real-time P&L (realized + unrealized)
  - Maintains complete trade history

- **Risk Management**:
  - Stop losses (default: 20%)
  - Take profit targets (default: 50%)
  - Maximum position limits
  - Portfolio risk controls

- **Position Sizing Methods**:
  - `fixed`: Fixed dollar amount per trade
  - `confidence_scaled`: Scale by opportunity confidence
  - `kelly`: Kelly criterion based on edge

#### Configuration Options:

```python
TradeManagerConfig(
    initial_capital=10000.0,       # Starting cash (cents)
    max_position_size=1000.0,      # Max per position (cents)
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
```

#### Key Methods:

```python
# Evaluate if we should trade on an opportunity
should_trade, reason = manager.should_trade(opportunity)

# Execute a trade
position = manager.execute_trade(opportunity, side=Side.YES)

# Update prices for all positions
manager.update_position_prices(market_prices)

# Check and trigger stop losses / take profits
closed_ids = manager.check_stops_and_targets(market_prices)

# Close a position manually
manager.close_position(position_id, exit_price, reason)

# Get portfolio metrics
summary = manager.get_portfolio_summary()
manager.print_summary()
```

## Live Simulator ✅ COMPLETE

The simulator runs the trade manager with real Kalshi data using fake money to test strategies over time.

### Features:

1. **Live Simulation Mode**:
   - Fetches real market data from Kalshi
   - Uses fake money (paper trading)
   - Runs for specified duration or number of cycles
   - Updates positions and checks stops in real-time

2. **Performance Tracking**:
   - Portfolio snapshots over time
   - Total return, max drawdown
   - Win rate, average win/loss, profit factor
   - Opportunity conversion rate
   - Detailed rejection reason analysis

3. **Comprehensive Reporting**:
   - Real-time portfolio summary
   - Trade history and statistics
   - Open and closed positions
   - Performance metrics

4. **Visualization** (optional):
   - Equity curve over time (requires matplotlib)
   - Portfolio value tracking

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

# Run for 30 minutes
python3 simulator.py --minutes 30 --capital 500

# Continuous mode (Ctrl+C to stop)
python3 simulator.py --continuous --interval 120
```

**Option 3: Python API**

```python
from simulator import TradingSimulator, SimulatorConfig
from trade_manager import TradeManagerConfig
from analyzers.base import ConfidenceLevel

# Configure trade manager
trade_config = TradeManagerConfig(
    initial_capital=10000.0,  # $100 in cents
    max_position_size=1000.0,  # $10 per position
    min_confidence=ConfidenceLevel.MEDIUM,
    min_edge_cents=5.0,
    max_positions=10
)

# Configure simulator
sim_config = SimulatorConfig(
    trade_manager_config=trade_config,
    analyzer_names=['spread', 'mispricing', 'rsi'],
    max_markets=100,
    update_interval_seconds=60
)

# Create and run
simulator = TradingSimulator(sim_config)
report = simulator.run_for_duration(hours=1)

# Print results
simulator.print_summary()

# Optional: plot equity curve
simulator.plot_equity_curve()
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

### Performance Report

After the simulation, you get:

```
================================================================================
SIMULATION SUMMARY
================================================================================
Duration:         0:30:00
Cycles:           15
Snapshots:        6

--------------------------------------------------------------------------------
PORTFOLIO PERFORMANCE
--------------------------------------------------------------------------------
Initial Value:    $      100.00
Final Value:      $      103.50
Total P&L:        $        3.50  (  3.50%)
  Realized:       $        2.80
  Unrealized:     $        0.70
Max Drawdown:       1.20%

--------------------------------------------------------------------------------
TRADING STATISTICS
--------------------------------------------------------------------------------
Opportunities:       45
Trades:               8  (17.8% conversion)
Open Positions:       2
Closed Positions:     6

Win Rate:           66.7%
Avg Win:          $        0.80
Avg Loss:         $       -0.40
Profit Factor:            2.00

--------------------------------------------------------------------------------
TOP REJECTION REASONS
--------------------------------------------------------------------------------
Edge too small (3.5¢ < 5.0¢)                            20
Confidence too low (medium)                             12
At max positions (10)                                    5
```

### Configuration Options

See `SimulatorConfig` and `TradeManagerConfig` for all options:

**SimulatorConfig:**
- `analyzer_names`: List of analyzers to use
- `max_markets`: Max markets to analyze per cycle
- `update_interval_seconds`: Time between cycles
- `snapshot_interval_seconds`: Time between snapshots

**TradeManagerConfig:**
- `initial_capital`: Starting cash
- `min_confidence` / `min_strength`: Filter thresholds
- `min_edge_cents` / `min_edge_percent`: Edge requirements
- `max_positions`: Concurrent position limit
- `stop_loss_percent` / `take_profit_percent`: Exit triggers
- `position_sizing_method`: "fixed", "kelly", or "confidence_scaled"

## Usage Examples

### Basic Trade Manager Test

```python
from trade_manager import TradeManager, TradeManagerConfig
from analyzers.base import ConfidenceLevel

# Configure manager
config = TradeManagerConfig(
    initial_capital=10000.0,  # $100
    min_confidence=ConfidenceLevel.MEDIUM,
    min_edge_cents=5.0
)

manager = TradeManager(config)

# Get opportunities from analyzers
# (see main.py for full analyzer integration)

# Evaluate and trade
for opportunity in opportunities:
    should_trade, reason = manager.should_trade(opportunity)
    if should_trade:
        position = manager.execute_trade(opportunity)

# Check portfolio
manager.print_summary()
```

### Integration with Existing System

The trade manager integrates seamlessly with your existing `main.py`:

```python
# In main.py, after getting opportunities:
opportunities = self.run_analysis(markets)

# Add trade manager
from trade_manager import TradeManager, TradeManagerConfig

config = TradeManagerConfig(
    initial_capital=10000.0,
    min_confidence=ConfidenceLevel.HIGH,
    min_edge_cents=10.0
)
trade_manager = TradeManager(config)

# Evaluate opportunities
for opp in opportunities:
    should_trade, reason = trade_manager.should_trade(opp)
    if should_trade:
        trade_manager.execute_trade(opp)

# Update prices and check stops
# (would need current market data here)
trade_manager.print_summary()
```

## Testing

Run the trade manager test:
```bash
python3 trade_manager.py
```

This will:
1. Create a mock opportunity
2. Evaluate if it should be traded
3. Execute a trade
4. Simulate price movement
5. Show P&L updates
6. Close the position

## Next Steps

1. ✅ Trade Manager implemented
2. ✅ Live Simulator implemented
3. ✅ Performance analytics and reporting
4. 🔄 Run simulations to tune analyzer parameters
5. 📊 Optional: Add backtest mode for historical data
6. 💰 Connect to real Kalshi trading (when ready)
