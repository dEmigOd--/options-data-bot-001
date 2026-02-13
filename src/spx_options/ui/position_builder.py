"""
Position Builder UI: ticker, expirations, legs table with bid/ask, lazy and smart bot prices.
Runs IBKR supplier calls in a worker thread to keep UI responsive.
"""

from datetime import date
from typing import Any, List, Optional, Tuple

from PyQt6.QtCore import QObject, Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spx_options.position import (
    LegAction,
    PositionLeg,
    get_expirations,
    get_leg_quotes,
)
from spx_options.suppliers.base import OptionsChainSupplier
from spx_options.suppliers.ibkr import IBKROptionsSupplier


# ---- Worker thread for IBKR calls (blocking) ----


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
    expiration: date,
    legs: List[PositionLeg],
) -> Tuple[List[Tuple[PositionLeg, float, float]], float, float]:
    """Get leg quotes and totals (blocking)."""
    return get_leg_quotes(supplier, expiration, legs)


class _ExpirationsWorker(QThread):
    """Thread: load expirations and emit result."""

    def __init__(self, supplier: OptionsChainSupplier) -> None:
        super().__init__()
        self.supplier = supplier
        self.signals = _WorkerSignals()

    def run(self) -> None:
        try:
            expirations = _run_expirations(self.supplier)
            self.signals.expirations_ready.emit(expirations)
        except Exception as e:
            self.signals.error.emit(str(e))


class _LegQuotesWorker(QThread):
    """Thread: load leg quotes and totals, emit result."""

    def __init__(
        self,
        supplier: OptionsChainSupplier,
        expiration: date,
        legs: List[PositionLeg],
    ) -> None:
        super().__init__()
        self.supplier = supplier
        self.expiration = expiration
        self.legs = legs
        self.signals = _WorkerSignals()

    def run(self) -> None:
        try:
            resolved, lazy, smart = _run_leg_quotes(
                self.supplier, self.expiration, self.legs
            )
            self.signals.leg_quotes_ready.emit(resolved, lazy, smart)
        except Exception as e:
            self.signals.error.emit(str(e))


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


