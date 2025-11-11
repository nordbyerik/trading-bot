#!/usr/bin/env python3
"""
ML Analyzer Demo

Demonstrates using the ML predictor analyzer with the existing simulator infrastructure.

Usage:
    # Quick test (3 cycles)
    python demo_ml_analyzer.py --mode test

    # Longer simulation
    python demo_ml_analyzer.py --minutes 30

    # With custom ML configuration
    python demo_ml_analyzer.py --minutes 30 --model neural_network --confidence 0.75
"""

import argparse
import logging
import sys
from run_simulation import setup_simulation, run_cycles


def main():
    parser = argparse.ArgumentParser(description="ML Analyzer Demo with Simulator")

    # Simulation parameters
    parser.add_argument(
        '--mode',
        type=str,
        choices=['test', 'conservative', 'aggressive', 'ml'],
        default='ml',
        help='Simulation mode (ml = ML analyzer only)'
    )
    parser.add_argument(
        '--minutes',
        type=int,
        help='Minutes to run simulation (overrides mode)'
    )
    parser.add_argument(
        '--cycles',
        type=int,
        help='Number of cycles to run (overrides mode)'
    )

    # ML-specific parameters
    parser.add_argument(
        '--model',
        type=str,
        default='random_forest',
        choices=['logistic', 'random_forest', 'neural_network'],
        help='ML model type'
    )
    parser.add_argument(
        '--confidence',
        type=float,
        help='Minimum confidence threshold (0.0-1.0)'
    )
    parser.add_argument(
        '--training-markets',
        type=int,
        default=15,
        help='Number of markets for training'
    )
    parser.add_argument(
        '--training-days',
        type=int,
        default=7,
        help='Days of historical data for training'
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 80)
    print("ML Analyzer Demo - Using Existing Simulator Infrastructure")
    print("=" * 80)

    # Configure ML analyzer
    ml_config = {
        'model_type': args.model,
        'training_markets': args.training_markets,
        'training_days': args.training_days,
        'train_on_first_run': True,
    }

    # Set confidence thresholds if specified
    if args.confidence:
        ml_config['hard_min_confidence'] = args.confidence
        ml_config['soft_min_confidence'] = max(0.5, args.confidence - 0.1)

    print(f"\nML Configuration:")
    print(f"  Model: {args.model}")
    print(f"  Training markets: {args.training_markets}")
    print(f"  Training days: {args.training_days}")
    if args.confidence:
        print(f"  Min confidence: {args.confidence}")

    # Determine run parameters
    if args.cycles:
        duration_minutes = None
        cycles = args.cycles
    elif args.minutes:
        duration_minutes = args.minutes
        cycles = None
    elif args.mode == 'test':
        duration_minutes = None
        cycles = 3
    else:
        # Default: 30 minutes
        duration_minutes = 30
        cycles = None

    print(f"\nSimulation Parameters:")
    if cycles:
        print(f"  Cycles: {cycles}")
    else:
        print(f"  Duration: {duration_minutes} minutes")

    # Setup simulation with ML analyzer
    print("\n" + "=" * 80)
    print("Setting up simulator...")
    print("=" * 80)

    simulator = setup_simulation(
        analyzer_names=['ml_predictor'],  # Use only ML analyzer
        analyzer_configs={'ml_predictor': ml_config},
        initial_capital=10000.0,
        max_markets=50
    )

    # Run simulation
    print("\n" + "=" * 80)
    print("Starting simulation...")
    print("=" * 80)
    print("\nThe ML analyzer will:")
    print("  1. Train on historical data (first cycle)")
    print("  2. Make predictions on current markets")
    print("  3. Generate trading signals based on confidence")
    print("  4. Execute trades via the trade manager")
    print("\nPress Ctrl+C to stop\n")

    try:
        if cycles:
            run_cycles(simulator, cycles, sleep_between=60)
        else:
            run_cycles(simulator, None, duration_minutes=duration_minutes, sleep_between=60)

        # Print final summary
        print("\n" + "=" * 80)
        print("Simulation Complete!")
        print("=" * 80)

        report = simulator.get_performance_report()
        print(f"\nFinal Performance:")
        print(f"  Portfolio value: ${report['current_portfolio_value']:.2f}")
        print(f"  Total P&L: ${report['total_pnl']:.2f}")
        print(f"  Return: {report['total_return']:.2f}%")
        print(f"  Total trades: {report['total_trades']}")

        if report['total_trades'] > 0:
            print(f"  Win rate: {report['win_rate']:.1f}%")
            print(f"  Avg profit per trade: ${report['avg_profit_per_trade']:.2f}")

    except KeyboardInterrupt:
        print("\n\nSimulation interrupted by user")
        print("Generating final report...")

        report = simulator.get_performance_report()
        print(f"\nPerformance at interruption:")
        print(f"  Portfolio value: ${report['current_portfolio_value']:.2f}")
        print(f"  Total P&L: ${report['total_pnl']:.2f}")
        print(f"  Total trades: {report['total_trades']}")

    print("\n✅ Demo complete!")
    print("\nNext steps:")
    print("  - Review the ML analyzer in analyzers/ml_predictor_analyzer.py")
    print("  - Adjust confidence thresholds in config")
    print("  - Try different model types (--model)")
    print("  - Integrate with other analyzers for ensemble strategies")


if __name__ == "__main__":
    main()
