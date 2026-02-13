"""Position leg: strike, call/put, buy/sell."""

from dataclasses import dataclass
from enum import Enum


class LegAction(Enum):
    """Whether the leg is bought (debit) or sold (credit)."""
    BUY = "Buy"
    SELL = "Sell"


@dataclass(frozen=True)
class PositionLeg:
    """One option leg: strike, right (C/P), and action (Buy/Sell)."""

    strike: float
    right: str  # "C" or "P"
    action: LegAction

    def is_call(self) -> bool:
        return self.right.upper() == "C"

    def is_buy(self) -> bool:
        return self.action == LegAction.BUY
