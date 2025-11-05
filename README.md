# Kalshi Market Analysis System

A modular Python system for monitoring Kalshi prediction markets and identifying trading opportunities. The system analyzes market data to detect arbitrage, mispricings, wide spreads, and other inefficiencies - **without executing any trades**.

## Features

- **Six Analysis Modules**: Spread, Mispricing, Arbitrage, Momentum Fade, Correlation, and Imbalance analyzers
- **Multiple Notification Channels**: Console, file, email, and Slack
- **Configurable**: YAML-based configuration for all analyzers and notifiers
- **Rate Limiting**: Built-in API rate limiting and caching
- **Continuous Monitoring**: Run one-off analysis or continuous monitoring
- **No Authentication Required**: Uses public Kalshi API endpoints

## Installation

### Requirements

- Python 3.10+
- pip

### Setup

1. Clone or download this repository

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Copy the example configuration:
```bash
cp config.example.yaml config.yaml
```

4. Edit `config.yaml` to customize analyzers and notifiers

## Quick Start

### Run a single analysis cycle:
```bash
python main.py --once
```

### Run continuous monitoring (default 60-second interval):
```bash
python main.py
```

### Run with custom interval (e.g., every 2 minutes):
```bash
python main.py --interval 120
```

### Test a specific analyzer:
```bash
python main.py --analyzer spread --once
```

### List available analyzers:
```bash
python main.py --list-analyzers
```

## Analyzers

### 1. Spread Analyzer

Identifies markets with wide bid-ask spreads that may present market-making opportunities.

**What it detects:**
- Markets where `100¢ - (yes_bid + no_bid)` is large
- Potential for providing liquidity

**Example configuration:**
```yaml
spread:
  enabled: true
  config:
    min_spread_cents: 10
    wide_spread_cents: 20
    very_wide_spread_cents: 30
```

### 2. Mispricing Analyzer

Detects potential mispricings based on extreme probabilities and round number bias.

**What it detects:**
- Markets at very low prices (e.g., <5¢) or very high prices (e.g., >95¢)
- Prices clustering at round numbers (25¢, 50¢, 75¢) with low volume
- Potential behavioral biases

**Example configuration:**
```yaml
mispricing:
  enabled: true
  config:
    extreme_low_threshold: 5
    extreme_high_threshold: 95
    round_numbers: [25, 50, 75]
```

### 3. Arbitrage Analyzer

Finds risk-free arbitrage opportunities across markets.

**What it detects:**
- Simple arbitrage: When yes_bid + no_bid > 100¢ in a single market
- Cross-market arbitrage: When related markets have inconsistent pricing
- Opportunities to lock in guaranteed profits

**Example configuration:**
```yaml
arbitrage:
  enabled: true
  config:
    min_arb_cents: 2
    transaction_cost_cents: 1
```

### 4. Momentum Fade Analyzer

Tracks price changes over time and identifies sudden moves that may indicate overreaction.

**What it detects:**
- Rapid price movements
- Potential mean reversion opportunities
- Markets where recent momentum may fade

**Note:** Requires state tracking, best used in continuous mode.

**Example configuration:**
```yaml
momentum_fade:
  enabled: true
  config:
    min_price_change_cents: 10
    large_price_change_cents: 20
    lookback_periods: 3
```

### 5. Correlation Analyzer

Checks for logical consistency across related markets.

**What it detects:**
- Subset events priced higher than superset events
  - Example: "Team wins by 10+" priced higher than "Team wins"
- Correlation breaks in same event/series
- Logically inconsistent probabilities

**Example configuration:**
```yaml
correlation:
  enabled: true
  config:
    min_inconsistency_cents: 5
    check_same_event: true
    check_same_series: true
```

### 6. Imbalance Analyzer

Detects orderbook depth imbalances.

**What it detects:**
- One-sided liquidity (e.g., 5:1 ratio of yes:no depth)
- Very thin liquidity on one side
- Potential informed flow or mispricing signals

