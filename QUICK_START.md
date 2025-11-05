# Quick Start Guide

## Running Your First Simulation

### Test Run (Recommended First Step)

Run a quick 3-cycle test to make sure everything works:

```bash
python3 run_simulation.py --mode test --cycles 3
```

This will:
- Fetch real Kalshi market data
- Run spread and mispricing analyzers
- Execute trades with fake money ($100 starting capital)
- Complete 3 analysis cycles (~2-3 minutes)
- Show you a performance summary

### 30-Minute Simulation

Once the test works, try a longer run:

```bash
# Conservative approach (fewer, higher quality trades)
python3 run_simulation.py --mode conservative --minutes 30

# Aggressive approach (more trades, lower thresholds)
python3 run_simulation.py --mode aggressive --minutes 30

# Technical analysis only (RSI, MACD, Bollinger Bands)
python3 run_simulation.py --mode technical --minutes 30
```

### Custom Simulation

For full control:

```bash
python3 simulator.py \
    --hours 1 \
    --capital 500 \
    --interval 90 \
    --max-markets 75 \
    --analyzers spread,mispricing,rsi,imbalance
```

## Understanding the Output

### During Simulation

You'll see logs like:

```
2025-11-05 14:30:00 - INFO - Fetched 50 markets
2025-11-05 14:30:15 - INFO - SpreadAnalyzer found 5 opportunities
2025-11-05 14:30:15 - INFO - MispricingAnalyzer found 2 opportunities
2025-11-05 14:30:16 - INFO - TRADE EXECUTED: POS_0001 | MARKET-2025-11-05 | YES 10x @ 35¢
2025-11-05 14:30:16 - INFO - Cycle complete: 7 opps, 1 trades, 1 open positions
```

### Final Report

At the end, you get a detailed summary:

```
================================================================================
SIMULATION SUMMARY
================================================================================
Duration:         0:30:00
Cycles:           15
Snapshots:        6

--------------------------------------------------------------------------------
PORTFOLIO PERFORMANCE
--------------------------------------------------------------------------------
Initial Value:    $      100.00
Final Value:      $      103.50
Total P&L:        $        3.50  (  3.50%)
  Realized:       $        2.80
  Unrealized:     $        0.70
Max Drawdown:       1.20%

--------------------------------------------------------------------------------
TRADING STATISTICS
--------------------------------------------------------------------------------
Opportunities:       45
Trades:               8  (17.8% conversion)
Open Positions:       2
Closed Positions:     6

Win Rate:           66.7%
Avg Win:          $        0.80
Avg Loss:         $       -0.40
Profit Factor:            2.00
```

## Key Metrics Explained

- **Portfolio Value**: Cash + value of open positions
- **Total P&L**: How much you made/lost
  - **Realized**: Profit from closed positions
  - **Unrealized**: Current profit from open positions
- **Max Drawdown**: Largest drop from peak value
- **Conversion Rate**: % of opportunities that became trades
- **Win Rate**: % of closed positions that were profitable
- **Profit Factor**: Avg win / Avg loss (>1 is good, >2 is great)

## Simulation Modes Comparison

| Mode | Min Confidence | Min Edge | Max Positions | Analyzers | Best For |
|------|---------------|----------|---------------|-----------|----------|
| **Conservative** | HIGH | 10¢ / 5% | 5 | spread, mispricing, arbitrage | Low risk, high quality |
| **Aggressive** | MEDIUM | 3¢ / 2% | 10 | spread, mispricing, rsi, imbalance, momentum | More action, higher risk |
| **Technical** | MEDIUM | 5¢ | 8 | rsi, macd, bollinger_bands, ma_crossover | Technical analysis fans |
| **Test** | MEDIUM | 5¢ | 5 | spread, mispricing | Quick testing |

## Common Use Cases

### 1. Test a New Analyzer

```bash
python3 simulator.py --cycles 5 --analyzers your_new_analyzer --max-markets 30
```

### 2. Compare Strategies

```bash
# Run conservative
python3 run_simulation.py --mode conservative --minutes 60 > conservative_results.txt

# Run aggressive
python3 run_simulation.py --mode aggressive --minutes 60 > aggressive_results.txt

# Compare the results
diff conservative_results.txt aggressive_results.txt
```

### 3. Overnight Simulation

```bash
# Run for 8 hours
nohup python3 simulator.py --hours 8 --capital 1000 --interval 120 > overnight.log 2>&1 &

# Check progress
tail -f overnight.log

# Kill if needed
pkill -f simulator.py
```

### 4. Continuous Trading (Paper Trading)

```bash
# Run until manually stopped
python3 simulator.py --continuous --interval 60 --capital 1000
# Press Ctrl+C to stop and see results
```

## Tuning Your Strategy

### If you're getting too few trades:
- Lower `min_edge_cents` and `min_edge_percent`
- Change `min_confidence` to MEDIUM or LOW
- Change `min_strength` to SOFT
- Increase `max_positions`
- Add more analyzers
- Increase `max_markets`

### If you're losing money:
- Increase `min_edge_cents` and `min_edge_percent`
- Change `min_confidence` to HIGH
- Change `min_strength` to HARD
- Decrease `max_positions`
- Tighten `stop_loss_percent`
- Use only proven analyzers (spread, arbitrage)

### If positions are getting stopped out too much:
- Increase `stop_loss_percent` (e.g., 25% or 30%)
- Reduce `take_profit_percent` to lock in gains faster
- Use higher confidence thresholds

## Analyzing Results

Look for:

1. **Positive return** - Are you making money?
2. **High win rate** (>50%) - More wins than losses
3. **Good profit factor** (>1.5) - Wins are bigger than losses
4. **Reasonable conversion rate** (10-30%) - Not trading on everything
5. **Low max drawdown** (<10%) - Not risking too much

## Next Steps

Once you have good simulation results:

1. **Run longer simulations** - Test over multiple days
2. **Try different market conditions** - Weekdays vs weekends, volatile vs calm
3. **Fine-tune parameters** - Adjust thresholds based on results
4. **Analyze which analyzers work best** - Some may perform better than others
5. **Consider real trading** - When ready and confident

## Troubleshooting

**"No opportunities found"**
- Markets might be very liquid (narrow spreads)
- Try lower thresholds or different analyzers
- Increase `max_markets`

**"Insufficient cash" errors**
- Increase `initial_capital`
- Decrease `max_position_size`
- Reduce `max_positions`

**Rate limit errors**
- Increase `interval` (time between cycles)
- Decrease `max_markets`
- The client has built-in rate limiting

**No trades executed**
- Check rejection reasons in the summary
- Lower your quality thresholds
- Make sure analyzers are finding opportunities

## Safety Reminders

- ✅ This uses **FAKE MONEY** - no real trading
- ✅ Uses **READ-ONLY** API - cannot place real orders
- ✅ Safe to experiment with settings
- ⚠️ Past performance ≠ future results
- ⚠️ Test thoroughly before considering real trading

## Questions?

See the full documentation in `TRADE_MANAGER_README.md` for:
- Detailed architecture explanation
- Complete configuration reference
- API usage examples
- Integration with existing code
