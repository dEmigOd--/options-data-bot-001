"""SQL Server connection from config. Creates database if missing (fallback on connect failure)."""

import re
import logging

import pyodbc

from spx_options.config import SQL_CONNECTION_STRING, SQL_DATABASE

logger = logging.getLogger(__name__)

def _connection_string_to_master(conn_str: str) -> str:
    """Return a connection string pointing at master (for creating the target database)."""
    return re.sub(r"DATABASE=[^;]+", "DATABASE=master", conn_str, flags=re.I)


def _database_name_from_connection_string(conn_str: str) -> str:
    """Extract DATABASE= value from connection string, or fall back to SQL_DATABASE."""
    m = re.search(r"DATABASE=([^;]+)", conn_str, re.I)
    return m.group(1).strip() if m else SQL_DATABASE


def _safe_database_name(name: str) -> str:
    """Allow only alphanumeric and underscore for dynamic SQL safety."""
    safe = re.sub(r"[^a-zA-Z0-9_]", "", name)
    return safe if safe else SQL_DATABASE


def _ensure_database_exists() -> None:
    """Connect to master and create the target database if it does not exist."""
    db_name = _database_name_from_connection_string(SQL_CONNECTION_STRING)
    db_name = _safe_database_name(db_name)
    master_conn_str = _connection_string_to_master(SQL_CONNECTION_STRING)
    conn = pyodbc.connect(master_conn_str)
    conn.autocommit = True  # CREATE DATABASE not allowed inside a transaction
    try:
        cursor = conn.cursor()
        cursor.execute(
            "IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = ?) CREATE DATABASE [" + db_name + "]",
            (db_name,),
        )
        logger.info("Database %r created or already exists.", db_name)
    finally:
        conn.close()


def get_connection():
    """Return a new pyodbc connection. Creates database if missing (fallback on first failure)."""
    try:
        return pyodbc.connect(SQL_CONNECTION_STRING)
    except pyodbc.Error as e:
        err_str = str(e).upper()
        # Only attempt create when the error indicates database does not exist / cannot open
        if "4060" in err_str or "CANNOT OPEN DATABASE" in err_str or "REQUESTED BY THE LOGIN" in err_str:
            logger.warning("Connection failed (database may not exist): %s. Attempting to create database %r.", e, SQL_DATABASE)
            _ensure_database_exists()
            return pyodbc.connect(SQL_CONNECTION_STRING)
        raise
