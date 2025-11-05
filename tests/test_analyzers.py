"""
Unit tests for market analyzers.
"""

import pytest
from datetime import datetime

from analyzers.base import OpportunityType, ConfidenceLevel
from analyzers.spread_analyzer import SpreadAnalyzer
from analyzers.mispricing_analyzer import MispricingAnalyzer
from analyzers.arbitrage_analyzer import ArbitrageAnalyzer
from analyzers.correlation_analyzer import CorrelationAnalyzer
from analyzers.imbalance_analyzer import ImbalanceAnalyzer


class TestSpreadAnalyzer:
    """Tests for SpreadAnalyzer."""

    def test_wide_spread_detected(self):
        """Test that wide spreads are detected."""
        analyzer = SpreadAnalyzer(config={"min_spread_cents": 10})

        markets = [
            {
                "ticker": "WIDE-SPREAD",
                "title": "Market with wide spread",
                "volume": 1000,
                "orderbook": {
                    "yes": [[30, 100]],  # 30 cents
                    "no": [[40, 100]],   # 40 cents
                    # Spread = 100 - 30 - 40 = 30 cents (wide!)
                },
            }
        ]

        opportunities = analyzer.analyze(markets)

        assert len(opportunities) == 1
        assert opportunities[0].opportunity_type == OpportunityType.WIDE_SPREAD
        assert opportunities[0].additional_data["spread_cents"] == 30

    def test_narrow_spread_ignored(self):
        """Test that narrow spreads are ignored."""
        analyzer = SpreadAnalyzer(config={"min_spread_cents": 10})

        markets = [
            {
                "ticker": "NARROW-SPREAD",
                "title": "Market with narrow spread",
                "volume": 1000,
                "orderbook": {
                    "yes": [[48, 100]],
                    "no": [[50, 100]],
                    # Spread = 100 - 48 - 50 = 2 cents (narrow)
                },
            }
        ]

        opportunities = analyzer.analyze(markets)

        assert len(opportunities) == 0

    def test_no_orderbook_skipped(self):
        """Test that markets without orderbook are skipped."""
        analyzer = SpreadAnalyzer()

        markets = [
            {
                "ticker": "NO-ORDERBOOK",
                "title": "Market without orderbook",
                "volume": 1000,
            }
        ]

        opportunities = analyzer.analyze(markets)

        assert len(opportunities) == 0


class TestMispricingAnalyzer:
    """Tests for MispricingAnalyzer."""

    def test_extreme_low_price_detected(self):
        """Test that extreme low prices are detected."""
        analyzer = MispricingAnalyzer(config={"extreme_low_threshold": 5})

        markets = [
            {
                "ticker": "EXTREME-LOW",
                "title": "Market with extreme low price",
                "yes_price": 3,
                "volume": 100,
            }
        ]

        opportunities = analyzer.analyze(markets)

        assert len(opportunities) >= 1
        # Should flag as extreme low
        extreme_opp = [o for o in opportunities if o.additional_data.get("extreme_type") == "low"]
        assert len(extreme_opp) == 1

    def test_extreme_high_price_detected(self):
        """Test that extreme high prices are detected."""
        analyzer = MispricingAnalyzer(config={"extreme_high_threshold": 95})

        markets = [
            {
                "ticker": "EXTREME-HIGH",
                "title": "Market with extreme high price",
                "yes_price": 97,
                "volume": 100,
            }
        ]

        opportunities = analyzer.analyze(markets)

        assert len(opportunities) >= 1
        extreme_opp = [o for o in opportunities if o.additional_data.get("extreme_type") == "high"]
        assert len(extreme_opp) == 1

    def test_round_number_bias_detected(self):
        """Test that round number bias is detected."""
        analyzer = MispricingAnalyzer(config={
            "round_numbers": [25, 50, 75],
            "round_number_tolerance": 2,
            "max_volume_for_round_bias": 500,
        })

        markets = [
            {
                "ticker": "ROUND-50",
                "title": "Market at round number",
                "yes_price": 50,
                "volume": 100,  # Low volume
            }
        ]

        opportunities = analyzer.analyze(markets)

        assert len(opportunities) >= 1
        round_opp = [o for o in opportunities if o.additional_data.get("bias_type") == "round_number"]
        assert len(round_opp) == 1

    def test_normal_price_ignored(self):
        """Test that normal prices are ignored."""
        analyzer = MispricingAnalyzer()

        markets = [
            {
                "ticker": "NORMAL",
                "title": "Normal market",
                "yes_price": 65,
                "volume": 5000,
            }
        ]

        opportunities = analyzer.analyze(markets)

        assert len(opportunities) == 0


