"""
Live Trading Simulator

Simulates trading with real Kalshi market data using fake money.
Tracks performance over time and generates reports.
"""

import logging
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from kalshi_client import KalshiDataClient
from trade_manager import TradeManager, TradeManagerConfig, Side
from analyzers.base import BaseAnalyzer
from analyzers.spread_analyzer import SpreadAnalyzer
from analyzers.mispricing_analyzer import MispricingAnalyzer
from analyzers.arbitrage_analyzer import ArbitrageAnalyzer
from analyzers.rsi_analyzer import RSIAnalyzer
from analyzers.bollinger_bands_analyzer import BollingerBandsAnalyzer
from analyzers.macd_analyzer import MACDAnalyzer
from analyzers.ma_crossover_analyzer import MovingAverageCrossoverAnalyzer
from analyzers.momentum_fade_analyzer import MomentumFadeAnalyzer
from analyzers.correlation_analyzer import CorrelationAnalyzer
from analyzers.imbalance_analyzer import ImbalanceAnalyzer
from analyzers.theta_decay_analyzer import ThetaDecayAnalyzer
from analyzers.volume_trend_analyzer import VolumeTrendAnalyzer
from analyzers.event_volatility_analyzer import EventVolatilityCrushAnalyzer
from analyzers.recency_bias_analyzer import RecencyBiasAnalyzer
from analyzers.psychological_level_analyzer import PsychologicalLevelAnalyzer
from analyzers.liquidity_trap_analyzer import LiquidityTrapAnalyzer
from analyzers.value_bet_analyzer import ValueBetAnalyzer
from analyzers.trend_follower_analyzer import TrendFollowerAnalyzer
from analyzers.mean_reversion_analyzer import MeanReversionAnalyzer
from analyzers.volume_surge_analyzer import VolumeSurgeAnalyzer
from analyzers.orderbook_depth_analyzer import OrderbookDepthAnalyzer
from analyzers.price_extreme_reversion_analyzer import PriceExtremeReversionAnalyzer
from analyzers.ml_predictor_analyzer import MLPredictorAnalyzer


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
    # Novice exploitation analyzers
    "event_volatility": EventVolatilityCrushAnalyzer,
    "recency_bias": RecencyBiasAnalyzer,
    "psychological_levels": PsychologicalLevelAnalyzer,
    "liquidity_trap": LiquidityTrapAnalyzer,
    "value_bet": ValueBetAnalyzer,
    "trend_follower": TrendFollowerAnalyzer,
    "mean_reversion": MeanReversionAnalyzer,
    "volume_surge": VolumeSurgeAnalyzer,
    # Orderbook-based analyzers
    "orderbook_depth": OrderbookDepthAnalyzer,
    # Price-based analyzers
    "price_extreme_reversion": PriceExtremeReversionAnalyzer,
    # ML-based analyzers
    "ml_predictor": MLPredictorAnalyzer,
}


@dataclass
class PortfolioSnapshot:
    """Snapshot of portfolio state at a point in time."""
    timestamp: datetime
    portfolio_value: float
    cash: float
    position_value: float
    num_positions: int
    total_pnl: float
    realized_pnl: float
    unrealized_pnl: float


@dataclass
class SimulatorConfig:
    """Configuration for the trading simulator."""

    # Trade manager config
    trade_manager_config: TradeManagerConfig = field(default_factory=TradeManagerConfig)

    # Analyzer configuration
    analyzer_names: List[str] = field(default_factory=lambda: ["spread", "mispricing"])
    analyzer_configs: Dict[str, Dict] = field(default_factory=dict)

    # Data fetching
    max_markets: int = 100  # Max markets to analyze per cycle
    market_status: str = "open"  # Market status filter

    # Simulation timing
    update_interval_seconds: int = 60  # Time between cycles
    snapshot_interval_seconds: int = 300  # Time between portfolio snapshots

    # Kalshi client settings
    cache_ttl: int = 30
    rate_limit: float = 20.0


