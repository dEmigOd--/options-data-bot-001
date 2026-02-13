"""Audit trail for outbound connections (e.g. IBKR): log open/close with resolved IP."""

import socket
from spx_options.security_log import log_ibkr_access


def _resolve_ip(host: str) -> str:
    """Resolve host to IP; return host on failure."""
    try:
        return socket.gethostbyname(host)
    except (socket.gaierror, OSError):
        return host


def log_connection_open(host: str, port: int, client_id: int = 0) -> None:
    """Log that an outbound connection was opened (for audit of open IP connections)."""
    ip = _resolve_ip(host)
    log_ibkr_access(
        "CONNECTION_OPEN",
        f"host={host} resolved_ip={ip} port={port} clientId={client_id}",
    )


def log_connection_close(host: str, port: int) -> None:
    """Log that an outbound connection was closed."""
    ip = _resolve_ip(host)
    log_ibkr_access("CONNECTION_CLOSE", f"host={host} resolved_ip={ip} port={port}")
