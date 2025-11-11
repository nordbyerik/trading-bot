# Kalshi Trading Bot

A complete Python trading system for Kalshi prediction markets. Identifies trading opportunities using 13+ analyzers, manages positions with a sophisticated trade manager, and includes a full simulation environment for strategy testing.

## Features

- **13+ Analysis Modules**: Spread, mispricing, arbitrage, RSI, MACD, Bollinger Bands, momentum fade, theta decay, psychological levels, and more
- **Trade Manager**: Position management, P&L tracking, stop losses, take profits, and risk management
- **Live Simulator**: Backtest strategies with real Kalshi data using fake money
- **Multiple Notification Channels**: Console, file, email, and Slack
- **Configurable**: YAML-based configuration for all components
- **Kalshi API Client**: Full orderbook support, historical candlesticks, rate limiting, and caching
- **Authentication Support**: Public endpoints (no auth) and private endpoints (with RSA-PSS auth)

## Documentation

📚 **[API Guide](docs/API_GUIDE.md)** - Kalshi API setup, orderbook, authentication, endpoints, and troubleshooting

📊 **[Strategy Guide](docs/STRATEGY_GUIDE.md)** - Trading strategies, analyzers, trade manager, simulation, and risk management

## Installation

### Requirements

- Python 3.10+
- uv (recommended) or pip

### Setup

1. Clone or download this repository

2. Install dependencies:
```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -r requirements.txt
```

3. **(Optional)** Set up authentication for private endpoints:
```bash
export KALSHI_API_KEY_ID="your-key-id"
export KALSHI_PRIV_KEY="base64-encoded-private-key"
```

See [API Guide](docs/API_GUIDE.md) for authentication details.

## Quick Start

### Run Strategy Simulation

Test trading strategies with fake money:

```bash
# Quick test (3 cycles)
python3 run_simulation.py --mode test --cycles 3

# Conservative strategy for 30 minutes
python3 run_simulation.py --mode conservative --minutes 30

# Aggressive strategy
python3 run_simulation.py --mode aggressive --minutes 60

# Technical analysis (RSI, MACD, Bollinger Bands)
python3 run_simulation.py --mode technical --minutes 45
```

See [Strategy Guide](docs/STRATEGY_GUIDE.md) for detailed simulation options.

### Run Market Analysis

Analyze markets without trading:

```bash
# Single analysis cycle
python main.py --once

# Continuous monitoring (60-second interval)
python main.py

# Custom interval (e.g., every 2 minutes)
python main.py --interval 120

# Test specific analyzer
python main.py --analyzer spread --once

# List available analyzers
python main.py --list-analyzers
```

## Available Analyzers

The system includes 13+ specialized analyzers grouped into categories:

### Core Market Analyzers
- **Spread**: Wide bid-ask spreads (market-making opportunities)
- **Mispricing**: Extreme prices and behavioral biases
- **Arbitrage**: Risk-free cross-market opportunities
- **Imbalance**: Orderbook depth imbalances

### Technical Indicators
- **RSI**: Overbought/oversold signals (requires historical data)
- **MACD**: Trend signals
- **Bollinger Bands**: Volatility breakouts
- **MA Crossover**: Moving average crossovers

### Behavioral/Advanced
- **Momentum Fade**: Fade strong momentum moves
- **Theta Decay**: Time decay near expiration
- **Correlation**: Logical consistency across markets
- **Volume Trend**: Volume-based signals
- **Price Extreme Reversion**: Contrarian bets on extreme prices
- **Orderbook Depth**: Order flow imbalance signals

### Novice Exploitation (Advanced)
- **Event Volatility**: Fade FOMO spikes after news
- **Recency Bias**: Bet against short-term extrapolation
- **Psychological Levels**: Exploit biases at round numbers
- **Liquidity Trap**: Exploit thin orderbooks

See [Strategy Guide](docs/STRATEGY_GUIDE.md) for detailed analyzer descriptions, configurations, and usage examples.

## Notification Channels

### Console Notifier

Prints opportunities to the terminal. Always enabled by default.

**Configuration:**
```yaml
console:
  enabled: true
  min_confidence: low  # Options: low, medium, high
```

### File Notifier

Writes opportunities to a file (JSON or text format).

**Configuration:**
```yaml
file:
  enabled: true
  path: opportunities.json
  format: json  # Options: json, text
```

### Email Notifier

Sends notifications via email.

**Configuration:**
```yaml
email:
  enabled: true
  smtp_host: smtp.gmail.com
  smtp_port: 587
  sender: your-email@gmail.com
  recipients:
    - recipient@example.com
  username: your-email@gmail.com
  password: your-app-password  # Use app-specific password for Gmail
  use_tls: true
```

