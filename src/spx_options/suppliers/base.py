"""Pluggable interface for options chain data (read-only)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import List


@dataclass
class OptionQuote:
    """Single option quote: strike, kind, bid/ask/last."""

    expiration: date
    strike: float
    right: str  # "C" = call, "P" = put
    bid: float
    ask: float
    last: float

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
