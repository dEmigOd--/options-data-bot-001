"""Interactive Brokers options chain supplier (read-only, with security logging)."""

import logging
import math
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Tuple

from ib_insync import IB, Index, Option, util

from spx_options.position.leg import PositionLeg
from ib_insync.ib import OptionChain


def _safe_float(v, default: float = 0.0) -> float:
    """Coerce to float valid for SQL; replace NaN/inf/None/-1 with default."""
    if v is None or v == -1:
        return default
    try:
        f = float(v)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return default


def _safe_int(v, default: int = 0) -> int:
    """Coerce to int valid for DB; None/NaN -> default."""
    if v is None:
        return default
    try:
        if math.isnan(float(v)):
            return default
        return int(float(v))
    except (TypeError, ValueError):
        return default

from spx_options.audit import log_connection_close, log_connection_open
from spx_options.config import IBKR_CLIENT_ID, IBKR_HOST, IBKR_PORT, SPX_SYMBOL
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
        client_id: int = IBKR_CLIENT_ID,
        use_delayed_data: bool = True,
    ):
        self._host = host
        self._port = port
        self._client_id = client_id
        self._use_delayed_data = use_delayed_data
        self._ib = IB()
        self._spx = None
        # SPX = monthly, SPXW = weekly; merge expirations from both for full list
        self._trading_classes = ("SPX", "SPXW")
        self._exchange = "SMART"
        # Map expiration date -> (chain_params, trading_class) for get_chain(exp)
        self._expiration_to_chain: Dict[date, Tuple[Any, str]] = {}

    def connect(self) -> None:
        """Connect to TWS/Gateway. Call before get_expirations/get_chain."""
        if self._ib.isConnected():
            return
        log_ibkr_access("CONNECT", f"host={self._host} port={self._port} clientId={self._client_id}")
        self._ib.connect(self._host, self._port, clientId=self._client_id)
        log_connection_open(self._host, self._port, self._client_id)
        if self._use_delayed_data:
            self._ib.reqMarketDataType(4)  # Delayed
        self._spx = Index(SPX_SYMBOL, "CBOE")
        self._ib.qualifyContracts(self._spx)
        chains = self._ib.reqSecDefOptParams(
            self._spx.symbol, "", self._spx.secType, self._spx.conId
        )
        self._expiration_to_chain = {}
        for c in chains:
            trading_class = getattr(c, "tradingClass", None)
            exchange = getattr(c, "exchange", None)
            if trading_class not in self._trading_classes:
                continue
            if exchange not in (self._exchange, "CBOE"):
                continue
            exp_strs = getattr(c, "expirations", []) or []
            for s in exp_strs:
                try:
                    d = _parse_expiration(s)
                    self._expiration_to_chain[d] = (c, trading_class)
                except ValueError:
                    continue
        if not self._expiration_to_chain and chains:
            # Fallback: use first chain (legacy behaviour)
            c = chains[0]
            trading_class = getattr(c, "tradingClass", "SPX")
            for s in getattr(c, "expirations", []) or []:
                try:
                    d = _parse_expiration(s)
                    self._expiration_to_chain[d] = (c, trading_class)
                except ValueError:
                    continue
        log_ibkr_access(
            "SEC_DEF_OPT_PARAMS",
            f"expirations={len(self._expiration_to_chain)} (SPX+SPXW merged)",
        )

    def disconnect(self) -> None:
        if self._ib.isConnected():
            log_connection_close(self._host, self._port)
            self._ib.disconnect()
            log_ibkr_access("DISCONNECT", "")

    def __enter__(self) -> "IBKROptionsSupplier":
        self.connect()
        return self

    def __exit__(self, *args) -> None:
        self.disconnect()

    def get_expirations(self) -> List[date]:
        """Return available SPX option expiration dates (monthly SPX + weekly SPXW merged)."""
        self.connect()
        return sorted(self._expiration_to_chain.keys())

    def get_strikes(self, expiration: date) -> List[float]:
        """Return available strikes for the expiration (from sec def only; no contract/quote requests)."""
        self.connect()
        chain_info = self._expiration_to_chain.get(expiration)
        if not chain_info:
            return []
        chain_params, _ = chain_info
        return list(getattr(chain_params, "strikes", []) or [])

    def get_chain(self, expiration: date) -> List[OptionQuote]:
        """Return full chain (all strikes, calls and puts) for the given expiration."""
        self.connect()
        chain_info = self._expiration_to_chain.get(expiration)
        if not chain_info:
            logger.warning("Expiration %s not in any chain (SPX/SPXW)", expiration)
            return []
        chain_params, trading_class = chain_info
        exp_str = _format_expiration(expiration)
        strikes = list(getattr(chain_params, "strikes", []) or [])
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
                        tradingClass=trading_class,
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
            bid = _safe_float(t.bid)
            ask = _safe_float(t.ask)
            last = _safe_float(t.last)
            vol = _safe_int(getattr(t, "volume", None))
            oi = _safe_int(
                getattr(t, "callOpenInterest", None) if c.right == "C" else getattr(t, "putOpenInterest", None)
            )
            exp = _parse_expiration(c.lastTradeDateOrContractMonth)
            out.append(
                OptionQuote(
                    expiration=exp,
                    strike=_safe_float(c.strike),
                    right=c.right,
                    bid=bid,
                    ask=ask,
                    last=last,
                    volume=vol,
                    open_interest=oi,
                )
            )
        return out

    def get_quotes_for_legs(self, legs: List[PositionLeg]) -> List[OptionQuote]:
        """Request quotes only for the given legs (no full chain). One OptionQuote per leg, same order."""
        self.connect()
        if not legs:
            return []
        # Build one contract per leg (same order); skip leg if expiration not in chain
        contracts: List[Any] = []
        leg_indices: List[int] = []  # contracts[k] corresponds to legs[leg_indices[k]]
        for i, leg in enumerate(legs):
            chain_info = self._expiration_to_chain.get(leg.expiration)
            if not chain_info:
                continue
            _chain_params, trading_class = chain_info
            exp_str = _format_expiration(leg.expiration)
            contracts.append(
                Option(
                    SPX_SYMBOL,
                    exp_str,
                    leg.strike,
                    leg.right.upper(),
                    self._exchange,
                    tradingClass=trading_class,
                )
            )
            leg_indices.append(i)
        # Start with all legs as no-quote
        out: List[OptionQuote] = [
            OptionQuote(expiration=leg.expiration, strike=leg.strike, right=leg.right, bid=0.0, ask=0.0, last=0.0)
            for leg in legs
        ]
        if not contracts:
            return out
        qualified = self._ib.qualifyContracts(*contracts)
        if not qualified:
            return out
        log_ibkr_access("REQ_TICKERS", f"legs={len(qualified)} (active legs only)")
        tickers = self._ib.reqTickers(*qualified)
        # Allow time for all tickers to receive data (streaming)
        util.sleep(0.5)
        # Map each ticker to (exp, strike, right) so we assign to the correct leg regardless of order
        ticker_by_key: Dict[Tuple[date, float, str], Any] = {}
        for t in tickers:
            c = t.contract
            exp = _parse_expiration(c.lastTradeDateOrContractMonth)
            key = (exp, _safe_float(c.strike), c.right.upper())
            ticker_by_key[key] = t
        for i, leg in enumerate(legs):
            key = (leg.expiration, leg.strike, leg.right.upper())
            t = ticker_by_key.get(key)
            if t is None:
                continue
            c = t.contract
            greeks = getattr(t, "modelGreeks", None) or getattr(t, "lastGreeks", None) or getattr(t, "bidGreeks", None) or getattr(t, "askGreeks", None)
            delta_val = None
            if greeks is not None:
                d = getattr(greeks, "delta", None)
                if d is not None and d != -1:
                    delta_val = _safe_float(d)
            out[i] = OptionQuote(
                expiration=_parse_expiration(c.lastTradeDateOrContractMonth),
                strike=_safe_float(c.strike),
                right=c.right,
                bid=_safe_float(t.bid),
                ask=_safe_float(t.ask),
                last=_safe_float(t.last),
                volume=_safe_int(getattr(t, "volume", None)),
                open_interest=_safe_int(
                    getattr(t, "callOpenInterest", None) if c.right == "C" else getattr(t, "putOpenInterest", None)
                ),
                delta=delta_val,
            )
        return out