class PositionBuilderWindow(QMainWindow):
    """Window: ticker, expiration list, legs table, lazy/smart bot prices."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Position Builder – Lazy / Smart bot price")
        self._supplier: Optional[IBKROptionsSupplier] = None
        self._expirations: List[date] = []
        self._legs: List[PositionLeg] = []
        self._expirations_worker: Optional[_ExpirationsWorker] = None
        self._quotes_worker: Optional[_LegQuotesWorker] = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_prices)
        self._refresh_timer.setInterval(15_000)  # 15 seconds
        self._refresh_timer.start()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # ---- Ticker and expirations ----
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
        layout.addWidget(ticker_group)

        layout.addWidget(QLabel("Expiration (select one):"))
        self.expiration_list = QListWidget()
        self.expiration_list.setMaximumHeight(120)
        self.expiration_list.currentItemChanged.connect(self._on_expiration_selected)
        layout.addWidget(self.expiration_list)

        # ---- Add leg ----
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
        add_leg_btn = QPushButton("Add leg")
        add_leg_btn.clicked.connect(self._on_add_leg)
        leg_layout.addRow(add_leg_btn)
        layout.addWidget(leg_group)

        # ---- Legs table ----
        layout.addWidget(QLabel("Legs (Bid / Ask from market):"))
        self.legs_table = QTableWidget()
        self.legs_table.setColumnCount(5)
        self.legs_table.setHorizontalHeaderLabels(
            ["Strike", "Type", "Action", "Bid", "Ask"]
        )
        self.legs_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.legs_table.setMaximumHeight(200)
        layout.addWidget(self.legs_table)

        remove_leg_btn = QPushButton("Remove selected leg")
        remove_leg_btn.clicked.connect(self._on_remove_leg)
        layout.addWidget(remove_leg_btn)

        # ---- Summary prices ----
        summary_group = QGroupBox("Composite price")
        summary_layout = QFormLayout(summary_group)
        self.lazy_label = QLabel("—")
        self.lazy_label.setStyleSheet("font-weight: bold;")
        summary_layout.addRow("Lazy bot price (buy=ask, sell=bid):", self.lazy_label)
        self.smart_label = QLabel("—")
        self.smart_label.setStyleSheet("font-weight: bold;")
        summary_layout.addRow("Smart bot price (mid):", self.smart_label)
        layout.addWidget(summary_group)

        # ---- Refresh ----
        self.refresh_btn = QPushButton("Refresh prices")
        self.refresh_btn.clicked.connect(self._refresh_prices)
        layout.addWidget(self.refresh_btn)

        layout.addStretch()

    def _get_supplier(self) -> Optional[IBKROptionsSupplier]:
        """Return supplier instance; connection happens in worker thread on first use."""
        if self._supplier is None:
            self._supplier = IBKROptionsSupplier()
        return self._supplier

    def _on_load_expirations(self) -> None:
        """Start worker to load expirations for current ticker."""
        ticker = self.ticker_edit.text().strip() or "SPX"
        if self._expirations_worker is not None and self._expirations_worker.isRunning():
            return
        supplier = self._get_supplier()
        self.load_exp_btn.setEnabled(False)
        self._expirations_worker = _ExpirationsWorker(supplier)
        self._expirations_worker.signals.expirations_ready.connect(self._on_expirations_loaded)
        self._expirations_worker.signals.error.connect(self._on_worker_error)
        self._expirations_worker.finished.connect(
            lambda: self.load_exp_btn.setEnabled(True)
        )
        self._expirations_worker.start()

    def _on_expirations_loaded(self, expirations: list) -> None:
        """Fill expiration list from worker result."""
        self._expirations = expirations
        self.expiration_list.clear()
        for d in expirations:
            item = QListWidgetItem(d.strftime("%Y-%m-%d"))
            item.setData(Qt.ItemDataRole.UserRole, d)
            self.expiration_list.addItem(item)

    def _on_worker_error(self, message: str) -> None:
        """Show error from worker."""
        QMessageBox.warning(self, "Error", message)

    def _on_expiration_selected(self) -> None:
        """When user selects an expiration, refresh prices if we have legs."""
        self._refresh_prices()

    def _on_add_leg(self) -> None:
        """Parse strike/right/action and append leg, then refresh table and prices."""
        try:
            strike = float(self.strike_edit.text().strip().replace(",", ""))
        except ValueError:
            QMessageBox.warning(self, "Add leg", "Enter a numeric strike.")
            return
        right = "C" if self.right_combo.currentText() == "Call" else "P"
        action = LegAction.BUY if self.action_combo.currentText() == "Buy" else LegAction.SELL
        leg = PositionLeg(strike=strike, right=right, action=action)
        self._legs.append(leg)
        self._redraw_legs_table()
        self._refresh_prices()

    def _on_remove_leg(self) -> None:
        """Remove selected row from legs and table."""
        row = self.legs_table.currentRow()
        if row < 0 or row >= len(self._legs):
            return
        self._legs.pop(row)
        self._redraw_legs_table()
        self._refresh_prices()

    def _redraw_legs_table(self) -> None:
        """Rebuild table rows from _legs; bid/ask left empty until refresh."""
        self.legs_table.setRowCount(len(self._legs))
        for row, leg in enumerate(self._legs):
            self.legs_table.setItem(row, 0, QTableWidgetItem(f"{leg.strike:.0f}"))
            self.legs_table.setItem(
                row, 1, QTableWidgetItem("Call" if leg.is_call() else "Put")
            )
            self.legs_table.setItem(
                row, 2, QTableWidgetItem(leg.action.value))
            self.legs_table.setItem(row, 3, QTableWidgetItem(""))
            self.legs_table.setItem(row, 4, QTableWidgetItem(""))

    def _refresh_prices(self) -> None:
        """Start worker to get leg quotes and totals, or run sync if no legs."""
        exp = self._current_expiration()
        if exp is None or not self._legs:
            self._set_totals_unknown()
            return
        if self._quotes_worker is not None and self._quotes_worker.isRunning():
            return
        supplier = self._get_supplier()
        self._quotes_worker = _LegQuotesWorker(supplier, exp, self._legs.copy())
        self._quotes_worker.signals.leg_quotes_ready.connect(self._on_leg_quotes_loaded)
        self._quotes_worker.signals.error.connect(self._on_worker_error)
        self._quotes_worker.start()

    def _current_expiration(self) -> Optional[date]:
        """Return selected expiration date or None."""
        item = self.expiration_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _on_leg_quotes_loaded(
        self,
        resolved: List[Tuple[PositionLeg, float, float]],
        lazy_total: float,
        smart_total: float,
    ) -> None:
        """Update table bid/ask and summary labels from worker result."""
        for row, (leg, bid, ask) in enumerate(resolved):
            if row < self.legs_table.rowCount():
                self.legs_table.setItem(row, 3, QTableWidgetItem(_format_price(bid)))
                self.legs_table.setItem(row, 4, QTableWidgetItem(_format_price(ask)))
        self._set_totals(lazy_total, smart_total)

    def _set_totals(self, lazy: float, smart: float) -> None:
        """Set lazy and smart labels with debit (red) / credit (blue)."""
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

    def _set_totals_unknown(self) -> None:
        """Clear totals when no expiration or no legs."""
        self.lazy_label.setText("—")
        self.smart_label.setText("—")
        self.lazy_label.setStyleSheet("font-weight: bold;")
        self.smart_label.setStyleSheet("font-weight: bold;")

    def closeEvent(self, event: Any) -> None:
        """Disconnect supplier on close."""
        if self._supplier is not None:
            try:
                self._supplier.disconnect()
            except Exception:
                pass
            self._supplier = None
        super().closeEvent(event)


def main() -> None:
    """Run Position Builder window (for python -m spx_options.ui.position_builder)."""
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    win = PositionBuilderWindow()
    win.resize(520, 620)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
