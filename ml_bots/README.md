# ML Bots - Machine Learning Trading System

Machine learning based trading bots for Kalshi prediction markets. This system provides a complete pipeline for fetching historical data, training ML models, and generating trading signals.

## Features

- **Data Pipeline**: Fetch and transform historical market data into ML-ready formats
- **Multiple ML Models**: Logistic Regression, Random Forest, Neural Networks
- **Technical Features**: RSI, MACD, moving averages, volatility, and more
- **Trading Signals**: Confidence-based trading recommendations
- **Flexible Architecture**: Easy to extend with custom models and features

## Quick Start

### 1. Install Dependencies

```bash
# Install ML dependencies
pip install pandas numpy scikit-learn torch matplotlib seaborn

# Or use requirements.txt
pip install -r requirements.txt
```

### 2. Run the Demo

```bash
# Basic demo (15 markets, 7 days, random forest)
python demo_ml_bot.py

# Custom configuration
python demo_ml_bot.py --model random_forest --markets 20 --days 10 --confidence 0.7

# Use neural network
python demo_ml_bot.py --model neural_network --markets 25 --days 14
```

### 3. Use in Your Code

```python
from ml_bots.bots.ml_trading_bot import MLTradingBot

# Initialize bot
bot = MLTradingBot(model_type='random_forest', min_confidence=0.65)

# Train model
result = bot.train_model(
    min_volume=100,
    max_markets=20,
    days_back=7,
    period_interval=60  # 1-hour candles
)

# Generate trading signals
signals = bot.generate_trading_signals(max_markets=10)

# Process signals
for signal in signals:
    print(f"{signal['action']} {signal['side']} on {signal['market']['ticker']}")
    print(f"Confidence: {signal['confidence']:.1%}")
```

## Architecture

```
ml_bots/
├── data_pipeline/           # Data fetching and transformation
│   ├── data_fetcher.py     # Fetch historical data from Kalshi
│   └── data_transformer.py # Transform to DataFrames/tensors
├── models/                  # ML model implementations
│   └── price_predictor.py  # Price prediction models
└── bots/                    # Trading bot implementations
    └── ml_trading_bot.py   # Main ML trading bot
```

## Data Pipeline

### HistoricalDataFetcher

Fetches historical market data from Kalshi API.

```python
from ml_bots.data_pipeline import HistoricalDataFetcher

fetcher = HistoricalDataFetcher()

# Fetch data for ML training
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

### DataTransformer

Transforms raw data into ML-ready formats.

```python
from ml_bots.data_pipeline import DataTransformer

transformer = DataTransformer()

# Convert candlesticks to DataFrame
df = transformer.candlesticks_to_dataframe(candlesticks)

# Add technical features
df = transformer.add_technical_features(df)

# Create labels for supervised learning
df = transformer.create_labels(df, prediction_horizon=1)

# Prepare features and labels
X, y = transformer.prepare_features_and_labels(df)

# Convert to tensors
X_tensor, y_tensor = transformer.to_torch_tensors(X, y)
```

## ML Models

### Supported Models

1. **Logistic Regression**: Fast, interpretable baseline
2. **Random Forest**: Best general-purpose model, provides feature importance
3. **Neural Network**: Deep learning with PyTorch (3-layer MLP)

### PricePredictor

```python
from ml_bots.models.price_predictor import PricePredictor

# Create model
predictor = PricePredictor(model_type='random_forest')

# Train
metrics = predictor.train(X_train, y_train, X_val, y_val)

# Predict
predictions = predictor.predict(X_test)
probabilities = predictor.predict_proba(X_test)

# Get feature importance (random forest only)
importance = predictor.get_feature_importance()

# Save/load model
predictor.save_model('model.pkl')
predictor.load_model('model.pkl')
```

## Technical Features

The data transformer automatically generates these features:

### Price Features
- `price_change`: Absolute price change
- `price_change_pct`: Percentage price change
- `ma_5`, `ma_10`, `ma_20`: Moving averages

### Technical Indicators
- `rsi_14`: Relative Strength Index (14 periods)
- `volatility_10`: Rolling standard deviation

### Volume Features
- `volume_change`: Change in volume
- `volume_ma_10`: Volume moving average

### Orderbook Features
- `spread`: Bid-ask spread

## Trading Signals

The bot generates trading signals with:

- **Market**: Market ticker and details
- **Action**: BUY or SELL
- **Side**: yes or no
- **Direction**: UP or DOWN (predicted price movement)
- **Confidence**: Prediction probability (0.0-1.0)
- **Latest Price**: Current market price

Example signal:

```python
{
    'market': {
        'ticker': 'INXD-25JAN10-T5000.00',
        'title': 'Will the S&P 500 close above 5000.00 on Jan 10?',
        'volume': 15234
    },
    'prediction': {
        'direction': 'UP',
        'confidence': 0.73,
        'latest_price': 48.5
    },
    'action': 'BUY',
    'side': 'yes'
}
```

## Demo Script Options

```bash
python demo_ml_bot.py [OPTIONS]

