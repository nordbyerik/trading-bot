"""
Kalshi API Data Client

Handles all interactions with the Kalshi API for fetching market data.
Supports both public endpoints (no auth) and authenticated endpoints (RSA signatures).
"""

import logging
import time
import threading
import base64
import os
import datetime
from typing import Any, Dict, List, Optional
from functools import lru_cache
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend


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
        max_retries: int = 3,
        api_key_id: Optional[str] = None,
        private_key_b64: Optional[str] = None
    ):
        """
        Initialize the Kalshi data client.

        Args:
            cache_ttl: Cache time-to-live in seconds
            rate_limit: Maximum requests per second (default: 20.0)
            rate_limit_burst: Maximum burst capacity (default: same as rate_limit)
            max_retries: Maximum number of retry attempts for failed requests
            api_key_id: Kalshi API key ID (optional, for authenticated requests)
            private_key_b64: Base64-encoded RSA private key (optional, for authenticated requests)
        """
        self.cache_ttl = cache_ttl
        self.rate_limiter = TokenBucketRateLimiter(
            rate=rate_limit,
            capacity=rate_limit_burst
        )

        # Authentication credentials
        self.api_key_id = api_key_id
        self.private_key = None
        if private_key_b64:
            self.private_key = self._load_private_key(private_key_b64)
            logger.info("RSA authentication enabled")

        # Set up session with retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Simple in-memory cache: {url: (data, timestamp)}
        self._cache: Dict[str, tuple[Any, float]] = {}

        logger.info("KalshiDataClient initialized")

    def _load_private_key(self, private_key_b64: str):
        """
        Load RSA private key from base64-encoded PEM string.

        Args:
            private_key_b64: Base64-encoded private key in PEM format

        Returns:
            Private key object
        """
        try:
            # Decode from base64
            private_key_pem = base64.b64decode(private_key_b64).decode('utf-8')

            # Load as a private key object
            private_key = serialization.load_pem_private_key(
                private_key_pem.encode(),
                password=None,
                backend=default_backend()
            )

            logger.info("Successfully loaded RSA private key")
            return private_key
        except Exception as e:
            logger.error(f"Failed to load private key: {e}")
            raise

    def _create_signature(self, timestamp: str, method: str, path: str) -> str:
        """
        Create RSA-PSS signature for Kalshi API authentication.

        Args:
            timestamp: Current timestamp in milliseconds
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path WITHOUT query parameters

        Returns:
            Base64-encoded signature string
        """
        if not self.private_key:
            raise ValueError("Private key not loaded. Cannot create signature.")

        # CRITICAL: Strip query parameters before signing
        path_without_query = path.split('?')[0]

        # Create message to sign: timestamp + method + path
        message = f"{timestamp}{method}{path_without_query}".encode('utf-8')

        # Sign with RSA-PSS (not PKCS1v15!)
        signature = self.private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH
            ),
            hashes.SHA256()
        )

        # Base64 encode the signature
        return base64.b64encode(signature).decode('utf-8')

    def _get_auth_headers(self, method: str, endpoint: str) -> Dict[str, str]:
        """
        Generate authentication headers for Kalshi API requests.

        Args:
            method: HTTP method
            endpoint: API endpoint path (will be converted to full path for signing)

        Returns:
            Dictionary of authentication headers
        """
        if not self.api_key_id or not self.private_key:
            return {}

        # Generate timestamp in milliseconds (not seconds!)
        timestamp = str(int(datetime.datetime.now().timestamp() * 1000))

        # For signature, we need the full path including /trade-api/v2
        # The endpoint passed here doesn't include the base path
        full_path = f"/trade-api/v2{endpoint}"

        # Create signature using the full path
        signature = self._create_signature(timestamp, method, full_path)

        return {
            'KALSHI-ACCESS-KEY': self.api_key_id,
            'KALSHI-ACCESS-SIGNATURE': signature,
            'KALSHI-ACCESS-TIMESTAMP': timestamp
        }

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

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        method: str = "GET",
        json_data: Optional[Dict] = None,
        use_auth: bool = False
    ) -> Dict:
        """
        Make an HTTP request to the Kalshi API.

        Args:
            endpoint: API endpoint path (e.g., '/markets')
            params: Query parameters
            method: HTTP method (GET, POST, PUT, DELETE)
            json_data: JSON payload for POST/PUT requests
            use_auth: Whether to include authentication headers

        Returns:
            JSON response as dictionary

        Raises:
            requests.RequestException: If the request fails
        """
        url = f"{self.BASE_URL}{endpoint}"
        cache_key = f"{method}:{url}?{params}" if params else f"{method}:{url}"

        # Only cache GET requests
        if method == "GET":
            cached_data = self._get_from_cache(cache_key)
            if cached_data is not None:
                return cached_data

        # Rate limit
        self._rate_limit()

        # Prepare headers
        headers = {}
        if use_auth:
            auth_headers = self._get_auth_headers(method, endpoint)
            headers.update(auth_headers)
            logger.debug(f"Using authentication for {method} {endpoint}")

        try:
            logger.debug(f"Making {method} request to {endpoint} with params {params}")

            # Make the appropriate HTTP request
            if method == "GET":
                response = self.session.get(url, params=params, headers=headers, timeout=10)
            elif method == "POST":
                response = self.session.post(url, json=json_data, params=params, headers=headers, timeout=10)
            elif method == "PUT":
                response = self.session.put(url, json=json_data, params=params, headers=headers, timeout=10)
            elif method == "DELETE":
                response = self.session.delete(url, params=params, headers=headers, timeout=10)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()

            data = response.json()

            # Cache GET responses only
            if method == "GET":
                self._put_in_cache(cache_key, data)

            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"{method} request failed for {endpoint}: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response body: {e.response.text}")
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

    def get_events(
        self,
        status: Optional[str] = None,
        with_nested_markets: bool = False,
        with_milestones: bool = False,
        limit: int = 200,
        cursor: Optional[str] = None
    ) -> Dict:
        """
        Get events with optional filters.

        This is useful for finding long-lived markets (elections, predictions, etc.)
        that have sufficient historical data for technical analysis.

        Args:
            status: Filter by status ('open', 'closed', 'settled'). None = any status
            with_nested_markets: Include full market data nested in each event
            with_milestones: Include milestone data for each event
            limit: Number of results per page (max 200)
            cursor: Pagination cursor from previous response

        Returns:
            Dictionary with 'events' list and optional 'cursor' for pagination

        Example:
            # Find open events with their markets
            response = client.get_events(status='open', with_nested_markets=True)
            for event in response['events']:
                print(f"{event['event_ticker']}: {len(event.get('markets', []))} markets")
        """
        endpoint = "/events"
        params = {"limit": limit}

        if status:
            params["status"] = status
        if with_nested_markets:
            params["with_nested_markets"] = True
        if with_milestones:
            params["with_milestones"] = True
        if cursor:
            params["cursor"] = cursor

        return self._make_request(endpoint, params=params)

    def get_orderbook(self, market_ticker: str, use_auth: bool = False, depth: int = 0) -> Dict:
        """
        Get orderbook for a specific market.

        Args:
            market_ticker: Market ticker symbol
            use_auth: Whether to use authentication (some orderbooks may require it)
            depth: Orderbook depth (0 or negative for all levels, 1-100 for specific depth)

        Returns:
            Orderbook data with 'yes' and 'no' bid arrays
            Each bid is [price_in_cents, quantity]
            Note: Returns empty lists for yes/no when orderbook is null (no active orders)
        """
        endpoint = f"/markets/{market_ticker}/orderbook"
        params = {}
        if depth != 0:
            params["depth"] = depth

        response = self._make_request(endpoint, params=params if params else None, use_auth=use_auth)

        # Handle the nested orderbook structure and null values
        orderbook = response.get("orderbook", {})
        if orderbook:
            # Convert null values to empty lists for easier handling
            if orderbook.get("yes") is None:
                orderbook["yes"] = []
            if orderbook.get("no") is None:
                orderbook["no"] = []

        return response

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

    def get_balance(self) -> Dict:
        """
        Get portfolio balance (requires authentication).

        Returns:
            Dictionary containing balance information
        """
        if not self.api_key_id or not self.private_key:
            raise ValueError("Authentication required. Initialize client with api_key_id and private_key_b64.")

        endpoint = "/portfolio/balance"
        return self._make_request(endpoint, use_auth=True)

    def get_portfolio(self) -> Dict:
        """
        Get full portfolio information (requires authentication).

        Returns:
            Dictionary containing portfolio positions and settlements
        """
        if not self.api_key_id or not self.private_key:
            raise ValueError("Authentication required. Initialize client with api_key_id and private_key_b64.")

        endpoint = "/portfolio"
        return self._make_request(endpoint, use_auth=True)

    def get_fills(self, ticker: Optional[str] = None, limit: int = 100) -> Dict:
        """
        Get fill history (requires authentication).

        Args:
            ticker: Optional market ticker to filter fills
            limit: Maximum number of results

        Returns:
            Dictionary containing fills history
        """
        if not self.api_key_id or not self.private_key:
            raise ValueError("Authentication required. Initialize client with api_key_id and private_key_b64.")

        endpoint = "/portfolio/fills"
        params = {"limit": limit}
        if ticker:
            params["ticker"] = ticker

        return self._make_request(endpoint, params=params, use_auth=True)

    def get_orders(self, ticker: Optional[str] = None, status: Optional[str] = None) -> Dict:
        """
        Get orders (requires authentication).

        Args:
            ticker: Optional market ticker to filter orders
            status: Optional status filter (resting, canceled, executed)

        Returns:
            Dictionary containing orders
        """
        if not self.api_key_id or not self.private_key:
            raise ValueError("Authentication required. Initialize client with api_key_id and private_key_b64.")

        endpoint = "/portfolio/orders"
        params = {}
        if ticker:
            params["ticker"] = ticker
        if status:
            params["status"] = status

        return self._make_request(endpoint, params=params, use_auth=True)

    def create_order(
        self,
        ticker: str,
        action: str,
        side: str,
        count: int,
        type: str = "limit",
        yes_price: Optional[int] = None,
        no_price: Optional[int] = None,
        expiration_ts: Optional[int] = None
    ) -> Dict:
        """
        Create a new order (requires authentication).

        Args:
            ticker: Market ticker symbol
            action: 'buy' or 'sell'
            side: 'yes' or 'no'
            count: Number of contracts
            type: Order type ('limit' or 'market')
            yes_price: Price in cents for yes side (required for limit orders)
            no_price: Price in cents for no side (required for limit orders)
            expiration_ts: Optional expiration timestamp

        Returns:
            Dictionary containing order details
        """
        if not self.api_key_id or not self.private_key:
            raise ValueError("Authentication required. Initialize client with api_key_id and private_key_b64.")

        order_data = {
            "ticker": ticker,
            "action": action,
            "side": side,
            "count": count,
            "type": type
        }

        if yes_price is not None:
            order_data["yes_price"] = yes_price
        if no_price is not None:
            order_data["no_price"] = no_price
        if expiration_ts is not None:
            order_data["expiration_ts"] = expiration_ts

        endpoint = "/portfolio/orders"
        return self._make_request(endpoint, method="POST", json_data=order_data, use_auth=True)

    def cancel_order(self, order_id: str) -> Dict:
        """
        Cancel an existing order (requires authentication).

        Args:
            order_id: Order ID to cancel

        Returns:
            Dictionary containing cancellation details
        """
        if not self.api_key_id or not self.private_key:
            raise ValueError("Authentication required. Initialize client with api_key_id and private_key_b64.")

        endpoint = f"/portfolio/orders/{order_id}"
        return self._make_request(endpoint, method="DELETE", use_auth=True)

    @classmethod
    def from_env(cls, **kwargs) -> 'KalshiDataClient':
        """
        Create a client using credentials from environment variables.

        Expects:
            KALSHI_API_KEY_ID: API key ID
            KALSHI_PRIV_KEY: Base64-encoded private key

        Args:
            **kwargs: Additional arguments to pass to __init__

        Returns:
            Initialized KalshiDataClient with authentication
        """
        api_key_id = os.environ.get('KALSHI_API_KEY_ID')
        private_key_b64 = os.environ.get('KALSHI_PRIV_KEY')

        if not api_key_id or not private_key_b64:
            raise ValueError(
                "Missing required environment variables: KALSHI_API_KEY_ID and/or KALSHI_PRIV_KEY"
            )

        return cls(api_key_id=api_key_id, private_key_b64=private_key_b64, **kwargs)

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
