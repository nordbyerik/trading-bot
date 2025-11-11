"""
ML Predictor Analyzer

Uses machine learning to predict price movements and identify trading opportunities.
Trains on historical candlestick data with technical features.
"""

import logging
import sys
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

# Add parent directory to path for ml_bots imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from analyzers.base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength
from ml_bots.data_pipeline import HistoricalDataFetcher, DataTransformer
from ml_bots.models.price_predictor import PricePredictor

logger = logging.getLogger(__name__)


class MLPredictorAnalyzer(BaseAnalyzer):
    """
    Machine learning based analyzer that predicts price movements.

    Uses historical data to train a model, then makes predictions on current markets.
    Generates trading opportunities based on prediction confidence.
    """

    def _setup(self) -> None:
        """Initialize ML components."""
        # Apply default config
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

        # Initialize ML components
        self.fetcher = HistoricalDataFetcher(self.kalshi_client)
        self.transformer = DataTransformer()

        model_type = self.config.get('model_type', 'random_forest')
        self.predictor = PricePredictor(model_type=model_type)

        self.is_trained = False
        self.training_markets = []

        logger.info(f"MLPredictorAnalyzer initialized (model={model_type})")

    def get_name(self) -> str:
        return "ML Predictor"

    def get_description(self) -> str:
        return (
            "Uses machine learning to predict price movements based on "
            "historical patterns and technical indicators"
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            # Model configuration
            "model_type": "random_forest",  # logistic, random_forest, neural_network

            # Training parameters
            "train_on_first_run": True,  # Auto-train on first analyze() call
            "training_markets": 15,  # Markets to train on
            "training_days": 7,  # Days of historical data
            "training_interval": 60,  # Candlestick interval in minutes
            "prediction_horizon": 1,  # Periods ahead to predict

            # Signal generation - Hard thresholds (strict)
            "hard_min_confidence": 0.70,  # Minimum confidence for hard opportunities
            "hard_high_confidence": 0.80,  # High confidence threshold for hard

            # Signal generation - Soft thresholds (relaxed)
            "soft_min_confidence": 0.60,  # Minimum confidence for soft opportunities
            "soft_high_confidence": 0.70,  # High confidence threshold for soft

            # Edge estimation
            "edge_multiplier": 10,  # Multiplier for confidence to estimate edge
        }

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets using ML predictions.

        Args:
            markets: List of market data dictionaries

        Returns:
            List of ML-based opportunities
        """
        if not self.kalshi_client:
            logger.warning("MLPredictorAnalyzer requires kalshi_client for historical data")
            return []

        # Train model if not yet trained
        if not self.is_trained and self.config.get('train_on_first_run', True):
            logger.info("Training ML model on first run...")
            success = self._train_model()
            if not success:
                logger.error("Failed to train ML model")
                return []

        if not self.is_trained:
            logger.warning("ML model not trained yet")
            return []

        opportunities = []

        for market in markets:
            opportunity = self._analyze_market(market)
            if opportunity:
                opportunities.append(opportunity)

        logger.info(
            f"MLPredictorAnalyzer found {len(opportunities)} opportunities "
            f"out of {len(markets)} markets"
        )

        return opportunities

    def _train_model(self) -> bool:
        """
        Train the ML model on historical data.

        Returns:
            True if training successful, False otherwise
        """
        try:
            logger.info("Fetching training data...")
            dataset = self.fetcher.fetch_dataset_for_ml(
                min_volume=50,
                max_markets=self.config['training_markets'],
                days_back=self.config['training_days'],
                period_interval=self.config['training_interval']
            )

            if not dataset:
                logger.error("No training data available")
                return False

            self.training_markets = [d['market_ticker'] for d in dataset]
            logger.info(f"Fetched data for {len(dataset)} markets")

            # Transform data
            logger.info("Transforming data...")
            df = self.transformer.transform_dataset(
                dataset,
                add_features=True,
                create_labels=True,
                prediction_horizon=self.config['prediction_horizon']
            )

            if df.empty:
                logger.error("No valid data after transformation")
                return False

            # Prepare features and labels
            X, y = self.transformer.prepare_features_and_labels(df)

            if X.empty or y.empty:
                logger.error("No valid features/labels")
                return False

            logger.info(f"Prepared {len(X)} samples with {X.shape[1]} features")

            # Split data (time-based, no shuffle)
            X_train, X_test, y_train, y_test = self.transformer.train_test_split(
                X, y, test_size=0.2, shuffle=False
            )

            # Train model
            logger.info("Training model...")
            metrics = self.predictor.train(X_train, y_train, X_test, y_test)

            self.is_trained = True
            logger.info(f"Training complete: {metrics}")

            return True

        except Exception as e:
            logger.error(f"Error training model: {e}", exc_info=True)
            return False

    def _analyze_market(self, market: Dict[str, Any]) -> Optional[Opportunity]:
        """
        Analyze a single market and generate opportunity if prediction is confident.

        Args:
            market: Market data dictionary

        Returns:
            Opportunity if confident prediction, None otherwise
        """
        ticker = market.get('ticker')
        series_ticker = market.get('series_ticker')

        if not ticker or not series_ticker:
            return None

        # Skip if this was a training market (avoid overfitting signals)
        if ticker in self.training_markets:
            logger.debug(f"Skipping training market {ticker}")
            return None

        # Fetch recent historical data
        candlesticks = self.fetcher.fetch_market_candlesticks(
            series_ticker=series_ticker,
            market_ticker=ticker,
            days_back=3,  # Use fewer days for prediction
            period_interval=60
        )

        if not candlesticks or len(candlesticks) < 10:
            logger.debug(f"Insufficient data for {ticker}")
            return None

        # Transform to DataFrame with features
        df = self.transformer.candlesticks_to_dataframe(candlesticks, ticker)
        df = self.transformer.add_technical_features(df)

        # Prepare features
        X, _ = self.transformer.prepare_features_and_labels(df)

        if X.empty:
            logger.debug(f"No valid features for {ticker}")
            return None

        # Use most recent data point for prediction
        X_latest = X.tail(1)

        try:
            # Make prediction
            prediction = self.predictor.predict(X_latest)[0]
            confidence_raw = self.predictor.predict_proba(X_latest)[0]

            # Adjust confidence based on prediction direction
            # confidence_raw is probability of class 1 (price increase)
            if prediction == 0:
                # Predicting decrease, use inverse probability
                confidence = 1 - confidence_raw
                direction = 'down'
            else:
                confidence = confidence_raw
                direction = 'up'

            # Determine opportunity strength and confidence level
            strength = None
            conf_level = None

            # Check hard thresholds
            hard_min = self.config['hard_min_confidence']
            hard_high = self.config['hard_high_confidence']

            if confidence >= hard_min:
                strength = OpportunityStrength.HARD
                if confidence >= hard_high:
                    conf_level = ConfidenceLevel.HIGH
                else:
                    conf_level = ConfidenceLevel.MEDIUM
            else:
                # Check soft thresholds
                soft_min = self.config['soft_min_confidence']
                soft_high = self.config['soft_high_confidence']

                if confidence >= soft_min:
                    strength = OpportunityStrength.SOFT
                    if confidence >= soft_high:
                        conf_level = ConfidenceLevel.MEDIUM
                    else:
                        conf_level = ConfidenceLevel.LOW
                else:
                    # Below all thresholds
                    return None

            # Get current price
            current_price = df['yes_ask_close'].iloc[-1] if 'yes_ask_close' in df.columns else None
            if current_price is None:
                return None

            # Estimate edge based on confidence
            # Higher confidence = larger expected edge
            confidence_above_threshold = confidence - self.config[f'{strength.value}_min_confidence']
            estimated_edge_cents = confidence_above_threshold * self.config['edge_multiplier']
            estimated_edge_percent = (estimated_edge_cents / current_price) * 100 if current_price > 0 else 0

            # Build reasoning
            title = market.get('title', 'Unknown Market')
            model_type = self.predictor.model_type
            reasoning = (
                f"ML model ({model_type}) predicts price moving {direction.upper()} "
                f"with {confidence:.1%} confidence. "
                f"Based on {len(candlesticks)} recent candlesticks and {X.shape[1]} features."
            )

            # Add feature importance if available
            additional_data = {
                'prediction': int(prediction),
                'confidence': float(confidence),
                'direction': direction,
                'model_type': model_type,
                'current_price': float(current_price),
                'n_candlesticks': len(candlesticks),
                'n_features': X.shape[1]
            }

            # Add top features if using random forest
            if model_type == 'random_forest':
                feature_importance = self.predictor.get_feature_importance()
                if feature_importance is not None:
                    top_features = feature_importance.head(5).to_dict('records')
                    additional_data['top_features'] = top_features
                    # Add to reasoning
                    top_feat_names = [f['feature'] for f in top_features[:3]]
                    reasoning += f" Top features: {', '.join(top_feat_names)}."

            opportunity = Opportunity(
                opportunity_type=OpportunityType.MISPRICING,  # ML prediction is a type of mispricing detection
                confidence=conf_level,
                strength=strength,
                timestamp=datetime.now(),
                market_tickers=[ticker],
                market_titles=[title],
                market_urls=[self._make_market_url(ticker)],
                current_prices={ticker: float(current_price)},
                estimated_edge_cents=estimated_edge_cents,
                estimated_edge_percent=estimated_edge_percent,
                reasoning=reasoning,
                additional_data=additional_data
            )

            logger.info(
                f"[ML] {ticker}: {direction.upper()} prediction "
                f"(confidence={confidence:.1%}, strength={strength.value})"
            )

            return opportunity

        except Exception as e:
            logger.error(f"Error analyzing {ticker}: {e}", exc_info=True)
            return None

    def train_now(self) -> bool:
        """
        Manually trigger model training.

        Returns:
            True if training successful, False otherwise
        """
        return self._train_model()

    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the trained model.

        Returns:
            Dictionary with model information
        """
        info = {
            'model_type': self.predictor.model_type,
            'is_trained': self.is_trained,
            'training_markets': len(self.training_markets),
            'config': self.config
        }

        if self.is_trained and self.predictor.model_type == 'random_forest':
            feature_importance = self.predictor.get_feature_importance()
            if feature_importance is not None:
                info['top_features'] = feature_importance.head(10).to_dict('records')

        return info
