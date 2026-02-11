"""Data collection: fetch options chain at fixed interval and store in DB."""

import logging
import time
from datetime import date, datetime, timezone
from typing import Optional

from spx_options.config import COLLECTOR_INTERVAL_SECONDS
from spx_options.db.repository import OptionsRepository
from spx_options.suppliers.base import OptionsChainSupplier

logger = logging.getLogger(__name__)


def collect_once(
    supplier: OptionsChainSupplier,
    repo: OptionsRepository,
    expiration: Optional[date] = None,
) -> int:
    """
    Fetch chain for one expiration and store. If expiration is None, use next future expiration.
    Returns number of rows inserted.
    """
    expirations = supplier.get_expirations()
    today = date.today()
    future = [e for e in expirations if e >= today]
    if not future:
        logger.warning("No future expirations available")
        return 0
    target = expiration if expiration is not None else future[0]
    if target not in expirations:
        logger.warning("Expiration %s not in supplier list, using %s", target, future[0])
        target = future[0]

    chain = supplier.get_chain(target)
    if not chain:
        return 0
    snapshot_utc = datetime.now(timezone.utc)
    return repo.insert_snapshots(chain, snapshot_utc)


def run_collector_loop(
    supplier: OptionsChainSupplier,
    repo: OptionsRepository,
    interval_seconds: int = COLLECTOR_INTERVAL_SECONDS,
    expiration: Optional[date] = None,
) -> None:
    """
    Loop: every interval_seconds, fetch chain and store. Runs until KeyboardInterrupt.
    """
    repo.ensure_schema()
    supplier.connect()
    try:
        while True:
            try:
                n = collect_once(supplier, repo, expiration=expiration)
                logger.info("Stored %d quotes at %s", n, datetime.now(timezone.utc).isoformat())
            except Exception as e:
                logger.exception("Collect failed: %s", e)
            time.sleep(interval_seconds)
    finally:
        supplier.disconnect()
