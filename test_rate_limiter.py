#!/usr/bin/env python3
"""
Test script for the rate limiter implementation.

This script tests that the rate limiter correctly enforces the 20 req/s limit.
"""

import time
from kalshi_client import TokenBucketRateLimiter


def test_basic_rate_limiting():
    """Test basic rate limiting functionality."""
    print("Testing basic rate limiting (5 requests with 5 req/s limit)...")

    limiter = TokenBucketRateLimiter(rate=5.0)

    start = time.time()
    for i in range(5):
        limiter.acquire()
        elapsed = time.time() - start
        print(f"  Request {i+1}: {elapsed:.3f}s elapsed")

    total_time = time.time() - start
    print(f"Total time: {total_time:.3f}s")
    print(f"Expected: ~0.8s (4 intervals of 0.2s each)")
    print()


def test_burst_handling():
    """Test burst handling with capacity."""
    print("Testing burst handling...")

    # Allow burst of 10, but rate of 5/s
    limiter = TokenBucketRateLimiter(rate=5.0, capacity=10.0)

    start = time.time()

    # First 10 should go through immediately (burst)
    print("  Sending initial burst of 10 requests...")
    for i in range(10):
        limiter.acquire()
    burst_time = time.time() - start
    print(f"  Burst completed in: {burst_time:.3f}s (should be ~0s)")

    # Next 5 should be rate limited
    print("  Sending 5 more requests (should be rate limited)...")
    for i in range(5):
        limiter.acquire()
        elapsed = time.time() - start
        print(f"    Request {i+1}: {elapsed:.3f}s elapsed")

    total_time = time.time() - start
    print(f"Total time: {total_time:.3f}s")
    print(f"Expected: ~1.0s (burst + 1s for 5 more requests)")
    print()


def test_kalshi_rate_limit():
    """Test with Kalshi's actual rate limit (20 req/s)."""
    print("Testing Kalshi rate limit (40 requests at 20 req/s)...")

    limiter = TokenBucketRateLimiter(rate=20.0)

    start = time.time()
    request_times = []

    for i in range(40):
        limiter.acquire()
        elapsed = time.time() - start
        request_times.append(elapsed)
        if (i + 1) % 10 == 0:
            print(f"  Completed {i+1} requests in {elapsed:.3f}s")

    total_time = time.time() - start
    actual_rate = 40 / total_time

    print(f"Total time: {total_time:.3f}s")
    print(f"Actual rate: {actual_rate:.2f} req/s")
    print(f"Expected: ~2.0s (40 requests / 20 req/s)")
    print()


def test_threading_safety():
    """Test thread safety with concurrent requests."""
    import threading

    print("Testing thread safety (20 threads, 5 requests each)...")

    limiter = TokenBucketRateLimiter(rate=20.0)
    results = []

    def make_requests(thread_id):
        for i in range(5):
            start = time.time()
            limiter.acquire()
            elapsed = time.time() - start
            results.append((thread_id, i, time.time()))

    start = time.time()
    threads = []

    for i in range(20):
        thread = threading.Thread(target=make_requests, args=(i,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    total_time = time.time() - start
    actual_rate = 100 / total_time

    print(f"Total time: {total_time:.3f}s")
    print(f"Actual rate: {actual_rate:.2f} req/s")
    print(f"Expected: ~5.0s (100 requests / 20 req/s)")
    print()


if __name__ == "__main__":
    print("=" * 60)
    print("Rate Limiter Test Suite")
    print("=" * 60)
    print()

    test_basic_rate_limiting()
    test_burst_handling()
    test_kalshi_rate_limit()
    test_threading_safety()

    print("=" * 60)
    print("All tests completed!")
    print("=" * 60)
