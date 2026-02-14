"""
Connection log for Position Builder: status and errors go to logs/position_builder/connection.log.
No console output from this logger (file only), to avoid cluttering the terminal.
"""

import logging
from pathlib import Path

_CONNECTION_LOGGER_NAME = "spx_options.position_builder.connection"
_initialized = False


def _logs_dir() -> Path:
    """Project root: from src/spx_options/ui/connection_log.py go up to project root (parents[3])."""
    project_root = Path(__file__).resolve().parents[3]
    return project_root / "logs" / "position_builder"


def get_connection_logger() -> logging.Logger:
    """Return the connection logger; adds a file handler to logs/position_builder/connection.log if not yet done.
    Also redirects ib_insync logger to the same file so API connection errors are not printed to the terminal.
    """
    global _initialized
    logger = logging.getLogger(_CONNECTION_LOGGER_NAME)
    if not _initialized:
        _initialized = True
        logger.setLevel(logging.DEBUG)
        logger.propagate = False  # do not pass to root (avoids console)
        logs_dir = _logs_dir()
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / "connection.log"
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        )
        logger.addHandler(handler)
        # Redirect ib_insync to the same file so "API connection failed" etc. do not print to terminal
        ibkr_logger = logging.getLogger("ib_insync")
        ibkr_logger.propagate = False
        ibkr_logger.addHandler(handler)
        ibkr_logger.setLevel(logging.DEBUG)
    return logger
