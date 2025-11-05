# Analyzer Debugging Findings

**Date**: November 5, 2025
**Status**: CRITICAL ISSUES FOUND

## Executive Summary

The analyzers are not working properly due to fundamental data issues:

1. **All markets are multivariate** (KXMV prefix) - these are parlay/combo bets
2. **Multivariate markets don't have orderbook depth data** - API returns null
3. **Current market bid prices are 0¢** - no active liquidity
4. **Analyzers are trying to use orderbook data that doesn't exist**

## Root Cause Analysis

### Issue #1: Multivariate Markets Have No Orderbook Depth

**What we discovered:**
- All fetched markets have ticker prefix `KXMV` (Kalshi Multivariate)
- These are combo/parlay markets (e.g., "yes Bo Nix, yes Courtland Sutton, yes Troy Franklin...")
- The orderbook API endpoint returns: `{"orderbook": {"yes": null, "no": null}}`
- This is **by design** - multivariate markets don't expose orderbook depth

**Evidence:**
```json
{
  "ticker": "KXMVENFLSINGLEGAME-S20258A066D85916-F9A08FAF44C",
  "title": "yes Bo Nix,yes Courtland Sutton,yes Troy Franklin...",
  "orderbook": {
    "yes": null,
    "no": null,
    "yes_dollars": null,
    "no_dollars": null
  }
}
```

**Impact:**
- SpreadAnalyzer: ❌ Needs orderbook depth → Finds ZERO opportunities
- ArbitrageAnalyzer: ❌ Needs YES/NO bids → Finds ZERO opportunities
- ImbalanceAnalyzer: ❌ Needs orderbook depth → Finds ZERO opportunities
- All orderbook-dependent analyzers fail

### Issue #2: Markets Have Zero Bids

**What we discovered:**
Even though multivariate markets have top-level bid/ask data in the market object:
```json
{
  "yes_bid": 0,
  "yes_ask": 100,
  "no_bid": 0,
  "no_ask": 100,
  "last_price": 12
}
```

**The problem:** Both `yes_bid` and `no_bid` are **0¢**. This means:
- No one is actively bidding on these markets
- The "spread" is 0 to 100¢ (100% spread!)
- There's no liquidity to trade against

**Impact:**
Even if analyzers used market-level bid/ask data instead of orderbook depth:
- ArbitrageAnalyzer: Would see `yes_bid + no_bid = 0 + 0 = 0` (no arbitrage)
- SpreadAnalyzer: Would see 100¢ spread (but no actual liquidity)
- MispricingAnalyzer: Might trigger on extreme prices, but couldn't execute

### Issue #3: No Regular Markets Available

**What we discovered:**
- Fetched 500 open markets
- **ALL 500 are multivariate (KXMV)**
- ZERO regular single-event markets found

**Possible reasons:**
1. The trading session might be focused on NFL parlays
2. Regular markets might be closed/settled
3. API query might need different parameters (series filters, event types)
4. This might be a seasonal/timing issue (NFL gameday)

## Why "1-Cent Trades" Appeared Before

**Hypothesis:** If the analyzers DID find 1-cent opportunities in the past, it means:

1. **Regular markets existed** with actual orderbook data
2. **ArbitrageAnalyzer was too aggressive** with its thresholds:
   - `soft_min_arb_cents: 1` (accepts 1¢ profit opportunities)
   - Transaction costs are 1¢ per side = 2¢ total
   - Net profit on 1¢ arb: **1¢ - 2¢ = -1¢ LOSS!**

3. **TradeManager was configured incorrectly**:
   - Default `min_edge_cents: 5.0¢` would block 1¢ trades
   - If someone lowered it to `1¢`, these would execute
   - Result: **Guaranteed money loss**

## Current Analyzer Configurations

### Arbitrage Analyzer (analyzers/arbitrage_analyzer.py:40-47)

```python
{
    "hard_min_arb_cents": 2,      # Minimum 2¢ for HARD
    "soft_min_arb_cents": 1,      # Minimum 1¢ for SOFT ⚠️
    "transaction_cost_cents": 1   # 1¢ per side
}
```

**Problem:** `soft_min_arb_cents: 1` creates unprofitable trades!
- Gross profit: 1¢
- Transaction costs: 1¢ (buy YES) + 1¢ (buy NO) = 2¢
- **Net result: -1¢ loss**

### Trade Manager Filters (trade_manager.py:131-132)

```python
{
    "min_edge_cents": 5.0,        # Minimum 5¢ edge required
    "min_edge_percent": 2.0       # Minimum 2% ROI required
}
```

**Current state:** These defaults WOULD block 1¢ trades, which is good.
**Risk:** If someone lowered `min_edge_cents` to 1¢, unprofitable trades would execute.

## Recommendations

### Immediate Actions

#### 1. Fix Arbitrage Analyzer Thresholds

**File**: `analyzers/arbitrage_analyzer.py`

```python
# BEFORE (WRONG):
{
    "soft_min_arb_cents": 1,      # Net loss after fees!
    "transaction_cost_cents": 1
}

# AFTER (CORRECT):
{
    "soft_min_arb_cents": 3,      # 3¢ gross = 1¢ net after 2¢ fees
    "hard_min_arb_cents": 5,      # 5¢ gross = 3¢ net
    "transaction_cost_cents": 1
}
```

