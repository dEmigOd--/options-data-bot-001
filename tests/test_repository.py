"""Tests for options repository (require SQL Server)."""

from datetime import date, datetime, timezone

import pytest

from spx_options.db.repository import OptionsRepository
from spx_options.suppliers.base import OptionQuote


def test_ensure_schema() -> None:
    try:
        repo = OptionsRepository()
        repo.ensure_schema()
    except Exception as e:
        pytest.skip(f"SQL Server not available: {e}")


def test_insert_and_get_history() -> None:
    try:
        repo = OptionsRepository()
        repo.ensure_schema()
    except Exception as e:
        pytest.skip(f"SQL Server not available: {e}")

    exp = date(2027, 12, 17)
    quotes = [
        OptionQuote(expiration=exp, strike=6000.0, right="C", bid=1.0, ask=2.0, last=1.5),
    ]
    t = datetime(2025, 2, 11, 12, 0, 0, tzinfo=timezone.utc)
    repo.insert_snapshots(quotes, t)
    history = repo.get_price_history(exp, 6000.0, "C")
    assert len(history) >= 1
    row = history[-1]
    assert row[1] == 1.0 and row[2] == 2.0 and row[3] == 1.5
