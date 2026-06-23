"""beam_analyzer.ui.main_window -- Application main window."""

from __future__ import annotations

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from beam_analyzer.ui.state import AppState
from beam_analyzer.ui.tabs.tab_geometry import TabGeometry
from beam_analyzer.ui.tabs.tab_results import TabResults
from beam_analyzer.ui.tabs.tab_shear import TabShear


class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = AppState()
        self.setWindowTitle("Beam Analyzer")
        self.resize(1400, 900)

        self._setup_menu()
        self._setup_toolbar()
        self._setup_tabs()

    def _setup_menu(self) -> None:
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")

        act_quit = QAction("&Quit", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        help_menu = mb.addMenu("&Help")
        act_about = QAction("&About", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    def _setup_toolbar(self) -> None:
        tb = QToolBar("Main toolbar")
        tb.setMovable(False)
        self.addToolBar(tb)

        self._status_label = QLabel("Ready")
        tb.addWidget(self._status_label)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)

        tb.addWidget(QLabel("Units:"))
        self._unit_combo = QComboBox()
        self._unit_combo.addItems(["mm", "inches"])
        self._unit_combo.currentTextChanged.connect(self._on_unit_changed)
        tb.addWidget(self._unit_combo)

    def _setup_tabs(self) -> None:
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.setCentralWidget(self._tabs)

        self._tab_geometry = TabGeometry(self.state)
        self._tab_results = TabResults(self.state)
        self._tab_shear = TabShear(self.state)

        self._tabs.addTab(self._tab_geometry, "1 -- Geometry")
        self._tabs.addTab(self._tab_results, "2 -- Results")
        self._tabs.addTab(self._tab_shear, "3 -- Shear")

        self._tabs.currentChanged.connect(self._on_tab_changed)

        self._tab_geometry.slicing_finished.connect(self._tab_results.refresh)
        self._tab_geometry.slicing_finished.connect(self._tab_shear.refresh)

    def _on_tab_changed(self, index: int) -> None:
        tab = self._tabs.widget(index)
        refresh = getattr(tab, "refresh", None)
        if callable(refresh):
            refresh()

    def _on_unit_changed(self, text: str) -> None:
        old_unit = self.state.unit
        self.state.unit = "in" if text == "inches" else "mm"
        if self.state.unit != old_unit:
            self._tab_geometry.on_unit_changed(old_unit)
            self._tab_results.refresh()
            self._tab_shear.refresh()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Beam Analyzer",
            "<b>Beam Analyzer</b><br><br>"
            "Cross-section analysis tool for beam structures.<br>"
            "Import STEP files, slice into sections, and compute "
            "geometric properties (area, centroid, moments of inertia).<br><br>"
            "Built with PySide6, cadquery-ocp, Shapely, and Matplotlib.",
        )

    def closeEvent(self, event) -> None:
        ans = QMessageBox.question(
            self, "Quit",
            "Quit Beam Analyzer?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()

