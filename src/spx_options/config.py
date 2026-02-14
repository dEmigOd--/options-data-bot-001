"""Load configuration from environment (e.g. .env). Never commit credentials."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (parent of src)
_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_path)

# IBKR (read-only)
IBKR_USERNAME = os.getenv("IBKR_USERNAME", "")
IBKR_PASSWORD = os.getenv("IBKR_PASSWORD", "")
IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", "7497"))  # TWS (desktop) paper=7497 live=7496; Gateway paper=4002 live=4001
# Use different client IDs so expirations and quotes workers can both connect (TWS allows one connection per client ID)
IBKR_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", "1"))
IBKR_CLIENT_ID_QUOTES = int(os.getenv("IBKR_CLIENT_ID_QUOTES", "2"))

# SQL Server Express (database name used for auto-create fallback)
SQL_DATABASE = os.getenv("SQL_DATABASE", "OptionData")
# Example: "DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost\\SQLEXPRESS;DATABASE=OptionData;Trusted_Connection=yes;"
# Or with login: "...;UID=user;PWD=pass;"
SQL_CONNECTION_STRING = os.getenv(
    "SQL_CONNECTION_STRING",
    f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER=localhost\\SQLEXPRESS;DATABASE={SQL_DATABASE};Trusted_Connection=yes;",
)

# Data
SPX_SYMBOL = "SPX"
COLLECTOR_INTERVAL_SECONDS = 60
