"""
ML Trading Bot

Machine learning based trading bot that:
1. Fetches historical market data
2. Trains a price prediction model
3. Makes predictions on current market data
4. Generates trading signals based on predictions
"""

import logging
from typing import Optional, List, Dict, Tuple
import sys
import os

# Add parent directories to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from ml_bots.data_pipeline import HistoricalDataFetcher, DataTransformer
from ml_bots.models.price_predictor import PricePredictor
from kalshi_client import KalshiDataClient

logger = logging.getLogger(__name__)


class MLTradingBot:
    """
    ML-based trading bot for Kalshi markets.

    The bot:
    1. Discovers active markets
    2. Fetches historical data
    3. Trains an ML model
    4. Makes predictions and generates trading signals
    """

    def __init__(
        self,
        client: Optional[KalshiDataClient] = None,
        model_type: str = 'random_forest',
        min_confidence: float = 0.6
    ):
        """
        Initialize the ML trading bot.

        Args:
            client: KalshiDataClient instance (creates new if None)
            model_type: Type of ML model ('logistic', 'random_forest', 'neural_network')
            min_confidence: Minimum prediction confidence for trading signals (0.0-1.0)
        """
        self.client = client or KalshiDataClient()
        self.fetcher = HistoricalDataFetcher(self.client)
        self.transformer = DataTransformer()
        self.predictor = PricePredictor(model_type=model_type)
        self.min_confidence = min_confidence

        self.is_trained = False
        self.training_markets = []

        logger.info(
            f"MLTradingBot initialized (model={model_type}, "
            f"min_confidence={min_confidence})"
        )

    def train_model(
        self,
        min_volume: int = 100,
        max_markets: int = 20,
        days_back: int = 7,
        period_interval: int = 60,
        prediction_horizon: int = 1
    ) -> Dict:
        """
        Train the ML model on historical data.

        Args:
            min_volume: Minimum market volume
            max_markets: Maximum number of markets for training
            days_back: Days of historical data
            period_interval: Candlestick interval in minutes
            prediction_horizon: Periods ahead to predict

        Returns:
            Dictionary with training metrics
        """
        logger.info("Starting model training...")

        # 1. Fetch historical dataset
        logger.info("Fetching historical data...")
        dataset = self.fetcher.fetch_dataset_for_ml(
            min_volume=min_volume,
            max_markets=max_markets,
            days_back=days_back,
            period_interval=period_interval
        )

        if not dataset:
            logger.error("No data fetched for training")
            return {'error': 'No data available'}

        self.training_markets = [d['market_ticker'] for d in dataset]
        logger.info(f"Fetched data for {len(dataset)} markets")

        # 2. Transform data
        logger.info("Transforming data...")
        df = self.transformer.transform_dataset(
            dataset,
            add_features=True,
            create_labels=True,
            prediction_horizon=prediction_horizon
        )

        if df.empty:
            logger.error("No valid data after transformation")
            return {'error': 'Data transformation failed'}

        logger.info(f"Transformed data: {len(df)} samples")

        # 3. Prepare features and labels
        X, y = self.transformer.prepare_features_and_labels(df)

        if X.empty or y.empty:
            logger.error("No valid features/labels")
            return {'error': 'Feature preparation failed'}

        logger.info(f"Prepared {len(X)} samples with {X.shape[1]} features")

        # 4. Split data (use time-based split, no shuffle)
        X_train, X_test, y_train, y_test = self.transformer.train_test_split(
            X, y, test_size=0.2, shuffle=False
        )

        # 5. Train model
        logger.info("Training model...")
        metrics = self.predictor.train(X_train, y_train, X_test, y_test)

        self.is_trained = True
        logger.info(f"Training complete: {metrics}")

        return {
            'success': True,
            'metrics': metrics,
            'n_markets': len(dataset),
            'n_samples': len(df),
            'n_features': X.shape[1],
            'training_markets': self.training_markets
        }

    def predict_market(
        self,
        market_ticker: str,
        series_ticker: str,
        days_back: int = 7,
        period_interval: int = 60
    ) -> Optional[Dict]:
        """
        Make a prediction for a specific market.

        Args:
            market_ticker: Market ticker
            series_ticker: Series ticker
            days_back: Days of historical data to use
            period_interval: Candlestick interval in minutes

        Returns:
            Dictionary with prediction and confidence, or None if error
        """
        if not self.is_trained:
            logger.error("Model not trained yet. Call train_model() first.")
            return None

        # Fetch recent data for this market
        candlesticks = self.fetcher.fetch_market_candlesticks(
            series_ticker=series_ticker,
            market_ticker=market_ticker,
            days_back=days_back,
            period_interval=period_interval
        )

        if not candlesticks:
            logger.warning(f"No candlesticks for {market_ticker}")
            return None

        # Transform to DataFrame
        df = self.transformer.candlesticks_to_dataframe(candlesticks, market_ticker)
        df = self.transformer.add_technical_features(df)

        # Prepare features (use latest data point)
        X, _ = self.transformer.prepare_features_and_labels(df)

        if X.empty:
            logger.warning(f"No valid features for {market_ticker}")
            return None

        # Use most recent data point for prediction
        X_latest = X.tail(1)

        # Make prediction
        prediction = self.predictor.predict(X_latest)[0]
        confidence = self.predictor.predict_proba(X_latest)[0]

        # Adjust confidence based on prediction direction
        # confidence is probability of class 1 (price increase)
        if prediction == 0:
            # If predicting decrease, confidence is 1 - probability
            confidence = 1 - confidence

        result = {
            'market_ticker': market_ticker,
            'prediction': int(prediction),
            'confidence': float(confidence),
            'direction': 'UP' if prediction == 1 else 'DOWN',
            'latest_price': float(df['yes_ask_close'].iloc[-1]) if 'yes_ask_close' in df.columns else None
        }

        logger.info(
            f"Prediction for {market_ticker}: {result['direction']} "
            f"(confidence={result['confidence']:.3f})"
        )

        return result

    def generate_trading_signals(
        self,
        markets: Optional[List[Dict]] = None,
        min_volume: int = 50,
        max_markets: int = 10
    ) -> List[Dict]:
        """
        Generate trading signals for multiple markets.

        Args:
            markets: List of market dicts (fetches if None)
            min_volume: Minimum volume threshold
            max_markets: Maximum markets to analyze

        Returns:
            List of trading signal dictionaries
        """
        if not self.is_trained:
            logger.error("Model not trained yet. Call train_model() first.")
            return []

        # Discover markets if not provided
        if markets is None:
            logger.info("Discovering active markets...")
            markets = self.fetcher.discover_active_markets(
                min_volume=min_volume,
                max_markets=max_markets
            )

        if not markets:
            logger.warning("No markets to analyze")
            return []

        logger.info(f"Generating signals for {len(markets)} markets...")

        signals = []

        for market in markets:
            market_ticker = market.get('ticker')
            series_ticker = market.get('series_ticker')

            if not market_ticker or not series_ticker:
                continue

            # Make prediction
            prediction = self.predict_market(
                market_ticker=market_ticker,
                series_ticker=series_ticker
            )

            if prediction is None:
                continue

            # Only generate signal if confidence meets threshold
            if prediction['confidence'] >= self.min_confidence:
                signal = {
                    'market': market,
                    'prediction': prediction,
                    'action': 'BUY' if prediction['direction'] == 'UP' else 'SELL',
                    'side': 'yes' if prediction['direction'] == 'UP' else 'no',
                    'confidence': prediction['confidence']
                }
                signals.append(signal)

        logger.info(
            f"Generated {len(signals)} signals "
            f"(above confidence threshold of {self.min_confidence})"
        )

        return signals

    def get_model_info(self) -> Dict:
        """
        Get information about the trained model.

        Returns:
            Dictionary with model information
        """
        info = {
            'model_type': self.predictor.model_type,
            'is_trained': self.is_trained,
            'min_confidence': self.min_confidence,
            'training_markets': self.training_markets
        }

        # Add feature importance if available
        if self.is_trained and self.predictor.model_type == 'random_forest':
            feature_importance = self.predictor.get_feature_importance()
            if feature_importance is not None:
                info['top_features'] = feature_importance.head(10).to_dict('records')

        return info

    def save_model(self, filepath: str):
        """
        Save the trained model.

        Args:
            filepath: Path to save the model
        """
        if not self.is_trained:
            logger.warning("No trained model to save")
            return

        self.predictor.save_model(filepath)
        logger.info(f"Model saved to {filepath}")

    def load_model(self, filepath: str):
        """
        Load a previously trained model.

        Args:
            filepath: Path to the saved model
        """
        self.predictor.load_model(filepath)
        self.is_trained = True
        logger.info(f"Model loaded from {filepath}")


