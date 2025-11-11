#!/usr/bin/env python3
"""
Comprehensive Analyzer Benchmark Script

Tests all analyzers individually and in combinations to determine which
strategies perform best. Runs simulations with real Kalshi data and fake money.

Usage:
    # Run all tests (default 2 hours total)
    python3 benchmark_analyzers.py

    # Run for 4 hours total
    python3 benchmark_analyzers.py --hours 4

    # Test specific analyzers only
    python3 benchmark_analyzers.py --analyzers spread,rsi,llm_reasoning

    # Resume from previous run
    python3 benchmark_analyzers.py --resume results/benchmark_results.json
"""

import argparse
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

from simulator import TradingSimulator, SimulatorConfig
from trade_manager import TradeManagerConfig
from analyzers.base import ConfidenceLevel, OpportunityStrength

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Define test configurations
# Each test will run for total_hours / num_tests hours
TEST_CONFIGS = {
    # Individual analyzers (core)
    "spread_only": {
        "name": "Spread Only",
        "analyzers": ["spread"],
        "description": "Wide bid-ask spreads only",
    },
    "mispricing_only": {
        "name": "Mispricing Only",
        "analyzers": ["mispricing"],
        "description": "Extreme prices and behavioral biases",
    },
    "arbitrage_only": {
        "name": "Arbitrage Only",
        "analyzers": ["arbitrage"],
        "description": "Risk-free cross-market opportunities",
    },
    "imbalance_only": {
        "name": "Imbalance Only",
        "analyzers": ["imbalance"],
        "description": "Orderbook depth imbalances",
    },

    # Individual analyzers (technical)
    "rsi_only": {
        "name": "RSI Only",
        "analyzers": ["rsi"],
        "description": "RSI overbought/oversold",
    },
    "macd_only": {
        "name": "MACD Only",
        "analyzers": ["macd"],
        "description": "MACD trend signals",
    },
    "bollinger_only": {
        "name": "Bollinger Bands Only",
        "analyzers": ["bollinger_bands"],
        "description": "Bollinger band breakouts",
    },

    # Individual analyzers (behavioral)
    "theta_decay_only": {
        "name": "Theta Decay Only",
        "analyzers": ["theta_decay"],
        "description": "Time decay near expiration",
    },
    "momentum_fade_only": {
        "name": "Momentum Fade Only",
        "analyzers": ["momentum_fade"],
        "description": "Fade strong momentum moves",
    },
    "psychological_only": {
        "name": "Psychological Levels Only",
        "analyzers": ["psychological_levels"],
        "description": "Exploit biases at round numbers",
    },
    "event_volatility_only": {
        "name": "Event Volatility Only",
        "analyzers": ["event_volatility"],
        "description": "Fade FOMO spikes",
    },

    # Combinations - Core strategies
    "core_combo": {
        "name": "Core Combo",
        "analyzers": ["spread", "mispricing", "arbitrage"],
        "description": "Best core analyzers combined",
    },
    "technical_combo": {
        "name": "Technical Combo",
        "analyzers": ["rsi", "macd", "bollinger_bands", "ma_crossover"],
        "description": "All technical indicators",
    },
    "behavioral_combo": {
        "name": "Behavioral Combo",
        "analyzers": ["theta_decay", "momentum_fade", "psychological_levels", "event_volatility"],
        "description": "Behavioral exploitation strategies",
    },

    # Advanced combinations
    "small_market_specialist": {
        "name": "Small Market Specialist",
        "analyzers": ["spread", "mispricing", "psychological_levels"],
        "description": "Target low-volume markets",
        "max_volume": 5000,
    },
    "llm_enhanced": {
        "name": "LLM Enhanced",
        "analyzers": ["spread", "mispricing", "llm_reasoning"],
        "description": "Core strategies + LLM reasoning",
    },
    "kitchen_sink": {
        "name": "Kitchen Sink",
        "analyzers": [
            "spread", "mispricing", "arbitrage", "rsi", "imbalance",
            "momentum_fade", "theta_decay", "psychological_levels"
        ],
        "description": "Many analyzers combined",
    },
}


def create_base_trade_config() -> TradeManagerConfig:
    """Create base trade manager configuration."""
    return TradeManagerConfig(
        initial_capital=10000.0,  # $100 starting capital
        max_position_size=1500.0,  # $15 per position
        min_confidence=ConfidenceLevel.MEDIUM,
        min_strength=OpportunityStrength.SOFT,
        min_edge_cents=5.0,
        min_edge_percent=2.0,
        max_positions=8,
        position_sizing_method="confidence_scaled",
        stop_loss_percent=20.0,
        take_profit_percent=50.0,
    )


