#!/usr/bin/env python3
"""Check what types of markets are available."""

from kalshi_client import KalshiDataClient

client = KalshiDataClient()

print("Checking different market queries...\n")

# Try different queries
queries = [
    ("All open markets (no filter)", {"max_markets": 500, "status": "open"}),
    ("Markets with volume > 1000", {"max_markets": 500, "status": "open", "min_volume": 1000}),
    ("Markets with volume > 10000", {"max_markets": 500, "status": "open", "min_volume": 10000}),
]

for query_name, params in queries:
    print(f"{query_name}:")
    markets = client.get_all_open_markets(**params)

    # Categorize
    multi_markets = [m for m in markets if m.get("ticker", "").startswith("KXMV")]
    regular_markets = [m for m in markets if not m.get("ticker", "").startswith("KXMV")]

    print(f"  Total: {len(markets)}")
    print(f"  Multivariate (KXMV): {len(multi_markets)}")
    print(f"  Regular: {len(regular_markets)}")

    if regular_markets:
        print(f"  Sample regular markets:")
        for m in regular_markets[:3]:
            ticker = m.get("ticker", "")
            title = m.get("title", "")[:50]
            volume = m.get("volume", 0)
            print(f"    - {ticker}: {title}... (vol: {volume:,})")

    # Check ticker prefixes
    prefixes = {}
    for m in markets:
        ticker = m.get("ticker", "")
        prefix = ticker.split("-")[0] if ticker else "UNKNOWN"
        prefixes[prefix] = prefixes.get(prefix, 0) + 1

    print(f"  Ticker prefixes:")
    for prefix, count in sorted(prefixes.items(), key=lambda x: -x[1])[:10]:
        print(f"    {prefix}: {count}")

    print()

# Get a sample of the first regular market if any exist
print("\n" + "="*80)
print("Looking for any non-KXMV markets in depth...")
all_markets = client.get_all_open_markets(max_markets=1000, status="open")
print(f"Checked {len(all_markets)} markets total")

regular = [m for m in all_markets if not m.get("ticker", "").startswith("KXMV")]
print(f"Found {len(regular)} regular markets")

if regular:
    print("\nFirst regular market:")
    import json
    print(json.dumps(regular[0], indent=2, default=str))
