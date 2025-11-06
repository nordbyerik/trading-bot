"""
Theta Decay Analyzer

Identifies markets near expiration with prices that remain far from 0 or 1.
These represent potential opportunities where the market hasn't converged
to a clear outcome despite being close to resolution.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength


logger = logging.getLogger(__name__)


class ThetaDecayAnalyzer(BaseAnalyzer):
    """
    Analyzes markets approaching expiration for slow theta decay.

    Theta decay refers to the tendency of prediction market prices to converge
    toward 0 or 1 as expiration approaches. Markets that haven't converged
    may represent:
    - Genuine uncertainty about the outcome
    - Market inefficiency or mispricing
    - Potential arbitrage opportunities
    """

    def get_name(self) -> str:
        return "Theta Decay Analyzer"

    def get_description(self) -> str:
        return (
            "Identifies markets near expiration with prices far from 0 or 1, "
            "indicating slow theta decay and potential inefficiencies"
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            # Hard opportunity thresholds (strict requirements)
            "hard_hours_to_expiration": 24.0,  # Look at markets expiring within N hours for hard
            "hard_price_tolerance": 0.15,  # Distance from 0 or 1 (15 cents) for hard
            # Soft opportunity thresholds (relaxed requirements)
            "soft_hours_to_expiration": 48.0,  # Look at markets expiring within N hours for soft
            "soft_price_tolerance": 0.20,  # Distance from 0 or 1 (20 cents) for soft
            "min_hours_remaining": 1.0,  # Don't flag markets too close to expiration

            # Novice exploitation settings
            "panic_zone_hours": 6.0,  # Final hours where novices panic sell/buy
            "panic_multiplier": 2.0,  # Edge multiplier in panic zone
            "dead_cat_bounce_threshold": 0.10,  # Detect 10%+ moves in final hours
        }

    def _setup(self) -> None:
        """Apply default config values."""
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for slow theta decay.

        Args:
            markets: List of market data dictionaries with orderbook data

        Returns:
            List of theta decay opportunities
        """
        opportunities = []
        now = datetime.now(timezone.utc)

        for market in markets:
            opportunity = self._analyze_single_market(market, now)
            if opportunity:
                opportunities.append(opportunity)

        logger.info(
            f"ThetaDecayAnalyzer found {len(opportunities)} opportunities "
            f"out of {len(markets)} markets"
        )

        return opportunities

    def _analyze_single_market(
        self, market: Dict[str, Any], now: datetime
    ) -> Optional[Opportunity]:
        """Analyze a single market for theta decay opportunities."""
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "Unknown Market")

        # Extract expiration time
        # Try close_time first (when trading stops), then expiration_time
        expiration_str = market.get("close_time") or market.get("expiration_time")
        if not expiration_str:
            logger.debug(f"[THETA] {ticker}: No expiration time available")
            return None

        # Parse the expiration time
        expiration = self._parse_datetime(expiration_str)
        if not expiration:
            logger.debug(f"[THETA] {ticker}: Could not parse expiration time: {expiration_str}")
            return None

        # Calculate hours remaining
        hours_remaining = (expiration - now).total_seconds() / 3600.0

        # Skip if already expired
        if hours_remaining < 0:
            logger.debug(f"[THETA] {ticker}: Market already expired")
            return None

        # Skip if too close to expiration (last-minute volatility)
        if hours_remaining < self.config["min_hours_remaining"]:
            logger.debug(
                f"[THETA] {ticker}: Too close to expiration "
                f"({hours_remaining:.1f}h < {self.config['min_hours_remaining']}h min)"
            )
            return None

        # Get reference price
        price = self._extract_reference_price(market)
        if price is None:
            logger.debug(f"[THETA] {ticker}: No price available")
            return None

        # Determine opportunity strength (HARD or SOFT) based on time and price tolerance
        strength = None
        tolerance = None

        # Check hard thresholds first
        hard_hours = self.config["hard_hours_to_expiration"]
        hard_tolerance = self.config["hard_price_tolerance"]

        if hours_remaining <= hard_hours:
            tolerance = hard_tolerance
            lower_threshold = tolerance
            upper_threshold = 1.0 - tolerance

            # Only flag if price is in the "uncertain" middle range
            if lower_threshold <= price <= upper_threshold:
                strength = OpportunityStrength.HARD

        # Check soft thresholds if not hard
        if strength is None:
            soft_hours = self.config["soft_hours_to_expiration"]
            soft_tolerance = self.config["soft_price_tolerance"]

            if hours_remaining <= soft_hours:
                tolerance = soft_tolerance
                lower_threshold = tolerance
                upper_threshold = 1.0 - tolerance

                # Only flag if price is in the "uncertain" middle range
                if lower_threshold <= price <= upper_threshold:
                    strength = OpportunityStrength.SOFT

        # Log the calculated metrics for this market
        logger.info(
            f"[THETA] {ticker}: hours_remaining={hours_remaining:.1f}h, "
            f"price={price:.2f} ({price*100:.0f}¢), distance_from_certainty={min(price, 1.0 - price):.2f}"
        )

        # If doesn't meet either threshold
        if strength is None or tolerance is None:
            logger.info(
                f"[THETA] {ticker}: Not within time windows or price in converged range "
                f"(hours_remaining={hours_remaining:.1f}h, hard_window={self.config['hard_hours_to_expiration']}h, "
                f"soft_window={self.config['soft_hours_to_expiration']}h)"
            )
            return None

        # Calculate distance from nearest boundary (0 or 1)
        distance_from_certainty = min(price, 1.0 - price)

        # Check if we're in the panic zone (final hours where novices make mistakes)
        in_panic_zone = hours_remaining <= self.config["panic_zone_hours"]

        # Try to detect "dead cat bounce" - sudden moves against theta decay trend
        dead_cat_bounce = self._detect_dead_cat_bounce(market, price, hours_remaining)

        # Determine confidence based on time remaining and price
        # Less time + more uncertain price = higher confidence opportunity
        confidence = self._calculate_confidence(
            hours_remaining, distance_from_certainty, in_panic_zone, dead_cat_bounce
        )

        # Calculate estimated edge
        # The edge is based on the assumption that the price should converge
        # The further from convergence with less time, the bigger the potential edge
        # ENHANCED: Apply panic multiplier if in panic zone
        estimated_edge_cents = self._calculate_edge(
            price, hours_remaining, distance_from_certainty, in_panic_zone
        )

        # Calculate as percentage
        estimated_edge_percent = (
            (estimated_edge_cents / (price * 100)) * 100 if price > 0 else 0
        )

        # Create reasoning with novice behavior context
        reasoning_parts = [
            f"Market expires in {hours_remaining:.1f}h but price is {price:.2f} "
            f"(distance from certainty: {distance_from_certainty:.2f})."
        ]

        if in_panic_zone:
            reasoning_parts.append(
                "IN PANIC ZONE: Novices likely to make irrational decisions in final hours."
            )

        if dead_cat_bounce:
            reasoning_parts.append(
                "DEAD CAT BOUNCE detected: Recent spike against theta decay trend - "
                "exploit novice overreaction."
            )

        reasoning_parts.append("Slow theta decay suggests mispricing opportunity.")
        reasoning = " ".join(reasoning_parts)

        # Build opportunity
        opportunity = Opportunity(
            opportunity_type=OpportunityType.MISPRICING,  # Using MISPRICING as closest match
            confidence=confidence,
            strength=strength,
            timestamp=datetime.now(),
            market_tickers=[ticker],
            market_titles=[title],
            market_urls=[self._make_market_url(ticker)],
            current_prices={
                ticker: price * 100,  # Convert to cents
            },
            estimated_edge_cents=estimated_edge_cents,
            estimated_edge_percent=estimated_edge_percent,
            reasoning=reasoning,
            additional_data={
                "hours_remaining": round(hours_remaining, 2),
                "expiration_time": expiration.isoformat(),
                "distance_from_certainty": round(distance_from_certainty, 4),
                "tolerance": tolerance,
                "in_panic_zone": in_panic_zone,
                "dead_cat_bounce": dead_cat_bounce,
                "analysis_type": "theta_decay",
                "exploit_type": "novice_time_decay_misunderstanding",
            },
        )

        return opportunity

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        """Parse ISO 8601 datetime string to timezone-aware datetime."""
        if not value:
            return None
        try:
            # Handle 'Z' timezone indicator
            if value.endswith("Z"):
                value = value.replace("Z", "+00:00")
            return datetime.fromisoformat(value).astimezone(timezone.utc)
        except (ValueError, AttributeError):
            return None

    def _extract_reference_price(self, market: Dict[str, Any]) -> Optional[float]:
        """
        Extract a reference price from market data.

        Tries multiple sources in order of preference:
        1. last_price from market
        2. yes_bid from market
        3. Mid-price from orderbook

        Returns price as a fraction (0.0 to 1.0), not cents.
        """
        # Try direct price fields from market (these are in cents)
        for field in ["last_price", "yes_bid"]:
            value = market.get(field)
            if value is not None:
                # Convert from cents to fraction
                return float(value) / 100.0

        # Try orderbook if available
        orderbook = market.get("orderbook", {})
        yes_bids = orderbook.get("yes") or []
        yes_asks = orderbook.get("no") or []  # Note: "no" side acts like asks for yes

        if yes_bids and yes_asks:
            # Get best bid and ask (first in each list, already sorted)
            best_bid = yes_bids[0][0] if yes_bids else None
            best_ask = 100 - yes_asks[0][0] if yes_asks else None  # no bid = 100 - yes ask

            if best_bid is not None and best_ask is not None:
                # Calculate mid-price in cents, then convert to fraction
                mid_price_cents = (best_bid + best_ask) / 2.0
                return mid_price_cents / 100.0

        return None

    def _calculate_confidence(
        self,
        hours_remaining: float,
        distance_from_certainty: float,
        in_panic_zone: bool,
        dead_cat_bounce: bool
    ) -> ConfidenceLevel:
        """
        Calculate confidence level based on time and price.

        Less time + more uncertainty = higher confidence
        ENHANCED: Panic zone and dead cat bounce boost confidence
        """
        # Score based on urgency (less time = higher score)
        # EXPONENTIAL urgency in final hours
        if hours_remaining < 3:
            time_score = 4  # Extreme urgency
        elif hours_remaining < 6:
            time_score = 3
        elif hours_remaining < 12:
            time_score = 2
        else:
            time_score = 1

        # Score based on price uncertainty (further from 0/1 = higher score)
        if distance_from_certainty > 0.3:
            price_score = 3
        elif distance_from_certainty > 0.2:
            price_score = 2
        else:
            price_score = 1

        total_score = time_score + price_score

        # Boost for novice exploitation signals
        if in_panic_zone:
            total_score += 1  # Novices panic in final hours

        if dead_cat_bounce:
            total_score += 1  # Irrational spike before expiration

        # Map combined score to confidence level
        if total_score >= 6:
            return ConfidenceLevel.HIGH
        elif total_score >= 4:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW

    def _calculate_edge(
        self,
        price: float,
        hours_remaining: float,
        distance_from_certainty: float,
        in_panic_zone: bool
    ) -> float:
        """
        Calculate estimated edge in cents.

        This is a heuristic based on expected convergence.
        ENHANCED: Exponential urgency and panic zone multiplier
        """
        # Base edge is the distance from certainty
        # The assumption is that the price should eventually converge
        base_edge = distance_from_certainty * 100  # Convert to cents

        # Scale by urgency (less time = bigger edge if it converges)
        # EXPONENTIAL in final hours when novices panic
        if hours_remaining < 3:
            urgency_multiplier = 2.0  # Extreme urgency
        elif hours_remaining < 6:
            urgency_multiplier = 1.5
        elif hours_remaining < 12:
            urgency_multiplier = 1.2
        else:
            urgency_multiplier = 1.0

        edge = base_edge * urgency_multiplier

        # Apply panic multiplier if in panic zone
        if in_panic_zone:
            edge *= self.config["panic_multiplier"]

        return edge

    def _detect_dead_cat_bounce(
        self, market: Dict[str, Any], current_price: float, hours_remaining: float
    ) -> bool:
        """
        Detect if market is experiencing a "dead cat bounce" - an irrational spike
        against the theta decay trend in final hours.

        Novices often create short-lived price spikes before expiration due to:
        - Last-minute news overreaction
        - FOMO buying
        - Panic selling that gets bought up

        Returns True if dead cat bounce detected, False otherwise.
        """
        # Only check if close to expiration
        if hours_remaining > 12:
            return False

        # Fetch recent price history
        candlesticks = self._fetch_market_candlesticks(
            market,
            lookback_hours=min(24, int(hours_remaining) + 6),
            period_interval=60  # 1-hour candles
        )

        if not candlesticks or len(candlesticks) < 3:
            return False

        prices = self._extract_prices_from_candlesticks(candlesticks, "yes_ask_close")

        if not prices or len(prices) < 3:
            return False

        # Convert to fractions
        prices = [p / 100.0 for p in prices]

        # Check if recent price moved significantly against expected theta decay
        # Expected: price should be converging to 0 or 1
        # Dead cat bounce: price moved AWAY from nearest boundary

        older_price = prices[-3]  # 2 hours ago
        recent_price = prices[-1]  # Current

        # Determine which boundary (0 or 1) price should converge to
        target_boundary = 0.0 if older_price < 0.5 else 1.0

        # Calculate distances
        older_distance = abs(older_price - target_boundary)
        recent_distance = abs(recent_price - target_boundary)

        # Dead cat bounce: recent distance increased (moved away from convergence)
        distance_increase = recent_distance - older_distance
        distance_increase_pct = (distance_increase / older_distance * 100) if older_distance > 0 else 0

        # Flag as dead cat bounce if moved away by threshold amount
        if distance_increase_pct >= self.config["dead_cat_bounce_threshold"] * 100:
            logger.info(
                f"[THETA-DCB] {market.get('ticker')}: Dead cat bounce detected! "
                f"Moved {distance_increase_pct:.1f}% away from convergence target"
            )
            return True

        return False


