# Kalshi API Guide

Complete guide to working with the Kalshi API, including orderbook setup, authentication, and endpoint reference.

## Table of Contents
- [Authentication](#authentication)
- [Orderbook Setup](#orderbook-setup)
- [Available Endpoints](#available-endpoints)
- [Finding Long-Lived Markets](#finding-long-lived-markets)
- [Historical Data](#historical-data)
- [Missing/Future Endpoints](#missingfuture-endpoints)

---

## Authentication

### Setup
The Kalshi API uses **RSA-PSS with SHA256** signing for authenticated requests.

**Required Headers:**
- `KALSHI-ACCESS-KEY`: Your API key ID
- `KALSHI-ACCESS-SIGNATURE`: RSA-PSS signature
- `KALSHI-ACCESS-TIMESTAMP`: Timestamp in milliseconds

**Environment Variables:**
```bash
export KALSHI_API_KEY_ID="your-key-id"
export KALSHI_PRIV_KEY="base64-encoded-private-key"
```

**Usage:**
```python
from kalshi_client import KalshiDataClient

# With authentication (for private endpoints)
client = KalshiDataClient.from_env()

# Without authentication (for public endpoints)
client = KalshiDataClient()
```

**Important Notes:**
- Public endpoints (markets, orderbook, events) work without authentication
- Private endpoints (balance, orders, fills) require authentication
- Private keys cannot be recovered after initial download from Kalshi
- Store your private key securely

---

## Orderbook Setup

### How Kalshi Orderbooks Work

**Endpoint:** `GET /trade-api/v2/markets/{ticker}/orderbook`

**Key Concepts:**
1. **Bids Only:** Returns only bids (not asks), because in binary markets:
   - A YES bid at 7¢ = NO ask at 93¢
   - A NO bid at 30¢ = YES ask at 70¢

2. **Null Values:** API returns `null` when no orders exist:
   ```json
   {
     "orderbook": {
       "yes": null,
       "no": null,
       "yes_dollars": null,
       "no_dollars": null
     }
   }
   ```

3. **Response Structure:**
   ```python
   {
     "orderbook": {
       "yes": [[price_cents, quantity], ...],
       "no": [[price_cents, quantity], ...],
       "yes_dollars": [[price_dollars, quantity], ...],
       "no_dollars": [[price_dollars, quantity], ...]
     }
   }
   ```

### Usage Examples

**Basic Orderbook Fetching:**
```python
from kalshi_client import KalshiDataClient

client = KalshiDataClient()
response = client.get_orderbook("MARKET-TICKER")

orderbook = response.get("orderbook", {})
yes_orders = orderbook.get("yes", [])  # Returns empty list if null
no_orders = orderbook.get("no", [])

if yes_orders:
    price, quantity = yes_orders[0]
    print(f"Best YES bid: {price}¢ x {quantity} contracts")
```

**Limiting Orderbook Depth:**
```python
# Get full orderbook
full_ob = client.get_orderbook("MARKET-TICKER", depth=0)

# Get only top 5 levels
top_5 = client.get_orderbook("MARKET-TICKER", depth=5)
```

**Calculate Spread:**
```python
response = client.get_orderbook("MARKET-TICKER")
orderbook = response.get("orderbook", {})
yes_orders = orderbook.get("yes", [])
no_orders = orderbook.get("no", [])

if yes_orders and no_orders:
    best_yes_bid = yes_orders[0][0]
    best_no_bid = no_orders[0][0]

    # In an efficient market, YES bid + NO bid = 100¢
    spread = 100 - (best_yes_bid + best_no_bid)

    print(f"Spread: {spread}¢")
    print(f"Implied YES ask: {100 - best_no_bid}¢")
    print(f"Implied NO ask: {100 - best_yes_bid}¢")
```

### Empty Orderbooks
Many markets have empty orderbooks (all null values) because:
- No active orders are currently placed
- All previous orders have been filled
- The market has low liquidity
- The market is close to expiration

This is **normal behavior**. Our client handles this gracefully by returning empty lists.

**Test Results:** 92% of active markets have real orderbook data.

---

## Available Endpoints

Our `kalshi_client.py` currently implements:

### Market Data (Public)
- ✅ `get_market(ticker)` - Get single market details
- ✅ `get_markets(**filters)` - Get multiple markets with filters
- ✅ `get_orderbook(ticker, use_auth, depth)` - Get orderbook depth
- ✅ `get_trades(ticker, **filters)` - Get trade history
- ✅ `get_events(status, with_nested_markets, limit)` - Get events with markets

### Historical Data (Public)
- ✅ `get_market_candlesticks(ticker, **params)` - Get OHLCV candlestick data
  - Fixed: Prices are at `candlestick['yes_ask']['close']` (nested structure)
  - Supports multiple intervals: 1m, 5m, 15m, 1h, 1d

### Portfolio (Private - Requires Auth)
- ✅ `get_balance()` - Get account balance
- ✅ `get_orders(**filters)` - Get order history
- ✅ `get_fills(**filters)` - Get fill history

### Exchange Info (Public)
- ✅ `get_exchange_status()` - Get exchange status
- ✅ `get_exchange_schedule()` - Get trading schedule

### Rate Limiting
- Token bucket implementation
- Default: 20 requests per second
- Configurable via `rate_limit` and `rate_limit_burst` parameters

---

## Finding Long-Lived Markets

### The Problem
Most markets on Kalshi are short-lived (sports, news events):
- Using `get_markets()` typically finds markets <24 hours old
- Technical indicators (RSI, MACD, Bollinger Bands) need 14+ data points
- Need markets that are weeks or months old

### The Solution: GetEvents with Nested Markets

**Endpoint:** `GET /events`

**Key Parameters:**
- `with_nested_markets=true` - Returns markets nested in events
- `status=open` - Filter by status
- `limit=200` - Up to 200 events per page

**Why This Works:**
- Events represent long-term prediction categories
- Each event contains multiple related markets
- Found markets up to **159 days old**!

**Example Markets Found:**
- `KXWARMING-50`: 159 days old, 3.5K volume (global warming prediction)
- `KXNEWPOPE-70`: 116 days old (next Pope prediction)
- `KXELONMARS-99`: 75 days old, 17K volume (Elon Mars prediction)

**Usage:**
```python
client = KalshiDataClient()

# Get open events with nested markets
response = client.get_events(
    status="open",
    with_nested_markets=True,
    limit=200
)

events = response.get("events", [])
for event in events:
    markets = event.get("markets", [])
    for market in markets:
        ticker = market.get("ticker")
        # Process long-lived market...
```

---

## Historical Data

### Candlestick Data Structure

**Important:** Candlestick prices are in a nested structure:

```python
candlestick = {
    "yes_ask": {
        "open": 45,
        "high": 48,
        "low": 43,
        "close": 47
    },
    "yes_bid": {...},
    "no_ask": {...},
    "no_bid": {...},
    "price": {...},
    "start_period": 1234567890,
    "end_period": 1234571490
}
```

**Extracting Prices:**
```python
# WRONG - this doesn't exist
price = candlestick['yes_ask_close']

# CORRECT - nested structure
price = candlestick['yes_ask']['close']
```

**Available Fields:**
- `yes_ask` - YES ask side (buyers of YES)
- `yes_bid` - YES bid side (sellers of YES)
- `no_ask` - NO ask side (buyers of NO)
- `no_bid` - NO bid side (sellers of NO)
- `price` - Last trade price

**Example: Getting Historical Prices**
```python
client = KalshiDataClient()

# Get hourly candlesticks for last 100 hours
candlesticks = client.get_market_candlesticks(
    ticker="MARKET-TICKER",
    period_interval=60,  # 60 minutes
    limit=100
)

# Extract closing prices
prices = []
for candle in candlesticks:
    yes_ask = candle.get("yes_ask")
    if yes_ask and isinstance(yes_ask, dict):
        price = yes_ask.get("close")
        if price:
            prices.append(price)

# Now use for technical indicators (RSI, MACD, etc.)
```

---

## Missing/Future Endpoints

These endpoints exist in the Kalshi API but are not yet implemented in our client:

### 1. GetOrderQueuePositions ⭐ (High Priority)
- **Endpoint:** `/portfolio/orders/queue_positions`
- **What it does:** Shows how many contracts are ahead of your order in the queue
- **Why useful:** Critical for market making strategies
  - Know if your limit order will likely fill
  - Adjust pricing if stuck deep in queue
  - Cancel/resubmit strategically
- **Requires:** Authentication
- **Use case:** Any limit order strategy

### 2. GetIncentivePrograms
- **Endpoint:** `/incentive_programs`
- **What it does:** Volume-based fee rebates/discounts
- **Why useful:** Changes profitability calculations
  - Maker rebates can make strategies profitable
  - Know true transaction costs
- **Use case:** High-frequency / market making

### 3. GetLiveData (Sports/Events)
- **Endpoint:** `/live_data/{type}/milestone/{milestone_id}`
- **What it does:** Real-time sports scores and event data
- **Why useful:** In-play trading opportunities
- **Use case:** Event-driven strategies (react to goals, scores, etc.)

### 4. GetMultivariateEvents
- **Endpoint:** `/events/multivariate`
- **What it does:** Combo/parlay markets
- **Why useful:** Arbitrage between combos and singles
- **Use case:** Statistical arbitrage

### 5. GetEventForecastPercentilesHistory (Not Working)
- **Endpoint:** `/series/{series_ticker}/events/{ticker}/forecast_percentile_history`
- **Status:** Returns 400 errors - might be restricted or documentation outdated
- **Note:** Price history via candlesticks is sufficient for most use cases

---

## Implementation Recommendations

### For Technical Analysis Strategies
1. Use `get_events()` with `with_nested_markets=True` to find long-lived markets
2. Filter for markets >14 days old (enough history for RSI, MACD, Bollinger)
3. Use `get_market_candlesticks()` with 1-hour or 1-day intervals
4. Extract prices from nested `yes_ask.close` field
5. Apply technical indicators to historical price series

### For Market Making Strategies
1. Monitor orderbook depth with `get_orderbook(depth=5)`
2. Calculate spreads to find profitable quotes
3. Consider implementing `GetOrderQueuePositions` for fill probability
4. Consider implementing `GetIncentivePrograms` for accurate cost calculations

### For Event-Driven Strategies
1. Use `get_markets()` for recent sports/news events
2. Consider implementing `GetLiveData` for real-time event updates
3. React quickly to market-moving information

---

## Troubleshooting

### Issue: Cryptography Import Error
**Problem:** `ImportError: cannot import name 'hashes' from 'cryptography.hazmat.primitives'`

**Solution:** Add cryptography to dependencies:
```bash
# Add to pyproject.toml dependencies
cryptography>=41.0.0

# Install
uv sync
```

### Issue: Orderbook Returns Null
**Problem:** `TypeError: 'NoneType' object is not iterable`

**Solution:** Our client now handles null values automatically by converting to empty lists. Update to latest version of `kalshi_client.py`.

### Issue: Can't Find Old Markets
**Problem:** All markets appear to be <24 hours old

**Solution:** Use `get_events()` instead of `get_markets()`:
```python
# WRONG - finds mostly recent markets
markets = client.get_markets(status="open")

# CORRECT - finds long-lived markets
events = client.get_events(
    status="open",
    with_nested_markets=True
)
```

### Issue: Candlestick Prices Return None
**Problem:** Can't extract prices from candlestick data

**Solution:** Use nested structure:
```python
# Access nested fields
price = candlestick['yes_ask']['close']  # Not candlestick['yes_ask_close']
```

---

## References

- [Kalshi API Documentation](https://docs.kalshi.com)
- [Kalshi OpenAPI Spec](https://docs.kalshi.com/openapi.yaml) (5,735 lines)
- [Get Market Orderbook](https://docs.kalshi.com/api-reference/market/get-market-orderbook)
- [Authentication Guide](https://docs.kalshi.com/getting_started/quick_start_authenticated_requests)
