"""
Hype/FOMO Detector

Detects when markets are driven by hype and FOMO rather than fundamentals.
More sophisticated than Event Volatility analyzer - specifically targets irrational
pricing driven by crowd psychology.

Key signals:
- Sudden volume spikes (3x+ average) indicating retail FOMO
- Prices that defy base rates (low probability events priced too high)
- Price stagnation after spike (hype exhaustion)
- Extreme price moves without fundamental justification

Strategy: Fade the hype after detecting stagnation
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import statistics

from .base import BaseAnalyzer, Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength
from trade_manager import Side


logger = logging.getLogger(__name__)


class HypeFomoDetector(BaseAnalyzer):
    """
    Analyzes markets for hype-driven mispricing opportunities.

    Exploits novice behavior:
    - FOMO buying on trending topics
    - Overreaction to sensational headlines
    - Ignoring base rates and probabilities
    - Following the crowd without fundamental analysis

    This is more sophisticated than Event Volatility analyzer because it:
    1. Checks for price irrationality (against base rates)
    2. Requires stagnation after spike (hype exhaustion)
    3. Uses multiple signals to confirm hype vs informed flow
    4. Provides specific fade recommendations
    """

    def get_name(self) -> str:
        return "Hype/FOMO Detector"

    def get_description(self) -> str:
        return (
            "Detects markets driven by hype rather than fundamentals. "
            "Identifies FOMO-driven volume spikes and irrational pricing for fade opportunities."
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            # Hard opportunity thresholds (very high confidence)
            "hard_min_volume_spike": 3.5,  # 3.5x average volume = extreme FOMO
            "hard_min_price_change": 15.0,  # 15% move in lookback period
            "hard_max_stagnation": 0.03,  # < 3% movement after spike (hype exhausted)
            "hard_lookback_hours": 24,

            # Soft opportunity thresholds (moderate confidence)
            "soft_min_volume_spike": 2.5,  # 2.5x average volume
            "soft_min_price_change": 10.0,  # 10% move
            "soft_max_stagnation": 0.05,  # < 5% movement after spike
            "soft_lookback_hours": 48,

            # Irrationality detection
            "extreme_low_threshold": 10,  # Prices below 10¢ are suspicious if spiking
            "extreme_high_threshold": 90,  # Prices above 90¢ are suspicious if spiking
            "base_rate_deviation_bonus": 5.0,  # Extra edge for base rate violations

            # General settings
            "min_volume": 100,  # Minimum absolute volume
            "stagnation_window_hours": 6,  # Check last N hours for stagnation
            "exclude_near_expiration_hours": 8,  # Don't flag markets about to expire
            "min_data_points": 8,  # Need sufficient history
        }

    def _setup(self) -> None:
        """Apply default config values."""
        defaults = self.get_default_config()
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value

    def analyze(self, markets: List[Dict[str, Any]]) -> List[Opportunity]:
        """
        Analyze markets for hype/FOMO opportunities.

        Args:
            markets: List of market data dictionaries

        Returns:
            List of hype/FOMO fade opportunities
        """
        opportunities = []
        now = datetime.now(timezone.utc)

        for market in markets:
            opportunity = self._analyze_single_market(market, now)
            if opportunity:
                opportunities.append(opportunity)

        logger.info(
            f"HypeFomoDetector found {len(opportunities)} opportunities "
            f"out of {len(markets)} markets"
        )

        return opportunities

    def _analyze_single_market(
        self, market: Dict[str, Any], now: datetime
    ) -> Optional[Opportunity]:
        """Analyze a single market for hype/FOMO signals."""
        ticker = market.get("ticker", "UNKNOWN")
        title = market.get("title", "Unknown Market")
        last_price = market.get("last_price", 0)
        volume = market.get("volume", 0)

        # Check minimum volume
        if volume < self.config["min_volume"]:
            return None

        # Check if too close to expiration (natural convergence, not hype)
        expiration_str = market.get("close_time") or market.get("expiration_time")
        if expiration_str:
            expiration = self._parse_datetime(expiration_str)
            if expiration:
                hours_remaining = (expiration - now).total_seconds() / 3600.0
                if 0 < hours_remaining < self.config["exclude_near_expiration_hours"]:
                    return None

        # Try HARD thresholds first
        hard_result = self._detect_hype_fomo(
            market=market,
            lookback_hours=self.config["hard_lookback_hours"],
            min_volume_spike=self.config["hard_min_volume_spike"],
            min_price_change=self.config["hard_min_price_change"],
            max_stagnation=self.config["hard_max_stagnation"]
        )

        if hard_result:
            strength = OpportunityStrength.HARD
            result = hard_result
        else:
            # Try SOFT thresholds
            soft_result = self._detect_hype_fomo(
                market=market,
                lookback_hours=self.config["soft_lookback_hours"],
                min_volume_spike=self.config["soft_min_volume_spike"],
                min_price_change=self.config["soft_min_price_change"],
                max_stagnation=self.config["soft_max_stagnation"]
            )

            if soft_result:
                strength = OpportunityStrength.SOFT
                result = soft_result
            else:
                return None

        # Extract result data
        volume_spike = result["volume_spike"]
        price_change_pct = result["price_change_pct"]
        stagnation = result["stagnation"]
        current_price = result["current_price"]
        direction = result["direction"]
        is_irrational = result["is_irrational"]

        # Calculate confidence
        confidence = self._calculate_confidence(
            volume_spike, price_change_pct, stagnation, is_irrational
        )

        # Determine recommended side (fade the hype)
        if direction == "up":
            # Price spiked up on hype -> fade by selling (NO)
            side = Side.NO
            edge_from_reversal = (current_price * 100) - 50  # Expected reversion toward 50
        else:
            # Price dropped on panic -> fade by buying (YES)
            side = Side.YES
            edge_from_reversal = 50 - (current_price * 100)

        # Calculate edge
        estimated_edge_cents = self._calculate_edge(
            price_change_pct, volume_spike, stagnation, is_irrational
        )

        # Add base rate deviation bonus if irrational
        if is_irrational:
            estimated_edge_cents += self.config["base_rate_deviation_bonus"]

        # Calculate edge percent
        cost = current_price * 100 if side == Side.YES else (100 - current_price * 100)
        estimated_edge_percent = (estimated_edge_cents / cost * 100) if cost > 0 else 0

        # Build reasoning
        irrationality_note = ""
        if is_irrational:
            if current_price < 0.15:
                irrationality_note = " Price at extreme low despite hype spike - irrational pessimism or unlikely event overpriced."
            elif current_price > 0.85:
                irrationality_note = " Price at extreme high - likely FOMO-driven overconfidence."
            else:
                irrationality_note = " Price movement appears disconnected from fundamentals."

        reasoning = (
            f"HYPE/FOMO detected: {volume_spike:.1f}x volume spike with {price_change_pct:.1f}% "
            f"{direction}ward move. Price now stagnated ({stagnation*100:.1f}% movement in recent hours), "
            f"indicating hype exhaustion.{irrationality_note} "
            f"Recommended: Fade the {direction}ward move by taking {side.name} position."
        )

        # Get orderbook for pricing
        orderbook = market.get("orderbook", {})
        yes_bids = orderbook.get("yes", [])
        no_bids = orderbook.get("no", [])

        yes_bid = yes_bids[0][0] if yes_bids else last_price
        no_bid = no_bids[0][0] if no_bids else (100 - last_price)

        opportunity = Opportunity(
            opportunity_type=OpportunityType.MOMENTUM_FADE,
            confidence=confidence,
            strength=strength,
            timestamp=datetime.now(),
            market_tickers=[ticker],
            market_titles=[title],
            market_urls=[self._make_market_url(ticker)],
            current_prices={
                f"{ticker}_last": current_price * 100,
                f"{ticker}_yes_bid": yes_bid,
                f"{ticker}_no_bid": no_bid,
            },
            estimated_edge_cents=estimated_edge_cents,
            estimated_edge_percent=estimated_edge_percent,
            reasoning=reasoning,
            additional_data={
                "volume_spike": round(volume_spike, 2),
                "price_change_pct": round(price_change_pct, 2),
                "stagnation_pct": round(stagnation * 100, 2),
                "direction": direction,
                "is_irrational": is_irrational,
                "current_price": round(current_price, 4),
                "recommended_side": side.value,
                "strategy": "fade_hype",
                "analysis_type": "hype_fomo",
            },
        )

        logger.info(
            f"[HYPE/FOMO] {ticker}: {volume_spike:.1f}x vol, {price_change_pct:.1f}% {direction}, "
            f"{stagnation*100:.1f}% stagnation, irrational={is_irrational} (Strength: {strength.value})"
        )

        return opportunity

    def _detect_hype_fomo(
        self,
        market: Dict[str, Any],
        lookback_hours: int,
        min_volume_spike: float,
        min_price_change: float,
        max_stagnation: float
    ) -> Optional[Dict[str, Any]]:
        """
        Detect hype/FOMO patterns in market data.

        Returns analysis dict if pattern found, None otherwise.
        """
        ticker = market.get("ticker")

        # Fetch historical candlesticks
        candlesticks = self._fetch_market_candlesticks(
            market,
            lookback_hours=lookback_hours,
            period_interval=60  # 1-hour candles
        )

        if not candlesticks or len(candlesticks) < self.config["min_data_points"]:
            return None

        # Extract prices and volumes
        prices = self._extract_prices_from_candlesticks(candlesticks, "yes_ask_close")
        volumes = self._extract_volumes_from_candlesticks(candlesticks)

        if not prices or not volumes or len(prices) < self.config["min_data_points"]:
            return None

        # Convert prices to fractions
        prices = [p / 100.0 for p in prices]
        current_price = prices[-1]

        # 1. Check for volume spike
        volume_spike = self._calculate_volume_spike(volumes)
        if volume_spike < min_volume_spike:
            return None

        # 2. Check for significant price change
        price_start = prices[0]
        price_change = abs(current_price - price_start)
        price_change_pct = (price_change / price_start * 100) if price_start > 0 else 0

        if price_change_pct < min_price_change:
            return None

        # Determine direction
        direction = "up" if current_price > price_start else "down"

        # 3. Check for stagnation (hype exhaustion)
        stagnation_window = min(
            self.config["stagnation_window_hours"],
            len(prices) // 2  # Don't use more than half the data for stagnation check
        )
        stagnation = self._calculate_stagnation(prices, stagnation_window)

        if stagnation > max_stagnation:
            # Still moving too much, hype not exhausted
            return None

        # 4. Check for irrationality (price at extreme levels)
        is_irrational = self._check_price_irrationality(current_price * 100, direction)

        return {
            "volume_spike": volume_spike,
            "price_change_pct": price_change_pct,
            "stagnation": stagnation,
            "current_price": current_price,
            "direction": direction,
            "is_irrational": is_irrational,
        }

    def _calculate_volume_spike(self, volumes: List[float]) -> float:
        """
        Calculate volume spike ratio.

        Compares recent volume to historical average.
        """
        if len(volumes) < 4:
            return 1.0

        # Recent volume = last 2 periods
        recent_volume = sum(volumes[-2:]) / 2

        # Historical average = all except last 2 periods
        historical_volume = sum(volumes[:-2]) / len(volumes[:-2])

        if historical_volume == 0:
            return 1.0

        return recent_volume / historical_volume

    def _calculate_stagnation(self, prices: List[float], window: int) -> float:
        """
        Calculate price stagnation in recent window.

        Returns fraction of price movement (lower = more stagnated).
        """
        if len(prices) < window + 1:
            window = len(prices) - 1

        if window < 2:
            return 1.0  # Not enough data

        recent_prices = prices[-window:]
        recent_start = recent_prices[0]
        recent_end = recent_prices[-1]

        if recent_start == 0:
            return 1.0

        movement = abs(recent_end - recent_start) / recent_start
        return movement

    def _check_price_irrationality(self, price_cents: float, direction: str) -> bool:
        """
        Check if price is at irrational levels given the move direction.

        Irrational = price at extremes that defy base rates
        """
        # Upward hype spike to extreme high
        if direction == "up" and price_cents > self.config["extreme_high_threshold"]:
            return True

        # Downward panic to extreme low (or upward spike on low-prob event)
        if price_cents < self.config["extreme_low_threshold"]:
            return True

        return False

    def _calculate_confidence(
        self,
        volume_spike: float,
        price_change_pct: float,
        stagnation: float,
        is_irrational: bool
    ) -> ConfidenceLevel:
        """
        Calculate confidence level based on multiple signals.

        Higher confidence when:
        - Larger volume spike (more FOMO)
        - Larger price move (more extreme)
        - More stagnation (hype exhausted)
        - Irrational pricing (fundamentals ignored)
        """
        score = 0

        # Volume spike scoring
        if volume_spike >= 4.0:
            score += 3
        elif volume_spike >= 3.0:
            score += 2
        else:
            score += 1

        # Price change scoring
        if price_change_pct >= 20:
            score += 2
        elif price_change_pct >= 12:
            score += 1

        # Stagnation scoring (lower is better)
        if stagnation <= 0.02:  # < 2% movement
            score += 2
        elif stagnation <= 0.04:  # < 4% movement
            score += 1

        # Irrationality bonus
        if is_irrational:
            score += 2

        # Determine confidence level
        if score >= 7:
            return ConfidenceLevel.HIGH
        elif score >= 4:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW

    def _calculate_edge(
        self,
        price_change_pct: float,
        volume_spike: float,
        stagnation: float,
        is_irrational: bool
    ) -> float:
        """
        Calculate estimated edge in cents.

        Edge comes from expected reversion after hype fades.
        More extreme hype = larger expected reversion.
        """
        # Base edge from price reversion
        base_reversion_factor = 0.35  # Conservative 35% reversion

        # Adjust based on signals
        if volume_spike >= 4.0 and stagnation < 0.02:
            # Extreme FOMO + complete stagnation = high conviction
            reversion_factor = 0.55
        elif volume_spike >= 3.5 or (is_irrational and stagnation < 0.03):
            reversion_factor = 0.45
        elif volume_spike >= 3.0:
            reversion_factor = 0.40
        else:
            reversion_factor = base_reversion_factor

        # Calculate edge
        edge_cents = price_change_pct * reversion_factor

        # Minimum edge threshold
        return max(edge_cents, 3.0)

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        """Parse ISO 8601 datetime string to timezone-aware datetime."""
        if not value:
            return None
        try:
            if value.endswith("Z"):
                value = value.replace("Z", "+00:00")
            return datetime.fromisoformat(value).astimezone(timezone.utc)
        except (ValueError, AttributeError):
            return None


if __name__ == "__main__":
    # Simple test
    logging.basicConfig(level=logging.INFO)

    analyzer = HypeFomoDetector()
    print(f"Analyzer: {analyzer.get_name()}")
    print(f"Description: {analyzer.get_description()}")
    print(f"Config: {analyzer.config}")
