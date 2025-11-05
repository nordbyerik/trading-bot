"""
Kalshi API Data Client

Handles all interactions with the Kalshi API for fetching market data.
No authentication required for public market data endpoints.
"""

import logging
import time
import threading
from typing import Any, Dict, List, Optional
from functools import lru_cache
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """
    Thread-safe token bucket rate limiter.

    Allows bursts up to the bucket capacity while maintaining average rate over time.
    """

    def __init__(self, rate: float, capacity: float = None):
        """
        Initialize the rate limiter.

        Args:
            rate: Maximum requests per second
            capacity: Maximum burst size (defaults to rate, allowing 1 second of burst)
        """
        self.rate = rate  # tokens per second
        self.capacity = capacity if capacity is not None else rate
        self.tokens = self.capacity
        self.last_update = time.time()
        self.lock = threading.Lock()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_update

        # Add tokens based on elapsed time
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now

    def acquire(self, tokens: int = 1) -> None:
        """
        Acquire tokens, blocking if necessary.

        Args:
            tokens: Number of tokens to acquire (default: 1)
        """
        with self.lock:
            while True:
                self._refill()

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return

                # Calculate sleep time to get enough tokens
                tokens_needed = tokens - self.tokens
                sleep_time = tokens_needed / self.rate

                # Release lock while sleeping
                self.lock.release()
                time.sleep(sleep_time)
                self.lock.acquire()


