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

# SQL Server Express
# Example: "DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost\\SQLEXPRESS;DATABASE=SPXOptions;Trusted_Connection=yes;"
# Or with login: "...;UID=user;PWD=pass;"
SQL_CONNECTION_STRING = os.getenv(
    "SQL_CONNECTION_STRING",
    "DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost\\SQLEXPRESS;DATABASE=SPXOptions;Trusted_Connection=yes;",
)

# Data
SPX_SYMBOL = "SPX"
COLLECTOR_INTERVAL_SECONDS = 60