if __name__ == "__main__":
    # Demo usage
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 80)
    print("ML Trading Bot Demo")
    print("=" * 80)

    # Initialize bot
    bot = MLTradingBot(model_type='random_forest', min_confidence=0.6)

    # Train model
    print("\n--- Training Model ---")
    training_result = bot.train_model(
        min_volume=50,
        max_markets=10,
        days_back=5,
        period_interval=60
    )

    if training_result.get('success'):
        print(f"\nTraining successful!")
        print(f"Markets used: {training_result['n_markets']}")
        print(f"Total samples: {training_result['n_samples']}")
        print(f"Features: {training_result['n_features']}")
        print(f"Metrics: {training_result['metrics']}")

        # Get model info
        print("\n--- Model Info ---")
        info = bot.get_model_info()
        print(f"Model type: {info['model_type']}")
        print(f"Trained on {len(info['training_markets'])} markets")

        if 'top_features' in info:
            print("\nTop 5 features:")
            for feat in info['top_features'][:5]:
                print(f"  {feat['feature']}: {feat['importance']:.4f}")

        # Generate trading signals
        print("\n--- Generating Trading Signals ---")
        signals = bot.generate_trading_signals(
            min_volume=50,
            max_markets=5
        )

        print(f"\nGenerated {len(signals)} trading signals:")
        for i, signal in enumerate(signals, 1):
            market = signal['market']
            pred = signal['prediction']
            print(f"\n{i}. {market['ticker']}")
            print(f"   Action: {signal['action']} {signal['side']}")
            print(f"   Direction: {pred['direction']}")
            print(f"   Confidence: {pred['confidence']:.3f}")
            print(f"   Current price: {pred['latest_price']}¢")

    else:
        print(f"\nTraining failed: {training_result.get('error')}")
