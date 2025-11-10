#!/usr/bin/env python3
"""
Historical Backtesting with Real Kalshi Candlestick Data

This script fetches historical price data and simulates trading
to see actual P&L from our strategies.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List
from kalshi_client import KalshiDataClient
from trade_manager import TradeManager, TradeManagerConfig, Side
from analyzers.base import ConfidenceLevel
from analyzers.value_bet_analyzer import ValueBetAnalyzer
from analyzers.trend_follower_analyzer import TrendFollowerAnalyzer
from analyzers.mean_reversion_analyzer import MeanReversionAnalyzer
from analyzers.volume_surge_analyzer import VolumeSurgeAnalyzer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class HistoricalBacktester:
    """Backtests strategies using historical candlestick data."""
    
    def __init__(self):
        self.client = KalshiDataClient()
        self.analyzers = [
            ValueBetAnalyzer(),
            TrendFollowerAnalyzer(),
            MeanReversionAnalyzer(),
            VolumeSurgeAnalyzer(),
        ]
        
        trade_config = TradeManagerConfig(
            initial_capital=10000.0,  # $100
            max_position_size=1500.0,  # $15
            min_confidence=ConfidenceLevel.MEDIUM,
            min_edge_cents=5.0,
            max_positions=15,
            position_sizing_method='confidence_scaled',
        )
        self.trade_manager = TradeManager(trade_config)
    
    def get_markets_with_history(self, lookback_hours: int = 48) -> List[Dict]:
        """Get markets that have historical candlestick data."""
        logger.info("Fetching markets with volume...")
        
        # Get markets with decent volume
        markets = self.client.get_all_open_markets(
            max_markets=50,
            status="open",
            min_volume=500  # Higher volume = more likely to have history
        )
        
        logger.info(f"Found {len(markets)} markets with volume >= 500")
        
        markets_with_history = []
        end_ts = int(time.time())
        start_ts = end_ts - (lookback_hours * 3600)
        
        for i, market in enumerate(markets):
            ticker = market.get("ticker")
            series_ticker = market.get("series_ticker")
            
            if not series_ticker:
                series_ticker = ticker.split("-")[0] if ticker else None
            
            if not series_ticker or not ticker:
                continue
            
            try:
                # Try to fetch candlesticks
                candles = self.client.get_market_candlesticks(
                    series_ticker=series_ticker,
                    market_ticker=ticker,
                    start_ts=start_ts,
                    end_ts=end_ts,
                    period_interval=60  # 1 hour intervals
                )
                
                candlestick_data = candles.get("candlesticks", [])
                
                if candlestick_data and len(candlestick_data) >= 5:  # At least 5 data points
                    market["candlesticks"] = candlestick_data
                    market["series_ticker"] = series_ticker
                    markets_with_history.append(market)
                    logger.info(f"✓ {ticker[:40]}: {len(candlestick_data)} candles")
                    
                    if len(markets_with_history) >= 10:  # Limit for testing
                        break
            except Exception as e:
                logger.debug(f"Failed to get candlesticks for {ticker}: {e}")
                continue
        
        logger.info(f"Found {len(markets_with_history)} markets with historical data")
        return markets_with_history
    
    def simulate_from_history(self, markets: List[Dict]):
        """Simulate trading using historical price data."""
        if not markets:
            logger.error("No markets with historical data!")
            return
        
        logger.info(f"\n{'='*80}")
        logger.info("HISTORICAL BACKTEST SIMULATION")
        logger.info(f"{'='*80}\n")
        
        # Group all candlesticks by timestamp
        all_timestamps = set()
        for market in markets:
            for candle in market.get("candlesticks", []):
                all_timestamps.add(candle.get("ts"))
        
        timestamps = sorted(all_timestamps)
        logger.info(f"Simulating {len(timestamps)} time periods")
        logger.info(f"Start: {datetime.fromtimestamp(timestamps[0])}")
        logger.info(f"End: {datetime.fromtimestamp(timestamps[-1])}\n")
        
        # Run simulation for each timestamp
        for i, ts in enumerate(timestamps):
            # Get market state at this timestamp
            market_snapshot = []
            
            for market in markets:
                # Find the candlestick at this timestamp
                candle = None
                for c in market.get("candlesticks", []):
                    if c.get("ts") == ts:
                        candle = c
                        break
                
                if candle:
                    # Create market snapshot with current price
                    snapshot = {
                        "ticker": market.get("ticker"),
                        "title": market.get("title"),
                        "series_ticker": market.get("series_ticker"),
                        "last_price": candle.get("yes_ask_close", candle.get("yes_ask_open", 0)),
                        "volume": market.get("volume", 0),
                        "orderbook": self._create_orderbook_from_candle(candle),
                    }
                    market_snapshot.append(snapshot)
            
            # Update positions with current prices
            if i > 0:  # Skip first period (no positions yet)
                current_prices = {}
                for m in market_snapshot:
                    ticker = m.get("ticker")
                    price = m.get("last_price", 0)
                    current_prices[ticker] = {"yes": price, "no": 100 - price}
                
                self.trade_manager.update_positions(current_prices)
            
            # Run analyzers
            all_opportunities = []
            for analyzer in self.analyzers:
                try:
                    opps = analyzer.analyze(market_snapshot)
                    all_opportunities.extend(opps)
                except Exception as e:
                    logger.error(f"Analyzer error: {e}")
            
            # Process opportunities
            for opp in all_opportunities:
                should_trade, reason = self.trade_manager.should_trade(opp)
                if should_trade:
                    self.trade_manager.execute_trade(opp)
            
            # Log progress every 10 periods
            if (i + 1) % 10 == 0:
                stats = self.trade_manager.get_statistics()
                pnl = stats["total_pnl"] / 100
                logger.info(
                    f"Period {i+1}/{len(timestamps)}: "
                    f"Positions={stats['open_positions']}, "
                    f"P&L=${pnl:+.2f}"
                )
        
        # Final summary
        self._print_summary()
    
    def _create_orderbook_from_candle(self, candle: Dict) -> Dict:
        """Create synthetic orderbook from candlestick data."""
        yes_close = candle.get("yes_ask_close", candle.get("yes_ask_open", 50))
        
        return {
            "yes": [[yes_close, 100]],
            "no": [[100 - yes_close, 100]],
        }
    
    def _print_summary(self):
        """Print final backtest summary."""
        stats = self.trade_manager.get_statistics()
        
        print(f"\n{'='*80}")
        print("BACKTEST RESULTS")
        print(f"{'='*80}\n")
        
        print(f"Initial Capital:  ${stats['initial_capital']/100:.2f}")
        print(f"Final Value:      ${stats['portfolio_value']/100:.2f}")
        print(f"Total P&L:        ${stats['total_pnl']/100:+.2f} ({stats['total_pnl_percent']:+.2f}%)")
        print(f"  Realized:       ${stats['realized_pnl']/100:+.2f}")
        print(f"  Unrealized:     ${stats['unrealized_pnl']/100:+.2f}")
        
        print(f"\nTrades:")
        print(f"  Open Positions:   {stats['open_positions']}")
        print(f"  Closed Positions: {stats['closed_positions']}")
        print(f"  Total Trades:     {stats['total_trades']}")
        
        if stats['closed_positions'] > 0:
            wins = sum(1 for p in self.trade_manager.closed_positions if p.realized_pnl > 0)
            losses = sum(1 for p in self.trade_manager.closed_positions if p.realized_pnl < 0)
            win_rate = wins / stats['closed_positions'] * 100 if stats['closed_positions'] > 0 else 0
            
            print(f"\nWin Rate:")
            print(f"  Wins:   {wins}")
            print(f"  Losses: {losses}")
            print(f"  Rate:   {win_rate:.1f}%")
        
        print(f"\n{'='*80}\n")


if __name__ == "__main__":
    print("\n" + "="*80)
    print("HISTORICAL BACKTESTING WITH REAL KALSHI DATA")
    print("="*80 + "\n")
    
    backtester = HistoricalBacktester()
    
    # Get markets with historical data
    markets = backtester.get_markets_with_history(lookback_hours=72)
    
    if markets:
        # Run the backtest
        backtester.simulate_from_history(markets)
    else:
        print("No markets found with sufficient historical data!")
        print("Try again later or adjust the filters.")
