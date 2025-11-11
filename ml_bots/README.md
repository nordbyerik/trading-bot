# ML Bots - Machine Learning Data Pipeline & Analyzer

Machine learning infrastructure for Kalshi prediction markets, fully integrated with the existing trading bot system.

## Overview

This package provides:
- **Data Pipeline**: Fetch and transform historical market data
- **ML Models**: Train prediction models (Logistic, Random Forest, Neural Networks)
- **ML Analyzer**: Integrated analyzer for the simulator

The ML predictor works as a standard analyzer in the existing infrastructure, compatible with the simulator, trade manager, and all other analyzers.

## Quick Start

### Run ML Analyzer with Simulator

```bash
# Quick test (3 cycles)
python demo_ml_analyzer.py --mode test

# 30-minute simulation
python demo_ml_analyzer.py --minutes 30

# Custom model and confidence
python demo_ml_analyzer.py --minutes 30 --model neural_network --confidence 0.75
```

### Use in Simulation Scripts

```bash
# Use ML analyzer with existing run_simulation.py
python run_simulation.py --mode ml --minutes 30
```

### Combine with Other Analyzers

```python
from run_simulation import setup_simulation, run_cycles

# Combine ML with traditional analyzers
simulator = setup_simulation(
    analyzer_names=['ml_predictor', 'rsi', 'spread'],
    analyzer_configs={
        'ml_predictor': {
            'model_type': 'random_forest',
            'hard_min_confidence': 0.70,
            'training_markets': 20
        }
    }
)

run_cycles(simulator, duration_minutes=60)
```

## Architecture

```
ml_bots/
├── data_pipeline/           # Data utilities
│   ├── data_fetcher.py     # Fetch historical data from Kalshi
│   └── data_transformer.py # Transform to DataFrames/tensors + features
└── models/                  # ML models
    └── price_predictor.py  # Price prediction models

analyzers/
└── ml_predictor_analyzer.py # ML Analyzer (integrated with system)
```

## ML Analyzer Configuration

The ML analyzer follows the same configuration pattern as other analyzers:

```python
ml_config = {
    # Model configuration
    'model_type': 'random_forest',  # logistic, random_forest, neural_network

    # Training parameters
    'train_on_first_run': True,     # Auto-train on first analyze() call
    'training_markets': 15,          # Markets to train on
    'training_days': 7,              # Days of historical data
    'training_interval': 60,         # Candlestick interval (minutes)
    'prediction_horizon': 1,         # Periods ahead to predict

    # Hard thresholds (strict requirements)
    'hard_min_confidence': 0.70,     # Minimum confidence
    'hard_high_confidence': 0.80,    # High confidence threshold

    # Soft thresholds (relaxed requirements)
    'soft_min_confidence': 0.60,     # Minimum confidence
    'soft_high_confidence': 0.70,    # High confidence threshold

    # Edge estimation
    'edge_multiplier': 10,           # Confidence to edge conversion
}
```

## How It Works

### 1. Automatic Training

On first run, the analyzer:
1. Discovers active markets with sufficient volume
2. Fetches historical candlestick data (7 days by default)
3. Extracts technical features (RSI, MA, volatility, etc.)
4. Trains the selected ML model
5. Evaluates performance on validation set

### 2. Signal Generation

For each market analyzed:
1. Fetches recent historical data
2. Computes technical features
3. Makes prediction using trained model
4. Returns `Opportunity` if confidence meets threshold

### 3. Integration

The ML analyzer returns standard `Opportunity` objects, so:
- Trades are executed by `TradeManager`
- Performance tracked by `Simulator`
- Works alongside other analyzers
- Uses existing notification system

## Data Pipeline Usage

The data pipeline modules can be used independently:

### Fetch Historical Data

```python
from ml_bots.data_pipeline import HistoricalDataFetcher
from kalshi_client import KalshiDataClient

client = KalshiDataClient()
fetcher = HistoricalDataFetcher(client)

# Fetch dataset for ML training
dataset = fetcher.fetch_dataset_for_ml(
    min_volume=100,
    max_markets=20,
    days_back=7,
    period_interval=60
)

# Fetch specific market
candlesticks = fetcher.fetch_market_candlesticks(
    series_ticker='INXD',
    market_ticker='INXD-25JAN06-T4999.99',
    days_back=7,
    period_interval=60
)
```

### Transform Data

```python
from ml_bots.data_pipeline import DataTransformer

transformer = DataTransformer()

# Convert to DataFrame
df = transformer.candlesticks_to_dataframe(candlesticks)

# Add technical features
df = transformer.add_technical_features(df)

# Create labels
df = transformer.create_labels(df, prediction_horizon=1)

# Prepare for ML
X, y = transformer.prepare_features_and_labels(df)

# Convert to tensors (optional)
X_tensor, y_tensor = transformer.to_torch_tensors(X, y)
```

### Train Custom Model