def run_test(
    test_id: str,
    test_config: Dict[str, Any],
    duration_minutes: float,
) -> Dict[str, Any]:
    """
    Run a single analyzer test.

    Args:
        test_id: Test identifier
        test_config: Test configuration dict
        duration_minutes: How long to run test

    Returns:
        Results dictionary
    """
    print("\n" + "=" * 80)
    print(f"TEST: {test_config['name']}")
    print(f"Description: {test_config['description']}")
    print(f"Analyzers: {', '.join(test_config['analyzers'])}")
    print(f"Duration: {duration_minutes:.1f} minutes")
    print("=" * 80)

    # Create simulator config
    trade_config = create_base_trade_config()

    sim_config = SimulatorConfig(
        trade_manager_config=trade_config,
        analyzer_names=test_config["analyzers"],
        max_markets=100,
        min_volume=test_config.get("min_volume", 10),
        max_volume=test_config.get("max_volume", None),
        update_interval_seconds=60,
        snapshot_interval_seconds=180,
    )

    # Run simulation
    start_time = datetime.now()

    try:
        simulator = TradingSimulator(sim_config)
        report = simulator.run_for_duration(minutes=duration_minutes)

        # Get final summary
        summary = simulator.trade_manager.get_portfolio_summary()

        # Extract key metrics
        results = {
            "test_id": test_id,
            "name": test_config["name"],
            "analyzers": test_config["analyzers"],
            "description": test_config["description"],
            "duration_minutes": duration_minutes,
            "start_time": start_time.isoformat(),
            "end_time": datetime.now().isoformat(),

            # Performance metrics
            "initial_capital": summary["initial_capital"],
            "final_value": summary["portfolio_value"],
            "total_pnl": summary["total_pnl"],
            "total_pnl_percent": (summary["total_pnl"] / summary["initial_capital"] * 100),
            "realized_pnl": summary["realized_pnl"],
            "unrealized_pnl": summary["unrealized_pnl"],

            # Trading metrics
            "total_trades": summary["total_trades"],
            "num_open_positions": summary["num_open_positions"],
            "num_closed_positions": summary["num_closed_positions"],
            "win_rate": summary.get("win_rate", 0),
            "avg_win": summary.get("avg_win", 0),
            "avg_loss": summary.get("avg_loss", 0),
            "profit_factor": summary.get("profit_factor", 0),

            # Opportunity metrics
            "opportunities_found": simulator.opportunities_found,
            "opportunities_traded": simulator.opportunities_traded,
            "conversion_rate": (
                simulator.opportunities_traded / simulator.opportunities_found * 100
                if simulator.opportunities_found > 0 else 0
            ),

            # Snapshots for equity curve
            "snapshots": report.get("snapshots", []),

            "status": "completed"
        }

    except Exception as e:
        logger.error(f"Test {test_id} failed: {e}")
        results = {
            "test_id": test_id,
            "name": test_config["name"],
            "status": "failed",
            "error": str(e),
        }

    return results


def print_comparison_table(all_results: List[Dict[str, Any]]):
    """Print comparison table of all test results."""
    print("\n" + "=" * 120)
    print("BENCHMARK RESULTS SUMMARY")
    print("=" * 120)
    print()

    # Filter completed tests
    completed = [r for r in all_results if r.get("status") == "completed"]

    if not completed:
        print("No completed tests to display.")
        return

    # Sort by total P&L
    completed.sort(key=lambda x: x.get("total_pnl", 0), reverse=True)

    # Print header
    print(f"{'Rank':<5} {'Test Name':<30} {'Return':<12} {'Trades':<8} {'Win%':<8} {'PF':<8} {'Conv%':<8}")
    print("-" * 120)

    # Print rows
    for i, result in enumerate(completed, 1):
        name = result["name"][:28]
        return_pct = result.get("total_pnl_percent", 0)
        trades = result.get("total_trades", 0)
        win_rate = result.get("win_rate", 0)
        pf = result.get("profit_factor", 0)
        conv = result.get("conversion_rate", 0)

        # Color coding for return
        if return_pct > 5:
            return_str = f"+{return_pct:>6.2f}% 🟢"
        elif return_pct > 0:
            return_str = f"+{return_pct:>6.2f}% 🟡"
        elif return_pct > -5:
            return_str = f"{return_pct:>7.2f}% 🟡"
        else:
            return_str = f"{return_pct:>7.2f}% 🔴"

        print(f"{i:<5} {name:<30} {return_str:<12} {trades:<8} {win_rate:<7.1f}% {pf:<7.2f} {conv:<7.1f}%")

    print("-" * 120)
    print()

    # Print best performer details
    best = completed[0]
    print("🏆 BEST PERFORMER:")
    print(f"   {best['name']}")
    print(f"   Analyzers: {', '.join(best['analyzers'])}")
    print(f"   Return: {best['total_pnl_percent']:.2f}%")
    print(f"   Trades: {best['total_trades']} (Win rate: {best.get('win_rate', 0):.1f}%)")
    print(f"   Description: {best['description']}")
    print()


