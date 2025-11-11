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

    # Run with a YAML config file
    python3 run_simulation.py --config config_novice_exploit.yaml --minutes 30
"""

import logging
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from simulator import TradingSimulator, SimulatorConfig
from trade_manager import TradeManagerConfig
from analyzers.base import ConfidenceLevel, OpportunityStrength

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to YAML config file

    Returns:
        Configuration dictionary
    """
    config_file = Path(config_path)

    if not config_file.exists():
        logger.warning(f"Config file {config_path} not found, using defaults")
        return {}

    with open(config_file, "r") as f:
        config = yaml.safe_load(f)

    logger.info(f"Loaded configuration from {config_path}")
    return config


def create_simulator_from_yaml_config(
    yaml_config: Dict[str, Any],
    duration_override: Optional[float] = None
) -> SimulatorConfig:
    """
    Create a SimulatorConfig from a YAML configuration dict.

    Args:
        yaml_config: Configuration dict loaded from YAML
        duration_override: Optional duration in minutes to override

    Returns:
        SimulatorConfig instance
    """
    # Extract analyzer configurations
    analyzer_names = []
    analyzer_configs = {}

    for analyzer_name, analyzer_config in yaml_config.get("analyzers", {}).items():
        if analyzer_config.get("enabled", True):
            analyzer_names.append(analyzer_name)
            analyzer_configs[analyzer_name] = analyzer_config.get("config", {})

    # Create basic trade manager config
    # Note: For simulation, we use simpler defaults than the full bot
    trade_config = TradeManagerConfig(
        initial_capital=10000.0,  # $100
        max_position_size=1500.0,  # $15 per position
        min_confidence=ConfidenceLevel.MEDIUM,
        min_edge_cents=5.0,
        max_positions=8,
        position_sizing_method="confidence_scaled",
    )

    # Create simulator config
    sim_config = SimulatorConfig(
        trade_manager_config=trade_config,
        analyzer_names=analyzer_names,
        analyzer_configs=analyzer_configs,
        max_markets=yaml_config.get("max_markets_to_analyze", 100),
        market_status=yaml_config.get("market_status", "open"),
        update_interval_seconds=60,
        snapshot_interval_seconds=300,
        cache_ttl=yaml_config.get("cache_ttl", 30),
        rate_limit=yaml_config.get("rate_limit", 20.0),
    )

    return sim_config


def run_from_config_file(config_path: str, duration_minutes: float = 30):
    """
    Run simulation using a YAML config file.

    Args:
        config_path: Path to YAML configuration file
        duration_minutes: Duration to run simulation
    """
    print("\n" + "=" * 80)
    print(f"SIMULATION FROM CONFIG FILE: {config_path}")
    print("=" * 80 + "\n")

    # Load config
    yaml_config = load_config(config_path)

    if not yaml_config:
        print(f"Failed to load config from {config_path}")
        return None, None

    # Create simulator config from YAML
    sim_config = create_simulator_from_yaml_config(yaml_config, duration_minutes)

    # Print config summary
    print(f"Analyzers enabled: {', '.join(sim_config.analyzer_names)}")
    print(f"Max markets: {sim_config.max_markets}")
    print(f"Market status: {sim_config.market_status}")
    print(f"Duration: {duration_minutes} minutes\n")

    # Create and run simulator
    simulator = TradingSimulator(sim_config)
    report = simulator.run_for_duration(minutes=duration_minutes)
    simulator.print_summary()

    return simulator, report


def run_novice_exploit_simulation(duration_minutes: float = 30):
    """
    Run simulation using the novice exploitation analyzers.

    Includes: psychological_levels, recency_bias, theta_decay, event_volatility, hype_fomo
    """
    print("\n" + "=" * 80)
    print("NOVICE EXPLOITATION SIMULATION")
    print("Psychological levels, recency bias, theta decay, event volatility, hype/FOMO")
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
        analyzer_names=[
            "psychological_levels",
            "recency_bias",
            "theta_decay",
            "event_volatility",
            "hype_fomo",
        ],
        max_markets=100,
        update_interval_seconds=90,
        snapshot_interval_seconds=300,
    )

    simulator = TradingSimulator(sim_config)
    report = simulator.run_for_duration(minutes=duration_minutes)
    simulator.print_summary()

    return simulator, report


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

    parser = argparse.ArgumentParser(
        description="Run preset simulations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run novice exploit simulation for 30 minutes
  python3 run_simulation.py --mode novice_exploit --minutes 30

  # Run from YAML config file
  python3 run_simulation.py --config config_novice_exploit.yaml --minutes 30

  # Quick test with default settings
  python3 run_simulation.py --mode test --cycles 5
        """
    )
    parser.add_argument(
        "--mode",
        choices=["conservative", "aggressive", "technical", "novice_exploit", "test"],
        default="test",
        help="Simulation mode (default: test)",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to YAML config file (overrides --mode if specified)",
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

    # If config file is specified, use it
    if args.config:
        duration = args.minutes or 30
        simulator, report = run_from_config_file(args.config, duration)
    # Otherwise run selected mode
    elif args.mode == "conservative":
        duration = args.minutes or 30
        simulator, report = run_conservative_simulation(duration)
    elif args.mode == "aggressive":
        duration = args.minutes or 30
        simulator, report = run_aggressive_simulation(duration)
    elif args.mode == "technical":
        duration = args.minutes or 30
        simulator, report = run_technical_simulation(duration)
    elif args.mode == "novice_exploit":
        duration = args.minutes or 30
        simulator, report = run_novice_exploit_simulation(duration)
    else:  # test
        simulator, report = run_quick_test(args.cycles)

    # Plot if requested
    if args.plot and simulator:
        print("\nGenerating equity curve plot...")
        simulator.plot_equity_curve()