```python
from ml_bots.models.price_predictor import PricePredictor

# Create and train model
predictor = PricePredictor(model_type='random_forest')
metrics = predictor.train(X_train, y_train, X_val, y_val)

# Make predictions
predictions = predictor.predict(X_test)
probabilities = predictor.predict_proba(X_test)

# Get feature importance
importance = predictor.get_feature_importance()
```

## Technical Features

Automatically generated features include:

### Price Features
- `price_change`: Absolute price change
- `price_change_pct`: Percentage price change
- `ma_5`, `ma_10`, `ma_20`: Moving averages

### Technical Indicators
- `rsi_14`: Relative Strength Index
- `volatility_10`: Rolling standard deviation

### Volume Features
- `volume_change`: Change in volume
- `volume_ma_10`: Volume moving average

### Orderbook Features
- `spread`: Bid-ask spread

## ML Models

### Logistic Regression
- Fast, interpretable baseline
- Good for linear relationships
- Low computational cost

### Random Forest (Recommended)
- Best general-purpose model
- Handles non-linear patterns
- Provides feature importance
- Robust to overfitting

### Neural Network
- 3-layer MLP with dropout
- Can capture complex patterns
- Requires more training data
- Longer training time

## Examples

### Example 1: Basic ML Simulation

```bash
python demo_ml_analyzer.py --mode test
```

### Example 2: Neural Network

```bash
python demo_ml_analyzer.py --minutes 30 --model neural_network
```

### Example 3: High Confidence

```bash
python demo_ml_analyzer.py --minutes 60 --confidence 0.80
```

### Example 4: Ensemble Strategy

```python
# Combine ML with technical analyzers
simulator = setup_simulation(
    analyzer_names=['ml_predictor', 'rsi', 'macd', 'bollinger_bands'],
    analyzer_configs={
        'ml_predictor': {
            'model_type': 'random_forest',
            'hard_min_confidence': 0.75
        },
        'rsi': {'hard_overbought_threshold': 75},
        'macd': {'hard_signal_threshold': 2.0}
    }
)
```

## Integration Benefits

By integrating with existing infrastructure:

✅ **Works with Simulator**: Full backtesting and performance tracking
✅ **Uses TradeManager**: Position sizing, risk management, P&L tracking
✅ **Combines with Analyzers**: Build ensemble strategies
✅ **Standard Interface**: Same `Opportunity` model as other analyzers
✅ **Existing Notifications**: Console, file, email, Slack support

## Tips for Best Performance

1. **Training Data**: Use 7-14 days of historical data
2. **Market Selection**: Train on high-volume, active markets
3. **Model Choice**: Random Forest works well for most cases
4. **Confidence Threshold**: Start with 0.65-0.70, adjust based on results
5. **Ensemble**: Combine with technical analyzers for better signals
6. **Monitoring**: Track win rate and adjust thresholds accordingly

## Troubleshooting

### No Training Data

**Problem**: "No training data available"

**Solutions**:
- Increase `training_days` in config
- Lower `min_volume` threshold
- Ensure markets are active during training window

### Model Not Training

**Problem**: Model training fails

**Solutions**:
- Check that ML dependencies are installed (`pip install pandas numpy scikit-learn torch`)
- Verify Kalshi API is accessible
- Increase `training_markets` parameter

### No Signals Generated

**Problem**: ML analyzer finds no opportunities

**Solutions**:
- Lower `hard_min_confidence` or `soft_min_confidence`
- Ensure model is trained (`is_trained=True`)
- Check that analyzing non-training markets
- Verify markets have sufficient historical data

### Low Accuracy

**Problem**: Model accuracy below 60%

**Solutions**:
- Market prediction is inherently difficult
- Try different model types
- Increase training data (days and markets)
- Focus on specific market categories
- Combine with other analyzers

## Extending the System

### Create Custom Analyzer

```python
from analyzers.ml_predictor_analyzer import MLPredictorAnalyzer

class CustomMLAnalyzer(MLPredictorAnalyzer):
    def _analyze_market(self, market):
        # Add custom logic
        opportunity = super()._analyze_market(market)
        if opportunity:
            # Modify opportunity based on custom criteria
            pass
        return opportunity
```

### Add Custom Features

```python
from ml_bots.data_pipeline import DataTransformer

class CustomTransformer(DataTransformer):
    def add_technical_features(self, df):
        df = super().add_technical_features(df)
        # Add your custom features
        df['custom_indicator'] = df['yes_ask_close'].rolling(5).std()
        return df
```

## Performance Metrics

The ML analyzer is evaluated on:
- **Training Accuracy**: Performance on training set
- **Validation Accuracy**: Performance on held-out validation set
- **Win Rate**: Percentage of profitable trades (in simulation)
- **Average P&L**: Average profit per trade
- **Total Return**: Overall portfolio return

## Future Enhancements

Potential improvements:
- [ ] LSTM/GRU for sequence modeling
- [ ] Ensemble of multiple models
- [ ] Market-specific models (events, indices, etc.)
- [ ] Online learning (incremental updates)
- [ ] Sentiment analysis integration
- [ ] Cross-market correlation features

## License

MIT License - see repository root for details
