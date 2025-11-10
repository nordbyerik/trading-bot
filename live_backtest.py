#!/usr/bin/env python3
"""
Live Backtesting with Simulated Price Movements

Since Kalshi markets aren't actively trading right now, we'll simulate
realistic price movements based on market dynamics to test our strategies.
"""

import logging
import random
import time
from datetime import datetime
from typing import Dict, List
from kalshi_client import KalshiDataClient
from trade_manager import TradeManager, TradeManagerConfig, Side
from analyzers.base import ConfidenceLevel
from analyzers.value_bet_analyzer import ValueBetAnalyzer
from analyzers.trend_follower_analyzer import TrendFollowerAnalyzer
from analyzers.mean_reversion_analyzer import MeanReversionAnalyzer
from analyzers.volume_surge_analyzer import VolumeSurgeAnalyzer

logging.basicConfig(
    level=logging.WARNING,  # Reduce noise
    format="%(message)s"
)
logger = logging.getLogger(__name__)


class LiveBacktester:
    """Runs live backtesting with realistic price simulation."""
    
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
        self.price_history = {}  # Track price movements
    
    def simulate_price_movement(self, market: Dict, cycle: int) -> int:
        """
        Simulate realistic price movement for a market.
        
        Prices tend to:
        - Mean revert (move toward 50¢)
        - Show momentum (continue in same direction)
        - Have random walk component
        """
        ticker = market.get("ticker")
        current_price = market.get("last_price", 50)
        
        # Initialize if first time
        if ticker not in self.price_history:
            self.price_history[ticker] = {
                "initial": current_price,
                "prices": [current_price],
                "trend": random.choice([-1, 0, 1]),  # Downtrend, neutral, uptrend
            }
        
        history = self.price_history[ticker]
        
        # Mean reversion force (stronger when far from 50)
        distance_from_mean = current_price - 50
        mean_reversion = -distance_from_mean * 0.1  # 10% pull toward mean
        
        # Momentum force (continue trend)
        momentum = history["trend"] * 2
        
        # Random walk
        random_component = random.uniform(-3, 3)
        
        # Combine forces
        total_change = mean_reversion + momentum + random_component
        
        # Apply change
        new_price = current_price + total_change
        
        # Clamp to valid range [1, 99]
        new_price = max(1, min(99, int(new_price)))
        
        # Update history
        history["prices"].append(new_price)
        
        # Update trend based on recent movement
        if len(history["prices"]) >= 3:
            recent_change = history["prices"][-1] - history["prices"][-3]
            if recent_change > 5:
                history["trend"] = 1  # Uptrend
            elif recent_change < -5:
                history["trend"] = -1  # Downtrend
            else:
                history["trend"] = 0  # Neutral
        
        return new_price
    
    def run_backtest(self, num_cycles: int = 20, delay_seconds: float = 0.5):
        """Run live backtest simulation."""
        print(f"\n{'='*80}")
        print("LIVE BACKTEST SIMULATION")
        print(f"{'='*80}\n")
        
        print("Fetching initial markets...")
        
        # Get initial markets
        initial_markets = self.client.get_all_open_markets(
            max_markets=50,
            status="open",
            min_volume=50
        )
        
        # Filter for markets with valid prices
        markets = [m for m in initial_markets 
                   if m.get("last_price") and m.get("last_price") > 0]
        
        print(f"Tracking {len(markets)} markets")
        print(f"Running {num_cycles} cycles with price simulation\n")
        
        print(f"{'='*80}")
        print(f"{'Cycle':<6} {'Opps':<6} {'Trades':<8} {'Open':<6} {'P&L':<12} {'Portfolio':<12}")
        print(f"{'='*80}")
        
        for cycle in range(num_cycles):
            # Update prices with simulation
            updated_markets = []
            for market in markets:
                new_price = self.simulate_price_movement(market, cycle)
                
                updated_market = {
                    "ticker": market.get("ticker"),
                    "title": market.get("title"),
                    "series_ticker": market.get("series_ticker"),
                    "last_price": new_price,
                    "volume": market.get("volume", 100),
                    "orderbook": {
                        "yes": [[new_price, 100], [new_price - 1, 50]],
                        "no": [[100 - new_price, 100], [100 - new_price - 1, 50]],
                    }
                }
                updated_markets.append(updated_market)
            
            # Update positions with new prices
            if cycle > 0:
                current_prices = {}
                for m in updated_markets:
                    ticker = m.get("ticker")
                    price = m.get("last_price")
                    current_prices[ticker] = {"yes": price, "no": 100 - price}
                
                self.trade_manager.update_position_prices(current_prices)
            
            # Run analyzers
            all_opportunities = []
            for analyzer in self.analyzers:
                try:
                    opps = analyzer.analyze(updated_markets)
                    all_opportunities.extend(opps)
                except:
                    pass
            
            # Process opportunities
            trades_this_cycle = 0
            for opp in all_opportunities:
                should_trade, reason = self.trade_manager.should_trade(opp)
                if should_trade:
                    if self.trade_manager.execute_trade(opp):
                        trades_this_cycle += 1
            
            # Print progress
            stats = self.trade_manager.get_portfolio_summary()
            print(
                f"{cycle+1:<6} "
                f"{len(all_opportunities):<6} "
                f"{trades_this_cycle:<8} "
                f"{stats['num_open_positions']:<6} "
                f"${stats['total_pnl']/100:+8.2f}  "
                f"${stats['portfolio_value']/100:8.2f}"
            )
            
            time.sleep(delay_seconds)
        
        print(f"{'='*80}\n")
        
        # Final summary
        self._print_summary()
    
    def _print_summary(self):
        """Print final backtest summary."""
        stats = self.trade_manager.get_portfolio_summary()
        
        print(f"\n{'='*80}")
        print("BACKTEST RESULTS")
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
            losses = sum(1 for p in self.trade_manager.closed_positions if p.realized_pnl < 0)
            breakeven = sum(1 for p in self.trade_manager.closed_positions if p.realized_pnl == 0)
            win_rate = wins / stats['num_closed_positions'] * 100
            
            print(f"\nClosed Position Performance:")
            print(f"  Wins:      {wins} ({win_rate:.1f}%)")
            print(f"  Losses:    {losses} ({losses/stats['num_closed_positions']*100:.1f}%)")
            print(f"  Breakeven: {breakeven}")
            
            if wins > 0:
                avg_win = sum(p.realized_pnl for p in self.trade_manager.closed_positions if p.realized_pnl > 0) / wins / 100
                print(f"  Avg Win:   ${avg_win:.2f}")
            
            if losses > 0:
                avg_loss = sum(p.realized_pnl for p in self.trade_manager.closed_positions if p.realized_pnl < 0) / losses / 100
                print(f"  Avg Loss:  ${avg_loss:.2f}")
        
        print(f"\n{'='*80}\n")
        
        # Show some example price movements
        print("Sample Price Movements:")
        count = 0
        for ticker, history in self.price_history.items():
            if count >= 5:
                break
            if len(history["prices"]) > 1:
                initial = history["prices"][0]
                final = history["prices"][-1]
                change = final - initial
                print(f"  {ticker[:40]}: {initial}¢ → {final}¢ (Δ{change:+d}¢)")
                count += 1
        
        print(f"\n{'='*80}\n")


if __name__ == "__main__":
    backtester = LiveBacktester()
    backtester.run_backtest(num_cycles=30, delay_seconds=0.2)
    
    print("✓ Backtest complete!")
    print("\nNote: Prices were simulated using realistic market dynamics")
    print("(mean reversion + momentum + random walk) since Kalshi markets")
    print("are not actively trading right now.")