**Calculation:**
- Soft: 3¢ gross - 2¢ fees = **1¢ net profit** ✓
- Hard: 5¢ gross - 2¢ fees = **3¢ net profit** ✓

#### 2. Add Minimum Net Profit Check

Add validation that `min_arb_cents` must exceed `transaction_cost_cents * 2`:

```python
def validate_config(self):
    gross_threshold = self.config["soft_min_arb_cents"]
    total_costs = self.config["transaction_cost_cents"] * 2

    if gross_threshold <= total_costs:
        raise ValueError(
            f"soft_min_arb_cents ({gross_threshold}) must be > "
            f"total transaction costs ({total_costs})"
        )
```

#### 3. Handle Multivariate Markets Properly

**Option A:** Filter them out (recommended for now)

```python
def fetch_market_data(self):
    markets = self.client.get_all_open_markets(...)

    # Filter out multivariate markets (no orderbook support)
    regular_markets = [
        m for m in markets
        if not m.get("ticker", "").startswith("KXMV")
    ]

    return regular_markets
```

**Option B:** Adapt analyzers to use market-level bid/ask

For analyzers like Arbitrage that only need best bid/ask:

```python
def analyze(self, markets):
    for market in markets:
        # Try orderbook first
        orderbook = market.get("orderbook", {})
        yes_orders = orderbook.get("yes")

        if yes_orders and len(yes_orders) > 0:
            yes_bid = yes_orders[0][0]  # From orderbook
        else:
            # Fallback to market-level data
            yes_bid = market.get("yes_bid", 0)
```

**Option C:** Query for specific series/events

```python
# Target specific event types that have better liquidity
client.get_markets(
    series_ticker="INXD",     # S&P 500 daily markets
    status="open",
    min_volume=10000          # Higher volume threshold
)
```

#### 4. Add Data Quality Checks

```python
def should_analyze_market(market: Dict) -> Tuple[bool, str]:
    """Pre-filter markets before analysis."""

    # Check if multivariate
    if market.get("ticker", "").startswith("KXMV"):
        return False, "Multivariate market (no orderbook)"

    # Check for bid liquidity
    orderbook = market.get("orderbook", {})
    yes_orders = orderbook.get("yes", [])
    no_orders = orderbook.get("no", [])

    if not yes_orders and not no_orders:
        return False, "Empty orderbook"

    # Check for reasonable bids (not 0¢)
    if yes_orders and yes_orders[0][0] == 0:
        return False, "Zero bids"

    return True, "OK"
```

### Medium-Term Actions

1. **Add monitoring/alerting** for:
   - % of markets with empty orderbooks
   - % of opportunities below min profitable threshold
   - Actual vs expected fill rates

2. **Create analyzer test suite** with:
   - Synthetic market data
   - Known-good opportunities
   - Edge case scenarios

3. **Add simulation mode**:
   - Paper trade all opportunities
   - Track P&L without risk
   - Tune thresholds based on results

4. **Implement market quality scoring**:
   - Prioritize markets with deep orderbooks
   - Weight by volume, spread, liquidity
   - Skip markets below quality threshold

### Long-Term Actions

1. **Build market data pipeline**:
   - Cache orderbook snapshots
   - Historical price/volume data
   - Compute realized vs theoretical edge

2. **Machine learning for threshold optimization**:
   - Learn optimal min_edge per market type
   - Adaptive confidence scoring
   - Execution probability modeling

3. **Alternative data sources**:
   - If Kalshi offers websocket streams, use for real-time data
   - Consider multiple prediction market platforms
   - Cross-market arbitrage opportunities

## Testing the Analyzers

### Run Debug Script

```bash
# Test all analyzers (will show multivariate issue)
python debug_analyzers.py all 20

# Test specific analyzer
python debug_analyzers.py arbitrage 20
python debug_analyzers.py spread 20
python debug_analyzers.py mispricing 20
```

### What to Look For

**Good signs:**
- ✓ Markets with non-null orderbooks
- ✓ Opportunities with >5¢ edge
- ✓ "Would execute" on opportunities

**Bad signs:**
- ✗ All markets are KXMV (multivariate)
- ✗ Empty/null orderbooks
- ✗ Opportunities with 1-2¢ edge
- ✗ "Would not execute - Edge too small"

## Summary

| Issue | Severity | Impact | Fix Difficulty |
|-------|----------|--------|---------------|
| All markets are multivariate | 🔴 CRITICAL | No data for analyzers | Medium (need regular markets) |
| Empty orderbooks | 🔴 CRITICAL | Analyzers find nothing | Medium (market availability) |
| 1¢ arbitrage threshold too low | 🟠 HIGH | Unprofitable trades | Easy (config change) |
| No data validation | 🟡 MEDIUM | Silent failures | Easy (add checks) |
| No fallback to market-level bids | 🟡 MEDIUM | Miss some opportunities | Medium (code changes) |

## Next Steps

1. ✅ Run debug_analyzers.py to confirm findings
2. ⬜ Fix ArbitrageAnalyzer thresholds (3¢ minimum)
3. ⬜ Add data quality validation
4. ⬜ Filter out or handle multivariate markets
5. ⬜ Find and target regular markets with liquidity
6. ⬜ Add monitoring and alerting
7. ⬜ Test with live markets once fixed

---

**Questions to investigate:**
1. When do regular (non-KXMV) markets exist?
2. What series/events have the best liquidity?
3. What's the actual transaction cost structure?
4. Historical fill rates and slippage data?