**Example configuration:**
```yaml
imbalance:
  enabled: true
  config:
    min_imbalance_ratio: 3.0
    strong_imbalance_ratio: 5.0
    min_total_liquidity: 100
```

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
kalshi-bot-claude/
├── analyzers/              # Analysis modules
│   ├── __init__.py
│   ├── base.py            # Base analyzer interface
│   ├── spread_analyzer.py
│   ├── mispricing_analyzer.py
│   ├── arbitrage_analyzer.py
│   ├── momentum_fade_analyzer.py
│   ├── correlation_analyzer.py
│   └── imbalance_analyzer.py
├── tests/                 # Unit tests
│   ├── __init__.py
│   └── test_analyzers.py
├── kalshi_client.py       # Kalshi API client
├── notifier.py           # Notification system
├── main.py               # Main orchestrator
├── config.example.yaml   # Example configuration
├── requirements.txt      # Python dependencies
└── README.md            # This file
```

## Adding Custom Analyzers

To add a new analyzer:

1. Create a new file in `analyzers/` (e.g., `my_analyzer.py`)

2. Inherit from `BaseAnalyzer`:

```python
from analyzers.base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel

class MyAnalyzer(BaseAnalyzer):
    def get_name(self) -> str:
        return "My Custom Analyzer"

    def get_description(self) -> str:
        return "Describes what this analyzer does"

    def analyze(self, markets: List[Dict]) -> List[Opportunity]:
        opportunities = []

        for market in markets:
            # Your analysis logic here
            if some_condition:
                opp = Opportunity(
                    opportunity_type=OpportunityType.MISPRICING,
                    confidence=ConfidenceLevel.MEDIUM,
                    # ... other fields
                )
                opportunities.append(opp)

        return opportunities
```

3. Register your analyzer in `main.py`:

```python
ANALYZER_REGISTRY = {
    "my_analyzer": MyAnalyzer,
    # ... other analyzers
}
```

4. Add configuration to `config.yaml`:

```yaml
analyzers:
  my_analyzer:
    enabled: true
    config:
      custom_param: value
```

## Running Tests

```bash
# Run all tests
pytest tests/

# Run with verbose output
pytest tests/ -v

# Run specific test file
pytest tests/test_analyzers.py -v
```

## Important Notes

### Rate Limiting

The system includes built-in rate limiting to avoid overwhelming the Kalshi API:
- Default: 0.1 second delay between requests
- Configurable via `rate_limit_delay` in config
- Caching enabled (default 30 second TTL)

### API Limits

The example configuration limits analysis to 100 markets to prevent excessive API calls. Adjust `max_markets_to_analyze` based on your needs and API rate limits.

### No Trading

This system is for **analysis and notification only**. It does not execute trades. All identified opportunities should be manually reviewed before acting on them.

### Disclaimer

This software is for educational and research purposes only. Trading prediction markets involves risk. Past performance and identified patterns do not guarantee future results. Always do your own research and risk assessment.

## Troubleshooting

### "No module named 'yaml'"

Install PyYAML:
```bash
pip install pyyaml
```

### "Connection refused" errors

Check your internet connection and verify the Kalshi API is accessible:
```bash
curl https://api.elections.kalshi.com/trade-api/v2/markets?limit=1
```

### No opportunities found

This is normal! The analyzers use conservative thresholds. Try:
- Adjusting analyzer config parameters (lower thresholds)
- Running during high-volatility periods
- Enabling more analyzers

### High API usage

If you're hitting rate limits:
- Increase `rate_limit_delay` in config
- Decrease `max_markets_to_analyze`
- Increase polling `interval` for continuous mode

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## Support

For questions or issues:
- Open an issue on GitHub
- Check the Kalshi API documentation: https://docs.kalshi.com/

## Acknowledgments

- Built for the Kalshi prediction market platform
- Uses the public Kalshi API (no authentication required for market data)
