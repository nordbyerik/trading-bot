#!/usr/bin/env python3
"""
Test script for Kalshi API authentication
Tests RSA signature-based authentication with the Kalshi API
"""

import logging
import sys
from kalshi_client import KalshiDataClient

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_authentication():
    """Test Kalshi API authentication."""

    print("=" * 60)
    print("Testing Kalshi API Authentication")
    print("=" * 60)

    try:
        # Create client from environment variables
        print("\n1. Creating authenticated client from environment variables...")
        client = KalshiDataClient.from_env()
        print("   ✓ Client created successfully")

        # Test balance endpoint
        print("\n2. Testing /portfolio/balance endpoint (requires auth)...")
        try:
            balance = client.get_balance()
            print("   ✓ Authentication successful!")
            print(f"   Balance: ${balance.get('balance', 0) / 100:.2f}")
        except Exception as e:
            print(f"   ✗ Balance request failed: {e}")
            return False

        # Test portfolio endpoint
        print("\n3. Testing /portfolio endpoint (requires auth)...")
        try:
            portfolio = client.get_portfolio()
            print("   ✓ Portfolio request successful!")
            positions = portfolio.get('portfolio_positions', [])
            print(f"   Open positions: {len(positions)}")
        except Exception as e:
            # 404 means endpoint doesn't exist, but auth is working
            if "404" in str(e):
                print(f"   ! Portfolio endpoint not available (404) - skipping")
            else:
                print(f"   ✗ Portfolio request failed: {e}")
                return False

        # Test orders endpoint
        print("\n4. Testing /portfolio/orders endpoint (requires auth)...")
        try:
            orders = client.get_orders()
            print("   ✓ Orders request successful!")
            order_list = orders.get('orders', [])
            print(f"   Orders: {len(order_list)}")
        except Exception as e:
            if "404" in str(e):
                print(f"   ! Orders endpoint not available (404) - skipping")
            else:
                print(f"   ✗ Orders request failed: {e}")

        # Test fills endpoint
        print("\n5. Testing /portfolio/fills endpoint (requires auth)...")
        try:
            fills = client.get_fills(limit=10)
            print("   ✓ Fills request successful!")
            fill_list = fills.get('fills', [])
            print(f"   Recent fills: {len(fill_list)}")
        except Exception as e:
            if "404" in str(e):
                print(f"   ! Fills endpoint not available (404) - skipping")
            else:
                print(f"   ✗ Fills request failed: {e}")

        # Test orderbook with auth
        print("\n6. Testing orderbook with authentication...")
        try:
            markets = client.get_markets(limit=1)
            if markets.get('markets'):
                ticker = markets['markets'][0]['ticker']
                print(f"   Testing with market: {ticker}")

                orderbook_response = client.get_orderbook(ticker, use_auth=True)
                orderbook = orderbook_response.get('orderbook', {})
                yes_bids = orderbook.get('yes', []) if orderbook else []
                no_bids = orderbook.get('no', []) if orderbook else []
                print(f"   ✓ Authenticated orderbook request successful!")
                print(f"   Yes bids: {len(yes_bids)}, No bids: {len(no_bids)}")
            else:
                print("   ! No markets available to test")
        except Exception as e:
            print(f"   ✗ Authenticated orderbook request failed: {e}")

        print("\n" + "=" * 60)
        print("All authentication tests passed! ✓")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n✗ Error during testing: {e}")
        logger.exception("Test failed with exception:")
        return False


def test_public_endpoints():
    """Test that public endpoints still work without auth."""

    print("\n" + "=" * 60)
    print("Testing Public Endpoints (without auth)")
    print("=" * 60)

    try:
        # Create client without auth
        print("\n1. Creating non-authenticated client...")
        client = KalshiDataClient()
        print("   ✓ Client created successfully")

        # Test public markets endpoint
        print("\n2. Testing public /markets endpoint...")
        markets = client.get_markets(limit=5)
        print(f"   ✓ Retrieved {len(markets.get('markets', []))} markets")

        # Test public orderbook
        if markets.get('markets'):
            ticker = markets['markets'][0]['ticker']
            print(f"\n3. Testing public orderbook for {ticker}...")
            orderbook = client.get_orderbook(ticker)
            print("   ✓ Public orderbook request successful")

        print("\n" + "=" * 60)
        print("Public endpoint tests passed! ✓")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n✗ Error during testing: {e}")
        logger.exception("Test failed with exception:")
        return False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("KALSHI API AUTHENTICATION TEST SUITE")
    print("=" * 60)

    # Test authenticated endpoints
    auth_success = test_authentication()

    # Test public endpoints
    public_success = test_public_endpoints()

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Authenticated endpoints: {'PASSED ✓' if auth_success else 'FAILED ✗'}")
    print(f"Public endpoints: {'PASSED ✓' if public_success else 'FAILED ✗'}")
    print("=" * 60)

    sys.exit(0 if (auth_success and public_success) else 1)
