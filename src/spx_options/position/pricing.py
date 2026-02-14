"""Lazy bot and smart bot price totals from leg prices."""

from typing import List, Tuple

from spx_options.position.leg import LegAction, PositionLeg


def _leg_lazy_price(leg: PositionLeg, bid: float, ask: float) -> float:
    """Price used for this leg in lazy bot: buy -> ask (debit), sell -> bid (credit); scaled by multiplier."""
    mult = leg.multiplier
    if leg.action == LegAction.BUY:
        return mult * ask
    return -mult * bid  # credit is negative


def _leg_smart_price(leg: PositionLeg, bid: float, ask: float) -> float:
    """Price used for this leg in smart bot: mid; buy positive, sell negative; scaled by multiplier."""
    mult = leg.multiplier
    mid = (bid + ask) / 2.0 if (bid or ask) else 0.0
    if leg.action == LegAction.BUY:
        return mult * mid
    return -mult * mid


def lazy_bot_total(legs: List[Tuple[PositionLeg, float, float]]) -> float:
    """
    Total price using lazy bot rule: each buy leg uses ask, each sell uses bid.
    Returns positive = net debit, negative = net credit.
    """
    return sum(_leg_lazy_price(leg, bid, ask) for leg, bid, ask in legs)


def smart_bot_total(legs: List[Tuple[PositionLeg, float, float]]) -> float:
    """
    Total price using smart bot rule: each leg uses mid; buy positive, sell negative.
    """
    return sum(_leg_smart_price(leg, bid, ask) for leg, bid, ask in legs)
