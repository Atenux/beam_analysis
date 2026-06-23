"""Tab 3 -- Shear: applied loads, V/M diagrams, transverse shear stress tau(z)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from beam_analyzer.core.beam_statics import (
    PointLoad, DistLoad, PointMoment, solve_beam,
)
from beam_analyzer.core.shear_stress import shear_stress_profile
from beam_analyzer.ui.plot_widget import PlotWithToolbar

LOAD_TYPES = ("Point load", "Distributed", "Moment")


class TabShear(QWidget):
    """Define loads/supports, solve the beam, and show shear-stress results."""

    def __init__(self, state, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._solution = None
        self._profiles: list[dict] = []   # per-station tau(z) results (display units)
        self._setup_ui()

    # ------------------------------------------------------------------ UI
    def _setup_ui(self) -> None:
        root = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        left = QWidget()
        left.setMaximumWidth(360)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(8, 8, 8, 8)
        left_lay.setSpacing(8)
        splitter.addWidget(left)

        # --- Supports ----------------------------------------------------
        sup_box = QGroupBox("Supports")
        sup_form = QFormLayout(sup_box)

        self._model_combo = QComboBox()
        self._model_combo.addItems(["Simply supported", "Cantilever"])
        self._model_combo.currentIndexChanged.connect(self._on_model_changed)
        sup_form.addRow("Beam model:", self._model_combo)

        self._supA_spin = QDoubleSpinBox()
        self._supA_spin.setRange(-1e9, 1e9)
        self._supA_spin.setDecimals(3)
        self._lbl_supA = QLabel("Support A pos:")
        sup_form.addRow(self._lbl_supA, self._supA_spin)

        self._supB_spin = QDoubleSpinBox()
        self._supB_spin.setRange(-1e9, 1e9)
        self._supB_spin.setDecimals(3)
        self._lbl_supB = QLabel("Support B pos:")
        sup_form.addRow(self._lbl_supB, self._supB_spin)

        self._fixed_combo = QComboBox()
        self._fixed_combo.addItems(["Fixed at left end", "Fixed at right end"])
        self._lbl_fixed = QLabel("Fixing:")
        sup_form.addRow(self._lbl_fixed, self._fixed_combo)

        left_lay.addWidget(sup_box)

        # --- Loads -------------------------------------------------------
        load_box = QGroupBox("Loads")
        load_lay = QVBoxLayout(load_box)

        self._loads_table = QTableWidget(0, 5)
        self._loads_table.setHorizontalHeaderLabels(
            ["Type", "Pos1", "Pos2", "Val1", "Val2"])
        self._loads_table.horizontalHeader().setStretchLastSection(True)
        load_lay.addWidget(self._loads_table)

        btn_row = QHBoxLayout()
        btn_pt = QPushButton("+ Point")
        btn_pt.clicked.connect(lambda: self._add_load_row("Point load"))
        btn_dist = QPushButton("+ Distributed")
        btn_dist.clicked.connect(lambda: self._add_load_row("Distributed"))
        btn_mom = QPushButton("+ Moment")
        btn_mom.clicked.connect(lambda: self._add_load_row("Moment"))
        btn_del = QPushButton("Remove")
        btn_del.clicked.connect(self._remove_selected_row)
        for b in (btn_pt, btn_dist, btn_mom, btn_del):
            btn_row.addWidget(b)
        load_lay.addLayout(btn_row)

        self._load_hint = QLabel(
            "Point: Pos1, Val1=force (down +).  "
            "Distributed: Pos1..Pos2, Val1..Val2=intensity.  "
            "Moment: Pos1, Val1=moment (CCW +)."
        )
        self._load_hint.setWordWrap(True)
        self._load_hint.setStyleSheet("color: gray; font-size: 10px;")
        load_lay.addWidget(self._load_hint)

        left_lay.addWidget(load_box)

        self._btn_compute = QPushButton("Compute shear stresses")
        self._btn_compute.clicked.connect(self._compute)
        left_lay.addWidget(self._btn_compute)

        station_box = QGroupBox("Section station for tau(z)")
        station_lay = QHBoxLayout(station_box)
        self._station_combo = QComboBox()
        self._station_combo.currentIndexChanged.connect(self._on_station_changed)
        station_lay.addWidget(self._station_combo)
        left_lay.addWidget(station_box)

        self._btn_export = QPushButton("Export shear CSV...")
        self._btn_export.clicked.connect(self._export_csv)
        left_lay.addWidget(self._btn_export)

        self._status = QLabel("Slice a STEP file first (Geometry tab).")
        self._status.setWordWrap(True)
        left_lay.addWidget(self._status)
        left_lay.addStretch()

        # --- Right: plots + table ---------------------------------------
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        splitter.addWidget(right)

        diag_box = QGroupBox("Shear & Moment Diagrams")
        diag_lay = QVBoxLayout(diag_box)
        self._diagram_plot = PlotWithToolbar(figsize=(10, 4))
        diag_lay.addWidget(self._diagram_plot)
        right_lay.addWidget(diag_box, stretch=2)

        tau_box = QGroupBox("Shear Stress Distribution tau(z)")
        tau_lay = QVBoxLayout(tau_box)
        self._tau_plot = PlotWithToolbar(figsize=(6, 5))
        tau_lay.addWidget(self._tau_plot)
        right_lay.addWidget(tau_box, stretch=2)

        sum_box = QGroupBox("Per-Station Summary")
        sum_lay = QVBoxLayout(sum_box)
        self._table = QTableWidget(0, 3)
        self._table.horizontalHeader().setStretchLastSection(True)
        sum_lay.addWidget(self._table)
        right_lay.addWidget(sum_box, stretch=1)

        splitter.setSizes([320, 1000])

        self._on_model_changed(0)

    # --------------------------------------------------------------- loads
    def _add_load_row(self, load_type: str) -> None:
        r = self._loads_table.rowCount()
        self._loads_table.insertRow(r)
        type_item = QTableWidgetItem(load_type)
        type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._loads_table.setItem(r, 0, type_item)

        x_lo, x_hi = self._domain_display()
        mid = 0.5 * (x_lo + x_hi)
        if load_type == "Point load":
            defaults = [f"{mid:.3f}", "", "100", ""]
        elif load_type == "Distributed":
            defaults = [f"{x_lo:.3f}", f"{x_hi:.3f}", "1", "1"]
        else:  # Moment
            defaults = [f"{mid:.3f}", "", "100", ""]
        for c, val in enumerate(defaults, start=1):
            self._loads_table.setItem(r, c, QTableWidgetItem(val))

    def _remove_selected_row(self) -> None:
        rows = sorted({i.row() for i in self._loads_table.selectedIndexes()},
                      reverse=True)
        for r in rows:
            self._loads_table.removeRow(r)

    def _parse_loads(self):
        """Read the loads table into solver dataclasses (internal units)."""
        lf = self._state.length_factor
        point_loads, dist_loads, moments = [], [], []

        def num(r, c, default=0.0):
            item = self._loads_table.item(r, c)
            if item is None or not item.text().strip():
                return default
            return float(item.text())

        for r in range(self._loads_table.rowCount()):
            kind = self._loads_table.item(r, 0).text()
            if kind == "Point load":
                point_loads.append(PointLoad(x=num(r, 1) / lf, fz=num(r, 3)))
            elif kind == "Distributed":
                # intensity is force/length; divide by lf to get per internal length
                dist_loads.append(DistLoad(
                    x1=num(r, 1) / lf, x2=num(r, 2) / lf,
                    w1=num(r, 3) * lf, w2=num(r, 4) * lf))
            elif kind == "Moment":
                # moment = force*length; scale length part to internal units
                moments.append(PointMoment(x=num(r, 1) / lf, m=num(r, 3) / lf))
        return point_loads, dist_loads, moments

    # ------------------------------------------------------------- domain
    def _station_xs_internal(self) -> list[float]:
        if self._state.section_data:
            return [c.x for c in self._state.section_data]
        return list(self._state.x_stations_override)

    def _domain_internal(self) -> tuple[float, float]:
        xs = self._station_xs_internal()
        if xs:
            return min(xs), max(xs)
        return 0.0, 1.0

    def _domain_display(self) -> tuple[float, float]:
        lo, hi = self._domain_internal()
        lf = self._state.length_factor
        return lo * lf, hi * lf

    # ------------------------------------------------------------- supports
    def _on_model_changed(self, _index: int) -> None:
        cantilever = self._model_combo.currentText() == "Cantilever"
        self._lbl_supA.setVisible(not cantilever)
        self._supA_spin.setVisible(not cantilever)
        self._lbl_supB.setVisible(not cantilever)
        self._supB_spin.setVisible(not cantilever)
        self._lbl_fixed.setVisible(cantilever)
        self._fixed_combo.setVisible(cantilever)

    def _support_positions_internal(self) -> list[float]:
        lf = self._state.length_factor
        lo, hi = self._domain_internal()
        if self._model_combo.currentText() == "Cantilever":
            fixed_left = self._fixed_combo.currentIndex() == 0
            return [lo if fixed_left else hi]
        return [self._supA_spin.value() / lf, self._supB_spin.value() / lf]

    # --------------------------------------------------------------- solve
    def _compute(self) -> None:
        if not self._state.section_data:
            QMessageBox.information(
                self, "No sections",
                "Process a STEP file on the Geometry tab first.")
            return
        try:
            point_loads, dist_loads, moments = self._parse_loads()
        except ValueError:
            QMessageBox.warning(self, "Invalid input",
                                "Load table contains non-numeric values.")
            return

        domain = self._domain_internal()
        supports = self._support_positions_internal()
        try:
            self._solution = solve_beam(
                domain, supports, point_loads, dist_loads, moments)
        except ValueError as e:
            QMessageBox.warning(self, "Solver error", str(e))
            return

        self._compute_profiles()
        self._populate_station_combo()
        self._plot_diagrams()
        self._refresh_table()
        if self._profiles:
            self._plot_tau(0)
        rsum = ", ".join(
            f"R@{x * self._state.length_factor:.3g}={R:.3g}{self._state.force_label}"
            for x, R in self._solution.reactions)
        self._status.setText(f"{self._solution.notes}. Reactions: {rsum}")

    def _compute_profiles(self) -> None:
        self._profiles = []
        lf = self._state.length_factor
        for cut in self._state.section_data:
            if not cut.polygons:
                continue
            V = self._solution.shear_at(cut.x)
            try:
                prof = shear_stress_profile(cut.polygons, V, length_factor=lf)
            except Exception:
                continue
            prof["X"] = cut.x
            prof["V"] = V
            self._profiles.append(prof)

    # ---------------------------------------------------------------- plots
    def _plot_diagrams(self) -> None:
        if self._solution is None:
            return
        lf = self._state.length_factor
        u = self._state.length_label
        ba = self._state.beam_axis_label
        fu = self._state.force_label

        ax_v, ax_m = self._diagram_plot.fresh_axes(2, 1, sharex=True)
        x = self._solution.x * lf

        ax_v.plot(x, self._solution.V, color="#1f77b4", lw=1.5)
        ax_v.axhline(0, color="k", lw=0.6)
        ax_v.fill_between(x, self._solution.V, 0, color="#1f77b4", alpha=0.15)
        ax_v.set_ylabel(f"V ({fu})")
        ax_v.set_title("Shear Force")
        ax_v.grid(True, alpha=0.3)

        # M carries a length unit; solution.M is in internal length -> scale to display.
        M_disp = self._solution.M * lf
        ax_m.plot(x, M_disp, color="#d62728", lw=1.5)
        ax_m.axhline(0, color="k", lw=0.6)
        ax_m.fill_between(x, M_disp, 0, color="#d62728", alpha=0.15)
        ax_m.set_xlabel(f"{ba} ({u})")
        ax_m.set_ylabel(f"M ({fu}*{u})")
        ax_m.set_title("Bending Moment")
        ax_m.grid(True, alpha=0.3)

        for xr, _R in self._solution.reactions:
            ax_v.axvline(xr * lf, color="green", lw=0.8, ls=":")
            ax_m.axvline(xr * lf, color="green", lw=0.8, ls=":")

        self._diagram_plot.draw()

    def _plot_tau(self, index: int) -> None:
        if index < 0 or index >= len(self._profiles):
            return
        prof = self._profiles[index]
        u = self._state.length_label
        su = self._state.stress_label
        lf = self._state.length_factor

        ax = self._tau_plot.fresh_ax()
        z = prof["z"]
        tau = prof["tau"]
        finite = np.isfinite(tau)
        ax.plot(tau[finite], z[finite], color="#1f77b4", lw=1.6)
        ax.fill_betweenx(z[finite], tau[finite], 0, color="#1f77b4", alpha=0.15)
        ax.axhline(prof["zc"], color="gray", lw=0.8, ls="--", label="centroid")
        ax.axvline(0, color="k", lw=0.6)
        x_disp = prof["X"] * lf
        ax.set_xlabel(f"Shear stress tau ({su})")
        ax.set_ylabel(f"Z ({u})")
        ax.set_title(
            f"tau(z) at {self._state.beam_axis_label} = {x_disp:.3g} {u}   "
            f"(V = {prof['V']:.3g} {self._state.force_label}, "
            f"tau_max = {prof['tau_max']:.3g} {su})")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
        self._tau_plot.draw()

    def _on_station_changed(self, index: int) -> None:
        if 0 <= index < len(self._profiles):
            self._plot_tau(index)

    def _populate_station_combo(self) -> None:
        self._station_combo.blockSignals(True)
        self._station_combo.clear()
        lf = self._state.length_factor
        u = self._state.length_label
        ba = self._state.beam_axis_label
        for i, prof in enumerate(self._profiles):
            self._station_combo.addItem(
                f"{ba} = {prof['X'] * lf:.2f} {u} (station {i})")
        self._station_combo.blockSignals(False)

    # ---------------------------------------------------------------- table
    def _refresh_table(self) -> None:
        u = self._state.length_label
        fu = self._state.force_label
        su = self._state.stress_label
        ba = self._state.beam_axis_label
        lf = self._state.length_factor

        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(
            [f"{ba} ({u})", f"V ({fu})", f"tau_max ({su})"])
        self._table.setRowCount(len(self._profiles))
        for r, prof in enumerate(self._profiles):
            vals = [prof["X"] * lf, prof["V"], prof["tau_max"]]
            for c, val in enumerate(vals):
                item = QTableWidgetItem(f"{val:.4g}")
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(r, c, item)

    # --------------------------------------------------------------- export
    def _export_csv(self) -> None:
        if not self._profiles:
            QMessageBox.information(self, "No data",
                                    "Compute shear stresses first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export shear CSV", "", "CSV Files (*.csv)")
        if not path:
            return
        rows = []
        for prof in self._profiles:
            for z, tau, t, Q in zip(prof["z"], prof["tau"], prof["t"], prof["Q"]):
                rows.append({
                    f"X_{self._state.length_label}": prof["X"] * self._state.length_factor,
                    f"V_{self._state.force_label}": prof["V"],
                    f"z_{self._state.length_label}": z,
                    f"width_{self._state.length_label}": t,
                    "Q": Q,
                    f"tau_{self._state.stress_label}": tau,
                })
        pd.DataFrame(rows).to_csv(path, index=False)
        QMessageBox.information(self, "Export complete", f"Saved to:\n{path}")

    # -------------------------------------------------------------- refresh
    def refresh(self) -> None:
        """Called when this tab is shown or geometry/units change."""
        u = self._state.length_label
        self._lbl_supA.setText(f"Support A pos ({u}):")
        self._lbl_supB.setText(f"Support B pos ({u}):")

        x_lo, x_hi = self._domain_display()
        if self._supA_spin.value() == 0.0 and self._supB_spin.value() == 0.0:
            self._supA_spin.setValue(x_lo)
            self._supB_spin.setValue(x_hi)

        if self._state.section_data:
            self._status.setText(
                f"{len(self._state.section_data)} sections available. "
                "Define loads and click 'Compute shear stresses'.")
        else:
            self._status.setText("Slice a STEP file first (Geometry tab).")