### Slack Notifier

Posts notifications to a Slack channel via webhook.

**Configuration:**
```yaml
slack:
  enabled: true
  webhook_url: https://hooks.slack.com/services/YOUR/WEBHOOK/URL
  channel: "#trading-alerts"
```

## Example Output

```
================================================================================
FOUND 2 OPPORTUNITY(IES)
================================================================================

=== WIDE_SPREAD OPPORTUNITY ===
Confidence: medium
Time: 2025-01-05 14:23:15

Markets: PRES-2025-GOP
  - Republican wins 2025 presidential election
    https://kalshi.com/markets/PRES

Current Prices:
  PRES-2025-GOP_yes_bid: 45.0¢
  PRES-2025-GOP_no_bid: 48.0¢

Estimated Edge: 3.5¢ (3.8%)

Reasoning: Wide spread of 7.0¢ (Yes: 45¢ x 200, No: 48¢ x 150). Potential market-making opportunity.

--------------------------------------------------------------------------------

=== ARBITRAGE OPPORTUNITY ===
Confidence: high
Time: 2025-01-05 14:23:15

Markets: TEMP-NYC-2025-01-10
  - NYC temperature on Jan 10
    https://kalshi.com/markets/TEMP

Current Prices:
  TEMP-NYC-2025-01-10_yes_bid: 52.0¢
  TEMP-NYC-2025-01-10_no_bid: 51.0¢

Estimated Edge: 1.0¢ (1.0%)

Reasoning: Simple arbitrage: YES bid (52¢) + NO bid (51¢) = 103¢ > 100¢. Net profit: 1.0¢ per contract. Max contracts: 100
```

## Project Structure

```
trading-bot/
├── docs/                    # Documentation
│   ├── API_GUIDE.md        # Kalshi API guide
│   └── STRATEGY_GUIDE.md   # Trading strategies guide
├── analyzers/              # 13+ analyzer modules
│   ├── base.py            # Base analyzer interface
│   ├── spread_analyzer.py
│   ├── rsi_analyzer.py
│   ├── orderbook_depth_analyzer.py
│   └── ... (10+ more)
├── tests/                  # Test suite
│   ├── test_analyzers.py
│   ├── test_orderbook.py
│   └── test_examples.py
├── kalshi_client.py        # Kalshi API client
├── trade_manager.py        # Position & risk management
├── simulator.py            # Strategy backtesting
├── run_simulation.py       # Simulation runner
├── main.py                 # Market analysis orchestrator
├── notifier.py            # Notification system
├── market_maker_bot.py    # Market making bot
├── config_novice_exploit.yaml  # Example config
├── pyproject.toml         # Dependencies
└── README.md              # This file
```

## Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test
pytest tests/test_orderbook.py -v
pytest tests/test_analyzers.py -v

# Run orderbook examples
python tests/test_examples.py
```

## Important Notes

### Trading vs Analysis

- **Simulator mode** (`run_simulation.py`): Uses fake money for strategy testing
- **Analysis mode** (`main.py`): Identifies opportunities without trading
- **Live trading**: Available via trade manager and market maker bot (use at your own risk)

### Rate Limiting & API

- Built-in rate limiting (20 req/sec default)
- Token bucket algorithm with configurable limits
- Caching enabled (30 second TTL default)
- See [API Guide](docs/API_GUIDE.md) for details

### Disclaimer

**For educational and research purposes only.** Trading involves risk. Past performance does not guarantee future results. Start with paper trading, use small position sizes, and never risk more than you can afford to lose.

## Troubleshooting

### Missing Dependencies
```bash
# Install all dependencies
uv sync
# Or
pip install -r requirements.txt
```

### Orderbook Issues
See [API Guide - Troubleshooting](docs/API_GUIDE.md#troubleshooting) for:
- Null orderbook handling
- Authentication errors
- Candlestick price extraction
- Finding long-lived markets

### No Opportunities Found
This is normal! Try:
- Adjusting analyzer thresholds (see [Strategy Guide](docs/STRATEGY_GUIDE.md))
- Running during high-volatility periods
- Using simulator to test different configurations

### Rate Limiting
If hitting rate limits:
- Increase `rate_limit_delay` in config
- Decrease `max_markets_to_analyze`
- See [API Guide](docs/API_GUIDE.md) for rate limit details

## Support

- **Documentation**: [API Guide](docs/API_GUIDE.md) | [Strategy Guide](docs/STRATEGY_GUIDE.md)
- **Kalshi API**: https://docs.kalshi.com/
- **Issues**: Open an issue on GitHub

## License

MIT License

---

Built for the Kalshi prediction market platform. Uses the Kalshi API (public endpoints require no authentication).
