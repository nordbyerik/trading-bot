"""
Data Transformer

Transforms raw Kalshi market data into formats suitable for machine learning:
- Pandas DataFrames for analysis
- PyTorch tensors for deep learning
- Feature engineering and normalization
"""

import logging
from typing import List, Dict, Optional, Tuple, Union
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class DataTransformer:
    """
    Transforms Kalshi historical data into ML-ready formats.

    Supports:
    - Converting candlesticks to DataFrames
    - Feature engineering (technical indicators, price changes, etc.)
    - Normalization and scaling
    - Train/test splitting
    - PyTorch tensor conversion
    """

    def __init__(self):
        """Initialize the data transformer."""
        logger.info("DataTransformer initialized")

    def candlesticks_to_dataframe(
        self,
        candlesticks: List[Dict],
        market_ticker: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Convert candlestick data to a pandas DataFrame.

        Args:
            candlesticks: List of candlestick dictionaries from API
            market_ticker: Optional market ticker to add as column

        Returns:
            DataFrame with OHLC data, volume, and timestamps
        """
        if not candlesticks:
            logger.warning("Empty candlesticks list provided")
            return pd.DataFrame()

        # Extract relevant fields
        data = []
        for candle in candlesticks:
            row = {
                'timestamp': pd.to_datetime(candle.get('ts', 0), unit='s'),
                'yes_ask_open': candle.get('yes_ask_open'),
                'yes_ask_high': candle.get('yes_ask_high'),
                'yes_ask_low': candle.get('yes_ask_low'),
                'yes_ask_close': candle.get('yes_ask_close'),
                'yes_bid_open': candle.get('yes_bid_open'),
                'yes_bid_high': candle.get('yes_bid_high'),
                'yes_bid_low': candle.get('yes_bid_low'),
                'yes_bid_close': candle.get('yes_bid_close'),
                'volume': candle.get('volume', 0),
                'open_interest': candle.get('open_interest', 0),
            }

            # Add market ticker if provided
            if market_ticker:
                row['market_ticker'] = market_ticker

            data.append(row)

        df = pd.DataFrame(data)

        # Sort by timestamp
        if not df.empty:
            df = df.sort_values('timestamp').reset_index(drop=True)

        logger.info(f"Created DataFrame with {len(df)} rows")
        return df

    def add_technical_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add technical analysis features to the DataFrame.

        Features include:
        - Price changes (absolute and percentage)
        - Moving averages (5, 10, 20 periods)
        - RSI (Relative Strength Index)
        - Volatility (rolling standard deviation)
        - Volume changes

        Args:
            df: DataFrame with OHLC data

        Returns:
            DataFrame with added technical features
        """
        if df.empty:
            return df

        df = df.copy()

        # Use yes_ask_close as primary price
        price_col = 'yes_ask_close'

        if price_col not in df.columns or df[price_col].isna().all():
            logger.warning(f"No valid {price_col} data for feature engineering")
            return df

        # Price changes
        df['price_change'] = df[price_col].diff()
        df['price_change_pct'] = df[price_col].pct_change() * 100

        # Moving averages
        for window in [5, 10, 20]:
            df[f'ma_{window}'] = df[price_col].rolling(window=window).mean()

        # RSI (Relative Strength Index)
        df['rsi_14'] = self._calculate_rsi(df[price_col], period=14)

        # Volatility (rolling standard deviation)
        df['volatility_10'] = df[price_col].rolling(window=10).std()

        # Volume changes
        if 'volume' in df.columns:
            df['volume_change'] = df['volume'].diff()
            df['volume_ma_10'] = df['volume'].rolling(window=10).mean()

        # Spread (bid-ask spread)
        if 'yes_ask_close' in df.columns and 'yes_bid_close' in df.columns:
            df['spread'] = df['yes_ask_close'] - df['yes_bid_close']

        logger.info(f"Added technical features to DataFrame")
        return df

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """
        Calculate Relative Strength Index (RSI).

        Args:
            prices: Series of prices
            period: RSI period (default: 14)

        Returns:
            Series of RSI values (0-100)
        """
        delta = prices.diff()

        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def create_labels(
        self,
        df: pd.DataFrame,
        prediction_horizon: int = 1,
        price_col: str = 'yes_ask_close',
        threshold: float = 0.5
    ) -> pd.DataFrame:
        """
        Create target labels for supervised learning.

        Label is 1 if price increases by more than threshold, 0 otherwise.

        Args:
            df: DataFrame with price data
            prediction_horizon: Number of periods ahead to predict
            price_col: Price column to use for labels
            threshold: Minimum price change percentage to label as 1

        Returns:
            DataFrame with 'label' column added
        """
        if df.empty or price_col not in df.columns:
            return df

        df = df.copy()

        # Calculate future price change
        future_price = df[price_col].shift(-prediction_horizon)
        price_change_pct = ((future_price - df[price_col]) / df[price_col]) * 100

        # Create binary label
        df['label'] = (price_change_pct > threshold).astype(int)

        # Remove rows with NaN labels (last prediction_horizon rows)
        df = df[:-prediction_horizon]

        logger.info(
            f"Created labels with {prediction_horizon} period horizon "
            f"({df['label'].sum()} positive, {len(df) - df['label'].sum()} negative)"
        )

        return df

    def prepare_features_and_labels(
        self,
        df: pd.DataFrame,
        feature_cols: Optional[List[str]] = None,
        label_col: str = 'label'
    ) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Prepare features (X) and labels (y) for ML training.

        Args:
            df: DataFrame with features and labels
            feature_cols: List of feature column names (None = auto-detect)
            label_col: Name of label column

        Returns:
            Tuple of (X_features, y_labels)
        """
        if df.empty:
            return pd.DataFrame(), pd.Series()

        # Auto-detect feature columns if not provided
        if feature_cols is None:
            exclude_cols = [
                'timestamp', 'market_ticker', label_col,
                'yes_ask_open', 'yes_ask_high', 'yes_ask_low',
                'yes_bid_open', 'yes_bid_high', 'yes_bid_low'
            ]
            feature_cols = [col for col in df.columns if col not in exclude_cols]

        # Extract features and labels
        X = df[feature_cols].copy()
        y = df[label_col].copy() if label_col in df.columns else pd.Series()

        # Drop rows with NaN values
        if not y.empty:
            valid_mask = ~(X.isna().any(axis=1) | y.isna())
            X = X[valid_mask]
            y = y[valid_mask]
        else:
            X = X.dropna()

        logger.info(
            f"Prepared features: {X.shape[0]} samples, {X.shape[1]} features"
        )

        return X, y

    def to_numpy(
        self,
        X: pd.DataFrame,
        y: Optional[pd.Series] = None
    ) -> Union[np.ndarray, Tuple[np.ndarray, np.ndarray]]:
        """
        Convert DataFrame/Series to numpy arrays.

        Args:
            X: Feature DataFrame
            y: Optional label Series

        Returns:
            Numpy array(s)
        """
        X_array = X.values.astype(np.float32)

        if y is not None:
            y_array = y.values.astype(np.float32)
            return X_array, y_array

        return X_array

    def to_torch_tensors(
        self,
        X: pd.DataFrame,
        y: Optional[pd.Series] = None
    ):
        """
        Convert DataFrame/Series to PyTorch tensors.

        Args:
            X: Feature DataFrame
            y: Optional label Series

        Returns:
            PyTorch tensor(s)
        """
        try:
            import torch
        except ImportError:
            logger.error("PyTorch not installed. Install with: pip install torch")
            raise

        X_array, y_array = self.to_numpy(X, y) if y is not None else (self.to_numpy(X), None)

        X_tensor = torch.tensor(X_array, dtype=torch.float32)

        if y_array is not None:
            y_tensor = torch.tensor(y_array, dtype=torch.float32)
            return X_tensor, y_tensor

        return X_tensor

    def normalize_features(
        self,
        X: pd.DataFrame,
        method: str = 'standard'
    ) -> Tuple[pd.DataFrame, Dict]:
        """
        Normalize features using standard scaling or min-max scaling.

        Args:
            X: Feature DataFrame
            method: 'standard' (z-score) or 'minmax' (0-1 scaling)

        Returns:
            Tuple of (normalized_df, normalization_params)
        """
        from sklearn.preprocessing import StandardScaler, MinMaxScaler

        X_normalized = X.copy()
        params = {}

        if method == 'standard':
            scaler = StandardScaler()
        elif method == 'minmax':
            scaler = MinMaxScaler()
        else:
            raise ValueError(f"Unknown normalization method: {method}")

        X_normalized[X.columns] = scaler.fit_transform(X)

        params['scaler'] = scaler
        params['method'] = method
        params['feature_names'] = X.columns.tolist()

        logger.info(f"Normalized features using {method} scaling")
        return X_normalized, params

    def train_test_split(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        test_size: float = 0.2,
        shuffle: bool = False
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
        """
        Split data into train and test sets.

        Args:
            X: Features
            y: Labels
            test_size: Proportion of test set (0.0-1.0)
            shuffle: Whether to shuffle before splitting (False for time series)

        Returns:
            Tuple of (X_train, X_test, y_train, y_test)
        """
        from sklearn.model_selection import train_test_split as sklearn_split

        X_train, X_test, y_train, y_test = sklearn_split(
            X, y, test_size=test_size, shuffle=shuffle
        )

        logger.info(
            f"Split data: train={len(X_train)}, test={len(X_test)} "
            f"(test_size={test_size})"
        )

        return X_train, X_test, y_train, y_test

    def transform_dataset(
        self,
        dataset: List[Dict],
        add_features: bool = True,
        create_labels: bool = True,
        prediction_horizon: int = 1
    ) -> pd.DataFrame:
        """
        Transform a complete dataset (from HistoricalDataFetcher) into a single DataFrame.

        Args:
            dataset: List of market data dictionaries with candlesticks
            add_features: Whether to add technical features
            create_labels: Whether to create prediction labels
            prediction_horizon: Periods ahead for labels

        Returns:
            Combined DataFrame with all markets
        """
        all_dfs = []

        for data in dataset:
            market_ticker = data.get('market_ticker')
            candlesticks = data.get('candlesticks', [])

            if not candlesticks:
                continue

            # Convert to DataFrame
            df = self.candlesticks_to_dataframe(candlesticks, market_ticker)

            if df.empty:
                continue

            # Add features
            if add_features:
                df = self.add_technical_features(df)

            # Create labels
            if create_labels:
                df = self.create_labels(
                    df,
                    prediction_horizon=prediction_horizon
                )

            all_dfs.append(df)

        # Combine all DataFrames
        if all_dfs:
            combined_df = pd.concat(all_dfs, ignore_index=True)
            logger.info(
                f"Transformed {len(all_dfs)} markets into combined DataFrame "
                f"with {len(combined_df)} total rows"
            )
            return combined_df
        else:
            logger.warning("No data to transform")
            return pd.DataFrame()


if __name__ == "__main__":
    # Demo usage
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 80)
    print("Data Transformer Demo")
    print("=" * 80)

    # Create sample candlestick data
    import time
    now = int(time.time())
    sample_candlesticks = [
        {
            'ts': now - i * 3600,
            'yes_ask_open': 50 + i,
            'yes_ask_high': 55 + i,
            'yes_ask_low': 48 + i,
            'yes_ask_close': 52 + i,
            'yes_bid_open': 48 + i,
            'yes_bid_high': 53 + i,
            'yes_bid_low': 46 + i,
            'yes_bid_close': 50 + i,
            'volume': 100 + i * 10,
            'open_interest': 500
        }
        for i in range(30)
    ]

    transformer = DataTransformer()

    print("\n--- Converting to DataFrame ---")
    df = transformer.candlesticks_to_dataframe(
        sample_candlesticks,
        market_ticker='TEST-MARKET'
    )
    print(df.head())

    print("\n--- Adding Technical Features ---")
    df = transformer.add_technical_features(df)
    print(f"Features added: {df.columns.tolist()}")
    print(df[['timestamp', 'yes_ask_close', 'ma_5', 'ma_10', 'rsi_14']].tail())

    print("\n--- Creating Labels ---")
    df = transformer.create_labels(df, prediction_horizon=1, threshold=0.5)
    print(f"Labels: {df['label'].value_counts().to_dict()}")

    print("\n--- Preparing Features and Labels ---")
    X, y = transformer.prepare_features_and_labels(df)
    print(f"X shape: {X.shape}")
    print(f"y shape: {y.shape}")
    print(f"Features: {X.columns.tolist()}")

    print("\n--- Converting to Numpy ---")
    X_array, y_array = transformer.to_numpy(X, y)
    print(f"X array shape: {X_array.shape}")
    print(f"y array shape: {y_array.shape}")
