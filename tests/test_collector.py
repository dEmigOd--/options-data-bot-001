"""Tests for collector (one-shot with fake supplier)."""

from datetime import date

import pytest

from spx_options.collector import collect_once
from spx_options.db.repository import OptionsRepository
from spx_options.suppliers.base import OptionQuote, OptionsChainSupplier


class FakeSupplier(OptionsChainSupplier):
    def get_expirations(self):
        return [date(2026, 1, 16), date(2026, 2, 20)]

    def get_chain(self, expiration: date):
        return [
            OptionQuote(expiration=expiration, strike=6000.0, right="C", bid=10.0, ask=11.0, last=10.5),
        ]


def test_collect_once_returns_count() -> None:
    """collect_once with fake supplier returns number of rows (requires DB)."""
    try:
        repo = OptionsRepository()
        repo.ensure_schema()
    except Exception:
        pytest.skip("SQL Server not available")
    supplier = FakeSupplier()
    n = collect_once(supplier, repo, expiration=date(2026, 1, 16))
    assert n == 1
