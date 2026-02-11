"""Security logging for read-only IBKR access (what we request, when)."""

import logging
from datetime import datetime, timezone

_SECURITY_LOGGER_NAME = "spx_options.security"

def get_security_logger() -> logging.Logger:
    """Return the dedicated security logger. Callers should use this for IBKR access events."""
    return logging.getLogger(_SECURITY_LOGGER_NAME)


def log_ibkr_access(action: str, detail: str = "") -> None:
    """Log a read-only IBKR access event (for audit trail)."""
    logger = get_security_logger()
    msg = f"IBKR_ACCESS | {datetime.now(timezone.utc).isoformat()} | {action}"
    if detail:
        msg += f" | {detail}"
    logger.info(msg)
