"""Main UI: pick expiration, option kind, strike; view option price vs time."""

import sys
from datetime import date, datetime
from typing import List, Optional, Tuple

from PyQt6.QtCharts import QChart, QChartView, QDateTimeAxis, QLineSeries, QValueAxis
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QWidget,
)

from spx_options.db.repository import OptionsRepository


def _datetime_to_ms(dt: datetime) -> float:
    """Convert datetime to milliseconds since epoch for QDateTimeAxis."""
    return dt.timestamp() * 1000.0


class OptionViewerWindow(QMainWindow):
    """Window: expiration, call/put, strike selectors + price vs time chart."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SPX Options – Price vs Time")
        self.repo = OptionsRepository()
        self.repo.ensure_schema()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        # Controls
        layout.addWidget(QLabel("Expiration:"))
        self.exp_combo = QComboBox()
        self.exp_combo.setMinimumWidth(120)
        self.exp_combo.currentIndexChanged.connect(self._on_expiration_changed)
        layout.addWidget(self.exp_combo)

        layout.addWidget(QLabel("Kind:"))
        self.kind_combo = QComboBox()
        self.kind_combo.addItems(["Call", "Put"])
        self.kind_combo.currentIndexChanged.connect(self._on_selection_changed)
        layout.addWidget(self.kind_combo)

        layout.addWidget(QLabel("Strike:"))
        self.strike_combo = QComboBox()
        self.strike_combo.setMinimumWidth(100)
        self.strike_combo.currentIndexChanged.connect(self._on_selection_changed)
        layout.addWidget(self.strike_combo)

        # Chart
        self.chart = QChart()
        self.chart.setTitle("Option price vs time")
        self.chart.legend().setVisible(True)
        self._series_bid = QLineSeries()
        self._series_bid.setName("Bid")
        self._series_ask = QLineSeries()
        self._series_ask.setName("Ask")
        self._series_last = QLineSeries()
        self._series_last.setName("Last")
        self.chart.addSeries(self._series_bid)
        self.chart.addSeries(self._series_ask)
        self.chart.addSeries(self._series_last)

        self._axis_x = QDateTimeAxis()
        self._axis_x.setTickCount(8)
        self._axis_x.setFormat("MM/dd HH:mm")
        self.chart.addAxis(self._axis_x, Qt.AlignmentFlag.AlignBottom)
        self._series_bid.attachAxis(self._axis_x)
        self._series_ask.attachAxis(self._axis_x)
        self._series_last.attachAxis(self._axis_x)

        self._axis_y = QValueAxis()
        self.chart.addAxis(self._axis_y, Qt.AlignmentFlag.AlignLeft)
        self._series_bid.attachAxis(self._axis_y)
        self._series_ask.attachAxis(self._axis_y)
        self._series_last.attachAxis(self._axis_y)

        self.chart_view = QChartView(self.chart)
        self.chart_view.setMinimumSize(600, 400)
        layout.addWidget(self.chart_view, stretch=1)

        self._load_expirations()
        self._on_expiration_changed()

    def _load_expirations(self) -> None:
        expirations = self.repo.get_available_expirations()
        self.exp_combo.clear()
        for e in expirations:
            self.exp_combo.addItem(e.strftime("%Y-%m-%d"), e)
        if not expirations:
            self.exp_combo.addItem("(no data)", None)

    def _on_expiration_changed(self) -> None:
        exp = self.exp_combo.currentData()
        self.strike_combo.clear()
        if exp is not None:
            strikes = self.repo.get_strikes_for_expiration(exp)
            for s in strikes:
                self.strike_combo.addItem(f"{s:.0f}", s)
        if self.strike_combo.count() == 0:
            self.strike_combo.addItem("(none)", None)
        self._on_selection_changed()

    def _on_selection_changed(self) -> None:
        exp: Optional[date] = self.exp_combo.currentData()
        strike = self.strike_combo.currentData()
        kind = "C" if self.kind_combo.currentText() == "Call" else "P"
        if exp is None or strike is None:
            self._set_chart_data([])
            return
        history: List[Tuple[datetime, float, float, float]] = self.repo.get_price_history(
            exp, strike, kind
        )
        self._set_chart_data(history)

    def _set_chart_data(
        self, history: List[Tuple[datetime, float, float, float]]
    ) -> None:
        self._series_bid.clear()
        self._series_ask.clear()
        self._series_last.clear()
        if not history:
            return
        for dt, bid, ask, last in history:
            ms = _datetime_to_ms(dt)
            self._series_bid.append(ms, bid)
            self._series_ask.append(ms, ask)
            self._series_last.append(ms, last)
        # Adjust Y range
        all_vals = [v for row in history for v in row[1:4] if row]
        if all_vals:
            mn, mx = min(all_vals), max(all_vals)
            margin = (mx - mn) * 0.1 or 1
            self._axis_y.setRange(mn - margin, mx + margin)


def main() -> None:
    app = QApplication(sys.argv)
    win = OptionViewerWindow()
    win.resize(900, 500)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
