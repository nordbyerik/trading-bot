#!/usr/bin/env python3
"""
Debug script to test analyzers individually and inspect their behavior.

This script helps identify:
1. Data quality issues (malformed data, missing fields)
2. Overly optimistic analyzers (1-cent trades)
3. Analyzers finding no opportunities
4. Why trades are/aren't being executed
"""

import sys
import json
from datetime import datetime
from typing import List, Dict, Any
from colorama import init, Fore, Style

# Initialize colorama for colored output
init(autoreset=True)

# Import analyzers
from analyzers.spread_analyzer import SpreadAnalyzer
from analyzers.mispricing_analyzer import MispricingAnalyzer
from analyzers.arbitrage_analyzer import ArbitrageAnalyzer
from analyzers.imbalance_analyzer import ImbalanceAnalyzer
from analyzers.momentum_fade_analyzer import MomentumFadeAnalyzer
from analyzers.correlation_analyzer import CorrelationAnalyzer
from analyzers.theta_decay_analyzer import ThetaDecayAnalyzer
from analyzers.rsi_analyzer import RSIAnalyzer
from analyzers.ma_crossover_analyzer import MovingAverageCrossoverAnalyzer
from analyzers.bollinger_bands_analyzer import BollingerBandsAnalyzer
from analyzers.macd_analyzer import MACDAnalyzer
from analyzers.volume_trend_analyzer import VolumeTrendAnalyzer

from analyzers.base import Opportunity, OpportunityStrength, ConfidenceLevel
from kalshi_client import KalshiDataClient
from trade_manager import TradeManager, TradeManagerConfig


# All available analyzers
ANALYZERS = {
    "spread": ("Spread Analyzer", SpreadAnalyzer),
    "mispricing": ("Mispricing Analyzer", MispricingAnalyzer),
    "arbitrage": ("Arbitrage Analyzer", ArbitrageAnalyzer),
    "imbalance": ("Imbalance Analyzer", ImbalanceAnalyzer),
    "momentum": ("Momentum Fade Analyzer", MomentumFadeAnalyzer),
    "correlation": ("Correlation Analyzer", CorrelationAnalyzer),
    "theta": ("Theta Decay Analyzer", ThetaDecayAnalyzer),
    "rsi": ("RSI Analyzer", RSIAnalyzer),
    "ma": ("MA Crossover Analyzer", MovingAverageCrossoverAnalyzer),
    "bollinger": ("Bollinger Bands Analyzer", BollingerBandsAnalyzer),
    "macd": ("MACD Analyzer", MACDAnalyzer),
    "volume": ("Volume Trend Analyzer", VolumeTrendAnalyzer),
}


def print_header(text: str):
    """Print a formatted header"""
    print(f"\n{Fore.CYAN}{'='*80}")
    print(f"{Fore.CYAN}{text:^80}")
    print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")


def print_subheader(text: str):
    """Print a formatted subheader"""
    print(f"\n{Fore.YELLOW}{'-'*80}")
    print(f"{Fore.YELLOW}{text}")
    print(f"{Fore.YELLOW}{'-'*80}{Style.RESET_ALL}\n")


def validate_market_data(markets: List[Dict]) -> Dict[str, Any]:
    """Validate market data and report issues"""
    issues = []
    stats = {
        "total": len(markets),
        "with_orderbook": 0,
        "with_yes_price": 0,
        "with_no_price": 0,
        "with_volume": 0,
        "with_close_time": 0,
        "invalid_prices": [],
        "missing_orderbooks": [],
        "empty_orderbooks": [],
    }

    for market in markets:
        ticker = market.get("ticker", "UNKNOWN")

        # Check required fields
        if "yes_price" in market and market["yes_price"] is not None:
            stats["with_yes_price"] += 1
            # Check valid price range
            if not (0 <= market["yes_price"] <= 100):
                stats["invalid_prices"].append(ticker)
                issues.append(f"Invalid yes_price for {ticker}: {market['yes_price']}")

        if "no_price" in market and market["no_price"] is not None:
            stats["with_no_price"] += 1
            if not (0 <= market["no_price"] <= 100):
                stats["invalid_prices"].append(ticker)
                issues.append(f"Invalid no_price for {ticker}: {market['no_price']}")

        if "volume" in market:
            stats["with_volume"] += 1

        if "close_time" in market:
            stats["with_close_time"] += 1

        # Check orderbook
        if "orderbook" in market and market["orderbook"]:
            stats["with_orderbook"] += 1
            orderbook = market["orderbook"]

            # Check if orderbook has data
            yes_orders = orderbook.get("yes", [])
            no_orders = orderbook.get("no", [])

            if not yes_orders and not no_orders:
                stats["empty_orderbooks"].append(ticker)
                issues.append(f"Empty orderbook for {ticker}")
        else:
            stats["missing_orderbooks"].append(ticker)

    return {"stats": stats, "issues": issues}


