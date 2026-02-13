"""
Position builder service: resolves legs to bid/ask from chain and computes lazy/smart totals.
"""

from datetime import date
from typing import List, Optional, Tuple

from spx_options.position.leg import PositionLeg
from spx_options.position.pricing import lazy_bot_total, smart_bot_total
from spx_options.suppliers.base import OptionQuote, OptionsChainSupplier


def _quote_key(q: OptionQuote) -> Tuple[float, str]:
    """(strike, right) for matching legs to quotes."""
    return (q.strike, q.right.upper())


def _find_quote(chain: List[OptionQuote], leg: PositionLeg) -> Optional[OptionQuote]:
    """Return first quote matching leg strike and right, or None."""
    key = (leg.strike, leg.right.upper())
    for q in chain:
        if _quote_key(q) == key:
            return q
    return None


def get_expirations(supplier: OptionsChainSupplier) -> List[date]:
    """Return available expiration dates from the supplier (e.g. SPX)."""
    return supplier.get_expirations()


def get_leg_quotes(
    supplier: OptionsChainSupplier,
    expiration: date,
    legs: List[PositionLeg],
) -> Tuple[List[Tuple[PositionLeg, float, float]], float, float]:
    """
    Resolve each leg to (leg, bid, ask) from the chain; compute lazy and smart totals.
    Missing quotes use (0.0, 0.0).
    Returns (list of (leg, bid, ask), lazy_bot_total, smart_bot_total).
    """
    chain = supplier.get_chain(expiration)
    resolved: List[Tuple[PositionLeg, float, float]] = []
    for leg in legs:
        q = _find_quote(chain, leg)
        if q is not None:
            resolved.append((leg, q.bid, q.ask))
        else:
            resolved.append((leg, 0.0, 0.0))
    lazy = lazy_bot_total(resolved)
    smart = smart_bot_total(resolved)
    return (resolved, lazy, smart)