Options:
  --model TYPE           Model type: logistic, random_forest, neural_network
                         (default: random_forest)

  --markets N            Number of markets for training
                         (default: 15)

  --days N               Days of historical data
                         (default: 7)

  --confidence FLOAT     Minimum confidence threshold (0.0-1.0)
                         (default: 0.65)

  --signal-markets N     Number of markets to analyze for signals
                         (default: 10)

  --save-model PATH      Save trained model to file
                         (optional)
```

## Examples

### Example 1: Basic Usage

```bash
python demo_ml_bot.py
```

Output:
```
================================================================================
 ML Trading Bot Demo
================================================================================

Configuration:
  Model type: random_forest
  Training markets: 15
  Historical days: 7
  ...

✅ Training successful!
Training Statistics:
  Markets used: 15
  Total samples: 1247
  Features: 14

Model Performance:
  train_accuracy: 0.6234
  val_accuracy: 0.6012

✅ Generated 5 trading signals
```

### Example 2: Neural Network

```bash
python demo_ml_bot.py --model neural_network --days 14 --markets 25
```

### Example 3: High Confidence

```bash
python demo_ml_bot.py --confidence 0.80 --markets 30
```

### Example 4: Save Model

```bash
python demo_ml_bot.py --save-model models/my_model.pkl
```

## Extending the System

### Add Custom Features

```python
from ml_bots.data_pipeline import DataTransformer

class CustomTransformer(DataTransformer):
    def add_custom_features(self, df):
        # Add your custom features
        df['custom_feature'] = df['yes_ask_close'].rolling(3).mean()
        return df
```

### Create Custom Models

```python
from ml_bots.models.price_predictor import PricePredictor

class CustomPredictor(PricePredictor):
    def build_model(self, input_dim):
        # Implement your custom model
        pass
```

### Custom Trading Bot

```python
from ml_bots.bots.ml_trading_bot import MLTradingBot

class CustomMLBot(MLTradingBot):
    def custom_signal_logic(self, prediction):
        # Add custom logic for signal generation
        pass
```

## Performance Tips

1. **More Data**: Use more historical days (--days 14 or 30)
2. **More Markets**: Train on more markets (--markets 30+)
3. **Random Forest**: Generally performs best for this task
4. **Feature Engineering**: Add domain-specific features
5. **Ensemble Models**: Combine multiple model predictions

## Troubleshooting

### No Training Data

**Problem**: "No data fetched for training"

**Solutions**:
- Increase `--days` parameter for more historical data
- Decrease `min_volume` threshold in code
- Try different time periods (markets have varying activity)

### Low Accuracy

**Problem**: Model accuracy below 60%

**Solutions**:
- Market prediction is inherently difficult
- Try different model types (--model neural_network)
- Add more features in data_transformer.py
- Use longer historical periods (--days 30)
- Focus on specific market types

### No Signals Generated

**Problem**: "No trading signals generated"

**Solutions**:
- Lower confidence threshold (--confidence 0.55)
- Increase signal markets (--signal-markets 20)
- Ensure markets have sufficient historical data

## Disclaimer

**For educational and research purposes only.**

- Machine learning predictions are probabilistic, not guaranteed
- Past performance does not indicate future results
- Always perform additional due diligence
- Start with small positions to test strategies
- Never risk more than you can afford to lose

## Future Enhancements

Potential improvements:

- [ ] LSTM/GRU models for sequence prediction
- [ ] Reinforcement learning for strategy optimization
- [ ] Multi-market correlation analysis
- [ ] Sentiment analysis from market descriptions
- [ ] Portfolio optimization
- [ ] Backtesting framework
- [ ] Live trading integration
- [ ] Model performance tracking

## License

MIT License - see repository root for details