def print_data_validation(validation: Dict[str, Any]):
    """Print data validation results"""
    print_subheader("Data Validation Results")

    stats = validation["stats"]
    issues = validation["issues"]

    print(f"{Fore.GREEN}Total markets: {stats['total']}")
    print(f"Markets with yes_price: {stats['with_yes_price']} ({stats['with_yes_price']/stats['total']*100:.1f}%)")
    print(f"Markets with no_price: {stats['with_no_price']} ({stats['with_no_price']/stats['total']*100:.1f}%)")
    print(f"Markets with orderbook: {stats['with_orderbook']} ({stats['with_orderbook']/stats['total']*100:.1f}%)")
    print(f"Markets with volume: {stats['with_volume']} ({stats['with_volume']/stats['total']*100:.1f}%)")
    print(f"Markets with close_time: {stats['with_close_time']} ({stats['with_close_time']/stats['total']*100:.1f}%)")

    if stats['invalid_prices']:
        print(f"\n{Fore.RED}⚠ Markets with invalid prices: {len(stats['invalid_prices'])}")
        for ticker in stats['invalid_prices'][:5]:  # Show first 5
            print(f"  - {ticker}")

    if stats['missing_orderbooks']:
        print(f"\n{Fore.YELLOW}⚠ Markets missing orderbooks: {len(stats['missing_orderbooks'])}")
        for ticker in stats['missing_orderbooks'][:5]:  # Show first 5
            print(f"  - {ticker}")

    if stats['empty_orderbooks']:
        print(f"\n{Fore.YELLOW}⚠ Markets with empty orderbooks: {len(stats['empty_orderbooks'])}")
        for ticker in stats['empty_orderbooks'][:5]:  # Show first 5
            print(f"  - {ticker}")

    if issues:
        print(f"\n{Fore.RED}Issues found ({len(issues)} total):")
        for issue in issues[:10]:  # Show first 10
            print(f"  {Fore.RED}- {issue}")
        if len(issues) > 10:
            print(f"  {Fore.RED}... and {len(issues) - 10} more")


def print_opportunity(opp: Opportunity, index: int):
    """Print a formatted opportunity"""
    # Color based on edge size
    if opp.estimated_edge_cents < 2:
        color = Fore.RED
        flag = "🚨 TINY EDGE"
    elif opp.estimated_edge_cents < 5:
        color = Fore.YELLOW
        flag = "⚠ SMALL EDGE"
    elif opp.estimated_edge_cents < 10:
        color = Fore.GREEN
        flag = "✓ GOOD EDGE"
    else:
        color = Fore.CYAN
        flag = "★ EXCELLENT EDGE"

    print(f"\n{color}Opportunity #{index + 1} - {flag}{Style.RESET_ALL}")
    print(f"  Type: {opp.opportunity_type.value}")
    print(f"  Confidence: {opp.confidence.value} | Strength: {opp.strength.value}")
    print(f"  Edge: {color}{opp.estimated_edge_cents:.2f}¢{Style.RESET_ALL} ({opp.estimated_edge_percent:.2f}%)")
    print(f"  Market: {opp.market_tickers[0]}")
    print(f"  Title: {opp.market_titles[0][:60]}...")
    print(f"  Current Prices: {opp.current_prices}")
    print(f"  Reasoning: {opp.reasoning[:100]}...")

    # Highlight specific concerns
    if opp.estimated_edge_cents <= 1:
        print(f"  {Fore.RED}⚠ WARNING: 1-cent edge! This is likely too small to profit after fees.{Style.RESET_ALL}")