class TestArbitrageAnalyzer:
    """Tests for ArbitrageAnalyzer."""

    def test_simple_arbitrage_detected(self):
        """Test that simple arbitrage (YES + NO > 100) is detected."""
        analyzer = ArbitrageAnalyzer(config={"min_arb_cents": 2, "transaction_cost_cents": 1})

        markets = [
            {
                "ticker": "ARB-SIMPLE",
                "title": "Market with arbitrage",
                "orderbook": {
                    "yes": [[55, 100]],
                    "no": [[50, 100]],
                    # 55 + 50 = 105 > 100 (5 cents gross profit)
                },
            }
        ]

        opportunities = analyzer.analyze(markets)

        assert len(opportunities) == 1
        assert opportunities[0].opportunity_type == OpportunityType.ARBITRAGE
        # Net profit should be gross - transaction costs
        assert opportunities[0].additional_data["gross_profit"] == 5

    def test_no_arbitrage_when_fair(self):
        """Test that no arbitrage is detected when prices are fair."""
        analyzer = ArbitrageAnalyzer()

        markets = [
            {
                "ticker": "FAIR-MARKET",
                "title": "Fair market",
                "orderbook": {
                    "yes": [[48, 100]],
                    "no": [[50, 100]],
                    # 48 + 50 = 98 < 100 (no arbitrage)
                },
            }
        ]

        opportunities = analyzer.analyze(markets)

        # Filter to only simple arbitrage (not cross-market)
        simple_arb = [o for o in opportunities if len(o.market_tickers) == 1]
        assert len(simple_arb) == 0


class TestCorrelationAnalyzer:
    """Tests for CorrelationAnalyzer."""

    def test_correlation_break_detected(self):
        """Test that correlation breaks are detected."""
        analyzer = CorrelationAnalyzer(config={"min_inconsistency_cents": 5})

        markets = [
            {
                "ticker": "CORR-1",
                "title": "Team A wins",
                "yes_price": 55,
                "event_ticker": "GAME-1",
            },
            {
                "ticker": "CORR-2",
                "title": "Team A wins by at least 10 points",
                "yes_price": 65,  # Inconsistent! Should be <= 55
                "event_ticker": "GAME-1",
            },
        ]

        opportunities = analyzer.analyze(markets)

        assert len(opportunities) >= 1
        assert opportunities[0].opportunity_type == OpportunityType.CORRELATION_BREAK

    def test_consistent_prices_ignored(self):
        """Test that consistent prices are not flagged."""
        analyzer = CorrelationAnalyzer()

        markets = [
            {
                "ticker": "CONS-1",
                "title": "Team A wins",
                "yes_price": 60,
                "event_ticker": "GAME-2",
            },
            {
                "ticker": "CONS-2",
                "title": "Team A wins by at least 10 points",
                "yes_price": 40,  # Consistent (subset <= superset)
                "event_ticker": "GAME-2",
            },
        ]

        opportunities = analyzer.analyze(markets)

        assert len(opportunities) == 0


class TestImbalanceAnalyzer:
    """Tests for ImbalanceAnalyzer."""

    def test_large_imbalance_detected(self):
        """Test that large orderbook imbalances are detected."""
        analyzer = ImbalanceAnalyzer(config={
            "min_imbalance_ratio": 3.0,
            "min_total_liquidity": 100,
        })

        markets = [
            {
                "ticker": "IMB-1",
                "title": "Market with imbalance",
                "yes_price": 55,
                "orderbook": {
                    "yes": [[55, 500]],  # 500 contracts
                    "no": [[45, 100]],   # 100 contracts (5:1 ratio!)
                },
            }
        ]

        opportunities = analyzer.analyze(markets)

        assert len(opportunities) == 1
        assert opportunities[0].opportunity_type == OpportunityType.IMBALANCE
        assert opportunities[0].additional_data["imbalance_ratio"] >= 3.0

    def test_balanced_market_ignored(self):
        """Test that balanced markets are ignored."""
        analyzer = ImbalanceAnalyzer(config={"min_imbalance_ratio": 3.0})

        markets = [
            {
                "ticker": "BALANCED",
                "title": "Balanced market",
                "yes_price": 50,
                "orderbook": {
                    "yes": [[50, 200]],
                    "no": [[50, 200]],  # Perfectly balanced
                },
            }
        ]

        opportunities = analyzer.analyze(markets)

        assert len(opportunities) == 0

    def test_low_liquidity_ignored(self):
        """Test that low liquidity markets are ignored."""
        analyzer = ImbalanceAnalyzer(config={
            "min_imbalance_ratio": 3.0,
            "min_total_liquidity": 100,
        })

        markets = [
            {
                "ticker": "LOW-LIQ",
                "title": "Low liquidity market",
                "yes_price": 50,
                "orderbook": {
                    "yes": [[50, 30]],  # Only 30 contracts
                    "no": [[50, 10]],   # Only 10 contracts (total = 40 < 100)
                },
            }
        ]

        opportunities = analyzer.analyze(markets)

        assert len(opportunities) == 0


# Fixtures for common test data
@pytest.fixture
def sample_market():
    """Sample market data for testing."""
    return {
        "ticker": "SAMPLE-2025-01-01",
        "title": "Sample Market",
        "yes_price": 50,
        "volume": 1000,
        "event_ticker": "SAMPLE-EVENT",
        "series_ticker": "SAMPLE",
        "orderbook": {
            "yes": [[50, 100], [49, 50]],
            "no": [[50, 100], [49, 50]],
        },
    }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
