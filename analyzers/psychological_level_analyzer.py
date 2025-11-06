"""
Psychological Level Analyzer

Exploits novice traders' behavioral biases around psychological price levels:
- Round number bias (25¢, 50¢, 75¢)
- "Lottery ticket" mispricing (1-5¢ appears cheap nominally)
- "Sure thing" trap (95-99¢ won't sell for fair value)
- 50¢ anchoring (uncertainty paralysis)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength


logger = logging.getLogger(__name__)


class PsychologicalLevelAnalyzer(BaseAnalyzer):
    """
    Analyzes markets for psychological pricing bias opportunities.

    Novice traders exhibit predictable behavioral biases:

    1. LOTTERY TICKET BIAS (1-5¢):
       - "It's only 2¢, might as well buy"
       - Ignore that 2¢ could represent 50:1 odds
       - Overvalue cheap nominal prices

    2. SURE THING TRAP (95-99¢):
       - Won't sell at 98¢ because "I want the full dollar"
       - Ignore that last 2¢ has huge opportunity cost
       - Overvalue certainty

    3. ROUND NUMBER CLUSTERING:
       - Orders cluster at 25¢, 50¢, 75¢
       - Prices "stick" near round numbers
       - Create predictable support/resistance

    4. 50¢ ANCHORING:
       - Maximum uncertainty = psychological resistance
       - Markets hover at 50¢ longer than justified
       - Novices paralyzed by indecision
    """

    def get_name(self) -> str:
        return "Psychological Level Analyzer"

    def get_description(self) -> str:
        return (
            "Exploits novice behavioral biases at psychological price levels: "
            "lottery tickets, sure things, round numbers, and 50¢ anchoring"
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            # Lottery ticket bias (low prices)
            "lottery_max_price": 0.05,  # 5¢
            "lottery_min_volume": 50,
            "lottery_implied_odds_threshold": 30.0,  # Flag if implied odds > 30:1

            # Sure thing trap (high prices)
            "sure_thing_min_price": 0.95,  # 95¢
            "sure_thing_min_volume": 100,
            "sure_thing_opportunity_cost_cents": 2.0,  # Value of last few cents

            # Round number clustering
            "round_numbers": [0.25, 0.50, 0.75],  # 25¢, 50¢, 75¢
            "round_number_tolerance": 0.02,  # ±2¢ from round number
            "round_min_volume": 75,
            "round_stickiness_hours": 6,  # How long price has been "stuck"

            # 50¢ anchoring (special case of round numbers)
            "anchor_center": 0.50,
            "anchor_tolerance": 0.05,  # 45-55¢ range
            "anchor_min_duration_hours": 12,  # How long at 50¢ to flag
            "anchor_min_volume": 100,

            # General thresholds for strength classification
            "hard_confidence_volume_multiplier": 2.0,
            "min_market_volume": 25,
        }

    def _setup(self) -> None:
        """Apply default config values."""
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for psychological level opportunities.

        Args:
            markets: List of market data dictionaries with orderbook data

        Returns:
            List of psychological bias opportunities
        """
        opportunities = []

        for market in markets:
            # Check all bias types
            lottery_opp = self._check_lottery_ticket_bias(market)
            if lottery_opp:
                opportunities.append(lottery_opp)
                continue  # Don't double-count same market

            sure_thing_opp = self._check_sure_thing_trap(market)
            if sure_thing_opp:
                opportunities.append(sure_thing_opp)
                continue

            round_number_opp = self._check_round_number_clustering(market)
            if round_number_opp:
                opportunities.append(round_number_opp)
                continue

            anchor_opp = self._check_50cent_anchoring(market)
            if anchor_opp:
                opportunities.append(anchor_opp)
                continue

        logger.info(
            f"PsychologicalLevelAnalyzer found {len(opportunities)} opportunities "
            f"out of {len(markets)} markets"
        )

        return opportunities

    def _check_lottery_ticket_bias(self, market: Dict[str, Any]) -> Optional[Opportunity]:
        """
        Detect lottery ticket bias: novices buying cheap nominal prices without
        understanding implied odds.
        """
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "Unknown Market")
        volume = market.get("volume", 0)

        if volume < self.config["lottery_min_volume"]:
            return None

        price = self._extract_reference_price(market)
        if price is None or price > self.config["lottery_max_price"]:
            return None

        # Calculate implied odds
        if price <= 0:
            return None
        implied_odds = (1.0 / price) - 1  # e.g., 0.02 = 49:1 odds

        if implied_odds < self.config["lottery_implied_odds_threshold"]:
            return None

        # This is a lottery ticket situation
        # High volume + low price + high implied odds = novices chasing lottery

        # Determine strength based on volume and odds
        strength = OpportunityStrength.SOFT
        if volume >= self.config["lottery_min_volume"] * self.config["hard_confidence_volume_multiplier"]:
            if implied_odds >= 50:
                strength = OpportunityStrength.HARD

        confidence = ConfidenceLevel.HIGH if implied_odds >= 50 else ConfidenceLevel.MEDIUM

        # Edge: these are often overpriced because novices think "cheap"
        # True fair value might be even lower
        estimated_edge_cents = min(price * 100 * 0.5, 2.0)  # Assume 50% overpriced, cap at 2¢
        estimated_edge_percent = 50.0

        reasoning = (
            f"LOTTERY TICKET BIAS: Price at {price*100:.1f}¢ implies {implied_odds:.0f}:1 odds. "
            f"Novices buying because it's 'cheap' nominally, but likely overpriced. "
            f"High volume ({volume}) confirms novice activity."
        )

        opportunity = Opportunity(
            opportunity_type=OpportunityType.MISPRICING,
            confidence=confidence,
            strength=strength,
            timestamp=datetime.now(),
            market_tickers=[ticker],
            market_titles=[title],
            market_urls=[self._make_market_url(ticker)],
            current_prices={ticker: price * 100},
            estimated_edge_cents=estimated_edge_cents,
            estimated_edge_percent=estimated_edge_percent,
            reasoning=reasoning,
            additional_data={
                "price_cents": round(price * 100, 1),
                "implied_odds": round(implied_odds, 1),
                "bias_type": "lottery_ticket",
                "exploit_type": "nominal_price_illusion",
            },
        )

        logger.info(
            f"[PSYCH-LOTTERY] {ticker}: {price*100:.1f}¢ ({implied_odds:.0f}:1 odds), "
            f"volume={volume} (Strength: {strength.value})"
        )

        return opportunity

    def _check_sure_thing_trap(self, market: Dict[str, Any]) -> Optional[Opportunity]:
        """
        Detect sure thing trap: novices holding 95-99¢ positions refusing to sell
        for fair value because they "want the full dollar."
        """
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "Unknown Market")
        volume = market.get("volume", 0)

        if volume < self.config["sure_thing_min_volume"]:
            return None

        price = self._extract_reference_price(market)
        if price is None or price < self.config["sure_thing_min_price"]:
            return None

        # This is a "sure thing" situation
        # Novices are holding expensive positions, refusing to sell

        # Calculate opportunity cost
        gap_to_dollar = (1.0 - price) * 100  # In cents
        opportunity_cost = self.config["sure_thing_opportunity_cost_cents"]

        # Determine strength
        strength = OpportunityStrength.SOFT
        if volume >= self.config["sure_thing_min_volume"] * 1.5 and price >= 0.97:
            strength = OpportunityStrength.HARD

        confidence = ConfidenceLevel.HIGH if price >= 0.97 else ConfidenceLevel.MEDIUM

        # Edge: ability to buy at slightly lower price or sell at premium
        estimated_edge_cents = min(gap_to_dollar * 0.5, 3.0)  # Cap at 3¢
        estimated_edge_percent = (estimated_edge_cents / (price * 100)) * 100

        reasoning = (
            f"SURE THING TRAP: Price at {price*100:.1f}¢ (gap to $1: {gap_to_dollar:.1f}¢). "
            f"Novices holding because they 'want the full dollar' but ignoring "
            f"opportunity cost. Could offer liquidity at discount or exploit stickiness."
        )

        opportunity = Opportunity(
            opportunity_type=OpportunityType.MISPRICING,
            confidence=confidence,
            strength=strength,
            timestamp=datetime.now(),
            market_tickers=[ticker],
            market_titles=[title],
            market_urls=[self._make_market_url(ticker)],
            current_prices={ticker: price * 100},
            estimated_edge_cents=estimated_edge_cents,
            estimated_edge_percent=estimated_edge_percent,
            reasoning=reasoning,
            additional_data={
                "price_cents": round(price * 100, 1),
                "gap_to_dollar_cents": round(gap_to_dollar, 2),
                "bias_type": "sure_thing_trap",
                "exploit_type": "certainty_overvaluation",
            },
        )

        logger.info(
            f"[PSYCH-SURE] {ticker}: {price*100:.1f}¢ (gap: {gap_to_dollar:.1f}¢), "
            f"volume={volume} (Strength: {strength.value})"
        )

        return opportunity

    def _check_round_number_clustering(self, market: Dict[str, Any]) -> Optional[Opportunity]:
        """
        Detect round number clustering: prices sticking near 25¢, 50¢, 75¢.
        """
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "Unknown Market")
        volume = market.get("volume", 0)

        if volume < self.config["round_min_volume"]:
            return None

        price = self._extract_reference_price(market)
        if price is None:
            return None

        # Check if near any round number (excluding 50¢, handled separately)
        round_numbers = [rn for rn in self.config["round_numbers"] if abs(rn - 0.50) > 0.01]
        nearest_round = None
        min_distance = float('inf')

        for rn in round_numbers:
            distance = abs(price - rn)
            if distance < min_distance:
                min_distance = distance
                nearest_round = rn

        if min_distance > self.config["round_number_tolerance"]:
            return None

        # Check if price has been stuck near this level
        candlesticks = self._fetch_market_candlesticks(
            market,
            lookback_hours=self.config["round_stickiness_hours"],
            period_interval=60
        )

        stickiness_confirmed = False
        if candlesticks and len(candlesticks) >= 2:
            prices = self._extract_prices_from_candlesticks(candlesticks, "yes_ask_close")
            if prices:
                prices_fraction = [p / 100.0 for p in prices]
                # Check if most recent prices are near this round number
                near_count = sum(1 for p in prices_fraction
                               if abs(p - nearest_round) <= self.config["round_number_tolerance"])
                if near_count >= len(prices_fraction) * 0.6:  # 60% of time near round number
                    stickiness_confirmed = True

        if not stickiness_confirmed:
            return None

        # Detected round number clustering
        strength = OpportunityStrength.SOFT
        if volume >= self.config["round_min_volume"] * 2:
            strength = OpportunityStrength.HARD

        confidence = ConfidenceLevel.MEDIUM

        estimated_edge_cents = 2.0  # Moderate edge from exploiting clustering
        estimated_edge_percent = (estimated_edge_cents / (price * 100)) * 100

        reasoning = (
            f"ROUND NUMBER CLUSTERING: Price stuck near {nearest_round*100:.0f}¢ "
            f"(current: {price*100:.1f}¢). Novices anchor on round numbers creating "
            f"predictable support/resistance. Can exploit breakout or continue providing liquidity."
        )

        opportunity = Opportunity(
            opportunity_type=OpportunityType.MISPRICING,
            confidence=confidence,
            strength=strength,
            timestamp=datetime.now(),
            market_tickers=[ticker],
            market_titles=[title],
            market_urls=[self._make_market_url(ticker)],
            current_prices={ticker: price * 100},
            estimated_edge_cents=estimated_edge_cents,
            estimated_edge_percent=estimated_edge_percent,
            reasoning=reasoning,
            additional_data={
                "price_cents": round(price * 100, 1),
                "round_number_cents": round(nearest_round * 100, 0),
                "distance_cents": round(min_distance * 100, 1),
                "bias_type": "round_number_clustering",
                "exploit_type": "psychological_anchoring",
            },
        )

        logger.info(
            f"[PSYCH-ROUND] {ticker}: Stuck at {nearest_round*100:.0f}¢ "
            f"(Strength: {strength.value})"
        )

        return opportunity

    def _check_50cent_anchoring(self, market: Dict[str, Any]) -> Optional[Opportunity]:
        """
        Detect 50¢ anchoring: maximum uncertainty paralyzes novices.
        """
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "Unknown Market")
        volume = market.get("volume", 0)

        if volume < self.config["anchor_min_volume"]:
            return None

        price = self._extract_reference_price(market)
        if price is None:
            return None

        # Check if in the 50¢ zone
        distance_from_50 = abs(price - self.config["anchor_center"])
        if distance_from_50 > self.config["anchor_tolerance"]:
            return None

        # Check duration at this level
        candlesticks = self._fetch_market_candlesticks(
            market,
            lookback_hours=self.config["anchor_min_duration_hours"],
            period_interval=60
        )

        duration_confirmed = False
        if candlesticks and len(candlesticks) >= self.config["anchor_min_duration_hours"] // 2:
            prices = self._extract_prices_from_candlesticks(candlesticks, "yes_ask_close")
            if prices:
                prices_fraction = [p / 100.0 for p in prices]
                # Check if consistently near 50¢
                anchor_count = sum(1 for p in prices_fraction
                                  if abs(p - 0.50) <= self.config["anchor_tolerance"])
                if anchor_count >= len(prices_fraction) * 0.7:  # 70% of time near 50¢
                    duration_confirmed = True

        if not duration_confirmed:
            return None

        # Detected 50¢ anchoring
        strength = OpportunityStrength.HARD if volume >= self.config["anchor_min_volume"] * 1.5 else OpportunityStrength.SOFT
        confidence = ConfidenceLevel.HIGH

        estimated_edge_cents = 3.0
        estimated_edge_percent = (estimated_edge_cents / (price * 100)) * 100

        reasoning = (
            f"50¢ ANCHORING: Price hovering at {price*100:.1f}¢ for extended period. "
            f"Maximum uncertainty creates paralysis among novices. High volume ({volume}) "
            f"confirms indecision. Opportunity to take informed directional position or "
            f"provide liquidity as market eventually resolves."
        )

        opportunity = Opportunity(
            opportunity_type=OpportunityType.MISPRICING,
            confidence=confidence,
            strength=strength,
            timestamp=datetime.now(),
            market_tickers=[ticker],
            market_titles=[title],
            market_urls=[self._make_market_url(ticker)],
            current_prices={ticker: price * 100},
            estimated_edge_cents=estimated_edge_cents,
            estimated_edge_percent=estimated_edge_percent,
            reasoning=reasoning,
            additional_data={
                "price_cents": round(price * 100, 1),
                "distance_from_50_cents": round(distance_from_50 * 100, 1),
                "bias_type": "50cent_anchoring",
                "exploit_type": "uncertainty_paralysis",
            },
        )

        logger.info(
            f"[PSYCH-50] {ticker}: Anchored at {price*100:.1f}¢, volume={volume} "
            f"(Strength: {strength.value})"
        )

        return opportunity

    def _extract_reference_price(self, market: Dict[str, Any]) -> Optional[float]:
        """
        Extract a reference price from market data.
        Returns price as a fraction (0.0 to 1.0), not cents.
        """
        # Try direct price fields from market (these are in cents)
        for field in ["last_price", "yes_bid"]:
            value = market.get(field)
            if value is not None:
                return float(value) / 100.0

        # Try orderbook
        orderbook = market.get("orderbook", {})
        yes_bids = orderbook.get("yes") or []
        yes_asks = orderbook.get("no") or []

        if yes_bids and yes_asks:
            best_bid = yes_bids[0][0] if yes_bids else None
            best_ask = 100 - yes_asks[0][0] if yes_asks else None

            if best_bid is not None and best_ask is not None:
                mid_price_cents = (best_bid + best_ask) / 2.0
                return mid_price_cents / 100.0

        return None


if __name__ == "__main__":
    # Simple test
    logging.basicConfig(level=logging.INFO)

    analyzer = PsychologicalLevelAnalyzer()
    print(f"Analyzer: {analyzer.get_name()}")
    print(f"Description: {analyzer.get_description()}")
    print(f"Config: {analyzer.config}")
