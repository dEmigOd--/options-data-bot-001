"""Position leg: expiration, strike, call/put, buy/sell."""

from dataclasses import dataclass
from datetime import date
from enum import Enum


class LegAction(Enum):
    """Whether the leg is bought (debit) or sold (credit)."""
    BUY = "Buy"
    SELL = "Sell"


@dataclass(frozen=True)
class PositionLeg:
    """One option leg: expiration, strike, right (C/P), action (Buy/Sell), and optional multiplier."""

    expiration: date
    strike: float
    right: str  # "C" or "P"
    action: LegAction
    multiplier: int = 1  # e.g. sell 2 contracts at this strike

    def is_call(self) -> bool:
        return self.right.upper() == "C"

    def is_buy(self) -> bool:
        return self.action == LegAction.BUY
