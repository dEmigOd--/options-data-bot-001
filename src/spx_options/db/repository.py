"""Repository for option snapshots: insert and query price history."""

import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Tuple

import pyodbc

from spx_options.config import SPX_SYMBOL
from spx_options.db.connection import get_connection
from spx_options.suppliers.base import OptionQuote

_SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"
_TABLE_PLACEHOLDER = "__TABLE_NAME__"


def _safe_table_name(underlying: str) -> str:
    """Build table name for underlying: option_snapshots_SPX. Only alphanumeric and _ allowed."""
    safe = re.sub(r"[^a-zA-Z0-9_]", "", underlying)
    if not safe:
        raise ValueError(f"Invalid underlying for table name: {underlying!r}")
    return f"option_snapshots_{safe}"


def _ensure_schema(cursor: pyodbc.Cursor, table_name: str) -> None:
    """Create table for this underlying if it does not exist (schema.sql, placeholder replaced)."""
    if not _SCHEMA_FILE.exists():
        return
    content = _SCHEMA_FILE.read_text(encoding="utf-8")
    content = content.replace(_TABLE_PLACEHOLDER, table_name)
    batches = [b.strip() for b in content.split("GO") if b.strip()]
    for batch in batches:
        cursor.execute(batch)


class OptionsRepository:
    """Insert snapshots and query price vs time for a single option. One table per underlying."""

    def __init__(self, underlying: str = SPX_SYMBOL):
        self.underlying = underlying
        self._table_name = _safe_table_name(underlying)

    def ensure_schema(self) -> None:
        """Create table for this underlying if it does not exist."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            _ensure_schema(cursor, self._table_name)
            conn.commit()
        finally:
            conn.close()

    def insert_snapshots(
        self, quotes: List[OptionQuote], snapshot_utc: datetime
    ) -> int:
        """Insert a batch of option quotes for one snapshot time. Returns row count."""
        if not quotes:
            return 0
        conn = get_connection()
        try:
            cursor = conn.cursor()
            _ensure_schema(cursor, self._table_name)
            for q in quotes:
                cursor.execute(
                    f"""
                    INSERT INTO dbo.[{self._table_name}]
                    (expiration_date, strike, option_type, bid, ask, last, snapshot_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        q.expiration,
                        q.strike,
                        q.right,
                        q.bid,
                        q.ask,
                        q.last,
                        snapshot_utc,
                    ),
                )
            conn.commit()
            return len(quotes)
        finally:
            conn.close()

    def get_price_history(
        self,
        expiration: date,
        strike: float,
        option_type: str,
    ) -> List[Tuple[datetime, float, float, float]]:
        """
        Return (snapshot_utc, bid, ask, last) for the given option, ordered by time.
        option_type: 'C' or 'P'.
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT snapshot_utc, bid, ask, last
                FROM dbo.[{self._table_name}]
                WHERE expiration_date = ? AND strike = ? AND option_type = ?
                ORDER BY snapshot_utc
                """,
                (expiration, strike, option_type.upper()),
            )
            return [(row[0], row[1], row[2], row[3]) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_available_expirations(self) -> List[date]:
        """Return distinct expiration dates present in the database."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            _ensure_schema(cursor, self._table_name)
            conn.commit()
            cursor.execute(
                f"""
                SELECT DISTINCT expiration_date FROM dbo.[{self._table_name}]
                ORDER BY expiration_date
                """,
                (),
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_strikes_for_expiration(self, expiration: date) -> List[float]:
        """Return distinct strikes for the given expiration."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT DISTINCT strike FROM dbo.[{self._table_name}]
                WHERE expiration_date = ?
                ORDER BY strike
                """,
                (expiration,),
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()
