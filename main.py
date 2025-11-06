#!/usr/bin/env python3
"""
Kalshi Market Analysis System - Main Orchestrator

Coordinates data fetching, analysis, and notifications for Kalshi prediction markets.
"""

import argparse
import logging
import signal
import sys
import time
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from kalshi_client import KalshiDataClient
from notifier import ConsoleNotifier, FileNotifier, EmailNotifier, SlackNotifier
from analyzers.base import BaseAnalyzer
from analyzers.spread_analyzer import SpreadAnalyzer
from analyzers.mispricing_analyzer import MispricingAnalyzer
from analyzers.arbitrage_analyzer import ArbitrageAnalyzer
from analyzers.momentum_fade_analyzer import MomentumFadeAnalyzer
from analyzers.correlation_analyzer import CorrelationAnalyzer
from analyzers.imbalance_analyzer import ImbalanceAnalyzer
from analyzers.theta_decay_analyzer import ThetaDecayAnalyzer
from analyzers.ma_crossover_analyzer import MovingAverageCrossoverAnalyzer
from analyzers.rsi_analyzer import RSIAnalyzer
from analyzers.bollinger_bands_analyzer import BollingerBandsAnalyzer
from analyzers.macd_analyzer import MACDAnalyzer
from analyzers.volume_trend_analyzer import VolumeTrendAnalyzer
from analyzers.event_volatility_analyzer import EventVolatilityCrushAnalyzer
from analyzers.recency_bias_analyzer import RecencyBiasAnalyzer
from analyzers.psychological_level_analyzer import PsychologicalLevelAnalyzer
from analyzers.liquidity_trap_analyzer import LiquidityTrapAnalyzer


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Analyzer registry
ANALYZER_REGISTRY = {
    "spread": SpreadAnalyzer,
    "mispricing": MispricingAnalyzer,
    "arbitrage": ArbitrageAnalyzer,
    "momentum_fade": MomentumFadeAnalyzer,
    "correlation": CorrelationAnalyzer,
    "imbalance": ImbalanceAnalyzer,
    "theta_decay": ThetaDecayAnalyzer,
    "ma_crossover": MovingAverageCrossoverAnalyzer,
    "rsi": RSIAnalyzer,
    "bollinger_bands": BollingerBandsAnalyzer,
    "macd": MACDAnalyzer,
    "volume_trend": VolumeTrendAnalyzer,
    # NEW: Novice exploitation analyzers
    "event_volatility": EventVolatilityCrushAnalyzer,
    "recency_bias": RecencyBiasAnalyzer,
    "psychological_levels": PsychologicalLevelAnalyzer,
    "liquidity_trap": LiquidityTrapAnalyzer,
}