def save_results(results: List[Dict[str, Any]], output_path: str):
    """Save results to JSON file."""
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w') as f:
        json.dump({
            "benchmark_time": datetime.now().isoformat(),
            "results": results
        }, f, indent=2)

    logger.info(f"Results saved to {output_file}")


def load_results(input_path: str) -> List[Dict[str, Any]]:
    """Load results from JSON file."""
    with open(input_path, 'r') as f:
        data = json.load(f)
    return data.get("results", [])


def main():
    """Main benchmark function."""
    parser = argparse.ArgumentParser(
        description="Benchmark all analyzers",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=2.0,
        help="Total hours for all tests (default: 2)",
    )
    parser.add_argument(
        "--analyzers",
        type=str,
        help="Comma-separated list of test IDs to run (default: all)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="results/benchmark_results.json",
        help="Output file for results",
    )
    parser.add_argument(
        "--resume",
        type=str,
        help="Resume from previous results file",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available test configurations and exit",
    )

    args = parser.parse_args()

    # List configs and exit
    if args.list:
        print("\nAvailable test configurations:")
        print("-" * 80)
        for test_id, config in TEST_CONFIGS.items():
            print(f"{test_id:30} - {config['name']}")
            print(f"{'':30}   Analyzers: {', '.join(config['analyzers'])}")
            print(f"{'':30}   {config['description']}")
            print()
        return

    # Load previous results if resuming
    completed_tests = set()
    all_results = []

    if args.resume:
        print(f"Resuming from {args.resume}...")
        all_results = load_results(args.resume)
        completed_tests = {r["test_id"] for r in all_results if r.get("status") == "completed"}
        print(f"Found {len(completed_tests)} completed tests, skipping those.")
        print()

    # Determine which tests to run
    if args.analyzers:
        test_ids = [tid.strip() for tid in args.analyzers.split(",")]
        tests_to_run = {tid: TEST_CONFIGS[tid] for tid in test_ids if tid in TEST_CONFIGS}
    else:
        tests_to_run = {tid: cfg for tid, cfg in TEST_CONFIGS.items() if tid not in completed_tests}

    if not tests_to_run:
        print("No tests to run!")
        return

    # Calculate time per test
    num_tests = len(tests_to_run)
    total_minutes = args.hours * 60
    minutes_per_test = total_minutes / num_tests

    print("=" * 80)
    print("ANALYZER BENCHMARK")
    print("=" * 80)
    print(f"Total duration: {args.hours:.1f} hours ({total_minutes:.0f} minutes)")
    print(f"Number of tests: {num_tests}")
    print(f"Time per test: {minutes_per_test:.1f} minutes")
    print()
    print("Tests to run:")
    for test_id, config in tests_to_run.items():
        print(f"  - {test_id}: {config['name']}")
    print("=" * 80)
    print()

    # Run tests
    start_time = datetime.now()

    for i, (test_id, test_config) in enumerate(tests_to_run.items(), 1):
        print(f"\n[{i}/{num_tests}] Running test: {test_id}")

        result = run_test(test_id, test_config, minutes_per_test)
        all_results.append(result)

        # Save intermediate results
        save_results(all_results, args.output)

        # Print quick summary
        if result.get("status") == "completed":
            print(f"\n✅ {test_config['name']}: {result['total_pnl_percent']:+.2f}% return")
            print(f"   Trades: {result['total_trades']}, Win rate: {result.get('win_rate', 0):.1f}%")
        else:
            print(f"\n❌ {test_config['name']}: FAILED")

    # Print final comparison
    total_time = (datetime.now() - start_time).total_seconds() / 60
    print(f"\n\nBenchmark completed in {total_time:.1f} minutes")

    print_comparison_table(all_results)

    print(f"\n💾 Results saved to: {args.output}")
    print()


if __name__ == "__main__":
    main()
