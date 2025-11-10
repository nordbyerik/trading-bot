from kalshi_client import KalshiDataClient

client = KalshiDataClient()

# Get markets with good volume
markets = client.get_all_open_markets(max_markets=100, status="open", min_volume=100)

print(f"Found {len(markets)} markets with volume >= 100\n")

# Check for real orderbooks
real_orderbooks = 0
for market in markets:
    ticker = market.get("ticker")
    try:
        orderbook_response = client.get_orderbook(ticker)
        orderbook = orderbook_response.get("orderbook", {})
        
        if orderbook.get("yes") is not None and orderbook.get("no") is not None:
            real_orderbooks += 1
            print(f"✓ Real orderbook: {ticker[:40]}... (vol: {market.get('volume')})")
            if real_orderbooks >= 5:
                break
    except:
        pass

print(f"\nFound {real_orderbooks} markets with real orderbooks out of {len(markets)}")
