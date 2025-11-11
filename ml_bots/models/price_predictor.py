"""
Price Predictor Model

Simple ML model for predicting price movements in Kalshi markets.
Supports both traditional ML (logistic regression, random forest) and
neural networks (PyTorch).
"""

import logging
from typing import Optional, Dict, Tuple, List
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class PricePredictor:
    """
    Price prediction model using scikit-learn or PyTorch.

    Predicts whether market price will increase or decrease.
    """

    def __init__(self, model_type: str = 'logistic'):
        """
        Initialize the price predictor.

        Args:
            model_type: Type of model to use
                - 'logistic': Logistic Regression
                - 'random_forest': Random Forest Classifier
                - 'neural_network': Simple PyTorch neural network
        """
        self.model_type = model_type
        self.model = None
        self.is_trained = False
        self.feature_names = None

        logger.info(f"PricePredictor initialized with model_type={model_type}")

    def build_model(self, input_dim: Optional[int] = None):
        """
        Build the ML model.

        Args:
            input_dim: Number of input features (required for neural_network)
        """
        if self.model_type == 'logistic':
            from sklearn.linear_model import LogisticRegression
            self.model = LogisticRegression(max_iter=1000, random_state=42)
            logger.info("Built Logistic Regression model")

        elif self.model_type == 'random_forest':
            from sklearn.ensemble import RandomForestClassifier
            self.model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42
            )
            logger.info("Built Random Forest model")

        elif self.model_type == 'neural_network':
            if input_dim is None:
                raise ValueError("input_dim required for neural_network model")

            try:
                import torch
                import torch.nn as nn
            except ImportError:
                raise ImportError("PyTorch required for neural_network model")

            # Simple 3-layer neural network
            class SimpleNN(nn.Module):
                def __init__(self, input_dim):
                    super().__init__()
                    self.fc1 = nn.Linear(input_dim, 64)
                    self.fc2 = nn.Linear(64, 32)
                    self.fc3 = nn.Linear(32, 1)
                    self.relu = nn.ReLU()
                    self.sigmoid = nn.Sigmoid()
                    self.dropout = nn.Dropout(0.2)

                def forward(self, x):
                    x = self.relu(self.fc1(x))
                    x = self.dropout(x)
                    x = self.relu(self.fc2(x))
                    x = self.dropout(x)
                    x = self.sigmoid(self.fc3(x))
                    return x

            self.model = SimpleNN(input_dim)
            logger.info(f"Built Neural Network model (input_dim={input_dim})")

        else:
            raise ValueError(f"Unknown model_type: {self.model_type}")

    def train(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: Optional[pd.DataFrame] = None,
        y_val: Optional[pd.Series] = None,
        epochs: int = 50,
        batch_size: int = 32
    ) -> Dict:
        """
        Train the model.

        Args:
            X_train: Training features
            y_train: Training labels
            X_val: Validation features (optional)
            y_val: Validation labels (optional)
            epochs: Number of epochs (for neural networks)
            batch_size: Batch size (for neural networks)

        Returns:
            Dictionary with training metrics
        """
        self.feature_names = X_train.columns.tolist()

        # Build model if not already built
        if self.model is None:
            self.build_model(input_dim=X_train.shape[1])

        if self.model_type in ['logistic', 'random_forest']:
            # Scikit-learn models
            logger.info(f"Training {self.model_type} model...")
            self.model.fit(X_train.values, y_train.values)

            train_score = self.model.score(X_train.values, y_train.values)
            metrics = {'train_accuracy': train_score}

            if X_val is not None and y_val is not None:
                val_score = self.model.score(X_val.values, y_val.values)
                metrics['val_accuracy'] = val_score

            logger.info(f"Training complete: {metrics}")
            self.is_trained = True
            return metrics

        elif self.model_type == 'neural_network':
            # PyTorch neural network
            import torch
            import torch.nn as nn
            import torch.optim as optim
            from torch.utils.data import TensorDataset, DataLoader

            logger.info(f"Training neural network for {epochs} epochs...")

            # Convert to tensors
            X_train_tensor = torch.tensor(X_train.values, dtype=torch.float32)
            y_train_tensor = torch.tensor(y_train.values, dtype=torch.float32).reshape(-1, 1)

            # Create data loader
            train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
            train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

            # Loss and optimizer
            criterion = nn.BCELoss()
            optimizer = optim.Adam(self.model.parameters(), lr=0.001)

            # Training loop
            for epoch in range(epochs):
                self.model.train()
                total_loss = 0
                correct = 0
                total = 0

                for batch_X, batch_y in train_loader:
                    optimizer.zero_grad()
                    outputs = self.model(batch_X)
                    loss = criterion(outputs, batch_y)
                    loss.backward()
                    optimizer.step()

                    total_loss += loss.item()
                    predicted = (outputs >= 0.5).float()
                    correct += (predicted == batch_y).sum().item()
                    total += batch_y.size(0)

                train_accuracy = correct / total

                if (epoch + 1) % 10 == 0:
                    logger.info(
                        f"Epoch {epoch + 1}/{epochs}, "
                        f"Loss: {total_loss / len(train_loader):.4f}, "
                        f"Accuracy: {train_accuracy:.4f}"
                    )

            metrics = {'train_accuracy': train_accuracy, 'final_loss': total_loss / len(train_loader)}

            # Validation
            if X_val is not None and y_val is not None:
                val_accuracy = self._evaluate_nn(X_val, y_val)
                metrics['val_accuracy'] = val_accuracy

            logger.info(f"Training complete: {metrics}")
            self.is_trained = True
            return metrics

    def _evaluate_nn(self, X_val: pd.DataFrame, y_val: pd.Series) -> float:
        """
        Evaluate neural network on validation set.

        Args:
            X_val: Validation features
            y_val: Validation labels

        Returns:
            Validation accuracy
        """
        import torch

        self.model.eval()
        X_val_tensor = torch.tensor(X_val.values, dtype=torch.float32)
        y_val_tensor = torch.tensor(y_val.values, dtype=torch.float32).reshape(-1, 1)

        with torch.no_grad():
            outputs = self.model(X_val_tensor)
            predicted = (outputs >= 0.5).float()
            accuracy = (predicted == y_val_tensor).float().mean().item()

        return accuracy

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """
        Make predictions on new data.

        Args:
            X: Features to predict on

        Returns:
            Array of predictions (0 or 1)
        """
        if not self.is_trained:
            raise ValueError("Model not trained yet. Call train() first.")

        if self.model_type in ['logistic', 'random_forest']:
            predictions = self.model.predict(X.values)

        elif self.model_type == 'neural_network':
            import torch

            self.model.eval()
            X_tensor = torch.tensor(X.values, dtype=torch.float32)

            with torch.no_grad():
                outputs = self.model(X_tensor)
                predictions = (outputs >= 0.5).float().numpy().flatten()

        return predictions

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """
        Predict class probabilities.

        Args:
            X: Features to predict on

        Returns:
            Array of probabilities for class 1 (price increase)
        """
        if not self.is_trained:
            raise ValueError("Model not trained yet. Call train() first.")

        if self.model_type in ['logistic', 'random_forest']:
            # Returns probabilities for both classes
            proba = self.model.predict_proba(X.values)
            # Return probability of class 1
            return proba[:, 1]

        elif self.model_type == 'neural_network':
            import torch

            self.model.eval()
            X_tensor = torch.tensor(X.values, dtype=torch.float32)

            with torch.no_grad():
                outputs = self.model(X_tensor)
                probabilities = outputs.numpy().flatten()

            return probabilities

    def get_feature_importance(self) -> Optional[pd.DataFrame]:
        """
        Get feature importance (for tree-based models).

        Returns:
            DataFrame with feature names and importance scores, or None
        """
        if self.model_type != 'random_forest':
            logger.warning(f"Feature importance not available for {self.model_type}")
            return None

        if not self.is_trained:
            logger.warning("Model not trained yet")
            return None

        importance_df = pd.DataFrame({
            'feature': self.feature_names,
            'importance': self.model.feature_importances_
        })
        importance_df = importance_df.sort_values('importance', ascending=False)

        return importance_df

    def save_model(self, filepath: str):
        """
        Save the trained model to disk.

        Args:
            filepath: Path to save the model
        """
        if not self.is_trained:
            logger.warning("Model not trained yet")
            return

        import pickle

        model_data = {
            'model_type': self.model_type,
            'model': self.model,
            'feature_names': self.feature_names,
            'is_trained': self.is_trained
        }

        with open(filepath, 'wb') as f:
            pickle.dump(model_data, f)

        logger.info(f"Model saved to {filepath}")

    def load_model(self, filepath: str):
        """
        Load a trained model from disk.

        Args:
            filepath: Path to the saved model
        """
        import pickle

        with open(filepath, 'rb') as f:
            model_data = pickle.load(f)

        self.model_type = model_data['model_type']
        self.model = model_data['model']
        self.feature_names = model_data['feature_names']
        self.is_trained = model_data['is_trained']

        logger.info(f"Model loaded from {filepath}")


if __name__ == "__main__":
    # Demo usage
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 80)
    print("Price Predictor Demo")
    print("=" * 80)

    # Create synthetic data
    np.random.seed(42)
    n_samples = 1000
    n_features = 10

    X = pd.DataFrame(
        np.random.randn(n_samples, n_features),
        columns=[f'feature_{i}' for i in range(n_features)]
    )
    y = pd.Series((X['feature_0'] + X['feature_1'] > 0).astype(int))

    # Split data
    split_idx = int(0.8 * n_samples)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    # Test different models
    for model_type in ['logistic', 'random_forest']:
        print(f"\n--- Testing {model_type} ---")

        predictor = PricePredictor(model_type=model_type)
        metrics = predictor.train(X_train, y_train, X_test, y_test)

        print(f"Metrics: {metrics}")

        # Make predictions
        predictions = predictor.predict(X_test)
        probabilities = predictor.predict_proba(X_test)

        print(f"Predictions: {predictions[:10]}")
        print(f"Probabilities: {probabilities[:10]}")

        # Feature importance (for random forest)
        if model_type == 'random_forest':
            importance = predictor.get_feature_importance()
            print(f"\nTop 5 features:\n{importance.head()}")
