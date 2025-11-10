# Kalshi Order Book and Client Setup

## Summary

This document describes the setup and fixes applied to the Kalshi order book and client functionality.

## Issues Fixed

### 1. Missing Cryptography Dependency
**Problem:** The `kalshi_client.py` uses the `cryptography` library for RSA-PSS authentication, but it was not listed in the project dependencies.

**Solution:** Added `cryptography>=41.0.0` to `pyproject.toml`

```bash
uv sync  # Install the updated dependencies
```

### 2. Orderbook Null Value Handling
**Problem:** The Kalshi API returns `null` values for `yes` and `no` fields in the orderbook when there are no active orders. The code was not handling these null values, causing crashes.

**API Response Example:**
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

**Solution:** Updated `get_orderbook()` method in `kalshi_client.py` to:
- Accept a `depth` parameter for controlling orderbook depth
- Convert `null` values to empty lists `[]` for easier handling
- Updated documentation to clarify the behavior

## How the Kalshi Orderbook Works

According to the Kalshi API documentation:

1. **Endpoint:** `GET /trade-api/v2/markets/{ticker}/orderbook`

2. **Authentication:** Requires three headers:
   - `KALSHI-ACCESS-KEY`: Your API key ID
   - `KALSHI-ACCESS-SIGNATURE`: RSA-PSS signature
   - `KALSHI-ACCESS-TIMESTAMP`: Timestamp in milliseconds

3. **Bids Only:** The orderbook returns only bids (not asks), because in binary markets:
   - A YES bid at 7¢ is equivalent to a NO ask at 93¢
   - A NO bid at 30¢ is equivalent to a YES ask at 70¢

4. **Response Structure:**
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

5. **Depth Parameter:** Use `depth=N` to limit orderbook levels (0 for all, 1-100 for specific depth)

## Usage Examples

### Basic Orderbook Fetching
```python
from kalshi_client import KalshiDataClient

client = KalshiDataClient()
response = client.get_orderbook("MARKET-TICKER-HERE")

orderbook = response.get("orderbook", {})
yes_orders = orderbook.get("yes", [])  # Returns empty list if null
no_orders = orderbook.get("no", [])

if yes_orders:
    price, quantity = yes_orders[0]
    print(f"Best YES bid: {price}¢ x {quantity} contracts")
```

### Authenticated Orderbook Fetching
```python
# Set environment variables first:
# export KALSHI_API_KEY_ID="your-key-id"
# export KALSHI_PRIV_KEY="base64-encoded-private-key"

client = KalshiDataClient.from_env()
response = client.get_orderbook("MARKET-TICKER-HERE", use_auth=True)
```

### Limiting Orderbook Depth
```python
client = KalshiDataClient()

# Get full orderbook
full_ob = client.get_orderbook("MARKET-TICKER", depth=0)

# Get only top 5 levels
top_5 = client.get_orderbook("MARKET-TICKER", depth=5)
```

### Calculate Spread
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

## Important Notes

### Empty Orderbooks
Many markets may have empty orderbooks (all null values) because:
- No active orders are currently placed
- All previous orders have been filled
- The market has low liquidity
- The market is close to expiration

This is **normal behavior** and not an error. The client now handles this gracefully by returning empty lists.

### Authentication
- **Public endpoints** (markets, orderbook, etc.) work without authentication
- **Private endpoints** (balance, orders, fills, etc.) require authentication
- Authentication uses **RSA-PSS with SHA256** signing
- Private keys cannot be recovered after initial download from Kalshi

### Rate Limits
The client includes a token bucket rate limiter:
- Default: 20 requests per second
- Configurable via `rate_limit` parameter
- Burst capacity via `rate_limit_burst` parameter

## Testing

Run the comprehensive test suite:
```bash
# Without authentication
uv run python test_orderbook_comprehensive.py

# With authentication (set env vars first)
export KALSHI_API_KEY_ID="your-key-id"
export KALSHI_PRIV_KEY="base64-encoded-private-key"
uv run python test_orderbook_comprehensive.py
```

Run the usage examples:
```bash
uv run python examples_orderbook_usage.py
```

## Files Modified/Created

1. **Modified:**
   - `pyproject.toml` - Added cryptography dependency
   - `kalshi_client.py` - Fixed orderbook null handling, added depth parameter

2. **Created:**
   - `test_orderbook_comprehensive.py` - Comprehensive test suite
   - `examples_orderbook_usage.py` - Usage examples
   - `ORDERBOOK_SETUP.md` - This documentation

## References

- [Kalshi API - Get Market Orderbook](https://docs.kalshi.com/api-reference/market/get-market-orderbook)
- [Kalshi API - Authentication Guide](https://docs.kalshi.com/getting_started/quick_start_authenticated_requests)
- [Kalshi API Reference](https://docs.kalshi.com/api-reference)