def check_trade_execution(opportunity: Opportunity, trade_manager: TradeManager) -> Dict[str, Any]:
    """Check if an opportunity would be executed by TradeManager"""
    should_trade, reason = trade_manager.should_trade(opportunity)

    # Get detailed breakdown
    result = {
        "should_trade": should_trade,
        "reason": reason,
        "checks": {}
    }

    # Manual checks to provide detailed feedback
    config = trade_manager.config

    # Check edge thresholds
    edge_cents_ok = opportunity.estimated_edge_cents >= config.min_edge_cents
    edge_percent_ok = opportunity.estimated_edge_percent >= config.min_edge_percent

    result["checks"]["edge_cents"] = {
        "pass": edge_cents_ok,
        "value": opportunity.estimated_edge_cents,
        "threshold": config.min_edge_cents,
    }
    result["checks"]["edge_percent"] = {
        "pass": edge_percent_ok,
        "value": opportunity.estimated_edge_percent,
        "threshold": config.min_edge_percent,
    }

    # Check confidence
    if config.min_confidence:
        confidence_levels = [ConfidenceLevel.LOW, ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH]
        min_conf_idx = confidence_levels.index(config.min_confidence)
        opp_conf_idx = confidence_levels.index(opportunity.confidence)
        confidence_ok = opp_conf_idx >= min_conf_idx

        result["checks"]["confidence"] = {
            "pass": confidence_ok,
            "value": opportunity.confidence.value,
            "threshold": config.min_confidence.value,
        }

    # Check strength
    if config.min_strength:
        strength_ok = opportunity.strength == OpportunityStrength.HARD or config.min_strength == OpportunityStrength.SOFT
        result["checks"]["strength"] = {
            "pass": strength_ok,
            "value": opportunity.strength.value,
            "threshold": config.min_strength.value,
        }

    return result


def print_trade_check(trade_check: Dict[str, Any]):
    """Print trade execution check results"""
    if trade_check["should_trade"]:
        print(f"\n  {Fore.GREEN}✓ WOULD EXECUTE THIS TRADE{Style.RESET_ALL}")
    else:
        print(f"\n  {Fore.RED}✗ WOULD NOT EXECUTE - {trade_check['reason']}{Style.RESET_ALL}")

    print(f"\n  Detailed checks:")
    for check_name, check_data in trade_check["checks"].items():
        status = f"{Fore.GREEN}✓" if check_data["pass"] else f"{Fore.RED}✗"
        print(f"    {status} {check_name}: {check_data['value']} (threshold: {check_data['threshold']}){Style.RESET_ALL}")


