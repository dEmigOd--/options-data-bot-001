"""
P&L at expiration: value of an options position at expiry for a range of underlying prices.
"""

from typing import List, Tuple

from spx_options.position.leg import LegAction, PositionLeg


def _leg_payoff_at_s(leg: PositionLeg, s: float) -> float:
    """Intrinsic value of one leg at underlying price s (at expiration)."""
    k = leg.strike
    mult = leg.multiplier
    if leg.right.upper() == "C":
        intrinsic = max(0.0, s - k)
    else:
        intrinsic = max(0.0, k - s)
    if leg.action == LegAction.BUY:
        return mult * intrinsic
    return -mult * intrinsic


def pnl_at_expiry_curve(
    legs: List[PositionLeg],
    cost_basis: float,
    s_min: float,
    s_max: float,
    steps: int = 80,
) -> List[Tuple[float, float]]:
    """
    P&L at expiration over a range of underlying prices.
    cost_basis: net debit (positive) or credit (negative) paid for the position; P&L = value_at_expiry - cost_basis.
    Returns list of (underlying_price, pnl).
    """
    if not legs:
        return []
    out: List[Tuple[float, float]] = []
    for i in range(steps + 1):
        s = s_min + (s_max - s_min) * (i / steps)
        value = sum(_leg_payoff_at_s(leg, s) for leg in legs)
        pnl = value - cost_basis
        out.append((s, pnl))
    return out