if __name__ == "__main__":
    # Simple test with mock data
    logging.basicConfig(level=logging.INFO)

    now = datetime.now(timezone.utc)

    # Create a datetime 8 hours in the future
    from datetime import timedelta
    expiration_time = now + timedelta(hours=8)
    expiration_str = expiration_time.isoformat()

    # Mock market data
    mock_markets = [
        {
            "ticker": "TEST-THETA-01",
            "title": "Test market with slow theta decay",
            "close_time": expiration_str,
            "last_price": 45,  # 45 cents - very uncertain with only 8 hours left
            "volume": 1000,
            "orderbook": {
                "yes": [[44, 100], [42, 50]],
                "no": [[54, 100], [52, 50]],
            },
        },
        {
            "ticker": "TEST-THETA-02",
            "title": "Test market with normal theta decay",
            "close_time": expiration_str,
            "last_price": 95,  # 95 cents - already converged
            "volume": 5000,
            "orderbook": {
                "yes": [[94, 200]],
                "no": [[4, 200]],
            },
        },
    ]

    analyzer = ThetaDecayAnalyzer()
    opportunities = analyzer.analyze(mock_markets)

    print(f"\nFound {len(opportunities)} opportunities:\n")
    for opp in opportunities:
        print(opp)
        print(f"  Additional data: {opp.additional_data}\n")
