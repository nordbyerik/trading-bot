# Missing Kalshi API Endpoints Analysis

## Summary

We reviewed the complete Kalshi OpenAPI spec (5735 lines) and identified several useful endpoints that could improve our trading bot. Most importantly, we discovered better ways to find long-lived markets.

## Key Discovery: GetEvents with Nested Markets ✅

**Endpoint:** `GET /events`
**Parameters:**
- `with_nested_markets=true` - Returns markets nested in events
- `status=open` - Filter by status
- `limit=200` - Up to 200 events per page

**Why This Matters:**
- Found markets up to **159 days old**! (vs. finding only <1 day old markets before)
- Examples found:
  - `KXWARMING-50`: 159 days old, 3.5K volume (global warming prediction)
  - `KXNEWPOPE-70`: 116 days old (next Pope prediction)
  - `KXELONMARS-99`: 75 days old, 17K volume (Elon Mars prediction)

**Use Case:** Perfect for technical analysis strategies (RSI, MACD, etc.)

## Missing Endpoints (Priority Order)

### 1. GetEventForecastPercentilesHistory (Attempted - Not Working)
- **Endpoint:** `/series/{series_ticker}/events/{ticker}/forecast_percentile_history`
- **Status:** Returns 400 errors - might be restricted or documentation outdated
- **Potential:** Would show market sentiment evolution over time
- **Skip for now** - price history sufficient

### 2. GetOrderQueuePositions ⭐ (High Priority)
- **Endpoint:** `/portfolio/orders/queue_positions`
- **What it does:** Shows how many contracts are ahead of your order in the queue
- **Why useful:** Critical for market making strategies
  - Know if your limit order will likely fill
  - Adjust pricing if stuck deep in queue
  - Cancel/resubmit strategically
- **Requires:** Authentication
- **Use case:** Any limit order strategy

### 3. GetLiveData (Sports/Events)
- **Endpoint:** `/live_data/{type}/milestone/{milestone_id}`
- **What it does:** Real-time sports scores and event data
- **Why useful:** In-play trading opportunities
- **Use case:** Event-driven strategies (react to goals, scores, etc.)

### 4. GetIncentivePrograms
- **Endpoint:** `/incentive_programs`
- **What it does:** Volume-based fee rebates/discounts
- **Why useful:** Changes profitability calculations
  - Maker rebates can make strategies profitable
  - Know true transaction costs
- **Use case:** High-frequency / market making

### 5. GetMultivariateEvents
- **Endpoint:** `/events/multivariate`
- **What it does:** Combo/parlay markets
- **Why useful:** Arbitrage between combos and singles
- **Use case:** Statistical arbitrage

## What We Already Have ✅

Our `kalshi_client.py` already implements:
- ✅ Market data (GetMarket, GetMarkets)
- ✅ Orderbook (GetMarketOrderbook) - working perfectly (92% real data)
- ✅ Historical candlesticks (GetMarketCandlesticks) - fixed price extraction
- ✅ Trades history (GetTrades)
- ✅ Portfolio (GetBalance, GetOrders, GetFills)
- ✅ Exchange info (GetExchangeStatus, GetExchangeSchedule)
- ✅ Events (GetEvent) - but not GetEvents with filters

## Recommendations

### Immediate Actions:
1. **Add GetEvents endpoint** to kalshi_client.py
   - Enables finding long-lived markets efficiently
   - Required parameters: `with_nested_markets`, `status`, `limit`
   - Already works - just needs wrapper method

2. **Filter simulator for old markets**
   - Use GetEvents to find markets >7 days old
   - Run technical analysis only on these
   - Ignore new sports/news markets

### Future Enhancements:
3. **Add GetOrderQueuePositions** (for market making)
4. **Add GetIncentivePrograms** (for cost calculations)
5. **Add GetLiveData** (for event-driven trading)

## Implementation Priority

**Phase 1 (Now):**
- Add `get_events()` method to KalshiDataClient
- Filter simulator to use events API
- Test RSI/MACD on 100+ day old markets

**Phase 2 (Later):**
- Add queue position tracking for execution quality
- Add incentive program data for profitability analysis
- Add live data integration for event-driven strategies

## Testing Notes

- GetEvents endpoint works without authentication ✅
- Returns clean data structure with nested markets ✅
- Can efficiently find long-lived prediction markets ✅
- Perfect for technical analysis strategies ✅

## Code Changes Needed

```python
# Add to kalshi_client.py
def get_events(
    self,
    status: Optional[str] = None,
    with_nested_markets: bool = False,
    limit: int = 200
) -> Dict:
    """Get events with optional filters."""
    endpoint = "/events"
    params = {
        "limit": limit,
        "with_nested_markets": with_nested_markets
    }
    if status:
        params["status"] = status
    return self._make_request(endpoint, params=params)
```

This simple addition unlocks access to 100+ day old markets for technical analysis!
