"""Pluggable interface for options chain data (read-only)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from spx_options.position.leg import PositionLeg


@dataclass
class OptionQuote:
    """Single option quote: strike, kind, bid/ask/last, volume, open_interest, optional delta."""

    expiration: date
    strike: float
    right: str  # "C" = call, "P" = put
    bid: float
    ask: float
    last: float
    volume: int = 0
    open_interest: int = 0
    delta: Optional[float] = None

    @property
    def is_call(self) -> bool:
        return self.right.upper() == "C"


class OptionsChainSupplier(ABC):
    """Read-only supplier of options chain data. Implementations: IBKR, etc."""

    @abstractmethod
    def get_expirations(self) -> List[date]:
        """Return available expiration dates for the underlying (e.g. SPX)."""
        ...

    @abstractmethod
    def get_chain(self, expiration: date) -> List[OptionQuote]:
        """Return full chain (all strikes, calls and puts) for the given expiration."""
        ...

    def get_strikes(self, expiration: date) -> List[float]:
        """Return list of available strikes for the expiration (no quote data). Override for lightweight strike list."""
        return []

    def get_quotes_for_legs(self, legs: "List[PositionLeg]") -> List[OptionQuote]:
        """
        Return one OptionQuote per leg (same order), only for the given legs.
        Default: fetch full chain per expiration and match; override to request only those contracts.
        """
        chains: dict = {}
        quotes: List[OptionQuote] = []
        for leg in legs:
            if leg.expiration not in chains:
                chains[leg.expiration] = self.get_chain(leg.expiration)
            chain = chains[leg.expiration]
            q = next(
                (x for x in chain if x.strike == leg.strike and x.right.upper() == leg.right.upper()),
                None,
            )
            if q is not None:
                quotes.append(q)
            else:
                quotes.append(
                    OptionQuote(
                        expiration=leg.expiration,
                        strike=leg.strike,
                        right=leg.right,
                        bid=0.0,
                        ask=0.0,
                        last=0.0,
                        delta=None,
                    )
                )
        return quotes