class TradingSimulator:
    """
    Live trading simulator using real Kalshi data with fake money.

    Simulates the complete trading lifecycle:
    1. Fetch market data
    2. Run analyzers to find opportunities
    3. Evaluate and execute trades
    4. Update positions and check stops
    5. Track performance over time
    """

    def __init__(self, config: Optional[SimulatorConfig] = None):
        """
        Initialize the simulator.

        Args:
            config: Simulator configuration
        """
        self.config = config or SimulatorConfig()
        self.running = False
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None

        # Initialize components
        self.client = KalshiDataClient(
            cache_ttl=self.config.cache_ttl,
            rate_limit=self.config.rate_limit
        )

        self.trade_manager = TradeManager(self.config.trade_manager_config)
        self.analyzers = self._setup_analyzers()

        # Performance tracking
        self.snapshots: List[PortfolioSnapshot] = []
        self.cycle_count = 0
        self.last_snapshot_time = None

        # Statistics
        self.opportunities_found = 0
        self.opportunities_traded = 0
        self.opportunities_rejected: Dict[str, int] = {}

        logger.info("TradingSimulator initialized")
        logger.info(f"Analyzers: {[a.get_name() for a in self.analyzers]}")
        logger.info(f"Update interval: {self.config.update_interval_seconds}s")
        logger.info(f"Starting capital: ${self.config.trade_manager_config.initial_capital/100:.2f}")

    def _setup_analyzers(self) -> List[BaseAnalyzer]:
        """Set up analyzers based on configuration."""
        analyzers = []

        for analyzer_name in self.config.analyzer_names:
            if analyzer_name not in ANALYZER_REGISTRY:
                logger.warning(f"Unknown analyzer: {analyzer_name}")
                continue

            analyzer_class = ANALYZER_REGISTRY[analyzer_name]
            analyzer_config = self.config.analyzer_configs.get(analyzer_name, {})
            analyzer = analyzer_class(config=analyzer_config, kalshi_client=self.client)
            analyzers.append(analyzer)
            logger.info(f"Enabled analyzer: {analyzer.get_name()}")

        return analyzers

    def _take_snapshot(self) -> None:
        """Take a snapshot of current portfolio state."""
        summary = self.trade_manager.get_portfolio_summary()

        snapshot = PortfolioSnapshot(
            timestamp=datetime.now(),
            portfolio_value=summary['portfolio_value'],
            cash=summary['cash'],
            position_value=summary['position_value'],
            num_positions=summary['num_open_positions'],
            total_pnl=summary['total_pnl'],
            realized_pnl=summary['realized_pnl'],
            unrealized_pnl=summary['unrealized_pnl']
        )

        self.snapshots.append(snapshot)
        self.last_snapshot_time = datetime.now()

        logger.debug(f"Portfolio snapshot: ${snapshot.portfolio_value/100:.2f}")

    def _create_synthetic_orderbook(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a synthetic orderbook from last_price when real orderbook is empty.

        Args:
            market: Market dictionary with last_price

        Returns:
            Synthetic orderbook dict with yes and no arrays
        """
        last_price = market.get("last_price")
        volume = market.get("volume", 0)

        # If no last_price, we can't create synthetic orderbook
        if last_price is None:
            return {"yes": None, "no": None}

        # Add some spread around the last price to simulate orderbook
        # Use a tighter spread for higher volume markets
        if volume > 10000:
            spread = 2  # 2 cent spread for high volume
        elif volume > 1000:
            spread = 3  # 3 cent spread for medium volume
        else:
            spread = 5  # 5 cent spread for low volume

        # Calculate synthetic bids
        # last_price is typically the YES price
        yes_price = last_price
        no_price = 100 - last_price

        # Create synthetic bid/ask with spread
        yes_bid = max(1, yes_price - spread // 2)
        yes_ask = min(99, yes_price + spread // 2)
        no_bid = max(1, no_price - spread // 2)
        no_ask = min(99, no_price + spread // 2)

        # Use volume to estimate orderbook depth (quantity)
        # Higher volume = more depth
        base_qty = max(10, volume // 100)

        # Create orderbook arrays: [[price, quantity], ...]
        return {
            "yes": [[yes_bid, base_qty], [yes_bid - 1, base_qty // 2]],
            "no": [[no_bid, base_qty], [no_bid - 1, base_qty // 2]],
        }

    def _fetch_markets_with_orderbooks(self) -> List[Dict[str, Any]]:
        """
        Fetch markets with orderbook data.

        Returns:
            List of enriched market dictionaries
        """
        logger.info("Fetching market data...")

        # Fetch markets with minimum volume to ensure liquid markets
        markets = self.client.get_all_open_markets(
            max_markets=self.config.max_markets,
            status=self.config.market_status,
            min_volume=10  # Filter for markets with at least some volume
        )
        logger.info(f"Fetched {len(markets)} markets")

        # Filter out markets with no last_price (untradable)
        markets_with_price = [m for m in markets if m.get("last_price") is not None and m.get("last_price") > 0]
        logger.info(f"Filtered to {len(markets_with_price)} markets with valid prices")
        markets = markets_with_price

        # Enrich with orderbooks
        enriched_markets = []
        synthetic_count = 0

        for i, market in enumerate(markets):
            ticker = market.get("ticker")

            try:
                orderbook_response = self.client.get_orderbook(ticker)
                orderbook = orderbook_response.get("orderbook", {})

                # Check if orderbook is empty (yes/no are None)
                if orderbook.get("yes") is None or orderbook.get("no") is None:
                    # Create synthetic orderbook from last_price
                    synthetic_orderbook = self._create_synthetic_orderbook(market)
                    market["orderbook"] = synthetic_orderbook
                    if synthetic_orderbook.get("yes") is not None:
                        synthetic_count += 1
                else:
                    market["orderbook"] = orderbook

                # Extract series_ticker if not present
                if not market.get("series_ticker") and ticker:
                    market["series_ticker"] = ticker.split("-")[0]

                enriched_markets.append(market)

                if (i + 1) % 20 == 0:
                    logger.debug(f"Fetched orderbooks for {i + 1}/{len(markets)} markets")

            except Exception as e:
                logger.debug(f"Failed to fetch orderbook for {ticker}: {e}")
                # Try to create synthetic orderbook even if fetch fails
                try:
                    synthetic_orderbook = self._create_synthetic_orderbook(market)
                    if synthetic_orderbook.get("yes") is not None:
                        market["orderbook"] = synthetic_orderbook
                        market["series_ticker"] = ticker.split("-")[0] if ticker else None
                        enriched_markets.append(market)
                        synthetic_count += 1
                except:
                    continue

        logger.info(f"Enriched {len(enriched_markets)} markets with orderbooks ({synthetic_count} synthetic)")
        return enriched_markets

    def _extract_market_prices(self, markets: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
        """
        Extract current market prices from market data.

        Args:
            markets: List of market dictionaries with orderbooks

        Returns:
            Dict mapping ticker -> {"yes": price, "no": price}
        """
        market_prices = {}

        for market in markets:
            ticker = market.get("ticker")
            orderbook = market.get("orderbook", {})

            yes_bids = orderbook.get("yes", [])
            no_bids = orderbook.get("no", [])

            if yes_bids and no_bids:
                yes_price = yes_bids[0][0] if yes_bids[0] else None
                no_price = no_bids[0][0] if no_bids[0] else None

                if yes_price is not None and no_price is not None:
                    market_prices[ticker] = {
                        "yes": yes_price,
                        "no": no_price
                    }

        return market_prices

    def _run_analysis(self, markets: List[Dict[str, Any]]) -> List[Any]:
        """
        Run all analyzers on market data.

        Args:
            markets: List of market dictionaries

        Returns:
            List of opportunities found
        """
        all_opportunities = []

        for analyzer in self.analyzers:
            try:
                opportunities = analyzer.analyze(markets)
                all_opportunities.extend(opportunities)
                logger.info(f"{analyzer.get_name()} found {len(opportunities)} opportunities")
            except Exception as e:
                logger.error(f"Error running {analyzer.get_name()}: {e}", exc_info=True)

        return all_opportunities

    def _process_opportunities(self, opportunities: List[Any]) -> Tuple[int, int]:
        """
        Process opportunities and execute trades.

        Args:
            opportunities: List of opportunities to process

        Returns:
            Tuple of (num_traded, num_rejected)
        """
        num_traded = 0
        num_rejected = 0

        for opp in opportunities:
            should_trade, reason = self.trade_manager.should_trade(opp)

            if should_trade:
                position = self.trade_manager.execute_trade(opp)
                if position:
                    num_traded += 1
                    self.opportunities_traded += 1
                else:
                    num_rejected += 1
                    self.opportunities_rejected[reason] = self.opportunities_rejected.get(reason, 0) + 1
            else:
                num_rejected += 1
                self.opportunities_rejected[reason] = self.opportunities_rejected.get(reason, 0) + 1

        return num_traded, num_rejected

    def _update_positions_and_check_stops(self, market_prices: Dict[str, Dict[str, float]]) -> int:
        """
        Update position prices and check stop losses / take profits.

        Args:
            market_prices: Current market prices

        Returns:
            Number of positions closed
        """
        # Update prices
        self.trade_manager.update_position_prices(market_prices)

        # Check stops and targets
        closed_ids = self.trade_manager.check_stops_and_targets(market_prices)

        if closed_ids:
            logger.info(f"Closed {len(closed_ids)} positions (stops/targets)")

        return len(closed_ids)

    def run_cycle(self) -> Dict[str, Any]:
        """
        Run one complete simulation cycle.

        Returns:
            Dictionary with cycle statistics
        """
        cycle_start = time.time()
        self.cycle_count += 1

        logger.info("=" * 80)
        logger.info(f"Cycle {self.cycle_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 80)

        try:
            # 1. Fetch market data
            markets = self._fetch_markets_with_orderbooks()

            # 2. Extract current prices for position updates
            market_prices = self._extract_market_prices(markets)

            # 3. Update positions and check stops
            positions_closed = self._update_positions_and_check_stops(market_prices)

            # 4. Run analyzers
            opportunities = self._run_analysis(markets)
            self.opportunities_found += len(opportunities)

            # 5. Process opportunities and execute trades
            num_traded, num_rejected = self._process_opportunities(opportunities)

            # 6. Take snapshot if needed
            now = datetime.now()
            if (self.last_snapshot_time is None or
                (now - self.last_snapshot_time).total_seconds() >= self.config.snapshot_interval_seconds):
                self._take_snapshot()

            # Prepare cycle summary
            cycle_summary = {
                "cycle": self.cycle_count,
                "markets_analyzed": len(markets),
                "opportunities_found": len(opportunities),
                "trades_executed": num_traded,
                "opportunities_rejected": num_rejected,
                "positions_closed": positions_closed,
                "portfolio_value": self.trade_manager.portfolio_value,
                "total_pnl": self.trade_manager.total_pnl,
                "num_open_positions": len(self.trade_manager.positions),
                "cycle_duration": time.time() - cycle_start
            }

            # Log summary
            logger.info(f"Cycle complete: {len(opportunities)} opps, {num_traded} trades, "
                       f"{len(self.trade_manager.positions)} open positions, "
                       f"Portfolio: ${self.trade_manager.portfolio_value/100:.2f} "
                       f"(P&L: ${self.trade_manager.total_pnl/100:+.2f})")

            return cycle_summary

        except Exception as e:
            logger.error(f"Error in cycle {self.cycle_count}: {e}", exc_info=True)
            return {
                "cycle": self.cycle_count,
                "error": str(e),
                "cycle_duration": time.time() - cycle_start
            }

    def run_for_duration(
        self,
        hours: Optional[float] = None,
        minutes: Optional[float] = None,
        cycles: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Run simulator for a specified duration or number of cycles.

        Args:
            hours: Number of hours to run (mutually exclusive with minutes/cycles)
            minutes: Number of minutes to run (mutually exclusive with hours/cycles)
            cycles: Number of cycles to run (mutually exclusive with hours/minutes)

        Returns:
            Performance report dictionary
        """
        # Determine run duration
        if cycles is not None:
            total_cycles = cycles
            duration = None
            logger.info(f"Starting simulation for {cycles} cycles")
        elif hours is not None:
            duration = timedelta(hours=hours)
            total_cycles = None
            logger.info(f"Starting simulation for {hours} hour(s)")
        elif minutes is not None:
            duration = timedelta(minutes=minutes)
            total_cycles = None
            logger.info(f"Starting simulation for {minutes} minute(s)")
        else:
            raise ValueError("Must specify either hours, minutes, or cycles")

        self.running = True
        self.start_time = datetime.now()

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        # Take initial snapshot
        self._take_snapshot()

        cycle_summaries = []

        try:
            while self.running:
                # Run a cycle
                summary = self.run_cycle()
                cycle_summaries.append(summary)

                # Check stopping conditions
                if total_cycles is not None:
                    if self.cycle_count >= total_cycles:
                        logger.info(f"Completed {total_cycles} cycles")
                        break
                elif duration is not None:
                    elapsed = datetime.now() - self.start_time
                    if elapsed >= duration:
                        logger.info(f"Duration reached ({duration})")
                        break

                # Sleep until next cycle
                if self.running:
                    logger.info(f"Sleeping for {self.config.update_interval_seconds}s...")
                    time.sleep(self.config.update_interval_seconds)

        except Exception as e:
            logger.error(f"Simulation error: {e}", exc_info=True)

        finally:
            self.running = False
            self.end_time = datetime.now()

            # Take final snapshot
            self._take_snapshot()

        # Generate performance report
        report = self.generate_performance_report()

        return report

    def run_continuous(self) -> None:
        """Run simulator continuously until stopped."""
        logger.info("Starting continuous simulation (Ctrl+C to stop)")

        self.running = True
        self.start_time = datetime.now()

        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        self._take_snapshot()

        try:
            while self.running:
                self.run_cycle()

                if self.running:
                    logger.info(f"Sleeping for {self.config.update_interval_seconds}s...")
                    time.sleep(self.config.update_interval_seconds)

        finally:
            self.running = False
            self.end_time = datetime.now()
            self._take_snapshot()

            logger.info("Simulation stopped")
            self.print_summary()

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, stopping simulation...")
        self.running = False

    def generate_performance_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive performance report.

        Returns:
            Dictionary with performance metrics
        """
        if not self.start_time:
            return {"error": "Simulation not started"}

        # Time metrics
        end_time = self.end_time or datetime.now()
        total_duration = end_time - self.start_time

        # Portfolio metrics
        portfolio_summary = self.trade_manager.get_portfolio_summary()

        # Calculate additional metrics
        initial_value = self.config.trade_manager_config.initial_capital
        final_value = portfolio_summary['portfolio_value']

        # Win/loss analysis
        closed_positions = self.trade_manager.closed_positions
        winning_trades = [p for p in closed_positions if p.realized_pnl > 0]
        losing_trades = [p for p in closed_positions if p.realized_pnl < 0]

        win_rate = (len(winning_trades) / len(closed_positions) * 100
                   if closed_positions else 0.0)

        avg_win = (sum(p.realized_pnl for p in winning_trades) / len(winning_trades)
                  if winning_trades else 0.0)
        avg_loss = (sum(p.realized_pnl for p in losing_trades) / len(losing_trades)
                   if losing_trades else 0.0)

        # Snapshot analysis
        if len(self.snapshots) >= 2:
            max_value = max(s.portfolio_value for s in self.snapshots)
            min_value = min(s.portfolio_value for s in self.snapshots)
            max_drawdown = ((max_value - min_value) / max_value * 100
                          if max_value > 0 else 0.0)
        else:
            max_drawdown = 0.0

        report = {
            "simulation": {
                "start_time": self.start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration": str(total_duration),
                "total_cycles": self.cycle_count,
                "snapshots_taken": len(self.snapshots)
            },
            "portfolio": {
                "initial_value": initial_value,
                "final_value": final_value,
                "total_pnl": portfolio_summary['total_pnl'],
                "realized_pnl": portfolio_summary['realized_pnl'],
                "unrealized_pnl": portfolio_summary['unrealized_pnl'],
                "return_percent": portfolio_summary['return_percent'],
                "max_drawdown_percent": max_drawdown,
                "final_cash": portfolio_summary['cash'],
                "final_position_value": portfolio_summary['position_value']
            },
            "trading": {
                "opportunities_found": self.opportunities_found,
                "opportunities_traded": self.opportunities_traded,
                "conversion_rate": (self.opportunities_traded / self.opportunities_found * 100
                                  if self.opportunities_found > 0 else 0.0),
                "total_trades": portfolio_summary['num_trades'],
                "open_positions": portfolio_summary['num_open_positions'],
                "closed_positions": portfolio_summary['num_closed_positions'],
                "win_rate": win_rate,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "profit_factor": (abs(avg_win / avg_loss) if avg_loss != 0 else float('inf'))
            },
            "rejection_reasons": self.opportunities_rejected
        }

        return report

    def print_summary(self) -> None:
        """Print formatted simulation summary."""
        report = self.generate_performance_report()

        print("\n" + "=" * 80)
        print("SIMULATION SUMMARY")
        print("=" * 80)

        # Simulation info
        sim = report['simulation']
        print(f"Duration:         {sim['duration']}")
        print(f"Cycles:           {sim['total_cycles']}")
        print(f"Snapshots:        {sim['snapshots_taken']}")

        print("\n" + "-" * 80)
        print("PORTFOLIO PERFORMANCE")
        print("-" * 80)

        # Portfolio metrics
        pf = report['portfolio']
        print(f"Initial Value:    ${pf['initial_value']/100:>12,.2f}")
        print(f"Final Value:      ${pf['final_value']/100:>12,.2f}")
        print(f"Total P&L:        ${pf['total_pnl']/100:>12,.2f}  ({pf['return_percent']:>6.2f}%)")
        print(f"  Realized:       ${pf['realized_pnl']/100:>12,.2f}")
        print(f"  Unrealized:     ${pf['unrealized_pnl']/100:>12,.2f}")
        print(f"Max Drawdown:     {pf['max_drawdown_percent']:>6.2f}%")

        print("\n" + "-" * 80)
        print("TRADING STATISTICS")
        print("-" * 80)

        # Trading metrics
        tr = report['trading']
        print(f"Opportunities:    {tr['opportunities_found']:>6}")
        print(f"Trades:           {tr['opportunities_traded']:>6}  ({tr['conversion_rate']:.1f}% conversion)")
        print(f"Open Positions:   {tr['open_positions']:>6}")
        print(f"Closed Positions: {tr['closed_positions']:>6}")

        if tr['closed_positions'] > 0:
            print(f"\nWin Rate:         {tr['win_rate']:>6.1f}%")
            print(f"Avg Win:          ${tr['avg_win']/100:>12,.2f}")
            print(f"Avg Loss:         ${tr['avg_loss']/100:>12,.2f}")
            if tr['avg_loss'] != 0:
                print(f"Profit Factor:    {tr['profit_factor']:>12.2f}")

        # Rejection reasons
        if report['rejection_reasons']:
            print("\n" + "-" * 80)
            print("TOP REJECTION REASONS")
            print("-" * 80)
            sorted_rejections = sorted(
                report['rejection_reasons'].items(),
                key=lambda x: x[1],
                reverse=True
            )
            for reason, count in sorted_rejections[:5]:
                print(f"{reason:50s} {count:>6}")

        print("=" * 80 + "\n")

        # Print detailed portfolio summary
        self.trade_manager.print_summary()

    def plot_equity_curve(self, save_path: Optional[str] = None) -> None:
        """
        Plot equity curve over time.

        Args:
            save_path: Optional path to save plot image
        """
        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
        except ImportError:
            logger.warning("matplotlib not installed, cannot plot equity curve")
            return

        if not self.snapshots:
            logger.warning("No snapshots available to plot")
            return

        timestamps = [s.timestamp for s in self.snapshots]
        values = [s.portfolio_value / 100 for s in self.snapshots]  # Convert to dollars

        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(timestamps, values, linewidth=2)
        ax.axhline(y=self.config.trade_manager_config.initial_capital / 100,
                  color='gray', linestyle='--', alpha=0.5, label='Initial Capital')

        ax.set_xlabel('Time')
        ax.set_ylabel('Portfolio Value ($)')
        ax.set_title('Portfolio Equity Curve')
        ax.grid(True, alpha=0.3)
        ax.legend()

        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.xticks(rotation=45)
        plt.tight_layout()

        if save_path:
            plt.savefig(save_path)
            logger.info(f"Equity curve saved to {save_path}")
        else:
            plt.show()


if __name__ == "__main__":
    import argparse

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Parse arguments
    parser = argparse.ArgumentParser(description="Kalshi Trading Simulator")
    parser.add_argument("--hours", type=float, help="Run for N hours")
    parser.add_argument("--minutes", type=float, help="Run for N minutes")
    parser.add_argument("--cycles", type=int, help="Run for N cycles")
    parser.add_argument("--interval", type=int, default=60,
                       help="Update interval in seconds (default: 60)")
    parser.add_argument("--capital", type=float, default=100.0,
                       help="Initial capital in dollars (default: 100)")
    parser.add_argument("--max-markets", type=int, default=100,
                       help="Max markets to analyze (default: 100)")
    parser.add_argument("--analyzers", type=str, default="spread,mispricing",
                       help="Comma-separated list of analyzers (default: spread,mispricing)")
    parser.add_argument("--continuous", action="store_true",
                       help="Run continuously until stopped")
    parser.add_argument("--plot", action="store_true",
                       help="Plot equity curve at end")

    args = parser.parse_args()

    # Create configuration
    trade_config = TradeManagerConfig(
        initial_capital=args.capital * 100,  # Convert to cents
        max_position_size=args.capital * 10,  # 10% per position
        min_edge_cents=5.0
    )

    sim_config = SimulatorConfig(
        trade_manager_config=trade_config,
        analyzer_names=args.analyzers.split(","),
        max_markets=args.max_markets,
        update_interval_seconds=args.interval
    )

    # Create simulator
    simulator = TradingSimulator(sim_config)

    # Run simulation
    if args.continuous:
        simulator.run_continuous()
    elif args.hours or args.minutes or args.cycles:
        report = simulator.run_for_duration(
            hours=args.hours,
            minutes=args.minutes,
            cycles=args.cycles
        )
        simulator.print_summary()

        if args.plot:
            simulator.plot_equity_curve()
    else:
        print("Must specify --hours, --minutes, --cycles, or --continuous")
        parser.print_help()