class KalshiDataClient:
    """Client for fetching market data from Kalshi API."""

    BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

    def __init__(
        self,
        cache_ttl: int = 30,
        rate_limit: float = 20.0,
        rate_limit_burst: float = None,
        max_retries: int = 3
    ):
        """
        Initialize the Kalshi data client.

        Args:
            cache_ttl: Cache time-to-live in seconds
            rate_limit: Maximum requests per second (default: 20.0)
            rate_limit_burst: Maximum burst capacity (default: same as rate_limit)
            max_retries: Maximum number of retry attempts for failed requests
        """
        self.cache_ttl = cache_ttl
        self.rate_limiter = TokenBucketRateLimiter(
            rate=rate_limit,
            capacity=rate_limit_burst
        )

        # Set up session with retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Simple in-memory cache: {url: (data, timestamp)}
        self._cache: Dict[str, tuple[Any, float]] = {}

        logger.info("KalshiDataClient initialized")

    def _rate_limit(self) -> None:
        """Enforce rate limiting using token bucket algorithm."""
        self.rate_limiter.acquire()

    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get data from cache if not expired."""
        if key in self._cache:
            data, timestamp = self._cache[key]
            if time.time() - timestamp < self.cache_ttl:
                logger.debug(f"Cache hit for {key}")
                return data
            else:
                # Cache expired, remove it
                del self._cache[key]
        return None

    def _put_in_cache(self, key: str, data: Any) -> None:
        """Store data in cache with current timestamp."""
        self._cache[key] = (data, time.time())

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """
        Make an HTTP GET request to the Kalshi API.

        Args:
            endpoint: API endpoint path (e.g., '/markets')
            params: Query parameters

        Returns:
            JSON response as dictionary

        Raises:
            requests.RequestException: If the request fails
        """
        url = f"{self.BASE_URL}{endpoint}"
        cache_key = f"{url}?{params}" if params else url

        # Check cache first
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        # Rate limit
        self._rate_limit()

        try:
            logger.debug(f"Making request to {endpoint} with params {params}")
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Cache the response
            self._put_in_cache(cache_key, data)

            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {endpoint}: {e}")
            raise

    def get_series(self, series_ticker: str) -> Dict:
        """
        Get series information.

        Args:
            series_ticker: Series ticker symbol

        Returns:
            Series data dictionary
        """
        endpoint = f"/series/{series_ticker}"
        return self._make_request(endpoint)

    def get_markets(
        self,
        series_ticker: Optional[str] = None,
        status: Optional[str] = "open",
        limit: int = 200,
        cursor: Optional[str] = None,
        min_close_ts: Optional[int] = None,
        max_close_ts: Optional[int] = None
    ) -> Dict:
        """
        Get markets with optional filters.

        Args:
            series_ticker: Filter by series ticker
            status: Filter by status (open, closed, etc.)
            limit: Maximum number of results per page
            cursor: Pagination cursor
            min_close_ts: Filter items that close after this Unix timestamp
            max_close_ts: Filter items that close before this Unix timestamp

        Returns:
            Dictionary with 'markets' list and 'cursor' for pagination
        """
        params: Dict[str, Any] = {"limit": limit}

        if series_ticker:
            params["series_ticker"] = series_ticker
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor
        if min_close_ts is not None:
            params["min_close_ts"] = min_close_ts
        if max_close_ts is not None:
            params["max_close_ts"] = max_close_ts

        return self._make_request("/markets", params=params)

    def get_all_open_markets(
        self,
        max_markets: Optional[int] = None,
        status: str = "open",
        min_volume: Optional[int] = None
    ) -> List[Dict]:
        """
        Fetch all markets with specified status, handling pagination automatically.

        Args:
            max_markets: Maximum number of markets to fetch (None for all markets)
            status: Market status filter ('open', 'closed', 'settled', or comma-separated list)
            min_volume: Minimum volume threshold - only keep markets with volume >= this value

        Returns:
            List of market dictionaries (filtered by volume if min_volume is specified)
        """
        all_markets = []
        cursor = None
        total_fetched = 0
        total_filtered_out = 0

        logger.info(
            f"Fetching {status} markets"
            f"{f' (max: {max_markets})' if max_markets else ''}"
            f"{f' (min_volume: {min_volume:,})' if min_volume else ''}..."
        )

        while True:
            # Always request full pages to maximize efficiency
            # We'll filter after fetching
            limit = 200

            response = self.get_markets(status=status, cursor=cursor, limit=limit)
            markets = response.get("markets", [])
            total_fetched += len(markets)

            # Filter by volume if specified
            if min_volume is not None:
                filtered_markets = [m for m in markets if m.get("volume", 0) >= min_volume]
                filtered_out = len(markets) - len(filtered_markets)
                total_filtered_out += filtered_out
                markets = filtered_markets
                if filtered_out > 0:
                    logger.debug(
                        f"Filtered out {filtered_out} markets with volume < {min_volume:,}"
                    )

            all_markets.extend(markets)

            cursor = response.get("cursor")
            logger.debug(
                f"Fetched {len(markets)} markets (after filtering), "
                f"total so far: {len(all_markets)}"
            )

            # Stop if we've hit our limit or there's no more data
            if max_markets and len(all_markets) >= max_markets:
                # Trim to exact limit
                all_markets = all_markets[:max_markets]
                logger.info(f"Reached max_markets limit of {max_markets}")
                break

            if not cursor:
                break

        if min_volume is not None:
            logger.info(
                f"Fetched {total_fetched} total markets, "
                f"filtered to {len(all_markets)} with volume >= {min_volume:,} "
                f"({total_filtered_out} filtered out)"
            )
        else:
            logger.info(f"Fetched total of {len(all_markets)} markets")

        return all_markets

    def get_event(self, event_ticker: str) -> Dict:
        """
        Get event details.

        Args:
            event_ticker: Event ticker symbol

        Returns:
            Event data dictionary
        """
        endpoint = f"/events/{event_ticker}"
        return self._make_request(endpoint)

    def get_orderbook(self, market_ticker: str) -> Dict:
        """
        Get orderbook for a specific market.

        Args:
            market_ticker: Market ticker symbol

        Returns:
            Orderbook data with 'yes' and 'no' bid arrays
            Each bid is [price_in_cents, quantity]
        """
        endpoint = f"/markets/{market_ticker}/orderbook"
        return self._make_request(endpoint)

    def get_market(self, market_ticker: str) -> Dict:
        """
        Get detailed information for a specific market.

        Args:
            market_ticker: Market ticker symbol

        Returns:
            Market data dictionary
        """
        endpoint = f"/markets/{market_ticker}"
        result = self._make_request(endpoint)
        # API returns {"market": {...}}, extract the market object
        return result.get("market", result)

    def get_market_candlesticks(
        self,
        series_ticker: str,
        market_ticker: str,
        start_ts: int,
        end_ts: int,
        period_interval: int = 60
    ) -> Dict:
        """
        Get historical candlestick data for a specific market.

        Args:
            series_ticker: Series ticker symbol
            market_ticker: Market ticker symbol
            start_ts: Start timestamp (Unix timestamp in seconds)
            end_ts: End timestamp (Unix timestamp in seconds)
            period_interval: Candlestick period in minutes (1, 60, or 1440)

        Returns:
            Dictionary containing candlestick data with OHLC prices, volume, and open interest
        """
        if period_interval not in [1, 60, 1440]:
            raise ValueError("period_interval must be 1 (1min), 60 (1hr), or 1440 (1day)")

        endpoint = f"/series/{series_ticker}/markets/{market_ticker}/candlesticks"
        params = {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "period_interval": period_interval
        }
        return self._make_request(endpoint, params=params)

    def get_event_candlesticks(
        self,
        series_ticker: str,
        event_ticker: str,
        start_ts: int,
        end_ts: int,
        period_interval: int = 60
    ) -> Dict:
        """
        Get aggregated historical candlestick data for all markets in an event.

        Args:
            series_ticker: Series ticker symbol
            event_ticker: Event ticker symbol
            start_ts: Start timestamp (Unix timestamp in seconds)
            end_ts: End timestamp (Unix timestamp in seconds)
            period_interval: Candlestick period in minutes (1, 60, or 1440)

        Returns:
            Dictionary containing:
            - market_tickers: List of market tickers in the event
            - market_candlesticks: Array of candlestick data for each market
            - adjusted_end_ts: Potentially adjusted end timestamp
        """
        if period_interval not in [1, 60, 1440]:
            raise ValueError("period_interval must be 1 (1min), 60 (1hr), or 1440 (1day)")

        endpoint = f"/series/{series_ticker}/events/{event_ticker}/candlesticks"
        params = {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "period_interval": period_interval
        }
        return self._make_request(endpoint, params=params)

    def get_trades(
        self,
        market_ticker: Optional[str] = None,
        min_ts: Optional[int] = None,
        max_ts: Optional[int] = None,
        limit: int = 100,
        cursor: Optional[str] = None
    ) -> Dict:
        """
        Get historical trade data.

        Args:
            market_ticker: Filter by specific market ticker (optional)
            min_ts: Minimum timestamp for trades (Unix timestamp in seconds)
            max_ts: Maximum timestamp for trades (Unix timestamp in seconds)
            limit: Maximum number of results per page (default: 100)
            cursor: Pagination cursor

        Returns:
            Dictionary with 'trades' list and 'cursor' for pagination
        """
        params: Dict[str, Any] = {"limit": limit}

        if market_ticker:
            params["ticker"] = market_ticker
        if min_ts is not None:
            params["min_ts"] = min_ts
        if max_ts is not None:
            params["max_ts"] = max_ts
        if cursor:
            params["cursor"] = cursor

        return self._make_request("/markets/trades", params=params)

    def get_exchange_status(self) -> Dict:
        """
        Get the current exchange status.

        Returns:
            Dictionary containing exchange operational status and trading state
        """
        return self._make_request("/exchange/status")

    def get_exchange_schedule(self) -> Dict:
        """
        Get the exchange trading schedule.

        Returns:
            Dictionary containing exchange schedule information
        """
        return self._make_request("/exchange/schedule")

    def get_exchange_announcements(self) -> Dict:
        """
        Get exchange-wide announcements.

        Returns:
            Dictionary containing list of announcements
        """
        return self._make_request("/exchange/announcements")

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        logger.info("Cache cleared")

    def get_cache_stats(self) -> Dict[str, int]:
        """Get statistics about the cache."""
        return {
            "cached_items": len(self._cache),
            "cache_ttl": self.cache_ttl
        }


if __name__ == "__main__":
    # Simple test/demo
    logging.basicConfig(level=logging.INFO)

    client = KalshiDataClient()

    # Test fetching a few markets
    print("\n=== Testing get_markets ===")
    result = client.get_markets(limit=5)
    print(f"Found {len(result.get('markets', []))} markets")

    if result.get('markets'):
        first_market = result['markets'][0]
        print(f"\nFirst market: {first_market.get('ticker')}")
        print(f"Title: {first_market.get('title')}")

        # Test getting orderbook
        print(f"\n=== Testing get_orderbook for {first_market.get('ticker')} ===")
        try:
            orderbook = client.get_orderbook(first_market['ticker'])
            yes_bids = orderbook.get('yes', [])
            no_bids = orderbook.get('no', [])
            print(f"Yes bids: {len(yes_bids)} orders")
            print(f"No bids: {len(no_bids)} orders")
            if yes_bids:
                print(f"Best yes bid: {yes_bids[0][0]}¢ for {yes_bids[0][1]} contracts")
            if no_bids:
                print(f"Best no bid: {no_bids[0][0]}¢ for {no_bids[0][1]} contracts")
        except Exception as e:
            print(f"Error fetching orderbook: {e}")

        # Test new endpoints: exchange status
        print("\n=== Testing get_exchange_status ===")
        try:
            status = client.get_exchange_status()
            print(f"Exchange status: {status.get('exchange_active', 'N/A')}")
            print(f"Trading active: {status.get('trading_active', 'N/A')}")
        except Exception as e:
            print(f"Error fetching exchange status: {e}")

        # Test market candlesticks if we have a market with series info
        market = first_market
        series_ticker = market.get('series_ticker')
        market_ticker = market.get('ticker')

        if series_ticker and market_ticker:
            print(f"\n=== Testing get_market_candlesticks for {market_ticker} ===")
            try:
                # Get candlesticks for the last 24 hours
                import time
                end_ts = int(time.time())
                start_ts = end_ts - (24 * 60 * 60)  # 24 hours ago

                candlesticks = client.get_market_candlesticks(
                    series_ticker=series_ticker,
                    market_ticker=market_ticker,
                    start_ts=start_ts,
                    end_ts=end_ts,
                    period_interval=60  # 1-hour intervals
                )

                candles = candlesticks.get('candlesticks', [])
                print(f"Retrieved {len(candles)} candlesticks")
                if candles:
                    first_candle = candles[0]
                    print(f"First candle: timestamp={first_candle.get('ts')}, "
                          f"open={first_candle.get('yes_ask_open')}, "
                          f"close={first_candle.get('yes_ask_close')}, "
                          f"volume={first_candle.get('volume')}")
            except Exception as e:
                print(f"Error fetching candlesticks: {e}")

        # Test trades history
        print(f"\n=== Testing get_trades (last 10 trades) ===")
        try:
            trades = client.get_trades(limit=10)
            trade_list = trades.get('trades', [])
            print(f"Retrieved {len(trade_list)} recent trades")
            if trade_list:
                first_trade = trade_list[0]
                print(f"Most recent trade: market={first_trade.get('ticker')}, "
                      f"side={first_trade.get('side')}, "
                      f"price={first_trade.get('yes_price')}¢, "
                      f"count={first_trade.get('count')}")
        except Exception as e:
            print(f"Error fetching trades: {e}")

    print(f"\nCache stats: {client.get_cache_stats()}")
