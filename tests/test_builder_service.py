"""Unit tests for position builder service (resolve legs to quotes, totals)."""

from datetime import date
from unittest.mock import MagicMock

from spx_options.position.builder_service import get_expirations, get_leg_quotes
from spx_options.position.leg import LegAction, PositionLeg
from spx_options.suppliers.base import OptionQuote, OptionsChainSupplier


def _leg(strike: float, right: str, action: LegAction) -> PositionLeg:
    return PositionLeg(strike=strike, right=right, action=action)


def _quote(exp: date, strike: float, right: str, bid: float, ask: float) -> OptionQuote:
    return OptionQuote(expiration=exp, strike=strike, right=right, bid=bid, ask=ask, last=0.0)


def test_get_expirations_delegates_to_supplier() -> None:
    """get_expirations returns supplier.get_expirations()."""
    supplier = MagicMock(spec=OptionsChainSupplier)
    supplier.get_expirations.return_value = [date(2026, 3, 20), date(2026, 6, 19)]
    result = get_expirations(supplier)
    assert result == [date(2026, 3, 20), date(2026, 6, 19)]
    supplier.get_expirations.assert_called_once()


def test_get_leg_quotes_resolves_and_totals() -> None:
    """Legs are matched to chain by strike+right; lazy and smart totals computed."""
    exp = date(2026, 3, 20)
    chain = [
        _quote(exp, 4000.0, "C", 10.0, 11.0),
        _quote(exp, 4100.0, "C", 8.0, 9.0),
    ]
    supplier = MagicMock(spec=OptionsChainSupplier)
    supplier.get_chain.return_value = chain

    legs = [
        _leg(4000.0, "C", LegAction.BUY),
        _leg(4100.0, "C", LegAction.SELL),
    ]
    resolved, lazy, smart = get_leg_quotes(supplier, exp, legs)

    assert len(resolved) == 2
    assert resolved[0] == (legs[0], 10.0, 11.0)
    assert resolved[1] == (legs[1], 8.0, 9.0)
    assert lazy == 11.0 - 8.0  # 3.0 debit
    assert smart == 10.5 - 8.5  # 2.0 (mid buy - mid sell)


def test_get_leg_quotes_missing_quote_uses_zeros() -> None:
    """If a leg has no matching quote, use bid=0, ask=0."""
    exp = date(2026, 3, 20)
    supplier = MagicMock(spec=OptionsChainSupplier)
    supplier.get_chain.return_value = []

    legs = [_leg(4000.0, "C", LegAction.BUY)]
    resolved, lazy, smart = get_leg_quotes(supplier, exp, legs)

    assert resolved == [(legs[0], 0.0, 0.0)]
    assert lazy == 0.0
    assert smart == 0.0
