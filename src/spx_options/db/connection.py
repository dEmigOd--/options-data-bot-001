"""SQL Server connection from config. Database must exist (create manually or via script)."""

import pyodbc

from spx_options.config import SQL_CONNECTION_STRING


def get_connection():
    """Return a new pyodbc connection. Caller must close it."""
    return pyodbc.connect(SQL_CONNECTION_STRING)
