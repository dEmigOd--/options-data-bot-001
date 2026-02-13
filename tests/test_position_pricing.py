"""Unit tests for position pricing (lazy bot and smart bot)."""

from spx_options.position.leg import LegAction, PositionLeg
from spx_options.position.pricing import lazy_bot_total, smart_bot_total


def _leg(strike: float, right: str, action: LegAction) -> PositionLeg:
    return PositionLeg(strike=strike, right=right, action=action)


def test_lazy_bot_buy_uses_ask() -> None:
    """Lazy: buy leg uses ask (debit)."""
    leg = _leg(4000.0, "C", LegAction.BUY)
    total = lazy_bot_total([(leg, 10.0, 11.0)])
    assert total == 11.0


def test_lazy_bot_sell_uses_bid_credit() -> None:
    """Lazy: sell leg uses bid as credit (negative)."""
    leg = _leg(4000.0, "P", LegAction.SELL)
    total = lazy_bot_total([(leg, 5.0, 6.0)])
    assert total == -5.0


def test_lazy_bot_multi_leg() -> None:
    """Lazy: debit minus credit."""
    legs_with_quotes = [
        (_leg(4000.0, "C", LegAction.BUY), 10.0, 11.0),
        (_leg(4100.0, "C", LegAction.SELL), 8.0, 9.0),
    ]
    assert lazy_bot_total(legs_with_quotes) == 11.0 - 8.0  # 3.0 debit


def test_smart_bot_uses_mid() -> None:
    """Smart: buy leg uses mid."""
    leg = _leg(4000.0, "C", LegAction.BUY)
    total = smart_bot_total([(leg, 10.0, 12.0)])
    assert total == 11.0


def test_smart_bot_sell_negative_mid() -> None:
    """Smart: sell leg uses negative mid."""
    leg = _leg(4000.0, "P", LegAction.SELL)
    total = smart_bot_total([(leg, 4.0, 6.0)])
    assert total == -5.0


def test_smart_bot_multi_leg() -> None:
    """Smart: sum of mid with sign by action."""
    legs_with_quotes = [
        (_leg(4000.0, "C", LegAction.BUY), 10.0, 12.0),
        (_leg(4100.0, "C", LegAction.SELL), 8.0, 10.0),
    ]
    # buy mid 11, sell mid -9 -> 2.0
    assert smart_bot_total(legs_with_quotes) == 2.0
