#!/usr/bin/env python3
"""
Quick simulation runner with preset configurations.

Examples:
    # Run for 5 cycles with default settings
    python3 run_simulation.py --cycles 5

    # Run for 1 hour with more capital
    python3 run_simulation.py --hours 1 --capital 1000

    # Run for 30 minutes with specific analyzers
    python3 run_simulation.py --minutes 30 --analyzers spread,rsi,imbalance
"""

import logging
from simulator import TradingSimulator, SimulatorConfig
from trade_manager import TradeManagerConfig
from analyzers.base import ConfidenceLevel, OpportunityStrength

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def run_conservative_simulation(duration_minutes: float = 30):
    """Run conservative simulation (high confidence, hard opportunities only)."""
    print("\n" + "=" * 80)
    print("CONSERVATIVE SIMULATION")
    print("High confidence, hard opportunities, tight filters")
    print("=" * 80 + "\n")

    trade_config = TradeManagerConfig(
        initial_capital=10000.0,  # $100
        max_position_size=1000.0,  # $10 per position
        min_confidence=ConfidenceLevel.HIGH,  # Only high confidence
        min_strength=OpportunityStrength.HARD,  # Only hard opportunities
        min_edge_cents=10.0,  # Minimum 10¢ edge
        min_edge_percent=5.0,  # Minimum 5% edge
        max_positions=5,
        position_sizing_method="fixed",
        stop_loss_percent=20.0,
        take_profit_percent=50.0,
    )

    sim_config = SimulatorConfig(
        trade_manager_config=trade_config,
        analyzer_names=["spread", "mispricing", "arbitrage"],
        max_markets=50,
        update_interval_seconds=120,  # 2 minutes between cycles
        snapshot_interval_seconds=300,  # 5 minute snapshots
    )

    simulator = TradingSimulator(sim_config)
    report = simulator.run_for_duration(minutes=duration_minutes)
    simulator.print_summary()

    return simulator, report


def run_aggressive_simulation(duration_minutes: float = 30):
    """Run aggressive simulation (lower thresholds, more trades)."""
    print("\n" + "=" * 80)
    print("AGGRESSIVE SIMULATION")
    print("Lower thresholds, more trades, higher risk")
    print("=" * 80 + "\n")

    trade_config = TradeManagerConfig(
        initial_capital=10000.0,  # $100
        max_position_size=2000.0,  # $20 per position
        min_confidence=ConfidenceLevel.MEDIUM,  # Medium confidence OK
        min_strength=OpportunityStrength.SOFT,  # Soft opportunities OK
        min_edge_cents=3.0,  # Minimum 3¢ edge
        min_edge_percent=2.0,  # Minimum 2% edge
        max_positions=10,
        position_sizing_method="confidence_scaled",  # Scale by confidence
        stop_loss_percent=25.0,
        take_profit_percent=40.0,
    )

    sim_config = SimulatorConfig(
        trade_manager_config=trade_config,
        analyzer_names=["spread", "mispricing", "rsi", "imbalance", "momentum_fade"],
        max_markets=100,
        update_interval_seconds=60,  # 1 minute between cycles
        snapshot_interval_seconds=180,  # 3 minute snapshots
    )

    simulator = TradingSimulator(sim_config)
    report = simulator.run_for_duration(minutes=duration_minutes)
    simulator.print_summary()

    return simulator, report


def run_technical_simulation(duration_minutes: float = 30):
    """Run simulation using only technical analyzers."""
    print("\n" + "=" * 80)
    print("TECHNICAL ANALYSIS SIMULATION")
    print("Focus on RSI, MACD, Bollinger Bands, Moving Averages")
    print("=" * 80 + "\n")

    trade_config = TradeManagerConfig(
        initial_capital=10000.0,  # $100
        max_position_size=1500.0,  # $15 per position
        min_confidence=ConfidenceLevel.MEDIUM,
        min_edge_cents=5.0,
        max_positions=8,
        position_sizing_method="confidence_scaled",
    )

    sim_config = SimulatorConfig(
        trade_manager_config=trade_config,
        analyzer_names=["rsi", "macd", "bollinger_bands", "ma_crossover"],
        max_markets=75,
        update_interval_seconds=90,
        snapshot_interval_seconds=300,
    )

    simulator = TradingSimulator(sim_config)
    report = simulator.run_for_duration(minutes=duration_minutes)
    simulator.print_summary()

    return simulator, report


def run_quick_test(cycles: int = 3):
    """Run quick test simulation."""
    print("\n" + "=" * 80)
    print("QUICK TEST SIMULATION")
    print(f"Running {cycles} cycles to test the system")
    print("=" * 80 + "\n")

    trade_config = TradeManagerConfig(
        initial_capital=10000.0,
        max_position_size=1000.0,
        min_confidence=ConfidenceLevel.MEDIUM,
        min_edge_cents=5.0,
        max_positions=5,
    )

    sim_config = SimulatorConfig(
        trade_manager_config=trade_config,
        analyzer_names=[
            "mispricing",
            "rsi",
            "macd",
            "bollinger_bands",
            "ma_crossover",
        ],
        max_markets=50,
        update_interval_seconds=30,
    )

    simulator = TradingSimulator(sim_config)
    report = simulator.run_for_duration(cycles=cycles)
    simulator.print_summary()

    return simulator, report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run preset simulations")
    parser.add_argument(
        "--mode",
        choices=["conservative", "aggressive", "technical", "test"],
        default="test",
        help="Simulation mode (default: test)",
    )
    parser.add_argument(
        "--minutes", type=float, help="Duration in minutes (for non-test modes)"
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=3,
        help="Number of cycles (for test mode, default: 3)",
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Plot equity curve at end (requires matplotlib)",
    )

    args = parser.parse_args()

    # Run selected mode
    if args.mode == "conservative":
        duration = args.minutes or 30
        simulator, report = run_conservative_simulation(duration)
    elif args.mode == "aggressive":
        duration = args.minutes or 30
        simulator, report = run_aggressive_simulation(duration)
    elif args.mode == "technical":
        duration = args.minutes or 30
        simulator, report = run_technical_simulation(duration)
    else:  # test
        simulator, report = run_quick_test(args.cycles)

    # Plot if requested
    if args.plot:
        print("\nGenerating equity curve plot...")
        simulator.plot_equity_curve()