class MarketAnalysisOrchestrator:
    """
    Main orchestrator for the Kalshi market analysis system.

    Coordinates:
    - Data fetching from Kalshi API
    - Running multiple analyzers
    - Sending notifications
    - Scheduling repeated analysis
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the orchestrator.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.running = False
        self.client = KalshiDataClient(
            cache_ttl=config.get("cache_ttl", 30),
            rate_limit=config.get("rate_limit", 20.0),
            rate_limit_burst=config.get("rate_limit_burst"),
        )

        # Initialize analyzers
        self.analyzers = self._setup_analyzers()

        # Initialize notifiers
        self.notifiers = self._setup_notifiers()

        logger.info(
            f"Initialized with {len(self.analyzers)} analyzers and {len(self.notifiers)} notifiers"
        )

    def _setup_analyzers(self) -> List[BaseAnalyzer]:
        """Set up analyzers based on configuration."""
        analyzers = []
        analyzer_configs = self.config.get("analyzers", {})

        for analyzer_name, analyzer_config in analyzer_configs.items():
            if not analyzer_config.get("enabled", True):
                continue

            analyzer_class = ANALYZER_REGISTRY.get(analyzer_name)
            if not analyzer_class:
                logger.warning(f"Unknown analyzer: {analyzer_name}")
                continue

            config_params = analyzer_config.get("config", {})
            # Pass kalshi_client to enable candlesticks pre-warming
            analyzer = analyzer_class(config=config_params, kalshi_client=self.client)
            analyzers.append(analyzer)
            logger.info(f"Enabled analyzer: {analyzer.get_name()}")

        # If no analyzers configured, enable defaults
        if not analyzers:
            logger.warning("No analyzers configured, enabling defaults")
            analyzers = [
                SpreadAnalyzer(kalshi_client=self.client),
                MispricingAnalyzer(kalshi_client=self.client),
                ArbitrageAnalyzer(kalshi_client=self.client),
            ]

        return analyzers

    def _setup_notifiers(self) -> List:
        """Set up notifiers based on configuration."""
        notifiers = []
        notifier_configs = self.config.get("notifiers", {})

        # Console notifier
        if notifier_configs.get("console", {}).get("enabled", True):
            console_config = notifier_configs.get("console", {})
            notifiers.append(
                ConsoleNotifier(min_confidence=console_config.get("min_confidence"))
            )

        # File notifier
        if notifier_configs.get("file", {}).get("enabled", False):
            file_config = notifier_configs["file"]
            notifiers.append(
                FileNotifier(
                    file_path=file_config.get("path", "opportunities.json"),
                    format=file_config.get("format", "json"),
                )
            )

        # Email notifier
        if notifier_configs.get("email", {}).get("enabled", False):
            email_config = notifier_configs["email"]
            notifiers.append(
                EmailNotifier(
                    smtp_host=email_config["smtp_host"],
                    smtp_port=email_config["smtp_port"],
                    sender=email_config["sender"],
                    recipients=email_config["recipients"],
                    username=email_config.get("username"),
                    password=email_config.get("password"),
                    use_tls=email_config.get("use_tls", True),
                )
            )

        # Slack notifier
        if notifier_configs.get("slack", {}).get("enabled", False):
            slack_config = notifier_configs["slack"]
            notifiers.append(
                SlackNotifier(
                    webhook_url=slack_config["webhook_url"],
                    channel=slack_config.get("channel"),
                )
            )

        # Default to console if no notifiers configured
        if not notifiers:
            notifiers.append(ConsoleNotifier())

        logger.info(f"Enabled {len(notifiers)} notifier(s)")
        return notifiers

    def fetch_market_data(self) -> List[Dict[str, Any]]:
        """
        Fetch market data with orderbooks.

        Returns:
            List of market dictionaries with embedded orderbook data
        """
        logger.info("Fetching market data...")

        # Fetch markets up to the configured limit
        max_markets = self.config.get("max_markets_to_analyze", 100)
        market_status = self.config.get("market_status", "open")
        min_volume = self.config.get("min_market_volume")

        markets = self.client.get_all_open_markets(
            max_markets=max_markets,
            status=market_status,
            min_volume=min_volume
        )
        logger.info(f"Fetched {len(markets)} {market_status} markets")

        # Fetch orderbooks for each market
        enriched_markets = []
        for i, market in enumerate(markets):
            ticker = market.get("ticker")

            try:
                orderbook_response = self.client.get_orderbook(ticker)
                # Extract the actual orderbook data from the response wrapper
                market["orderbook"] = orderbook_response.get("orderbook", {})

                # Extract series_ticker if not present (needed for candlestick fetching)
                if not market.get("series_ticker") and ticker:
                    # Series ticker is the first part before the first hyphen
                    market["series_ticker"] = ticker.split("-")[0]

                enriched_markets.append(market)

                if (i + 1) % 20 == 0:
                    logger.info(
                        f"Fetched orderbooks for {i + 1}/{len(markets)} markets"
                    )

            except Exception as e:
                logger.warning(f"Failed to fetch orderbook for {ticker}: {e}")
                continue

        logger.info(
            f"Successfully enriched {len(enriched_markets)} markets with orderbook data"
        )
        return enriched_markets

    def run_analysis(self, markets: List[Dict[str, Any]]) -> List[Any]:
        """
        Run all analyzers on market data.

        Args:
            markets: List of market data dictionaries

        Returns:
            List of all opportunities found
        """
        all_opportunities = []

        for analyzer in self.analyzers:
            logger.info(f"Running {analyzer.get_name()}...")
            try:
                opportunities = analyzer.analyze(markets)
                all_opportunities.extend(opportunities)
                logger.info(
                    f"{analyzer.get_name()} found {len(opportunities)} opportunities"
                )
            except Exception as e:
                logger.error(f"Error running {analyzer.get_name()}: {e}", exc_info=True)

        return all_opportunities

    def send_notifications(self, opportunities: List[Any]) -> None:
        """
        Send notifications through all configured notifiers.

        Args:
            opportunities: List of opportunities to notify about
        """
        if not opportunities:
            logger.info("No opportunities to notify about")
            return

        for notifier in self.notifiers:
            try:
                notifier.send(opportunities)
            except Exception as e:
                logger.error(
                    f"Error sending notification via {notifier.__class__.__name__}: {e}"
                )

    def run_once(self) -> None:
        """Run a single analysis cycle."""
        logger.info("=" * 80)
        logger.info(f"Starting analysis cycle at {datetime.now()}")
        logger.info("=" * 80)

        try:
            # Fetch data
            markets = self.fetch_market_data()

            # Run analysis
            opportunities = self.run_analysis(markets)

            # Send notifications
            self.send_notifications(opportunities)

            logger.info(
                f"Analysis cycle complete. Found {len(opportunities)} total opportunities."
            )

        except Exception as e:
            logger.error(f"Error in analysis cycle: {e}", exc_info=True)

    def run_continuous(self, interval: int = 60) -> None:
        """
        Run continuous analysis on a schedule.

        Args:
            interval: Seconds between analysis cycles
        """
        self.running = True

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        logger.info(f"Starting continuous analysis (interval: {interval}s)")
        logger.info("Press Ctrl+C to stop")

        while self.running:
            self.run_once()

            if self.running:
                logger.info(f"Sleeping for {interval} seconds...")
                time.sleep(interval)

        logger.info("Shutting down gracefully...")

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, stopping...")
        self.running = False


def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from YAML file."""
    config_file = Path(config_path)

    if not config_file.exists():
        logger.warning(f"Config file {config_path} not found, using defaults")
        return {}

    with open(config_file, "r") as f:
        config = yaml.safe_load(f)

    logger.info(f"Loaded configuration from {config_path}")
    return config


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Kalshi Market Analysis System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--config",
        "-c",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Run analysis once and exit (default: continuous)",
    )

    parser.add_argument(
        "--interval",
        "-i",
        type=int,
        default=60,
        help="Analysis interval in seconds (default: 60)",
    )

    parser.add_argument(
        "--analyzer",
        "-a",
        choices=list(ANALYZER_REGISTRY.keys()),
        help="Run only a specific analyzer (for testing)",
    )

    parser.add_argument(
        "--list-analyzers",
        action="store_true",
        help="List available analyzers and exit",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Set log level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # List analyzers
    if args.list_analyzers:
        print("\nAvailable Analyzers:")
        print("-" * 40)
        for name, analyzer_class in ANALYZER_REGISTRY.items():
            analyzer = analyzer_class()
            print(f"\n{name}:")
            print(f"  Name: {analyzer.get_name()}")
            print(f"  Description: {analyzer.get_description()}")
        print()
        return

    # Load configuration
    config = load_config(args.config)

    # Override config for single analyzer test
    if args.analyzer:
        config["analyzers"] = {args.analyzer: {"enabled": True}}

    # Create orchestrator
    orchestrator = MarketAnalysisOrchestrator(config)

    # Run
    if args.once:
        orchestrator.run_once()
    else:
        orchestrator.run_continuous(interval=args.interval)


if __name__ == "__main__":
    main()
