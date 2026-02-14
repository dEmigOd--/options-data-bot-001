"""
Position Builder UI: ticker, expirations, legs table with bid/ask, lazy and smart bot prices.
Runs IBKR supplier calls in a worker thread to keep UI responsive.
"""

import asyncio
import queue
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

try:
    from PyQt6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
    _HAS_QTCHARTS = True
except ImportError:
    _HAS_QTCHARTS = False
    QChart = None  # type: ignore[misc, assignment]
    QChartView = None  # type: ignore[misc, assignment]
    QLineSeries = None  # type: ignore[misc, assignment]
    QValueAxis = None  # type: ignore[misc, assignment]

from PyQt6.QtCore import QDate, QObject, Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QTextCharFormat
from PyQt6.QtWidgets import (
    QApplication,
    QCalendarWidget,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spx_options.config import IBKR_CLIENT_ID
from spx_options.position import (
    LegAction,
    PositionLeg,
    get_expirations,
    get_leg_quotes,
    lazy_bot_total,
    smart_bot_total,
)
from spx_options.position.pnl_curve import pnl_at_expiry_curve
from spx_options.suppliers.base import OptionsChainSupplier
from spx_options.suppliers.ibkr import IBKROptionsSupplier
from spx_options.ui.connection_log import get_connection_logger

# Initialize connection log (and redirect ib_insync to file) before any API use
get_connection_logger()

# Legs table column indices (Expiration first; width for YYYY-MM-DD)
COL_EXPIRATION = 0
COL_STRIKE = 1
COL_TYPE = 2
COL_ACTION = 3
COL_MULT = 4
COL_BID = 5
COL_ASK = 6
COL_DELTA = 7
COL_EDIT = 8
COL_REMOVE = 9
EXPIRATION_COLUMN_WIDTH = 92

# Minimum width for Bid/Ask (e.g. "1234.56")
BID_ASK_MIN_WIDTH = 72
# Bid = blue, Ask = red
COLOR_BID = QColor(0, 0, 180)
COLOR_ASK = QColor(180, 0, 0)
# Buy = blue, Sell = red (with ~0.1 alpha for background)
COLOR_BUY = QColor(0, 0, 200)
COLOR_SELL = QColor(200, 0, 0)
COLOR_BUY_BG = QColor(0, 0, 200, 26)   # ~0.1 alpha
COLOR_SELL_BG = QColor(200, 0, 0, 26)


# ---- Edit leg dialog ----


class _EditLegDialog(QDialog):
    """Dialog to edit expiration, strike, type, action, and multiplier for one leg (not bid/ask)."""

    def __init__(
        self,
        parent: Optional[QWidget],
        expiration: date,
        strike: float,
        right: str,
        action: LegAction,
        multiplier: int,
        available_expirations: List[date],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit leg")
        layout = QFormLayout(self)
        self.exp_combo = QComboBox()
        for d in available_expirations:
            self.exp_combo.addItem(d.strftime("%Y-%m-%d"), d)
        self._set_expiration_combo(expiration)
        layout.addRow("Expiration:", self.exp_combo)
        self.strike_edit = QLineEdit()
        self.strike_edit.setText(f"{strike:.0f}")
        layout.addRow("Strike:", self.strike_edit)
        self.right_combo = QComboBox()
        self.right_combo.addItems(["Call", "Put"])
        self.right_combo.setCurrentText("Call" if right.upper() == "C" else "Put")
        layout.addRow("Type:", self.right_combo)
        self.action_combo = QComboBox()
        self.action_combo.addItems(["Buy", "Sell"])
        self.action_combo.setCurrentText(action.value)
        layout.addRow("Action:", self.action_combo)
        self.mult_spin = QSpinBox()
        self.mult_spin.setRange(1, 999)
        self.mult_spin.setValue(multiplier)
        layout.addRow("Multiplier:", self.mult_spin)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addRow(bb)

    def _set_expiration_combo(self, expiration: date) -> None:
        """Select the combo item that matches the given date."""
        for i in range(self.exp_combo.count()):
            if self.exp_combo.itemData(i) == expiration:
                self.exp_combo.setCurrentIndex(i)
                return
        if self.exp_combo.count():
            self.exp_combo.setCurrentIndex(0)

    def get_leg(self) -> Optional[PositionLeg]:
        """Return a new PositionLeg from current values, or None if invalid."""
        try:
            strike = float(self.strike_edit.text().strip().replace(",", ""))
        except ValueError:
            return None
        exp = self.exp_combo.currentData()
        if exp is None:
            return None
        right = "C" if self.right_combo.currentText() == "Call" else "P"
        action = LegAction.BUY if self.action_combo.currentText() == "Buy" else LegAction.SELL
        mult = self.mult_spin.value()
        return PositionLeg(expiration=exp, strike=strike, right=right, action=action, multiplier=mult)


class _WorkerSignals(QObject):
    """Signals emitted by worker (must be QObject for cross-thread)."""
    expirations_ready = pyqtSignal(list)  # list of date
    leg_quotes_ready = pyqtSignal(list, float, float)  # resolved, lazy_total, smart_total
    error = pyqtSignal(str)


def _run_expirations(supplier: OptionsChainSupplier) -> List[date]:
    """Get expirations from supplier (blocking)."""
    return get_expirations(supplier)


def _run_leg_quotes(
    supplier: OptionsChainSupplier,
    legs: List[PositionLeg],
) -> Tuple[List[Tuple[PositionLeg, float, float]], float, float]:
    """Get leg quotes and totals (blocking); each leg has its own expiration."""
    return get_leg_quotes(supplier, legs)


class _IBWorker(QThread):
    """Single worker: one IB connection for expirations and for all leg quotes.
    Connects once, loads expirations, then processes quote requests (all legs at once per request).
    """

    def __init__(self) -> None:
        super().__init__()
        self._request_queue: "queue.Queue[Optional[List[PositionLeg]]]" = queue.Queue()
        self.signals = _WorkerSignals()

    def request_refresh(self, legs: List[PositionLeg]) -> None:
        """Request quotes for all legs in one go (thread-safe).
        Drops any pending requests so only this one is queued; new legs get filled as soon as worker is free.
        """
        try:
            drained: List[Optional[List[PositionLeg]]] = []
            while True:
                try:
                    x = self._request_queue.get_nowait()
                    if x is None:
                        drained.append(None)
                except queue.Empty:
                    break
            for x in drained:
                self._request_queue.put(x)
        except Exception:
            pass
        self._request_queue.put(legs)

    def stop(self) -> None:
        """Ask the worker to disconnect and exit."""
        self._request_queue.put(None)

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        supplier: Optional[IBKROptionsSupplier] = None
        try:
            supplier = IBKROptionsSupplier(client_id=IBKR_CLIENT_ID, use_frozen_data=True)
            try:
                supplier.connect()
            except Exception as e:
                get_connection_logger().error("Connection failed: %s", e)
                self.signals.error.emit((str(e) or "").strip() or "Connection failed")
                return
            try:
                expirations = supplier.get_expirations()
                self.signals.expirations_ready.emit(expirations)
            except Exception as e:
                get_connection_logger().error("Load expirations failed: %s", e)
                self.signals.error.emit((str(e) or "").strip() or "Load expirations failed")
                return
            while True:
                legs = self._request_queue.get()
                if legs is None:
                    break
                if not legs:
                    continue
                try:
                    resolved, lazy, smart = _run_leg_quotes(supplier, legs)
                    self.signals.leg_quotes_ready.emit(resolved, lazy, smart)
                except Exception as e:
                    get_connection_logger().error("Load leg quotes failed: %s", e)
                    self.signals.error.emit(
                        (str(e) or "").strip() or "Load leg quotes failed"
                    )
        finally:
            if supplier is not None:
                try:
                    supplier.disconnect()
                except Exception:
                    pass
            loop.close()


# ---- Main window ----


def _format_price(value: float) -> str:
    """Format price for display; empty if no data."""
    if value == 0.0:
        return ""
    return f"{value:.2f}"


def _debit_credit_color(amount: float) -> QColor:
    """Red for debit (positive), blue for credit (negative)."""
    if amount > 0:
        return QColor(180, 0, 0)
    return QColor(0, 0, 180)


def _user_friendly_error(raw: str) -> str:
    """Turn API/event-loop errors into a message that explains what to do."""
    raw_lower = raw.lower()
    if "event loop" in raw_lower or "dummy" in raw_lower or "no running" in raw_lower:
        return (
            "The data provider (TWS or IB Gateway) is not running or not reachable. "
            "Start TWS or IB Gateway, enable the API, and ensure it is listening on the configured port. "
            "Then click Connect or Load expirations.\n\nTechnical detail: " + raw
        )
    if "connection refused" in raw_lower or "connect" in raw_lower and "fail" in raw_lower:
        return (
            "Cannot connect to TWS or IB Gateway. Check that it is running and that "
            "API settings allow connections from this machine (host/port in .env).\n\nTechnical detail: " + raw
        )
    if "send" in raw_lower and ("none" in raw_lower or "nonetype" in raw_lower or "attribute" in raw_lower):
        return (
            "Connection lost or API not ready (socket error). "
            "Click Connect to reconnect, then try again.\n\nTechnical detail: " + raw
        )
    return raw


class PositionBuilderWindow(QMainWindow):
    """Window: ticker, expiration list, legs table, lazy/smart bot prices."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Position Builder – Lazy / Smart bot price")
        self._expirations: List[date] = []
        self._expirations_set: set = set()  # fast lookup for calendar
        self._selected_expiration: Optional[date] = None
        self._legs: List[PositionLeg] = []
        self._ib_worker: Optional[_IBWorker] = None
        self._refresh_after_quotes_loaded = False  # when True, run one more refresh when worker finishes (e.g. leg added while worker running)
        self._connected = False
        self._last_connect_was_auto = False
        self._connection_attempted_on_show = False
        self._suppress_leg_cell_change = False  # block itemChanged while we redraw/apply edit
        self._lazy_total: Optional[float] = None  # for P&L chart cost basis
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_prices)
        self._refresh_timer.setInterval(15_000)  # 15 seconds; active legs only, started when connected
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.timeout.connect(self._on_auto_reconnect)
        self._reconnect_timer.setInterval(60_000)  # 1 minute
        self._reconnect_timer.start()

        central = QWidget()
        main_layout = QHBoxLayout(central)
        scroll = QScrollArea()
        scroll.setWidget(central)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setCentralWidget(scroll)

        # ---- Left column: connection, underlying, calendar, P&L ----
        left = QWidget()
        left_layout = QVBoxLayout(left)

        conn_group = QGroupBox("API connection")
        conn_layout = QHBoxLayout(conn_group)
        conn_layout.addWidget(QLabel("Status:"))
        self.connection_label = QLabel("Disconnected")
        self.connection_label.setStyleSheet("font-weight: bold; color: gray;")
        conn_layout.addWidget(self.connection_label)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        conn_layout.addWidget(self.connect_btn)
        conn_layout.addStretch()
        left_layout.addWidget(conn_group)

        ticker_group = QGroupBox("Underlying")
        ticker_layout = QHBoxLayout(ticker_group)
        ticker_layout.addWidget(QLabel("Ticker:"))
        self.ticker_edit = QLineEdit()
        self.ticker_edit.setPlaceholderText("e.g. SPX")
        self.ticker_edit.setText("SPX")
        self.ticker_edit.setMaximumWidth(120)
        ticker_layout.addWidget(self.ticker_edit)
        self.load_exp_btn = QPushButton("Load expirations")
        self.load_exp_btn.clicked.connect(self._on_load_expirations)
        ticker_layout.addWidget(self.load_exp_btn)
        ticker_layout.addStretch()
        left_layout.addWidget(ticker_group)

        exp_row = QWidget()
        exp_row_layout = QHBoxLayout(exp_row)
        exp_row_layout.setContentsMargins(0, 0, 0, 0)
        exp_row_layout.addWidget(QLabel("Expiration (click an available date):"))
        self.expiration_date_label = QLabel("—")
        self.expiration_date_label.setStyleSheet("font-weight: bold;")
        exp_row_layout.addWidget(self.expiration_date_label)
        exp_row_layout.addStretch()
        left_layout.addWidget(exp_row)
        self.expiration_calendar = QCalendarWidget()
        self.expiration_calendar.setMinimumSize(320, 260)
        self.expiration_calendar.setGridVisible(True)
        self.expiration_calendar.clicked.connect(self._on_calendar_date_clicked)
        left_layout.addWidget(self.expiration_calendar)

        self._pnl_chart = None
        self._pnl_series = None
        self._pnl_axis_x = None
        self._pnl_axis_y = None
        if _HAS_QTCHARTS:
            pnl_group = QGroupBox("P&L at expiration")
            pnl_layout = QVBoxLayout(pnl_group)
            self._pnl_chart = QChart()
            self._pnl_chart.setTitle("P&L vs underlying price (intrinsic at expiry)")
            self._pnl_series = QLineSeries()
            self._pnl_series.setName("P&L")
            self._pnl_chart.addSeries(self._pnl_series)
            self._pnl_axis_x = QValueAxis()
            self._pnl_axis_x.setTitleText("Underlying")
            self._pnl_chart.addAxis(self._pnl_axis_x, Qt.AlignmentFlag.AlignBottom)
            self._pnl_series.attachAxis(self._pnl_axis_x)
            self._pnl_axis_y = QValueAxis()
            self._pnl_axis_y.setTitleText("P&L")
            self._pnl_chart.addAxis(self._pnl_axis_y, Qt.AlignmentFlag.AlignLeft)
            self._pnl_series.attachAxis(self._pnl_axis_y)
            self._pnl_chart.legend().setVisible(False)
            pnl_chart_view = QChartView(self._pnl_chart)
            pnl_chart_view.setMinimumHeight(200)
            pnl_chart_view.setMaximumHeight(260)
            pnl_layout.addWidget(pnl_chart_view)
            left_layout.addWidget(pnl_group)

        left_layout.addStretch()
        main_layout.addWidget(left, 1)  # ~half width

        # ---- Right column: add leg, legs table, composite, refresh, status ----
        right = QWidget()
        right_layout = QVBoxLayout(right)

        leg_group = QGroupBox("Add leg")
        leg_layout = QFormLayout(leg_group)
        self.strike_edit = QLineEdit()
        self.strike_edit.setPlaceholderText("e.g. 6000")
        leg_layout.addRow("Strike:", self.strike_edit)
        self.right_combo = QComboBox()
        self.right_combo.addItems(["Call", "Put"])
        leg_layout.addRow("Type:", self.right_combo)
        self.action_combo = QComboBox()
        self.action_combo.addItems(["Buy", "Sell"])
        leg_layout.addRow("Action:", self.action_combo)
        self.mult_spin = QSpinBox()
        self.mult_spin.setRange(1, 999)
        self.mult_spin.setValue(1)
        leg_layout.addRow("Multiplier:", self.mult_spin)
        self.add_leg_btn = QPushButton("Add leg")
        self.add_leg_btn.clicked.connect(self._on_add_leg)
        self.add_leg_btn.setEnabled(False)
        leg_layout.addRow(self.add_leg_btn)
        right_layout.addWidget(leg_group)

        right_layout.addWidget(QLabel("Legs (Bid / Ask from market):"))
        legs_header_widget = QWidget()
        legs_header_layout = QHBoxLayout(legs_header_widget)
        legs_header_layout.setContentsMargins(0, 0, 0, 2)
        legs_header_layout.addStretch()
        self.clear_all_legs_btn = QPushButton()
        _style = QApplication.instance().style() if QApplication.instance() else None
        _trash = _style.standardIcon(QStyle.StandardPixmap.SP_TrashIcon) if _style else None
        if _trash:
            self.clear_all_legs_btn.setIcon(_trash)
        else:
            self.clear_all_legs_btn.setText("\u2716")
        self.clear_all_legs_btn.setToolTip("Clear all legs")
        self.clear_all_legs_btn.setFixedSize(28, 22)
        self.clear_all_legs_btn.clicked.connect(self._on_clear_all_legs)
        legs_header_layout.addWidget(self.clear_all_legs_btn)
        right_layout.addWidget(legs_header_widget)
        self.legs_table = QTableWidget()
        self.legs_table.setColumnCount(10)
        self.legs_table.setHorizontalHeaderLabels(
            ["Expiration", "Strike", "Type", "Action", "Mult", "Bid", "Ask", "Delta", "Edit", "Remove"]
        )
        self.legs_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.legs_table.horizontalHeader().setSectionResizeMode(
            COL_EXPIRATION, QHeaderView.ResizeMode.Fixed
        )
        self.legs_table.setColumnWidth(COL_EXPIRATION, EXPIRATION_COLUMN_WIDTH)
        self.legs_table.horizontalHeader().setSectionResizeMode(
            COL_BID, QHeaderView.ResizeMode.Fixed
        )
        self.legs_table.horizontalHeader().setSectionResizeMode(
            COL_ASK, QHeaderView.ResizeMode.Fixed
        )
        self.legs_table.setColumnWidth(COL_BID, BID_ASK_MIN_WIDTH)
        self.legs_table.setColumnWidth(COL_ASK, BID_ASK_MIN_WIDTH)
        self.legs_table.horizontalHeader().setSectionResizeMode(
            COL_DELTA, QHeaderView.ResizeMode.Fixed
        )
        self.legs_table.setColumnWidth(COL_DELTA, 56)
        self.legs_table.setMinimumHeight(320)
        self.legs_table.setMaximumHeight(520)
        self.legs_table.itemChanged.connect(self._on_leg_cell_changed)
        right_layout.addWidget(self.legs_table)

        summary_group = QGroupBox("Composite price")
        summary_layout = QFormLayout(summary_group)
        self.lazy_label = QLabel("—")
        self.lazy_label.setStyleSheet("font-weight: bold;")
        summary_layout.addRow("Lazy bot price (buy=ask, sell=bid):", self.lazy_label)
        self.smart_label = QLabel("—")
        self.smart_label.setStyleSheet("font-weight: bold;")
        summary_layout.addRow("Smart bot price (mid):", self.smart_label)
        right_layout.addWidget(summary_group)

        self.refresh_btn = QPushButton("Refresh prices")
        self.refresh_btn.clicked.connect(self._request_leg_prices_refresh)
        right_layout.addWidget(self.refresh_btn)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(36)
        right_layout.addWidget(self.status_label)
        right_layout.addStretch()

        main_layout.addWidget(right, 1)  # ~half width

    def showEvent(self, event: Any) -> None:
        """Attempt connection when window is first shown."""
        super().showEvent(event)
        if not self._connection_attempted_on_show:
            self._connection_attempted_on_show = True
            self._last_connect_was_auto = True
            self._start_ib_worker()

    def _set_status_error(self, text: str) -> None:
        """Show error in status bar (red); no popup."""
        self.status_label.setText(text or "Error")
        self.status_label.setStyleSheet("color: red; font-size: 11px; font-weight: bold;")

    def _set_status_ok(self, text: str = "") -> None:
        """Clear error state or set neutral message (gray)."""
        self.status_label.setText(text)
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")

    def _set_connection_status(self, connected: bool) -> None:
        """Update connection status label, style, refresh timer, and Connect button."""
        self._connected = connected
        if connected:
            self.connection_label.setText("Connected")
            self.connection_label.setStyleSheet("font-weight: bold; color: darkgreen;")
            self.connect_btn.setEnabled(False)
            QTimer.singleShot(600, self._request_leg_prices_refresh)
            self._refresh_timer.start()
        else:
            self.connection_label.setText("Disconnected")
            self.connection_label.setStyleSheet("font-weight: bold; color: gray;")
            self._refresh_timer.stop()
            self.connect_btn.setEnabled(True)
            if self._ib_worker is not None:
                self._ib_worker.stop()
                self._ib_worker.wait(5000)
                try:
                    self._ib_worker.signals.expirations_ready.disconnect()
                    self._ib_worker.signals.leg_quotes_ready.disconnect()
                    self._ib_worker.signals.error.disconnect()
                except (TypeError, RuntimeError):
                    pass
                self._ib_worker = None

    def _start_ib_worker(self) -> None:
        """Start single IB worker: connect, load expirations, then process quote requests (all legs at once)."""
        if self._ib_worker is not None and self._ib_worker.isRunning():
            return
        get_connection_logger().info("Connection attempt (load expirations)...")
        self.load_exp_btn.setEnabled(False)
        self.connect_btn.setEnabled(False)
        self._ib_worker = _IBWorker()
        self._ib_worker.signals.expirations_ready.connect(self._on_expirations_loaded)
        self._ib_worker.signals.leg_quotes_ready.connect(self._on_leg_quotes_loaded)
        self._ib_worker.signals.leg_quotes_ready.connect(lambda *a: self._set_connection_status(True))
        self._ib_worker.signals.error.connect(self._on_ib_worker_error)
        self._ib_worker.finished.connect(self._on_ib_worker_finished)
        self._ib_worker.start()

    def _on_ib_worker_finished(self) -> None:
        """Re-enable Load expirations; Connect enabled only if disconnected."""
        self.load_exp_btn.setEnabled(True)
        self.connect_btn.setEnabled(not self._connected)

    def _on_ib_worker_error(self, message: str) -> None:
        """Single error handler: connection/expirations vs quotes."""
        if self._connected:
            self._on_quotes_error(message)
        else:
            self._on_expirations_error(message)

    def _on_connect_clicked(self) -> None:
        """Try to connect now (same as loading expirations; shows error on failure)."""
        self._last_connect_was_auto = False
        self._start_ib_worker()

    def _on_auto_reconnect(self) -> None:
        """Once per minute: if disconnected, try to connect without showing error on failure."""
        if self._connected:
            return
        if self._ib_worker is not None and self._ib_worker.isRunning():
            return
        self._last_connect_was_auto = True
        self._start_ib_worker()

    def _on_load_expirations(self) -> None:
        """Start worker: connect and load expirations (same connection used for leg quotes)."""
        self._last_connect_was_auto = False
        self._start_ib_worker()

    def _on_expirations_loaded(self, expirations: list) -> None:
        """Fill calendar with available expirations (highlight clickable dates) and mark connected."""
        self._set_connection_status(True)
        self._set_status_ok("")
        get_connection_logger().info("Connected; loaded %s expirations", len(expirations))
        # Clear previous highlights before setting new ones
        default_fmt = QTextCharFormat()
        for d in self._expirations:
            self.expiration_calendar.setDateTextFormat(QDate(d.year, d.month, d.day), default_fmt)
        self._expirations = sorted(expirations)
        self._expirations_set = set(self._expirations)
        # Highlight available expiration dates (bold, blue) – weekly and monthly
        fmt = QTextCharFormat()
        fmt.setFontWeight(700)
        fmt.setForeground(QColor(0, 70, 130))
        for d in self._expirations:
            self.expiration_calendar.setDateTextFormat(QDate(d.year, d.month, d.day), fmt)

    def _on_expirations_error(self, message: str) -> None:
        """Expirations worker failed: set disconnected; log to file; show error only if user clicked Connect/Load."""
        self._set_connection_status(False)
        get_connection_logger().warning("Connection/API error (expirations): %s", message)
        if not self._last_connect_was_auto:
            msg = (message or "").strip() or "Connection or API error (no details)."
            QMessageBox.warning(
                self,
                "Connection / API error",
                _user_friendly_error(msg),
            )

    def _on_quotes_error(self, message: str) -> None:
        """Quotes worker failed: log and show in status bar only (no popup); do NOT set disconnected."""
        get_connection_logger().warning("Connection/API error (quotes): %s", message)
        msg = (message or "").strip() or "Could not load prices (no details)."
        self._set_status_error("Prices: " + _user_friendly_error(msg))
        if self._refresh_after_quotes_loaded:
            self._refresh_after_quotes_loaded = False
            self._refresh_prices()
        elif self._connected:
            self._refresh_timer.start()

    def _update_expiration_date_label(self) -> None:
        """Show selected expiration date on the same line as the Expiration label."""
        if self._selected_expiration is not None:
            self.expiration_date_label.setText(self._selected_expiration.strftime("%Y-%m-%d"))
        else:
            self.expiration_date_label.setText("—")

    def _on_calendar_date_clicked(self, qdate: QDate) -> None:
        """When user clicks a date, use it if it is an available expiration (weekly/monthly)."""
        d = qdate.toPyDate()
        if d in self._expirations_set:
            self._selected_expiration = d
            self.expiration_calendar.setSelectedDate(qdate)
            self._update_expiration_date_label()
            self.add_leg_btn.setEnabled(True)
            self._request_leg_prices_refresh()
        else:
            self._set_status_ok("Date not available; click a highlighted date.")

    def _on_expiration_selected(self) -> None:
        """Called when selection should refresh; enable Add leg and refresh prices if we have legs."""
        self.add_leg_btn.setEnabled(self._current_expiration() is not None)
        self._request_leg_prices_refresh()

    def _leg_sort_key(self, leg: PositionLeg) -> Tuple[date, int, float]:
        """Order: expiration ascending, calls before puts, strike ascending."""
        return (leg.expiration, 0 if leg.right.upper() == "C" else 1, leg.strike)

    def _sort_legs(self) -> None:
        """Sort _legs by expiration (asc), then calls before puts, then strike (asc)."""
        self._legs.sort(key=self._leg_sort_key)

    def _restore_expiration_selection(self, exp: date) -> None:
        """Keep the given expiration selected in the calendar after adding a leg."""
        if self._current_expiration() == exp:
            return
        if exp in self._expirations_set:
            self._selected_expiration = exp
            self.expiration_calendar.blockSignals(True)
            self.expiration_calendar.setSelectedDate(QDate(exp.year, exp.month, exp.day))
            self.expiration_calendar.blockSignals(False)
            self._update_expiration_date_label()
            self.add_leg_btn.setEnabled(True)

    def _on_add_leg(self) -> None:
        """Add or merge leg: same expiration+strike+type updates multiplier (or nets with opposite action)."""
        exp = self._current_expiration()
        if exp is None:
            return
        try:
            strike = float(self.strike_edit.text().strip().replace(",", ""))
        except ValueError:
            QMessageBox.warning(self, "Add leg", "Enter a numeric strike.")
            return
        right = "C" if self.right_combo.currentText() == "Call" else "P"
        action = LegAction.BUY if self.action_combo.currentText() == "Buy" else LegAction.SELL
        mult = self.mult_spin.value()
        # Net with existing leg if same expiration, strike and type
        for i, existing in enumerate(self._legs):
            if (
                existing.expiration == exp
                and existing.strike == strike
                and existing.right.upper() == right
            ):
                # Net contracts: buy positive, sell negative
                existing_net = existing.multiplier if existing.action == LegAction.BUY else -existing.multiplier
                new_net = mult if action == LegAction.BUY else -mult
                net = existing_net + new_net
                if net == 0:
                    self._legs.pop(i)
                elif net > 0:
                    self._legs[i] = PositionLeg(
                        expiration=exp, strike=strike, right=right,
                        action=LegAction.BUY, multiplier=net,
                    )
                else:
                    self._legs[i] = PositionLeg(
                        expiration=exp, strike=strike, right=right,
                        action=LegAction.SELL, multiplier=abs(net),
                    )
                self._sort_legs()
                self._redraw_legs_table()
                self._recalculate_totals_from_table()
                self._request_leg_prices_refresh()
                self._restore_expiration_selection(exp)
                return
        self._legs.append(
            PositionLeg(expiration=exp, strike=strike, right=right, action=action, multiplier=mult)
        )
        self._sort_legs()
        self._redraw_legs_table()
        self._recalculate_totals_from_table()
        self._request_leg_prices_refresh()
        self._restore_expiration_selection(exp)

    def _on_edit_leg(self, row: int) -> None:
        """Open edit dialog for leg at row; replace, merge with same exp/strike/type, or clear price if strike changed."""
        if row < 0 or row >= len(self._legs):
            return
        leg = self._legs[row]
        d = _EditLegDialog(
            self,
            leg.expiration,
            leg.strike,
            leg.right,
            leg.action,
            leg.multiplier,
            self._expirations,
        )
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        new_leg = d.get_leg()
        if new_leg is None:
            QMessageBox.warning(self, "Edit leg", "Enter a numeric strike.")
            return
        exp, strike, right = new_leg.expiration, new_leg.strike, new_leg.right.upper()
        # If same (exp, strike, right) exists in another row, merge (same logic as add leg)
        for j, existing in enumerate(self._legs):
            if j == row:
                continue
            if (
                existing.expiration == exp
                and existing.strike == strike
                and existing.right.upper() == right
            ):
                existing_net = existing.multiplier if existing.action == LegAction.BUY else -existing.multiplier
                new_net = new_leg.multiplier if new_leg.action == LegAction.BUY else -new_leg.multiplier
                net = existing_net + new_net
                if net == 0:
                    self._legs.pop(max(row, j))
                    self._legs.pop(min(row, j))
                elif net > 0:
                    self._legs[j] = PositionLeg(
                        expiration=exp, strike=strike, right=right,
                        action=LegAction.BUY, multiplier=net,
                    )
                    self._legs.pop(row)
                else:
                    self._legs[j] = PositionLeg(
                        expiration=exp, strike=strike, right=right,
                        action=LegAction.SELL, multiplier=abs(net),
                    )
                    self._legs.pop(row)
                self._sort_legs()
                self._redraw_legs_table()
                self._recalculate_totals_from_table()
                self._request_leg_prices_refresh()
                return
        # No merge: replace this row's leg (strike/exp/right change -> no price in hand, redraw gives empty for that key)
        self._legs[row] = new_leg
        self._sort_legs()
        self._redraw_legs_table()
        self._recalculate_totals_from_table()
        self._request_leg_prices_refresh()

    def _row_for_cell_widget(self, widget: QWidget, column: int) -> int:
        """Return the table row that contains the given cell widget, or -1."""
        for r in range(self.legs_table.rowCount()):
            if self.legs_table.cellWidget(r, column) is widget:
                return r
        return -1

    def _on_remove_clicked(self) -> None:
        """Remove the leg in the row of the remove button; redraw so prices stay keyed by (date, strike, type)."""
        btn = self.sender()
        if btn is None:
            return
        row = self._row_for_cell_widget(btn, COL_REMOVE)
        if row < 0 or row >= len(self._legs):
            return
        self._legs.pop(row)
        self.legs_table.removeRow(row)
        self._redraw_legs_table()
        self._recalculate_totals_from_table()
        self._request_leg_prices_refresh()

    def _on_clear_all_legs(self) -> None:
        """Remove all legs; clear table and totals."""
        if not self._legs:
            return
        self._legs.clear()
        self._redraw_legs_table()
        self._set_totals_unknown()

    def _on_edit_clicked(self) -> None:
        """Open edit dialog for the leg in the row of the edit button that was clicked."""
        btn = self.sender()
        if btn is None:
            return
        row = self._row_for_cell_widget(btn, COL_EDIT)
        if row >= 0 and row < len(self._legs):
            self._on_edit_leg(row)

    def _row_for_leg(self, leg: PositionLeg) -> int:
        """Return table row index where _legs[row] matches (expiration, strike, right), or -1."""
        key = (leg.expiration, leg.strike, leg.right.upper())
        for row, L in enumerate(self._legs):
            if (L.expiration, L.strike, L.right.upper()) == key:
                return row
        return -1

    def _table_row_to_leg_key(self, r: int) -> Optional[Tuple[date, float, str]]:
        """Parse table row r into (expiration, strike, right) from cell content; None if invalid."""
        exp_item = self.legs_table.item(r, COL_EXPIRATION)
        strike_item = self.legs_table.item(r, COL_STRIKE)
        type_item = self.legs_table.item(r, COL_TYPE)
        if not exp_item or not strike_item or not type_item:
            return None
        try:
            exp = date.fromisoformat((exp_item.text() or "").strip())
        except ValueError:
            return None
        try:
            strike = float((strike_item.text() or "").strip().replace(",", ""))
        except ValueError:
            return None
        t = (type_item.text() or "").strip()
        right = "C" if t.lower() == "call" else "P" if t.lower() == "put" else ""
        if not right:
            return None
        return (exp, strike, right)

    def _recalculate_totals_from_table(self) -> None:
        """Compute lazy/smart totals from current table bid/ask and update labels.
        Uses _legs as source of truth (multipliers); table row i must correspond to _legs[i].
        """
        if not self._legs:
            self._set_totals_unknown()
            return
        if self.legs_table.rowCount() != len(self._legs):
            self._set_totals_unknown()
            return
        resolved: List[Tuple[PositionLeg, float, float]] = []
        for row, leg in enumerate(self._legs):
            bid_item = self.legs_table.item(row, COL_BID)
            ask_item = self.legs_table.item(row, COL_ASK)
            bid_s = (bid_item.text() or "").strip() if bid_item else ""
            ask_s = (ask_item.text() or "").strip() if ask_item else ""
            try:
                bid = float(bid_s) if bid_s else 0.0
            except ValueError:
                bid = 0.0
            try:
                ask = float(ask_s) if ask_s else 0.0
            except ValueError:
                ask = 0.0
            resolved.append((leg, bid, ask))
        if any(bid == 0.0 and ask == 0.0 for _, bid, ask in resolved):
            self._set_totals_unknown()
            return
        lazy = lazy_bot_total(resolved)
        smart = smart_bot_total(resolved)
        self._set_totals(lazy, smart)

    def _append_leg_row(self, leg: PositionLeg) -> None:
        """Append one row for the given leg; do not touch existing rows (prices stay intact)."""
        row = self.legs_table.rowCount()
        self.legs_table.insertRow(row)
        self.legs_table.setItem(row, COL_EXPIRATION, QTableWidgetItem(leg.expiration.strftime("%Y-%m-%d")))
        self.legs_table.setItem(row, COL_STRIKE, QTableWidgetItem(f"{leg.strike:.0f}"))
        self.legs_table.setItem(row, COL_TYPE, QTableWidgetItem("Call" if leg.is_call() else "Put"))
        action_item = QTableWidgetItem(leg.action.value)
        if leg.action == LegAction.BUY:
            action_item.setForeground(COLOR_BUY)
            action_item.setBackground(QBrush(COLOR_BUY_BG))
        else:
            action_item.setForeground(COLOR_SELL)
            action_item.setBackground(QBrush(COLOR_SELL_BG))
        self.legs_table.setItem(row, COL_ACTION, action_item)
        self.legs_table.setItem(row, COL_MULT, QTableWidgetItem(str(leg.multiplier)))
        bid_item = QTableWidgetItem("")
        bid_item.setFlags(bid_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.legs_table.setItem(row, COL_BID, bid_item)
        ask_item = QTableWidgetItem("")
        ask_item.setFlags(ask_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.legs_table.setItem(row, COL_ASK, ask_item)
        delta_item = QTableWidgetItem("—")
        delta_item.setFlags(delta_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.legs_table.setItem(row, COL_DELTA, delta_item)
        style = QApplication.instance().style() if QApplication.instance() else None
        trash_icon = style.standardIcon(QStyle.StandardPixmap.SP_TrashIcon) if style else None
        edit_btn = QPushButton("\u270E")
        edit_btn.setToolTip("Edit leg (strike, type, action, multiplier)")
        edit_btn.setFixedSize(28, 22)
        edit_btn.clicked.connect(self._on_edit_clicked)
        self.legs_table.setCellWidget(row, COL_EDIT, edit_btn)
        remove_btn = QPushButton()
        if trash_icon:
            remove_btn.setIcon(trash_icon)
        else:
            remove_btn.setText("\u2716")
        remove_btn.setToolTip("Remove this leg")
        remove_btn.setFixedSize(28, 22)
        remove_btn.clicked.connect(self._on_remove_clicked)
        self.legs_table.setCellWidget(row, COL_REMOVE, remove_btn)

    def _on_leg_cell_changed(self, item: QTableWidgetItem) -> None:
        """When user edits a leg cell (expiration, strike, type, action, mult), apply same logic as Edit."""
        if self._suppress_leg_cell_change:
            return
        col = item.column()
        if col not in (COL_EXPIRATION, COL_STRIKE, COL_TYPE, COL_ACTION, COL_MULT):
            return
        row = item.row()
        if row < 0 or row >= len(self._legs):
            return
        new_leg = self._leg_from_table_row(row)
        if new_leg is None:
            return
        self._suppress_leg_cell_change = True
        try:
            self._apply_leg_edit(row, new_leg)
        finally:
            self._suppress_leg_cell_change = False

    def _leg_from_table_row(self, row: int) -> Optional[PositionLeg]:
        """Build a PositionLeg from current table row content; None if invalid."""
        exp_item = self.legs_table.item(row, COL_EXPIRATION)
        strike_item = self.legs_table.item(row, COL_STRIKE)
        type_item = self.legs_table.item(row, COL_TYPE)
        action_item = self.legs_table.item(row, COL_ACTION)
        mult_item = self.legs_table.item(row, COL_MULT)
        if not all((exp_item, strike_item, type_item, action_item, mult_item)):
            return None
        try:
            exp = date.fromisoformat((exp_item.text() or "").strip())
        except ValueError:
            return None
        if exp not in self._expirations_set:
            return None
        try:
            strike = float((strike_item.text() or "").strip().replace(",", ""))
        except ValueError:
            return None
        t = (type_item.text() or "").strip()
        right = "C" if t.lower() == "call" else "P" if t.lower() == "put" else None
        if right is None:
            return None
        a = (action_item.text() or "").strip()
        action = LegAction.BUY if a.lower() == "buy" else LegAction.SELL if a.lower() == "sell" else None
        if action is None:
            return None
        try:
            mult = int(float((mult_item.text() or "1").strip()))
        except ValueError:
            mult = 1
        if mult < 1:
            mult = 1
        return PositionLeg(expiration=exp, strike=strike, right=right, action=action, multiplier=mult)

    def _apply_leg_edit(self, row: int, new_leg: PositionLeg) -> None:
        """Apply edit: merge if same (exp, strike, type) exists elsewhere, else replace; then sort, redraw, refresh."""
        exp, strike, right = new_leg.expiration, new_leg.strike, new_leg.right.upper()
        for j, existing in enumerate(self._legs):
            if j == row:
                continue
            if existing.expiration == exp and existing.strike == strike and existing.right.upper() == right:
                existing_net = existing.multiplier if existing.action == LegAction.BUY else -existing.multiplier
                new_net = new_leg.multiplier if new_leg.action == LegAction.BUY else -new_leg.multiplier
                net = existing_net + new_net
                if net == 0:
                    self._legs.pop(max(row, j))
                    self._legs.pop(min(row, j))
                elif net > 0:
                    self._legs[j] = PositionLeg(expiration=exp, strike=strike, right=right, action=LegAction.BUY, multiplier=net)
                    self._legs.pop(row)
                else:
                    self._legs[j] = PositionLeg(expiration=exp, strike=strike, right=right, action=LegAction.SELL, multiplier=abs(net))
                    self._legs.pop(row)
                self._sort_legs()
                self._redraw_legs_table()
                self._request_leg_prices_refresh()
                return
        self._legs[row] = new_leg
        self._sort_legs()
        self._redraw_legs_table()
        self._request_leg_prices_refresh()

    def _redraw_legs_table(self) -> None:
        """Rebuild table rows from _legs; preserve bid/ask/delta by (date, strike, type) from current table content."""
        self.legs_table.blockSignals(True)
        try:
            self._redraw_legs_table_impl()
        finally:
            self.legs_table.blockSignals(False)
        self._update_pnl_chart()

    def _redraw_legs_table_impl(self) -> None:
        price_by_leg: Dict[Tuple[date, float, str], Tuple[str, str, str]] = {}
        for r in range(self.legs_table.rowCount()):
            key = self._table_row_to_leg_key(r)
            if key is None:
                continue
            bid_item = self.legs_table.item(r, COL_BID)
            ask_item = self.legs_table.item(r, COL_ASK)
            delta_item = self.legs_table.item(r, COL_DELTA)
            bid_t = (bid_item.text() or "").strip()
            ask_t = (ask_item.text() or "").strip()
            delta_t = (delta_item.text() or "").strip() if delta_item else ""
            if bid_t or ask_t or delta_t:
                price_by_leg[key] = (bid_t, ask_t, delta_t)
        self.legs_table.setRowCount(len(self._legs))
        style = QApplication.instance().style() if QApplication.instance() else None
        trash_icon = style.standardIcon(QStyle.StandardPixmap.SP_TrashIcon) if style else None
        for row, leg in enumerate(self._legs):
            self.legs_table.setItem(
                row, COL_EXPIRATION, QTableWidgetItem(leg.expiration.strftime("%Y-%m-%d"))
            )
            self.legs_table.setItem(row, COL_STRIKE, QTableWidgetItem(f"{leg.strike:.0f}"))
            self.legs_table.setItem(
                row, COL_TYPE, QTableWidgetItem("Call" if leg.is_call() else "Put")
            )
            action_item = QTableWidgetItem(leg.action.value)
            if leg.action == LegAction.BUY:
                action_item.setForeground(COLOR_BUY)
                action_item.setBackground(QBrush(COLOR_BUY_BG))
            else:
                action_item.setForeground(COLOR_SELL)
                action_item.setBackground(QBrush(COLOR_SELL_BG))
            self.legs_table.setItem(row, COL_ACTION, action_item)
            self.legs_table.setItem(row, COL_MULT, QTableWidgetItem(str(leg.multiplier)))
            key = (leg.expiration, leg.strike, leg.right.upper())
            bid_t, ask_t, delta_t = price_by_leg.get(key, ("", "", ""))
            bid_item = QTableWidgetItem(bid_t)
            if bid_t:
                bid_item.setForeground(COLOR_BID)
            bid_item.setFlags(bid_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.legs_table.setItem(row, COL_BID, bid_item)
            ask_item = QTableWidgetItem(ask_t)
            if ask_t:
                ask_item.setForeground(COLOR_ASK)
            ask_item.setFlags(ask_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.legs_table.setItem(row, COL_ASK, ask_item)
            delta_item = QTableWidgetItem(delta_t if delta_t else "—")
            delta_item.setFlags(delta_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.legs_table.setItem(row, COL_DELTA, delta_item)
            edit_btn = QPushButton("\u270E")  # pencil
            edit_btn.setToolTip("Edit leg (strike, type, action, multiplier)")
            edit_btn.setFixedSize(28, 22)
            edit_btn.clicked.connect(self._on_edit_clicked)
            self.legs_table.setCellWidget(row, COL_EDIT, edit_btn)
            remove_btn = QPushButton()
            if trash_icon:
                remove_btn.setIcon(trash_icon)
            else:
                remove_btn.setText("\u2716")  # fallback X
            remove_btn.setToolTip("Remove this leg")
            remove_btn.setFixedSize(28, 22)
            remove_btn.clicked.connect(self._on_remove_clicked)
            self.legs_table.setCellWidget(row, COL_REMOVE, remove_btn)

    def _refresh_prices(self) -> None:
        """Request quotes for all legs at once from the single IB worker."""
        if not self._legs:
            self._set_totals_unknown()
            return
        if not self._connected or self._ib_worker is None or not self._ib_worker.isRunning():
            return
        self._ib_worker.request_refresh(self._legs.copy())

    def _request_leg_prices_refresh(self) -> None:
        """Trigger a price fetch (e.g. after add/edit/remove leg). Ensures periodic timer keeps running."""
        if not self._legs:
            return
        self._refresh_prices()
        if self._connected:
            self._refresh_timer.start()  # (re)start 15s periodic fetch

    def _current_expiration(self) -> Optional[date]:
        """Return selected expiration date or None."""
        return self._selected_expiration

    def _resolved_matches_current_legs(
        self,
        resolved: List[Tuple[PositionLeg, float, float, Optional[float]]],
    ) -> bool:
        """True iff resolved has same length and same (exp, strike, right) per index as _legs."""
        if len(resolved) != len(self._legs):
            return False
        for i, item in enumerate(resolved):
            leg = item[0]
            current = self._legs[i]
            if (
                leg.expiration != current.expiration
                or leg.strike != current.strike
                or leg.right.upper() != current.right.upper()
            ):
                return False
        return True

    def _on_leg_quotes_loaded(
        self,
        resolved: List[Tuple[PositionLeg, float, float, Optional[float]]],
        lazy_total: float,
        smart_total: float,
    ) -> None:
        """Update table bid/ask/delta by (date, strike, type); keep existing until we have new data.
        Only use worker's totals if resolved matches current _legs; otherwise recalc from table
        so multipliers/leg set are correct (avoids stale response overwriting after add/remove leg).
        """
        self._set_status_ok("")
        for item in resolved:
            leg = item[0]
            bid = item[1]
            ask = item[2]
            delta = item[3] if len(item) > 3 else None
            row = self._row_for_leg(leg)
            if row < 0 or row >= self.legs_table.rowCount():
                continue
            if bid != 0.0 or ask != 0.0:
                bid_item = QTableWidgetItem(_format_price(bid))
                bid_item.setForeground(COLOR_BID)
                self.legs_table.setItem(row, COL_BID, bid_item)
                ask_item = QTableWidgetItem(_format_price(ask))
                ask_item.setForeground(COLOR_ASK)
                self.legs_table.setItem(row, COL_ASK, ask_item)
            if delta is not None:
                self.legs_table.setItem(row, COL_DELTA, QTableWidgetItem(f"{delta:.2f}"))
        if self._resolved_matches_current_legs(resolved):
            self._set_totals(lazy_total, smart_total)
        else:
            self._recalculate_totals_from_table()
        # If all quotes are zero, hint: market closed (e.g. weekend) or strike not in chain
        if resolved and all(bid == 0.0 and ask == 0.0 for _, bid, ask, _ in resolved):
            self._set_status_ok(
                "No bid/ask (market may be closed—e.g. weekend). "
                "Otherwise check strike/expiration is in the chain."
            )
        # If a leg was added while this worker was running, run one more refresh with current legs
        if self._refresh_after_quotes_loaded:
            self._refresh_after_quotes_loaded = False
            self._refresh_prices()
        elif self._connected:
            self._refresh_timer.start()

    def _set_totals(self, lazy: float, smart: float) -> None:
        """Set lazy and smart labels with debit (red) / credit (blue); update P&L chart."""
        self._lazy_total = lazy
        lazy_text = f"{lazy:+.2f} (debit)" if lazy > 0 else f"{lazy:+.2f} (credit)"
        self.lazy_label.setText(lazy_text)
        self.lazy_label.setStyleSheet(
            f"font-weight: bold; color: {_debit_credit_color(lazy).name()};"
        )
        smart_text = f"{smart:+.2f} (debit)" if smart > 0 else f"{smart:+.2f} (credit)"
        self.smart_label.setText(smart_text)
        self.smart_label.setStyleSheet(
            f"font-weight: bold; color: {_debit_credit_color(smart).name()};"
        )
        self._update_pnl_chart()

    def _set_totals_unknown(self) -> None:
        """Clear totals when no expiration or no legs."""
        self._lazy_total = None
        self.lazy_label.setText("—")
        self.smart_label.setText("—")
        self.lazy_label.setStyleSheet("font-weight: bold;")
        self.smart_label.setStyleSheet("font-weight: bold;")
        self._update_pnl_chart()

    def _update_pnl_chart(self) -> None:
        """Refresh P&L-at-expiration curve from current legs and cost basis (lazy total). No-op if QtCharts not available."""
        if not _HAS_QTCHARTS or self._pnl_series is None or self._pnl_axis_x is None or self._pnl_axis_y is None:
            return
        self._pnl_series.clear()
        if not self._legs:
            self._pnl_axis_x.setRange(0, 100)
            self._pnl_axis_y.setRange(-1, 1)
            return
        strikes = [leg.strike for leg in self._legs]
        s_min = max(4000.0, min(strikes) - 400)
        s_max = min(10000.0, max(strikes) + 400)
        cost = self._lazy_total if self._lazy_total is not None else 0.0
        points = pnl_at_expiry_curve(self._legs, cost, s_min, s_max, 80)
        for s, pnl in points:
            self._pnl_series.append(s, pnl)
        self._pnl_axis_x.setRange(s_min, s_max)
        if points:
            pnls = [p for _, p in points]
            pad = (max(pnls) - min(pnls)) * 0.05 or 1.0
            self._pnl_axis_y.setRange(min(pnls) - pad, max(pnls) + pad)
        else:
            self._pnl_axis_y.setRange(-1, 1)

    def closeEvent(self, event: Any) -> None:
        """Stop single IB worker on close."""
        if self._ib_worker is not None:
            self._ib_worker.stop()
            self._ib_worker.wait(3000)
            self._ib_worker = None
        super().closeEvent(event)


# Default size applied on form open.
DEFAULT_FORM_WIDTH = 1173
DEFAULT_FORM_HEIGHT = 732


def main() -> None:
    """Run Position Builder window (for python -m spx_options.ui.position_builder)."""
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    win = PositionBuilderWindow()
    win.setMinimumWidth(900)
    win.setMinimumHeight(520)
    win.resize(max(DEFAULT_FORM_WIDTH, 900), max(DEFAULT_FORM_HEIGHT, 520))
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