def debug_analyzer(analyzer_key: str, markets: List[Dict], trade_manager: TradeManager):
    """Debug a specific analyzer"""
    if analyzer_key not in ANALYZERS:
        print(f"{Fore.RED}Unknown analyzer: {analyzer_key}{Style.RESET_ALL}")
        return

    analyzer_name, analyzer_class = ANALYZERS[analyzer_key]

    print_header(f"Debugging: {analyzer_name}")

    # Initialize analyzer
    analyzer = analyzer_class()

    # Show configuration
    print_subheader("Analyzer Configuration")
    config = analyzer.get_default_config()
    for key, value in config.items():
        print(f"  {key}: {value}")

    # Run analyzer
    print_subheader("Running Analysis")
    print(f"Analyzing {len(markets)} markets...")

    try:
        opportunities = analyzer.analyze(markets)
        print(f"{Fore.GREEN}✓ Analysis complete: Found {len(opportunities)} opportunities{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}✗ Analysis failed with error:{Style.RESET_ALL}")
        print(f"{Fore.RED}  {type(e).__name__}: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
        return

    # Show opportunities
    if not opportunities:
        print(f"\n{Fore.YELLOW}No opportunities found.{Style.RESET_ALL}")
        print(f"\nPossible reasons:")
        print(f"  1. Market conditions don't meet analyzer thresholds")
        print(f"  2. Data quality issues (check validation above)")
        print(f"  3. Analyzer configuration is too strict")
        return

    print_subheader(f"Found {len(opportunities)} Opportunities")

    # Group by edge size
    tiny_edge = [o for o in opportunities if o.estimated_edge_cents <= 1]
    small_edge = [o for o in opportunities if 1 < o.estimated_edge_cents <= 5]
    good_edge = [o for o in opportunities if 5 < o.estimated_edge_cents <= 10]
    excellent_edge = [o for o in opportunities if o.estimated_edge_cents > 10]

    print(f"\nEdge Distribution:")
    print(f"  {Fore.RED}Tiny (≤1¢): {len(tiny_edge)}{Style.RESET_ALL}")
    print(f"  {Fore.YELLOW}Small (1-5¢): {len(small_edge)}{Style.RESET_ALL}")
    print(f"  {Fore.GREEN}Good (5-10¢): {len(good_edge)}{Style.RESET_ALL}")
    print(f"  {Fore.CYAN}Excellent (>10¢): {len(excellent_edge)}{Style.RESET_ALL}")

    # Show examples from each category
    if tiny_edge:
        print(f"\n{Fore.RED}⚠ WARNING: {len(tiny_edge)} opportunities with ≤1¢ edge (likely unprofitable!){Style.RESET_ALL}")
        for i, opp in enumerate(tiny_edge[:3]):  # Show first 3
            print_opportunity(opp, i)
            trade_check = check_trade_execution(opp, trade_manager)
            print_trade_check(trade_check)

    if small_edge:
        print(f"\n{Fore.YELLOW}Found {len(small_edge)} opportunities with 1-5¢ edge:{Style.RESET_ALL}")
        for i, opp in enumerate(small_edge[:3]):  # Show first 3
            print_opportunity(opp, i)
            trade_check = check_trade_execution(opp, trade_manager)
            print_trade_check(trade_check)

    if good_edge:
        print(f"\n{Fore.GREEN}Found {len(good_edge)} opportunities with 5-10¢ edge:{Style.RESET_ALL}")
        for i, opp in enumerate(good_edge[:2]):  # Show first 2
            print_opportunity(opp, i)
            trade_check = check_trade_execution(opp, trade_manager)
            print_trade_check(trade_check)

    if excellent_edge:
        print(f"\n{Fore.CYAN}Found {len(excellent_edge)} opportunities with >10¢ edge:{Style.RESET_ALL}")
        for i, opp in enumerate(excellent_edge[:2]):  # Show first 2
            print_opportunity(opp, i)
            trade_check = check_trade_execution(opp, trade_manager)
            print_trade_check(trade_check)


def main():
    """Main debug function"""
    print_header("Trading Bot Analyzer Debugger")

    # Parse arguments
    if len(sys.argv) < 2:
        print(f"Usage: python debug_analyzers.py <analyzer_key> [limit]")
        print(f"\nAvailable analyzers:")
        for key, (name, _) in ANALYZERS.items():
            print(f"  {key:15} - {name}")
        print(f"\nOr use 'all' to debug all analyzers")
        print(f"\nOptional: [limit] - number of markets to fetch (default: 100)")
        sys.exit(1)

    analyzer_key = sys.argv[1].lower()
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 100

    # Initialize Kalshi client
    print(f"Initializing Kalshi client...")
    client = KalshiDataClient()

    # Fetch more markets initially since we'll filter out multivariate ones
    fetch_limit = limit * 10  # Fetch 10x since many will be filtered
    min_volume = None  # No volume filter - get all markets
    print(f"Fetching up to {fetch_limit} markets...")
    all_markets = client.get_all_open_markets(
        max_markets=fetch_limit,
        status="open",
        min_volume=min_volume
    )
    print(f"{Fore.GREEN}✓ Fetched {len(all_markets)} markets{Style.RESET_ALL}")

    # Filter out multivariate markets (they don't have orderbooks)
    print(f"\nFiltering out multivariate markets (KXMV prefix)...")
    multi_markets = [m for m in all_markets if m.get("ticker", "").startswith("KXMV")]
    regular_markets = [m for m in all_markets if not m.get("ticker", "").startswith("KXMV")]

    print(f"  Multivariate markets: {len(multi_markets)} (filtered out)")
    print(f"  Regular markets: {len(regular_markets)}")

    if len(regular_markets) == 0:
        print(f"\n{Fore.RED}ERROR: No regular (non-multivariate) markets found!{Style.RESET_ALL}")
        print(f"All {len(all_markets)} markets are multivariate (KXMV), which don't support orderbooks.")
        print(f"\nTry:")
        print(f"  1. Removing or lowering the min_volume filter")
        print(f"  2. Using 'settled' or 'closed' status to see historical markets")
        sys.exit(1)

    # Take only the number requested
    markets = regular_markets[:limit]
    print(f"\n{Fore.GREEN}✓ Using {len(markets)} regular markets for analysis{Style.RESET_ALL}")

    # Enrich with orderbook data
    print(f"\nEnriching markets with orderbook data...")
    enriched_markets = []
    failed_count = 0
    empty_orderbook_count = 0

    for i, market in enumerate(markets):
        ticker = market.get("ticker")
        try:
            orderbook_response = client.get_orderbook(ticker)
            orderbook = orderbook_response.get("orderbook", {})

            # Check if orderbook has actual data
            yes_orders = orderbook.get("yes")
            no_orders = orderbook.get("no")

            if yes_orders is None and no_orders is None:
                empty_orderbook_count += 1
                if empty_orderbook_count <= 3:
                    print(f"{Fore.YELLOW}  Warning: Orderbook is null for {ticker}{Style.RESET_ALL}")
            elif (not yes_orders or len(yes_orders) == 0) and (not no_orders or len(no_orders) == 0):
                empty_orderbook_count += 1

            market["orderbook"] = orderbook
            enriched_markets.append(market)

            if (i + 1) % 20 == 0:
                print(f"  Fetched orderbooks for {i + 1}/{len(markets)} markets...")
        except Exception as e:
            failed_count += 1
            if failed_count <= 3:  # Show first 3 failures
                print(f"{Fore.YELLOW}  Warning: Failed to fetch orderbook for {ticker}: {e}{Style.RESET_ALL}")

    print(f"{Fore.GREEN}✓ Enriched {len(enriched_markets)} markets with orderbook data{Style.RESET_ALL}")
    if empty_orderbook_count > 0:
        print(f"{Fore.YELLOW}  ({empty_orderbook_count} markets have empty/null orderbooks){Style.RESET_ALL}")
    if failed_count > 0:
        print(f"{Fore.RED}  ({failed_count} markets failed to fetch){Style.RESET_ALL}")

    markets = enriched_markets

    # Validate data
    validation = validate_market_data(markets)
    print_data_validation(validation)

    # Initialize TradeManager with default config
    trade_manager = TradeManager(
        config=TradeManagerConfig()  # Use default config
    )

    print_subheader("TradeManager Configuration")
    print(f"  Min edge (cents): {trade_manager.config.min_edge_cents}¢")
    print(f"  Min edge (percent): {trade_manager.config.min_edge_percent}%")
    print(f"  Min confidence: {trade_manager.config.min_confidence.value if trade_manager.config.min_confidence else 'None'}")
    print(f"  Min strength: {trade_manager.config.min_strength.value if trade_manager.config.min_strength else 'None'}")
    print(f"  Max positions: {trade_manager.config.max_positions}")

    # Debug analyzer(s)
    if analyzer_key == "all":
        for key in ANALYZERS.keys():
            debug_analyzer(key, markets, trade_manager)
            print("\n" + "="*80 + "\n")
    else:
        debug_analyzer(analyzer_key, markets, trade_manager)

    print_header("Debug Complete")


if __name__ == "__main__":
    main()
