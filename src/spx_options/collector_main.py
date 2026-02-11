"""Entry point for the data collector: run with python -m spx_options.collector_main."""

import logging
import sys

from spx_options.collector import run_collector_loop
from spx_options.db.repository import OptionsRepository
from spx_options.suppliers.ibkr import IBKROptionsSupplier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)


def main() -> None:
    supplier = IBKROptionsSupplier()
    repo = OptionsRepository()
    run_collector_loop(supplier, repo)


if __name__ == "__main__":
    main()
