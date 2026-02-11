"""Interactive Brokers options chain supplier (read-only, with security logging)."""

import logging
from datetime import date, datetime, timezone
from typing import List

from ib_insync import IB, Index, Option, util
from ib_insync.ib import OptionChain

from spx_options.config import IBKR_HOST, IBKR_PORT, SPX_SYMBOL
from spx_options.security_log import log_ibkr_access
from spx_options.suppliers.base import OptionQuote, OptionsChainSupplier

logger = logging.getLogger(__name__)

# IBKR uses string expirations YYYYMMDD
_EXPIRATION_FORMAT = "%Y%m%d"


def _parse_expiration(s: str) -> date:
    return datetime.strptime(s, _EXPIRATION_FORMAT).date()


def _format_expiration(d: date) -> str:
    return d.strftime(_EXPIRATION_FORMAT)


class IBKROptionsSupplier(OptionsChainSupplier):
    """Read-only SPX options chain from Interactive Brokers. Uses security logging."""

    def __init__(
        self,
        host: str = IBKR_HOST,
        port: int = IBKR_PORT,
        client_id: int = 1,
        use_delayed_data: bool = True,
    ):
        self._host = host
        self._port = port
        self._client_id = client_id
        self._use_delayed_data = use_delayed_data
        self._ib = IB()
        self._spx = None
        self._chain_params = None
        self._trading_class = "SPX"
        self._exchange = "SMART"

    def connect(self) -> None:
        """Connect to TWS/Gateway. Call before get_expirations/get_chain."""
        if self._ib.isConnected():
            return
        log_ibkr_access("CONNECT", f"host={self._host} port={self._port} clientId={self._client_id}")
        self._ib.connect(self._host, self._port, clientId=self._client_id)
        if self._use_delayed_data:
            self._ib.reqMarketDataType(4)  # Delayed
        self._spx = Index(SPX_SYMBOL, "CBOE")
        self._ib.qualifyContracts(self._spx)
        chains = self._ib.reqSecDefOptParams(
            self._spx.symbol, "", self._spx.secType, self._spx.conId
        )
        for c in chains:
            if getattr(c, "tradingClass", None) == self._trading_class and getattr(
                c, "exchange", None
            ) in (self._exchange, "CBOE"):
                self._chain_params = c
                break
        if not self._chain_params:
            self._chain_params = chains[0]
        log_ibkr_access("SEC_DEF_OPT_PARAMS", f"expirations={len(getattr(self._chain_params, 'expirations', []))} strikes={len(getattr(self._chain_params, 'strikes', []))}")

    def disconnect(self) -> None:
        if self._ib.isConnected():
            self._ib.disconnect()
            log_ibkr_access("DISCONNECT", "")

    def __enter__(self) -> "IBKROptionsSupplier":
        self.connect()
        return self

    def __exit__(self, *args) -> None:
        self.disconnect()

    def get_expirations(self) -> List[date]:
        """Return available SPX option expiration dates."""
        self.connect()
        exp_strs = getattr(self._chain_params, "expirations", []) or []
        return sorted(_parse_expiration(s) for s in exp_strs)

    def get_chain(self, expiration: date) -> List[OptionQuote]:
        """Return full chain (all strikes, calls and puts) for the given expiration."""
        self.connect()
        exp_str = _format_expiration(expiration)
        strikes = list(getattr(self._chain_params, "strikes", []) or [])
        if not strikes:
            return []

        contracts = []
        for strike in strikes:
            for right in ("C", "P"):
                contracts.append(
                    Option(
                        SPX_SYMBOL,
                        exp_str,
                        strike,
                        right,
                        self._exchange,
                        tradingClass=self._trading_class,
                    )
                )
        qualified = self._ib.qualifyContracts(*contracts)
        if not qualified:
            logger.warning("No contracts qualified for expiration %s", expiration)
            return []

        log_ibkr_access("REQ_TICKERS", f"expiration={exp_str} count={len(qualified)}")
        tickers = self._ib.reqTickers(*qualified)
        util.sleep(0.5)

        out: List[OptionQuote] = []
        for t in tickers:
            c = t.contract
            bid = float(t.bid) if t.bid is not None and t.bid != -1 else 0.0
            ask = float(t.ask) if t.ask is not None and t.ask != -1 else 0.0
            last = float(t.last) if t.last is not None and t.last != -1 else 0.0
            exp = _parse_expiration(c.lastTradeDateOrContractMonth)
            out.append(
                OptionQuote(
                    expiration=exp,
                    strike=float(c.strike),
                    right=c.right,
                    bid=bid,
                    ask=ask,
                    last=last,
                )
            )
        return out
