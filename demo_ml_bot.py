#!/usr/bin/env python3
"""
ML Bot Demo Script

Demonstrates the complete ML bot workflow:
1. Fetching historical data
2. Training a price prediction model
3. Generating trading signals

Usage:
    python demo_ml_bot.py [--model MODEL_TYPE] [--markets N] [--days N]

Options:
    --model: Model type (logistic, random_forest, neural_network) [default: random_forest]
    --markets: Number of markets for training [default: 15]
    --days: Days of historical data [default: 7]
    --confidence: Minimum confidence threshold [default: 0.65]
    --signal-markets: Number of markets to generate signals for [default: 10]
"""

import argparse
import logging
import sys
from ml_bots.bots.ml_trading_bot import MLTradingBot
from kalshi_client import KalshiDataClient


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80 + "\n")


def main():
    # Parse arguments
    parser = argparse.ArgumentParser(description="ML Trading Bot Demo")
    parser.add_argument(
        '--model',
        type=str,
        default='random_forest',
        choices=['logistic', 'random_forest', 'neural_network'],
        help='Model type to use'
    )
    parser.add_argument(
        '--markets',
        type=int,
        default=15,
        help='Number of markets for training'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Days of historical data'
    )
    parser.add_argument(
        '--confidence',
        type=float,
        default=0.65,
        help='Minimum confidence threshold (0.0-1.0)'
    )
    parser.add_argument(
        '--signal-markets',
        type=int,
        default=10,
        help='Number of markets to generate signals for'
    )
    parser.add_argument(
        '--save-model',
        type=str,
        help='Path to save trained model (optional)'
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print_section("ML Trading Bot Demo")
    print(f"Configuration:")
    print(f"  Model type: {args.model}")
    print(f"  Training markets: {args.markets}")
    print(f"  Historical days: {args.days}")
    print(f"  Confidence threshold: {args.confidence}")
    print(f"  Signal markets: {args.signal_markets}")

    # Initialize Kalshi client and bot
    print("\nInitializing bot...")
    client = KalshiDataClient()
    bot = MLTradingBot(
        client=client,
        model_type=args.model,
        min_confidence=args.confidence
    )

    # Step 1: Train the model
    print_section("Step 1: Training ML Model")
    print(f"Fetching historical data for {args.markets} markets...")
    print(f"Using {args.days} days of data with 1-hour intervals...")

    training_result = bot.train_model(
        min_volume=50,
        max_markets=args.markets,
        days_back=args.days,
        period_interval=60,
        prediction_horizon=1
    )

    if not training_result.get('success'):
        print(f"\n❌ Training failed: {training_result.get('error')}")
        print("\nPossible reasons:")
        print("  - No markets with sufficient historical data")
        print("  - Network connectivity issues")
        print("  - Markets closed or low volume period")
        print("\nTry:")
        print("  - Increasing --days parameter")
        print("  - Decreasing --markets parameter")
        print("  - Running during high-activity periods")
        sys.exit(1)

    print(f"\n✅ Training successful!")
    print(f"\nTraining Statistics:")
    print(f"  Markets used: {training_result['n_markets']}")
    print(f"  Total samples: {training_result['n_samples']}")
    print(f"  Features: {training_result['n_features']}")
    print(f"\nModel Performance:")
    metrics = training_result['metrics']
    for key, value in metrics.items():
        print(f"  {key}: {value:.4f}")

    # Step 2: Model info
    print_section("Step 2: Model Information")
    info = bot.get_model_info()
    print(f"Model type: {info['model_type']}")
    print(f"Minimum confidence: {info['min_confidence']}")
    print(f"Training markets: {len(info['training_markets'])}")

    if 'top_features' in info:
        print(f"\nTop 10 Most Important Features:")
        for i, feat in enumerate(info['top_features'], 1):
            print(f"  {i:2d}. {feat['feature']:20s} - {feat['importance']:.4f}")

    # Save model if requested
    if args.save_model:
        print(f"\nSaving model to {args.save_model}...")
        bot.save_model(args.save_model)
        print("✅ Model saved")

    # Step 3: Generate trading signals
    print_section("Step 3: Generating Trading Signals")
    print(f"Analyzing {args.signal_markets} active markets...")
    print(f"Minimum confidence: {args.confidence}")

    signals = bot.generate_trading_signals(
        min_volume=50,
        max_markets=args.signal_markets
    )

    if not signals:
        print("\n⚠️  No trading signals generated")
        print("\nPossible reasons:")
        print(f"  - No predictions met confidence threshold ({args.confidence})")
        print("  - Markets have insufficient data")
        print("\nTry:")
        print("  - Lowering --confidence parameter")
        print("  - Increasing --signal-markets parameter")
        sys.exit(0)

    print(f"\n✅ Generated {len(signals)} trading signals:")

    for i, signal in enumerate(signals, 1):
        market = signal['market']
        pred = signal['prediction']

        print(f"\n{'-' * 80}")
        print(f"Signal #{i}")
        print(f"{'-' * 80}")
        print(f"Market: {market['ticker']}")
        print(f"Title: {market.get('title', 'N/A')}")
        print(f"Volume: {market.get('volume', 0):,}")
        print(f"\nRecommendation:")
        print(f"  Action: {signal['action']} {signal['side'].upper()}")
        print(f"  Direction: {pred['direction']}")
        print(f"  Confidence: {pred['confidence']:.1%}")
        print(f"  Current Price: {pred['latest_price']}¢")

        # Calculate suggested position size based on confidence
        # Higher confidence = larger position
        base_position = 10
        position_multiplier = (pred['confidence'] - args.confidence) / (1.0 - args.confidence)
        suggested_contracts = int(base_position * (1 + position_multiplier * 2))

        print(f"\nSuggested Position:")
        print(f"  Contracts: {suggested_contracts}")
        print(f"  Risk: ~${suggested_contracts * pred['latest_price'] / 100:.2f}")

    # Summary
    print_section("Summary")
    print(f"✅ Model trained on {training_result['n_markets']} markets")
    print(f"✅ Generated {len(signals)} trading signals")
    print(f"✅ Average confidence: {sum(s['confidence'] for s in signals) / len(signals):.1%}")

    print(f"\nNext Steps:")
    print(f"  1. Review the signals above")
    print(f"  2. Perform additional due diligence on markets")
    print(f"  3. Consider market context and news")
    print(f"  4. Start with small positions to test the strategy")
    print(f"  5. Monitor performance and iterate")

    print("\n⚠️  Disclaimer: This is for educational purposes only.")
    print("Past performance does not guarantee future results.")
    print("Always trade responsibly and never risk more than you can afford to lose.\n")


if __name__ == "__main__":
    main()
