"""
Trade Manager

Manages trading decisions, positions, and portfolio state.
Uses analyzer outputs to make buy/sell decisions with risk management.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from analyzers.base import Opportunity, OpportunityType, ConfidenceLevel, OpportunityStrength

logger = logging.getLogger(__name__)


class Side(Enum):
    """Trading side."""
    YES = "yes"
    NO = "no"


class PositionStatus(Enum):
    """Position lifecycle status."""
    OPEN = "open"
    CLOSED = "closed"


@dataclass
class Position:
    """Represents an open or closed trading position."""

    # Identification
    position_id: str
    market_ticker: str
    side: Side

    # Entry details
    entry_price: float  # Price in cents
    quantity: int  # Number of contracts
    entry_time: datetime
    entry_reasoning: str

    # Current state
    status: PositionStatus = PositionStatus.OPEN
    current_price: Optional[float] = None  # Updated regularly

    # Exit details (for closed positions)
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reasoning: Optional[str] = None

    # P&L tracking
    realized_pnl: float = 0.0  # Profit/loss in cents

    # Metadata
    opportunity_type: Optional[OpportunityType] = None
    confidence: Optional[ConfidenceLevel] = None
    strength: Optional[OpportunityStrength] = None

    @property
    def cost_basis(self) -> float:
        """Total cost to enter this position in cents."""
        return self.entry_price * self.quantity

    @property
    def current_value(self) -> float:
        """Current market value of position in cents."""
        if self.status == PositionStatus.CLOSED:
            return self.exit_price * self.quantity if self.exit_price else 0.0

        if self.current_price is None:
            return self.cost_basis  # Default to cost basis if no current price

        return self.current_price * self.quantity

    @property
    def unrealized_pnl(self) -> float:
        """Unrealized profit/loss in cents."""
        if self.status == PositionStatus.CLOSED:
            return 0.0
        return self.current_value - self.cost_basis

    @property
    def total_pnl(self) -> float:
        """Total P&L (realized + unrealized) in cents."""
        if self.status == PositionStatus.CLOSED:
            return self.realized_pnl
        return self.unrealized_pnl

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "position_id": self.position_id,
            "market_ticker": self.market_ticker,
            "side": self.side.value,
            "entry_price": self.entry_price,
            "quantity": self.quantity,
            "entry_time": self.entry_time.isoformat(),
            "entry_reasoning": self.entry_reasoning,
            "status": self.status.value,
            "current_price": self.current_price,
            "exit_price": self.exit_price,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "exit_reasoning": self.exit_reasoning,
            "cost_basis": self.cost_basis,
            "current_value": self.current_value,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "total_pnl": self.total_pnl,
            "opportunity_type": self.opportunity_type.value if self.opportunity_type else None,
            "confidence": self.confidence.value if self.confidence else None,
            "strength": self.strength.value if self.strength else None,
        }


@dataclass
class TradeManagerConfig:
    """Configuration for trade manager."""

    # Capital management
    initial_capital: float = 10000.0  # Starting cash in cents
    max_position_size: float = 1000.0  # Max per position in cents
    max_portfolio_risk: float = 0.5  # Max fraction of capital at risk (0.0-1.0)

    # Opportunity filtering
    min_confidence: Optional[ConfidenceLevel] = None  # Minimum confidence to trade
    min_strength: Optional[OpportunityStrength] = None  # Minimum strength to trade
    min_edge_cents: float = 5.0  # Minimum expected edge in cents
    min_edge_percent: float = 2.0  # Minimum expected edge as percentage

    # Risk management
    stop_loss_percent: float = 20.0  # Stop loss as % of entry price
    take_profit_percent: float = 50.0  # Take profit as % of entry price
    max_positions: int = 10  # Maximum number of open positions

    # Position sizing
    position_sizing_method: str = "fixed"  # "fixed" or "kelly" or "confidence_scaled"
    base_position_size: float = 500.0  # Base position size in cents for fixed method


class TradeManager:
    """
    Manages trading decisions and portfolio state.

    Responsibilities:
    - Evaluate opportunities and decide whether to trade
    - Execute trades (buy/sell)
    - Track open positions and P&L
    - Apply risk management rules
    - Provide portfolio statistics
    """

    def __init__(self, config: Optional[TradeManagerConfig] = None):
        """
        Initialize the trade manager.

        Args:
            config: Configuration for trading behavior
        """
        self.config = config or TradeManagerConfig()

        # Portfolio state
        self.cash: float = self.config.initial_capital
        self.positions: Dict[str, Position] = {}  # position_id -> Position
        self.closed_positions: List[Position] = []
        self.trade_history: List[Dict[str, Any]] = []

        # Position counter for unique IDs
        self._position_counter = 0

        logger.info(f"TradeManager initialized with ${self.cash/100:.2f} capital")

    # ==================== Portfolio Properties ====================

    @property
    def total_position_value(self) -> float:
        """Total current value of all open positions in cents."""
        return sum(pos.current_value for pos in self.positions.values())

    @property
    def total_unrealized_pnl(self) -> float:
        """Total unrealized P&L across all positions in cents."""
        return sum(pos.unrealized_pnl for pos in self.positions.values())

    @property
    def total_realized_pnl(self) -> float:
        """Total realized P&L from closed positions in cents."""
        return sum(pos.realized_pnl for pos in self.closed_positions)

    @property
    def total_pnl(self) -> float:
        """Total P&L (realized + unrealized) in cents."""
        return self.total_realized_pnl + self.total_unrealized_pnl

    @property
    def portfolio_value(self) -> float:
        """Total portfolio value (cash + positions) in cents."""
        return self.cash + self.total_position_value

    @property
    def return_percent(self) -> float:
        """Portfolio return as percentage."""
        if self.config.initial_capital == 0:
            return 0.0
        return ((self.portfolio_value - self.config.initial_capital) /
                self.config.initial_capital * 100)

    # ==================== Opportunity Evaluation ====================

    def should_trade(self, opportunity: Opportunity) -> Tuple[bool, str]:
        """
        Evaluate whether to trade on an opportunity.

        Args:
            opportunity: Opportunity to evaluate

        Returns:
            Tuple of (should_trade, reason)
        """
        # Check if we're at max positions
        if len(self.positions) >= self.config.max_positions:
            return False, f"At max positions ({self.config.max_positions})"

        # Check confidence threshold
        if self.config.min_confidence:
            confidence_order = {
                ConfidenceLevel.LOW: 0,
                ConfidenceLevel.MEDIUM: 1,
                ConfidenceLevel.HIGH: 2
            }
            if confidence_order[opportunity.confidence] < confidence_order[self.config.min_confidence]:
                return False, f"Confidence too low ({opportunity.confidence.value})"

        # Check strength threshold
        if self.config.min_strength:
            strength_order = {
                OpportunityStrength.SOFT: 0,
                OpportunityStrength.HARD: 1
            }
            if strength_order[opportunity.strength] < strength_order[self.config.min_strength]:
                return False, f"Strength too low ({opportunity.strength.value})"

        # Check edge thresholds
        if opportunity.estimated_edge_cents < self.config.min_edge_cents:
            return False, f"Edge too small ({opportunity.estimated_edge_cents:.1f}¢ < {self.config.min_edge_cents}¢)"

        if opportunity.estimated_edge_percent < self.config.min_edge_percent:
            return False, f"Edge % too small ({opportunity.estimated_edge_percent:.1f}% < {self.config.min_edge_percent}%)"

        # Check available capital
        position_size = self._calculate_position_size(opportunity)
        if position_size > self.cash:
            return False, f"Insufficient cash (need {position_size/100:.2f}, have ${self.cash/100:.2f})"

        # Check if we already have a position in this market
        for pos in self.positions.values():
            if pos.market_ticker == opportunity.market_tickers[0]:
                return False, f"Already have position in {opportunity.market_tickers[0]}"

        return True, "All checks passed"

    def _calculate_position_size(self, opportunity: Opportunity) -> float:
        """
        Calculate position size for an opportunity in cents.

        Args:
            opportunity: Opportunity to size

        Returns:
            Position size in cents
        """
        if self.config.position_sizing_method == "fixed":
            return min(self.config.base_position_size, self.config.max_position_size)

        elif self.config.position_sizing_method == "confidence_scaled":
            # Scale position size by confidence level
            confidence_multipliers = {
                ConfidenceLevel.LOW: 0.5,
                ConfidenceLevel.MEDIUM: 0.75,
                ConfidenceLevel.HIGH: 1.0
            }
            multiplier = confidence_multipliers[opportunity.confidence]
            size = self.config.base_position_size * multiplier
            return min(size, self.config.max_position_size)

        elif self.config.position_sizing_method == "kelly":
            # Simple Kelly criterion approximation
            # Kelly = edge / odds
            # For simplicity, use edge_percent as proxy
            kelly_fraction = min(opportunity.estimated_edge_percent / 100, 0.25)  # Cap at 25%
            size = self.portfolio_value * kelly_fraction
            return min(size, self.config.max_position_size)

        else:
            logger.warning(f"Unknown position sizing method: {self.config.position_sizing_method}")
            return self.config.base_position_size

    def _determine_trade_side(self, opportunity: Opportunity) -> Optional[Side]:
        """
        Determine which side to trade based on opportunity type.

        Args:
            opportunity: Opportunity to evaluate

        Returns:
            Side to trade or None if unclear
        """
        # Different opportunity types suggest different sides
        # This is a simple heuristic - can be made more sophisticated

        if opportunity.opportunity_type == OpportunityType.WIDE_SPREAD:
            # For spreads, we could market-make, but for now pick the side
            # with better value (lower price)
            ticker = opportunity.market_tickers[0]
            yes_price = opportunity.current_prices.get(f"{ticker}_yes_bid", 50)
            no_price = opportunity.current_prices.get(f"{ticker}_no_bid", 50)
            return Side.YES if yes_price < no_price else Side.NO

        elif opportunity.opportunity_type == OpportunityType.MISPRICING:
            # Mispricing usually suggests which side is undervalued
            # Check additional_data for hints
            additional = opportunity.additional_data
            if "suggested_side" in additional:
                return Side.YES if additional["suggested_side"] == "yes" else Side.NO
            return Side.YES  # Default

        elif opportunity.opportunity_type in [OpportunityType.MOMENTUM_FADE,
                                              OpportunityType.IMBALANCE]:
            # These typically suggest fading the move (contrarian)
            # Would need more context, default to NO
            return Side.NO

        else:
            # Default to YES for other types
            return Side.YES

    # ==================== Trade Execution ====================

    def execute_trade(
        self,
        opportunity: Opportunity,
        side: Optional[Side] = None,
        price: Optional[float] = None,
        quantity: Optional[int] = None
    ) -> Optional[Position]:
        """
        Execute a trade based on an opportunity.

        Args:
            opportunity: Opportunity to trade on
            side: Which side to trade (YES/NO), auto-determined if None
            price: Entry price in cents, derived from opportunity if None
            quantity: Number of contracts, calculated if None

        Returns:
            New Position object or None if trade fails
        """
        # Determine side if not specified
        if side is None:
            side = self._determine_trade_side(opportunity)
            if side is None:
                logger.warning("Could not determine trade side")
                return None

        # Get market ticker
        if not opportunity.market_tickers:
            logger.warning("No market ticker in opportunity")
            return None
        ticker = opportunity.market_tickers[0]

        # Determine entry price if not specified
        if price is None:
            # Extract from opportunity current_prices
            price_key = f"{ticker}_{side.value}_bid"
            if price_key in opportunity.current_prices:
                price = opportunity.current_prices[price_key]
            else:
                # Fallback to mid-price estimate
                logger.warning(f"No {side.value} price found, using estimated mid-price")
                price = 50.0  # Default mid-price

        # Calculate quantity if not specified
        if quantity is None:
            position_value = self._calculate_position_size(opportunity)
            quantity = int(position_value / price) if price > 0 else 0
            if quantity == 0:
                logger.warning(f"Calculated quantity is 0 (price={price}, size={position_value})")
                return None

        # Calculate total cost
        cost = price * quantity

        # Check if we have enough cash
        if cost > self.cash:
            logger.warning(f"Insufficient cash: need {cost/100:.2f}, have {self.cash/100:.2f}")
            return None

        # Create position
        self._position_counter += 1
        position = Position(
            position_id=f"POS_{self._position_counter:04d}",
            market_ticker=ticker,
            side=side,
            entry_price=price,
            quantity=quantity,
            entry_time=datetime.now(),
            entry_reasoning=opportunity.reasoning,
            current_price=price,  # Initialize to entry price
            opportunity_type=opportunity.opportunity_type,
            confidence=opportunity.confidence,
            strength=opportunity.strength
        )

        # Update portfolio state
        self.cash -= cost
        self.positions[position.position_id] = position

        # Record trade
        trade_record = {
            "timestamp": datetime.now().isoformat(),
            "action": "OPEN",
            "position_id": position.position_id,
            "ticker": ticker,
            "side": side.value,
            "price": price,
            "quantity": quantity,
            "cost": cost,
            "cash_after": self.cash,
        }
        self.trade_history.append(trade_record)

        logger.info(
            f"TRADE EXECUTED: {position.position_id} | {ticker} | "
            f"{side.value.upper()} {quantity}x @ {price:.0f}¢ | "
            f"Cost: ${cost/100:.2f} | Cash: ${self.cash/100:.2f}"
        )

        return position

    def close_position(
        self,
        position_id: str,
        exit_price: float,
        reason: str = "Manual close"
    ) -> bool:
        """
        Close an open position.

        Args:
            position_id: ID of position to close
            exit_price: Exit price in cents
            reason: Reason for closing

        Returns:
            True if closed successfully
        """
        if position_id not in self.positions:
            logger.warning(f"Position {position_id} not found")
            return False

        position = self.positions[position_id]

        if position.status != PositionStatus.OPEN:
            logger.warning(f"Position {position_id} is not open")
            return False

        # Calculate proceeds
        proceeds = exit_price * position.quantity

        # Calculate realized P&L
        pnl = proceeds - position.cost_basis

        # Update position
        position.status = PositionStatus.CLOSED
        position.exit_price = exit_price
        position.exit_time = datetime.now()
        position.exit_reasoning = reason
        position.realized_pnl = pnl

        # Update portfolio
        self.cash += proceeds

        # Move to closed positions
        del self.positions[position_id]
        self.closed_positions.append(position)

        # Record trade
        trade_record = {
            "timestamp": datetime.now().isoformat(),
            "action": "CLOSE",
            "position_id": position_id,
            "ticker": position.market_ticker,
            "side": position.side.value,
            "exit_price": exit_price,
            "quantity": position.quantity,
            "proceeds": proceeds,
            "pnl": pnl,
            "reason": reason,
            "cash_after": self.cash,
        }
        self.trade_history.append(trade_record)

        logger.info(
            f"POSITION CLOSED: {position_id} | {position.market_ticker} | "
            f"{position.side.value.upper()} @ {exit_price:.0f}¢ | "
            f"P&L: ${pnl/100:.2f} | Cash: ${self.cash/100:.2f}"
        )

        return True

    # ==================== Portfolio Management ====================

    def update_position_prices(self, market_prices: Dict[str, Dict[str, float]]) -> None:
        """
        Update current prices for all open positions.

        Args:
            market_prices: Dict mapping ticker -> {"yes": price, "no": price}
        """
        for position in self.positions.values():
            ticker = position.market_ticker
            if ticker in market_prices:
                side_prices = market_prices[ticker]
                if position.side.value in side_prices:
                    position.current_price = side_prices[position.side.value]

    def check_stops_and_targets(self, market_prices: Dict[str, Dict[str, float]]) -> List[str]:
        """
        Check all positions for stop loss or take profit triggers.

        Args:
            market_prices: Dict mapping ticker -> {"yes": price, "no": price}

        Returns:
            List of position IDs that were closed
        """
        closed_position_ids = []

        for position_id, position in list(self.positions.items()):
            ticker = position.market_ticker
            if ticker not in market_prices:
                continue

            current_price = market_prices[ticker].get(position.side.value)
            if current_price is None:
                continue

            # Update current price
            position.current_price = current_price

            # Check stop loss
            pnl_percent = ((current_price - position.entry_price) / position.entry_price) * 100

            if pnl_percent <= -self.config.stop_loss_percent:
                self.close_position(
                    position_id,
                    current_price,
                    f"Stop loss triggered ({pnl_percent:.1f}%)"
                )
                closed_position_ids.append(position_id)
                continue

            # Check take profit
            if pnl_percent >= self.config.take_profit_percent:
                self.close_position(
                    position_id,
                    current_price,
                    f"Take profit triggered ({pnl_percent:.1f}%)"
                )
                closed_position_ids.append(position_id)
                continue

        return closed_position_ids

    # ==================== Reporting ====================

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get comprehensive portfolio summary."""
        return {
            "timestamp": datetime.now().isoformat(),
            "cash": self.cash,
            "position_value": self.total_position_value,
            "portfolio_value": self.portfolio_value,
            "initial_capital": self.config.initial_capital,
            "total_pnl": self.total_pnl,
            "realized_pnl": self.total_realized_pnl,
            "unrealized_pnl": self.total_unrealized_pnl,
            "return_percent": self.return_percent,
            "num_open_positions": len(self.positions),
            "num_closed_positions": len(self.closed_positions),
            "num_trades": len(self.trade_history),
        }

    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Get list of all open positions."""
        return [pos.to_dict() for pos in self.positions.values()]

    def get_closed_positions(self) -> List[Dict[str, Any]]:
        """Get list of all closed positions."""
        return [pos.to_dict() for pos in self.closed_positions]

    def get_trade_history(self) -> List[Dict[str, Any]]:
        """Get complete trade history."""
        return self.trade_history.copy()

    def print_summary(self) -> None:
        """Print formatted portfolio summary to console."""
        summary = self.get_portfolio_summary()

        print("\n" + "=" * 80)
        print("PORTFOLIO SUMMARY")
        print("=" * 80)
        print(f"Portfolio Value:  ${summary['portfolio_value']/100:>12,.2f}")
        print(f"Cash:            ${summary['cash']/100:>12,.2f}")
        print(f"Position Value:  ${summary['position_value']/100:>12,.2f}")
        print("-" * 80)
        print(f"Total P&L:       ${summary['total_pnl']/100:>12,.2f}  ({summary['return_percent']:>6.2f}%)")
        print(f"  Realized:      ${summary['realized_pnl']/100:>12,.2f}")
        print(f"  Unrealized:    ${summary['unrealized_pnl']/100:>12,.2f}")
        print("-" * 80)
        print(f"Open Positions:   {summary['num_open_positions']:>3}")
        print(f"Closed Positions: {summary['num_closed_positions']:>3}")
        print(f"Total Trades:     {summary['num_trades']:>3}")
        print("=" * 80 + "\n")

        # Print open positions if any
        if self.positions:
            print("OPEN POSITIONS:")
            print("-" * 80)
            for pos in self.positions.values():
                pnl = pos.unrealized_pnl
                pnl_pct = (pnl / pos.cost_basis * 100) if pos.cost_basis > 0 else 0
                print(f"{pos.position_id} | {pos.market_ticker:30s} | "
                      f"{pos.side.value.upper():3s} {pos.quantity:>4}x @ {pos.entry_price:>5.0f}¢ | "
                      f"P&L: ${pnl/100:>7.2f} ({pnl_pct:>6.2f}%)")
            print("-" * 80 + "\n")


if __name__ == "__main__":
    # Simple test
    logging.basicConfig(level=logging.INFO)

    # Create trade manager with test config
    config = TradeManagerConfig(
        initial_capital=10000.0,  # $100
        max_position_size=1000.0,  # $10
        min_confidence=ConfidenceLevel.MEDIUM,
        min_edge_cents=5.0,
    )

    manager = TradeManager(config)

    # Create a mock opportunity
    from analyzers.base import OpportunityType

    mock_opp = Opportunity(
        opportunity_type=OpportunityType.WIDE_SPREAD,
        confidence=ConfidenceLevel.HIGH,
        strength=OpportunityStrength.HARD,
        timestamp=datetime.now(),
        market_tickers=["TEST-2025-01-01"],
        market_titles=["Test Market"],
        market_urls=["https://kalshi.com/markets/TEST"],
        current_prices={
            "TEST-2025-01-01_yes_bid": 30.0,
            "TEST-2025-01-01_no_bid": 60.0,
        },
        estimated_edge_cents=10.0,
        estimated_edge_percent=15.0,
        reasoning="Test opportunity with wide spread",
        additional_data={}
    )

    # Test evaluation
    should_trade, reason = manager.should_trade(mock_opp)
    print(f"Should trade: {should_trade} - {reason}")

    if should_trade:
        # Execute trade
        position = manager.execute_trade(mock_opp, side=Side.YES)

        if position:
            # Print summary
            manager.print_summary()

            # Simulate price update
            print("Simulating price movement...")
            market_prices = {
                "TEST-2025-01-01": {"yes": 35.0, "no": 62.0}
            }
            manager.update_position_prices(market_prices)

            # Check portfolio again
            manager.print_summary()

            # Close position
            manager.close_position(position.position_id, 35.0, "Test close")
            manager.print_summary()
