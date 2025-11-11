"""
Historical Data Fetcher

Fetches historical market data from Kalshi API across multiple markets.
Supports candlesticks, trades, and orderbook snapshots.
"""

import logging
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path to import kalshi_client
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from kalshi_client import KalshiDataClient

logger = logging.getLogger(__name__)


class HistoricalDataFetcher:
    """
    Fetches historical market data from Kalshi API.

    Supports:
    - Candlestick data (OHLC) for individual markets or events
    - Historical trades
    - Multiple markets in parallel
    """

    def __init__(self, client: Optional[KalshiDataClient] = None):
        """
        Initialize the data fetcher.

        Args:
            client: KalshiDataClient instance. If None, creates a new one.
        """
        self.client = client or KalshiDataClient()
        logger.info("HistoricalDataFetcher initialized")

    def fetch_market_candlesticks(
        self,
        series_ticker: str,
        market_ticker: str,
        days_back: int = 7,
        period_interval: int = 60
    ) -> List[Dict]:
        """
        Fetch historical candlestick data for a single market.

        Args:
            series_ticker: Series ticker (e.g., 'INXD')
            market_ticker: Market ticker (e.g., 'INXD-25JAN06-T4999.99')
            days_back: Number of days of history to fetch
            period_interval: Candlestick period in minutes (1, 60, or 1440)

        Returns:
            List of candlestick dictionaries with OHLC data
        """
        end_ts = int(time.time())
        start_ts = end_ts - (days_back * 24 * 60 * 60)

        logger.info(
            f"Fetching {days_back} days of candlesticks for {market_ticker} "
            f"(interval: {period_interval}min)"
        )

        try:
            response = self.client.get_market_candlesticks(
                series_ticker=series_ticker,
                market_ticker=market_ticker,
                start_ts=start_ts,
                end_ts=end_ts,
                period_interval=period_interval
            )

            candlesticks = response.get('candlesticks', [])
            logger.info(f"Fetched {len(candlesticks)} candlesticks for {market_ticker}")
            return candlesticks

        except Exception as e:
            logger.error(f"Error fetching candlesticks for {market_ticker}: {e}")
            return []

    def fetch_event_candlesticks(
        self,
        series_ticker: str,
        event_ticker: str,
        days_back: int = 7,
        period_interval: int = 60
    ) -> Dict:
        """
        Fetch aggregated candlestick data for all markets in an event.

        Args:
            series_ticker: Series ticker
            event_ticker: Event ticker
            days_back: Number of days of history to fetch
            period_interval: Candlestick period in minutes (1, 60, or 1440)

        Returns:
            Dictionary with 'market_tickers' and 'market_candlesticks' arrays
        """
        end_ts = int(time.time())
        start_ts = end_ts - (days_back * 24 * 60 * 60)

        logger.info(
            f"Fetching {days_back} days of event candlesticks for {event_ticker} "
            f"(interval: {period_interval}min)"
        )

        try:
            response = self.client.get_event_candlesticks(
                series_ticker=series_ticker,
                event_ticker=event_ticker,
                start_ts=start_ts,
                end_ts=end_ts,
                period_interval=period_interval
            )

            market_tickers = response.get('market_tickers', [])
            logger.info(
                f"Fetched event candlesticks for {len(market_tickers)} markets "
                f"in {event_ticker}"
            )
            return response

        except Exception as e:
            logger.error(f"Error fetching event candlesticks for {event_ticker}: {e}")
            return {'market_tickers': [], 'market_candlesticks': []}

    def fetch_multiple_markets(
        self,
        market_specs: List[Tuple[str, str]],
        days_back: int = 7,
        period_interval: int = 60
    ) -> Dict[str, List[Dict]]:
        """
        Fetch historical data for multiple markets.

        Args:
            market_specs: List of (series_ticker, market_ticker) tuples
            days_back: Number of days of history to fetch
            period_interval: Candlestick period in minutes

        Returns:
            Dictionary mapping market_ticker to list of candlesticks
        """
        results = {}

        logger.info(f"Fetching data for {len(market_specs)} markets")

        for series_ticker, market_ticker in market_specs:
            candlesticks = self.fetch_market_candlesticks(
                series_ticker=series_ticker,
                market_ticker=market_ticker,
                days_back=days_back,
                period_interval=period_interval
            )
            results[market_ticker] = candlesticks

        logger.info(f"Fetched data for {len(results)} markets")
        return results

    def fetch_trades(
        self,
        market_ticker: Optional[str] = None,
        days_back: int = 1,
        limit: int = 1000
    ) -> List[Dict]:
        """
        Fetch historical trade data.

        Args:
            market_ticker: Specific market ticker (None for all markets)
            days_back: Number of days of history to fetch
            limit: Maximum number of trades per page

        Returns:
            List of trade dictionaries
        """
        end_ts = int(time.time())
        start_ts = end_ts - (days_back * 24 * 60 * 60)

        logger.info(
            f"Fetching {days_back} days of trades"
            f"{f' for {market_ticker}' if market_ticker else ''}"
        )

        all_trades = []
        cursor = None

        try:
            while True:
                response = self.client.get_trades(
                    market_ticker=market_ticker,
                    min_ts=start_ts,
                    max_ts=end_ts,
                    limit=limit,
                    cursor=cursor
                )

                trades = response.get('trades', [])
                all_trades.extend(trades)

                cursor = response.get('cursor')
                if not cursor:
                    break

                logger.debug(f"Fetched {len(trades)} trades, total: {len(all_trades)}")

            logger.info(f"Fetched total of {len(all_trades)} trades")
            return all_trades

        except Exception as e:
            logger.error(f"Error fetching trades: {e}")
            return []

    def discover_active_markets(
        self,
        min_volume: int = 100,
        max_markets: int = 50
    ) -> List[Dict]:
        """
        Discover active markets suitable for ML training.

        Args:
            min_volume: Minimum volume threshold
            max_markets: Maximum number of markets to return

        Returns:
            List of market dictionaries
        """
        logger.info(
            f"Discovering active markets (min_volume={min_volume}, "
            f"max={max_markets})"
        )

        try:
            markets = self.client.get_all_open_markets(
                max_markets=max_markets,
                min_volume=min_volume,
                status='open'
            )

            logger.info(f"Discovered {len(markets)} active markets")
            return markets

        except Exception as e:
            logger.error(f"Error discovering markets: {e}")
            return []

    def fetch_market_with_history(
        self,
        market: Dict,
        days_back: int = 7,
        period_interval: int = 60
    ) -> Optional[Dict]:
        """
        Fetch a market along with its historical data.

        Args:
            market: Market dictionary from API
            days_back: Number of days of history to fetch
            period_interval: Candlestick period in minutes

        Returns:
            Dictionary with market info and candlesticks, or None if error
        """
        series_ticker = market.get('series_ticker')
        market_ticker = market.get('ticker')

        if not series_ticker or not market_ticker:
            logger.warning(f"Market missing series_ticker or ticker: {market}")
            return None

        candlesticks = self.fetch_market_candlesticks(
            series_ticker=series_ticker,
            market_ticker=market_ticker,
            days_back=days_back,
            period_interval=period_interval
        )

        return {
            'market': market,
            'candlesticks': candlesticks,
            'series_ticker': series_ticker,
            'market_ticker': market_ticker
        }

    def fetch_dataset_for_ml(
        self,
        min_volume: int = 100,
        max_markets: int = 20,
        days_back: int = 7,
        period_interval: int = 60
    ) -> List[Dict]:
        """
        Fetch a complete dataset suitable for ML training.

        This discovers active markets and fetches their historical data.

        Args:
            min_volume: Minimum volume threshold
            max_markets: Maximum number of markets
            days_back: Days of historical data
            period_interval: Candlestick period in minutes

        Returns:
            List of dictionaries with market info and historical data
        """
        logger.info(
            f"Fetching ML dataset: {max_markets} markets, "
            f"{days_back} days, {period_interval}min intervals"
        )

        # Discover active markets
        markets = self.discover_active_markets(
            min_volume=min_volume,
            max_markets=max_markets
        )

        if not markets:
            logger.warning("No markets discovered")
            return []

        # Fetch historical data for each market
        dataset = []
        for market in markets:
            data = self.fetch_market_with_history(
                market=market,
                days_back=days_back,
                period_interval=period_interval
            )

            if data and len(data['candlesticks']) > 0:
                dataset.append(data)
            else:
                logger.debug(
                    f"Skipping {market.get('ticker')} - no historical data"
                )

        logger.info(
            f"Fetched complete dataset: {len(dataset)} markets "
            f"with historical data"
        )
        return dataset


if __name__ == "__main__":
    # Demo usage
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 80)
    print("Historical Data Fetcher Demo")
    print("=" * 80)

    fetcher = HistoricalDataFetcher()

    # Example 1: Fetch dataset for ML
    print("\n--- Fetching ML Dataset ---")
    dataset = fetcher.fetch_dataset_for_ml(
        min_volume=50,
        max_markets=5,
        days_back=3,
        period_interval=60
    )

    print(f"\nFetched {len(dataset)} markets with historical data")

    for i, data in enumerate(dataset[:3], 1):  # Show first 3
        market = data['market']
        candlesticks = data['candlesticks']
        print(f"\n{i}. {market['ticker']}")
        print(f"   Title: {market.get('title', 'N/A')}")
        print(f"   Volume: {market.get('volume', 0):,}")
        print(f"   Candlesticks: {len(candlesticks)}")

        if candlesticks:
            first = candlesticks[0]
            last = candlesticks[-1]
            print(f"   First price: {first.get('yes_ask_close', 'N/A')}¢")
            print(f"   Last price: {last.get('yes_ask_close', 'N/A')}¢")
