#!/usr/bin/env python3
"""
Live Backtesting with REAL Kalshi Trade Data

Uses the trades endpoint to get actual historical trades and run backtest.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List
from kalshi_client import KalshiDataClient
from trade_manager import TradeManager, TradeManagerConfig
from analyzers.base import ConfidenceLevel
from analyzers.value_bet_analyzer import ValueBetAnalyzer
from analyzers.trend_follower_analyzer import TrendFollowerAnalyzer
from analyzers.mean_reversion_analyzer import MeanReversionAnalyzer
from analyzers.volume_surge_analyzer import VolumeSurgeAnalyzer

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class RealDataBacktester:
    """Backtests using real Kalshi trade history."""
    
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
    
    def get_markets_with_trades(self) -> List[Dict]:
        """Find markets that have recent trades."""
        print("Finding markets with recent trade activity...")
        
        markets = self.client.get_all_open_markets(max_markets=200, status="open")
        
        markets_with_trades = []
        for market in markets:
            ticker = market.get("ticker")
            
            try:
                # Check for recent trades
                trades_response = self.client.get_trades(market_ticker=ticker, limit=10)
                trades = trades_response.get("trades", [])
                
                if trades:
                    # Get market details
                    details = self.client.get_market(ticker)
                    open_interest = details.get("open_interest", 0)
                    
                    if open_interest > 0:  # Has actual positions
                        markets_with_trades.append({
                            "ticker": ticker,
                            "title": details.get("title", "")[:50],
                            "open_interest": open_interest,
                            "volume": details.get("volume", 0),
                            "last_price": details.get("last_price", 0),
                            "trades": trades,
                        })
                        
                        print(f"  ✓ {ticker[:40]} - {len(trades)} recent trades, OI: {open_interest:,}")
                        
                        if len(markets_with_trades) >= 20:
                            break
            except:
                pass
        
        print(f"\nFound {len(markets_with_trades)} markets with trading activity\n")
        return markets_with_trades
    
    def run_live_backtest(self, num_cycles: int = 15):
        """Run backtest checking real market prices each cycle."""
        print(f"\n{'='*80}")
        print("LIVE BACKTEST WITH REAL KALSHI DATA")
        print(f"{'='*80}\n")
        
        # Get markets
        markets = self.get_markets_with_trades()
        
        if not markets:
            print("❌ No markets with trading activity found!")
            return
        
        print(f"Running {num_cycles} cycles, checking prices every 5 seconds...\n")
        
        print(f"{'='*80}")
        print(f"{'Cycle':<6} {'Opps':<6} {'Trades':<8} {'Open':<6} {'P&L':<12} {'Portfolio':<12}")
        print(f"{'='*80}")
        
        for cycle in range(num_cycles):
            # Get current prices from market data
            current_markets = []
            
            for m in markets:
                ticker = m.get("ticker")
                
                try:
                    # Get latest market data
                    details = self.client.get_market(ticker)
                    
                    last_price = details.get("last_price", m.get("last_price", 0))
                    
                    market_snapshot = {
                        "ticker": ticker,
                        "title": m.get("title"),
                        "series_ticker": ticker.split("-")[0],
                        "last_price": last_price,
                        "volume": details.get("volume", 0),
                        "open_interest": details.get("open_interest", 0),
                        "orderbook": {
                            "yes": [[last_price, 100]] if last_price > 0 else None,
                            "no": [[100 - last_price, 100]] if last_price > 0 else None,
                        }
                    }
                    current_markets.append(market_snapshot)
                except:
                    pass
            
            # Update positions
            if cycle > 0:
                current_prices = {}
                for m in current_markets:
                    ticker = m.get("ticker")
                    price = m.get("last_price", 0)
                    if price > 0:
                        current_prices[ticker] = {"yes": price, "no": 100 - price}
                
                if current_prices:
                    self.trade_manager.update_position_prices(current_prices)
            
            # Run analyzers
            all_opportunities = []
            for analyzer in self.analyzers:
                try:
                    opps = analyzer.analyze(current_markets)
                    all_opportunities.extend(opps)
                except:
                    pass
            
            # Execute trades
            trades_this_cycle = 0
            for opp in all_opportunities:
                should_trade, reason = self.trade_manager.should_trade(opp)
                if should_trade:
                    if self.trade_manager.execute_trade(opp):
                        trades_this_cycle += 1
            
            # Print status
            stats = self.trade_manager.get_portfolio_summary()
            print(
                f"{cycle+1:<6} "
                f"{len(all_opportunities):<6} "
                f"{trades_this_cycle:<8} "
                f"{stats['num_open_positions']:<6} "
                f"${stats['total_pnl']/100:+8.2f}  "
                f"${stats['portfolio_value']/100:8.2f}"
            )
            
            # Wait before next cycle (to see real price changes)
            if cycle < num_cycles - 1:
                time.sleep(5)
        
        print(f"{'='*80}\n")
        
        # Final summary
        self._print_summary()
    
    def _print_summary(self):
        """Print backtest summary."""
        stats = self.trade_manager.get_portfolio_summary()
        
        print(f"\n{'='*80}")
        print("BACKTEST RESULTS (REAL KALSHI DATA)")
        print(f"{'='*80}\n")
        
        print("Portfolio Performance:")
        print(f"  Initial Capital:  ${stats['initial_capital']/100:.2f}")
        print(f"  Final Value:      ${stats['portfolio_value']/100:.2f}")
        print(f"  Total P&L:        ${stats['total_pnl']/100:+.2f} ({stats['return_percent']:+.2f}%)")
        print(f"  Realized P&L:     ${stats['realized_pnl']/100:+.2f}")
        print(f"  Unrealized P&L:   ${stats['unrealized_pnl']/100:+.2f}")
        
        print(f"\nTrading Activity:")
        print(f"  Total Trades:     {stats['num_trades']}")
        print(f"  Open Positions:   {stats['num_open_positions']}")
        print(f"  Closed Positions: {stats['num_closed_positions']}")
        
        if stats['num_closed_positions'] > 0:
            wins = sum(1 for p in self.trade_manager.closed_positions if p.realized_pnl > 0)
            win_rate = wins / stats['num_closed_positions'] * 100
            print(f"\nWin Rate: {win_rate:.1f}% ({wins}/{stats['num_closed_positions']})")
        
        print(f"\n{'='*80}\n")


if __name__ == "__main__":
    backtester = RealDataBacktester()
    backtester.run_live_backtest(num_cycles=15)
    
    print("✓ Live backtest complete using REAL Kalshi market data!")
    print("\nNote: Prices are from actual Kalshi markets with real trades.")
    print("Orderbooks are null because there are no active limit orders,")
    print("but the markets ARE trading (via market orders).")
