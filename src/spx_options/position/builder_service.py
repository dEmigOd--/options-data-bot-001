"""
Position builder service: resolves legs to bid/ask from chain and computes lazy/smart totals.
"""

from datetime import date
from typing import List, Optional, Tuple

from spx_options.position.leg import PositionLeg
from spx_options.position.pricing import lazy_bot_total, smart_bot_total
from spx_options.suppliers.base import OptionQuote, OptionsChainSupplier


def get_expirations(supplier: OptionsChainSupplier) -> List[date]:
    """Return available expiration dates from the supplier (e.g. SPX)."""
    return supplier.get_expirations()


def get_leg_quotes(
    supplier: OptionsChainSupplier,
    legs: List[PositionLeg],
) -> Tuple[List[Tuple[PositionLeg, float, float, Optional[float]]], float, float]:
    """
    Resolve each leg to (leg, bid, ask, delta). Uses get_quotes_for_legs when available.
    Missing quotes use (0.0, 0.0, None).
    Returns (list of (leg, bid, ask, delta), lazy_bot_total, smart_bot_total).
    """
    quotes = supplier.get_quotes_for_legs(legs)
    resolved: List[Tuple[PositionLeg, float, float, Optional[float]]] = [
        (leg, q.bid, q.ask, getattr(q, "delta", None)) for leg, q in zip(legs, quotes)
    ]
    # Pricing functions expect (leg, bid, ask) only
    lazy = lazy_bot_total([(leg, bid, ask) for leg, bid, ask, _ in resolved])
    smart = smart_bot_total([(leg, bid, ask) for leg, bid, ask, _ in resolved])
    return (resolved, lazy, smart)
