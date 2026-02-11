"""Tests for options chain suppliers."""

from datetime import date

import pytest

from spx_options.suppliers.base import OptionQuote, OptionsChainSupplier


class FakeSupplier(OptionsChainSupplier):
    """Minimal implementation for testing."""

    def get_expirations(self):
        return [date(2025, 3, 21), date(2025, 6, 20)]

    def get_chain(self, expiration: date):
        return [
            OptionQuote(expiration=expiration, strike=6000.0, right="C", bid=100.0, ask=101.0, last=100.5),
            OptionQuote(expiration=expiration, strike=6000.0, right="P", bid=50.0, ask=51.0, last=50.2),
        ]


def test_option_quote_is_call() -> None:
    q = OptionQuote(date(2025, 1, 1), 6000.0, "C", 1.0, 2.0, 1.5)
    assert q.is_call is True
    q2 = OptionQuote(date(2025, 1, 1), 6000.0, "P", 1.0, 2.0, 1.5)
    assert q2.is_call is False


def test_fake_supplier_expirations() -> None:
    s = FakeSupplier()
    exps = s.get_expirations()
    assert len(exps) == 2
    assert exps[0] == date(2025, 3, 21)


def test_fake_supplier_chain() -> None:
    s = FakeSupplier()
    chain = s.get_chain(date(2025, 3, 21))
    assert len(chain) == 2
    assert chain[0].strike == 6000.0 and chain[0].right == "C"
    assert chain[1].right == "P" and chain[1].ask == 51.0
