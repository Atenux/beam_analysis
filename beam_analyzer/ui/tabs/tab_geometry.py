"""Tab 1 -- Geometry: STEP loading, slicing, side view, section view."""

from __future__ import annotations

import os
import tempfile

import numpy as np
from matplotlib.ticker import FuncFormatter

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from beam_analyzer.core.step_slicer import global_bounds, generate_side_view_image
from beam_analyzer.ui.plot_widget import PlotWithToolbar
from beam_analyzer.ui.worker import StepLoaderWorker, SliceWorker


class TabGeometry(QWidget):
    """Load a STEP file, slice it at N stations, show section properties."""

    slicing_finished = Signal()

    def __init__(self, state, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._loader: StepLoaderWorker | None = None
        self._slicer: SliceWorker | None = None
        self._station_xs: list[float] | None = None
        self._drag_station_index: int | None = None
        self._cid_press = None
        self._cid_move = None
        self._cid_release = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        left = QWidget()
        left.setMaximumWidth(320)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(8)
        splitter.addWidget(left)

        file_box = QGroupBox("STEP File")
        file_lay = QVBoxLayout(file_box)
        self._file_label = QLabel("No file loaded")
        self._file_label.setWordWrap(True)
        file_lay.addWidget(self._file_label)

        btn_row = QHBoxLayout()
        btn_open = QPushButton("Open STEP...")
        btn_open.clicked.connect(self._pick_step_file)
        btn_row.addWidget(btn_open)

        self._btn_gen_img = QPushButton("Generate Side View Image")
        self._btn_gen_img.setEnabled(False)
        self._btn_gen_img.clicked.connect(self._generate_side_view_image)
        self._btn_gen_img.setToolTip(
            "Generate a wireframe side view image from the STEP geometry "
            "and overlay it on the side view plot."
        )
        btn_row.addWidget(self._btn_gen_img)
        file_lay.addLayout(btn_row)

        self._img_visible_chk = QCheckBox("Show generated reference image")
        self._img_visible_chk.setChecked(True)
        self._img_visible_chk.toggled.connect(self._on_image_visibility_changed)
        self._img_visible_chk.setVisible(False)
        file_lay.addWidget(self._img_visible_chk)

        left_layout.addWidget(file_box)

        ctrl_box = QGroupBox("Slice Parameters")
        form = QFormLayout(ctrl_box)

        self._axis_combo = QComboBox()
        self._axis_combo.addItems(["X", "Y", "Z"])
        self._axis_combo.currentIndexChanged.connect(self._on_axis_changed)
        form.addRow("Beam direction:", self._axis_combo)

        self._n_spin = QSpinBox()
        self._n_spin.setRange(2, 200)
        self._n_spin.setValue(self._state.n_stations)
        form.addRow("Number of stations:", self._n_spin)

        self._deflection_spin = QDoubleSpinBox()
        self._deflection_spin.setRange(0.0001, 100.0)
        self._deflection_spin.setDecimals(4)
        self._deflection_spin.setValue(self._state.deflection)
        self._lbl_deflection = QLabel("Deflection tolerance (mm):")
        form.addRow(self._lbl_deflection, self._deflection_spin)

        self._xmin_spin = QDoubleSpinBox()
        self._xmin_spin.setRange(-1e6, 1e6)
        self._xmin_spin.setSpecialValueText("auto")
        self._xmin_spin.setValue(-1e6)
        self._lbl_xmin = QLabel("X min (mm):")
        form.addRow(self._lbl_xmin, self._xmin_spin)

        self._xmax_spin = QDoubleSpinBox()
        self._xmax_spin.setRange(-1e6, 1e6)
        self._xmax_spin.setSpecialValueText("auto")
        self._xmax_spin.setValue(1e6)
        self._lbl_xmax = QLabel("X max (mm):")
        form.addRow(self._lbl_xmax, self._xmax_spin)

        self._n_spin.valueChanged.connect(self._on_param_changed)
        self._xmin_spin.valueChanged.connect(self._on_param_changed)
        self._xmax_spin.valueChanged.connect(self._on_param_changed)

        left_layout.addWidget(ctrl_box)

        self._btn_slice = QPushButton("Compute Sections")
        self._btn_slice.setEnabled(False)
        self._btn_slice.setToolTip(
            "Compute cross-sections at the current slice positions. "
            "Drag vertical lines on the side view to adjust positions first."
        )
        self._btn_slice.clicked.connect(self._slice_at_current_positions)
        left_layout.addWidget(self._btn_slice)

        station_box = QGroupBox("Section Station")
        station_lay = QHBoxLayout(station_box)
        self._station_combo = QComboBox()
        self._station_combo.currentIndexChanged.connect(self._on_station_changed)
        station_lay.addWidget(self._station_combo)
        left_layout.addWidget(station_box)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        left_layout.addWidget(self._status_label)
        left_layout.addStretch()

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        splitter.addWidget(right)

        plot_tabs = QTabWidget()
        right_layout.addWidget(plot_tabs, stretch=2)

        self._side_view = PlotWithToolbar(figsize=(10, 3))
        plot_tabs.addTab(self._side_view, "Side View")
        self._connect_drag_handlers()

        self._section_view = PlotWithToolbar(figsize=(6, 6))
        plot_tabs.addTab(self._section_view, "Section at X")

        self._table = QTableWidget(0, 11)
        self._table.setHorizontalHeaderLabels([
            "X (mm)", "Area (mm^2)", "Yc (mm)", "Zc (mm)",
            "Iyy (mm^4)", "Izz (mm^4)", "Iyz (mm^4)",
            "Y_max (mm)", "Y_min (mm)", "Z_max (mm)", "Z_min (mm)",
        ])
        self._table.horizontalHeader().setStretchLastSection(True)
        right_layout.addWidget(self._table, stretch=1)

        splitter.setSizes([260, 900])

    def _pick_step_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open STEP file", "", "STEP files (*.step *.stp *.STEP *.STP)"
        )
        if not path:
            return
        self._state.step_path = path
        self._state.step_name = path.split("\\")[-1].split("/")[-1]
        self._file_label.setText(self._state.step_name)
        self._status_label.setText("Loading STEP...")
        self._btn_slice.setEnabled(False)

        self._loader = StepLoaderWorker(path, parent=self)
        self._loader.finished.connect(self._on_step_loaded)
        self._loader.error.connect(self._on_error)
        self._loader.start()

    def _on_step_loaded(self, parts: list) -> None:
        self._state.parts = parts
        self._state.all_part_names = [p.name for p in parts]

        self._state.all_part_x_ranges = []
        for part in parts:
            xmin, xmax = self._get_body_x_range(part)
            self._state.all_part_x_ranges.append((xmin, xmax))

        n = len(parts)
        self._compute_preview_stations()
        self._render_side_view()
        self._status_label.setText(
            f"Loaded {n} part(s). Generate side view, adjust slice positions, then click 'Compute Sections'."
        )
        self._btn_slice.setEnabled(True)
        self._btn_gen_img.setEnabled(True)

    def _get_body_x_range(self, part) -> tuple[float, float]:
        if hasattr(part, "bbox"):
            bbox = part.bbox
            return (bbox[0], bbox[3])
        if hasattr(part, "x_min") and hasattr(part, "x_max"):
            return (part.x_min, part.x_max)
        return (0.0, 0.0)

    def _compute_preview_stations(self) -> None:
        if not self._state.has_step():
            return
        xmin, xmax = global_bounds([ns.shape for ns in self._state.parts],
                                    axis=self._state.beam_axis)
        lf = self._state.length_factor
        xmin_user = self._xmin_spin.value() / lf
        xmax_user = self._xmax_spin.value() / lf
        if xmin_user > -1e5:
            xmin = xmin_user
        if xmax_user < 1e5:
            xmax = xmax_user
        n = self._n_spin.value()
        self._state.x_stations_override = list(np.linspace(xmin, xmax, n))
        self._station_xs = None

    def _on_param_changed(self) -> None:
        if self._state.section_data or not self._state.side_view_image_path:
            return
        self._compute_preview_stations()
        self._render_side_view()
        self._refresh_table()

    def _slice_at_current_positions(self) -> None:
        if not self._state.has_step():
            return
        self._status_label.setText("Slicing...")
        self._btn_slice.setEnabled(False)

        xs = self._state.x_stations_override
        if not xs:
            xmin, xmax = global_bounds([ns.shape for ns in self._state.parts],
                                        axis=self._state.beam_axis)
            lf = self._state.length_factor
            xmin_user = self._xmin_spin.value() / lf
            xmax_user = self._xmax_spin.value() / lf
            if xmin_user > -1e5:
                xmin = xmin_user
            if xmax_user < 1e5:
                xmax = xmax_user
            n = self._n_spin.value()
            xs = list(np.linspace(xmin, xmax, n))

        lf = self._state.length_factor
        self._state.deflection = self._deflection_spin.value() / lf
        self._station_xs = None

        self._slicer = SliceWorker(
            self._state.parts, xs,
            axis=self._state.beam_axis,
            deflection=self._state.deflection, parent=self
        )
        self._slicer.finished.connect(self._on_sliced)
        self._slicer.error.connect(self._on_error)
        self._slicer.start()

    def _on_sliced(self, results: list) -> None:
        self._state.section_data = results
        self._state.x_stations_override = [c.x for c in results]
        self._station_xs = None
        self._status_label.setText(f"{len(results)} section(s) computed.")
        self._btn_slice.setEnabled(True)
        self._populate_station_combo()
        self._refresh_plots()
        self._refresh_table()
        self.slicing_finished.emit()

    def _on_error(self, msg: str) -> None:
        self._status_label.setText(f"Error: {msg}")
        self._btn_slice.setEnabled(bool(self._state.has_step()))
        QMessageBox.critical(self, "Error", msg)

    def _on_station_changed(self, index: int) -> None:
        if index < 0 or not self._state.section_data:
            return
        self._plot_section_at(index)

    def _populate_station_combo(self) -> None:
        self._station_combo.blockSignals(True)
        self._station_combo.clear()
        lf = self._state.length_factor
        u = self._state.length_label
        ba = self._state.beam_axis_label
        for i, cut in enumerate(self._state.section_data):
            self._station_combo.addItem(f"{ba} = {cut.x * lf:.2f} {u} (station {i})")
        self._station_combo.blockSignals(False)

    def _refresh_plots(self) -> None:
        self._render_side_view()
        if self._state.section_data:
            self._plot_section_at(0)

    def _render_side_view(self) -> None:
        ax = self._side_view.fresh_ax()
        self._station_lines = []
        u = self._state.length_label
        ba = self._state.beam_axis_label
        _, sv = self._state.section_axis_labels

        has_image = (self._state.side_view_image_path
                     and self._state.side_view_image_visible
                     and os.path.isfile(self._state.side_view_image_path))
        has_sections = bool(self._state.section_data)
        xs_si = self._current_station_xs_si()

        if not has_image and not has_sections and not xs_si:
            ax.set_title("Side View -- no data")
            ax.set_xlabel(f"{ba} ({u})")
            ax.set_ylabel(f"{sv} ({u})")
            ax.grid(True, alpha=0.3)
            self._side_view.draw()
            return

        if has_image:
            self._overlay_reference_image(ax)

        if has_sections:
            z_min_vals = []
            z_max_vals = []
            x_vals = []
            for cut in self._state.section_data:
                if not cut.polygons:
                    continue
                z_min, z_max = self._get_cut_z_range(cut)
                if z_max <= z_min:
                    continue
                x_vals.append(cut.x)
                z_min_vals.append(z_min)
                z_max_vals.append(z_max)
            if x_vals:
                ax.plot(x_vals, z_max_vals, "k--", lw=1.5, alpha=0.6,
                        label="Top profile", zorder=2)
                ax.plot(x_vals, z_min_vals, "k--", lw=1.5, alpha=0.6,
                        label="Bottom profile", zorder=2)
                ax.fill_between(x_vals, z_min_vals, z_max_vals,
                                color="0.9", alpha=0.3, zorder=1)

        for i, x_val in enumerate(xs_si):
            line = ax.axvline(
                x=x_val, color="#1f77b4", lw=1.0, alpha=0.7, zorder=3,
                picker=5,
            )
            line._station_index = i
            self._station_lines.append(line)

        vertical_axis = {0: 2, 1: 2, 2: 1}[self._state.beam_axis]
        h_min, h_max = None, None
        v_min, v_max = None, None

        if has_sections and x_vals:
            h_min, h_max = min(x_vals), max(x_vals)
            v_min, v_max = min(z_min_vals), max(z_max_vals)
        elif has_image:
            h_min, h_max = self._state.side_view_image_xlim
            v_min, v_max = self._state.side_view_image_ylim
        else:
            h_min, h_max = global_bounds([ns.shape for ns in self._state.parts],
                                          axis=self._state.beam_axis)
            v_min, v_max = global_bounds([ns.shape for ns in self._state.parts],
                                          axis=vertical_axis)

        if h_min is not None and h_max is not None:
            h_pad = (h_max - h_min) * 0.05 if h_max > h_min else 1.0
            ax.set_xlim(h_min - h_pad, h_max + h_pad)
        if v_min is not None and v_max is not None:
            v_pad = (v_max - v_min) * 0.05 if v_max > v_min else 1.0
            ax.set_ylim(v_min - v_pad, v_max + v_pad)

        self._state.side_view_xlim = ax.get_xlim()
        self._state.side_view_ylim = ax.get_ylim()

        lf = self._state.length_factor
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v * lf:.4g}"))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v * lf:.4g}"))
        ax.set_xlabel(f"{ba} ({u})")
        ax.set_ylabel(f"{sv} ({u})")
        ax.set_title("Side View -- drag a slice line to reposition")
        ax.grid(True, alpha=0.3)
        if has_sections:
            ax.legend(fontsize=7, loc="best")
        self._side_view.draw()

    def _connect_drag_handlers(self) -> None:
        canvas = self._side_view.canvas
        self._cid_press = canvas.mpl_connect("pick_event", self._on_pick_station)
        self._cid_move = canvas.mpl_connect("motion_notify_event", self._on_drag_station)
        self._cid_release = canvas.mpl_connect("button_release_event", self._on_release_station)

    def _on_pick_station(self, event) -> None:
        line = event.artist
        idx = getattr(line, "_station_index", None)
        if idx is None:
            return
        toolbar = self._side_view.toolbar
        if getattr(toolbar, "mode", "") not in ("", "PAN", None):
            if toolbar.mode:
                return
        self._drag_station_index = idx

    def _on_drag_station(self, event) -> None:
        if self._drag_station_index is None:
            return
        if event.inaxes is None or event.xdata is None:
            return
        idx = self._drag_station_index
        xs = self._current_station_xs_si()
        if idx >= len(xs):
            self._drag_station_index = None
            return
        xs[idx] = float(event.xdata)
        self._station_xs = xs
        line = self._station_lines[idx]
        line.set_xdata([event.xdata, event.xdata])
        self._side_view.draw()

    def _on_release_station(self, event) -> None:
        if self._drag_station_index is None:
            return
        self._drag_station_index = None
        if self._station_xs is not None:
            self._state.x_stations_override = list(self._station_xs)
            self._refresh_table()
            self._status_label.setText(
                "Slice positions edited -- click 'Compute Sections' to update."
            )

    def _current_station_xs_si(self) -> list[float]:
        if self._station_xs is not None:
            return list(self._station_xs)
        if self._state.x_stations_override:
            return list(self._state.x_stations_override)
        return [c.x for c in self._state.section_data]

    def _get_cut_z_range(self, cut) -> tuple[float, float]:
        z_vals = []
        for poly in cut.polygons:
            coords = list(poly.exterior.coords)
            for pt in coords:
                z_vals.append(pt[1])
        if z_vals:
            return min(z_vals), max(z_vals)
        return 0.0, 0.0

    def _generate_side_view_image(self) -> None:
        if not self._state.parts:
            return

        self._status_label.setText("Generating side view image...")
        self._btn_gen_img.setEnabled(False)

        try:
            tmp_dir = tempfile.gettempdir()
            img_path = os.path.join(tmp_dir, "beam_analyzer_sideview.png")

            info = generate_side_view_image(
                self._state.parts, img_path,
                axis=self._state.beam_axis,
                deflection=self._state.deflection,
            )

            self._state.side_view_image_path = img_path
            self._state.side_view_image_visible = True
            self._state.side_view_image_xlim = info['xlim']
            self._state.side_view_image_ylim = info['ylim']
            self._img_visible_chk.setVisible(True)
            self._img_visible_chk.setChecked(True)
            self._img_visible_chk.setText(f"Show reference image ({info['width_px']}x{info['height_px']})")

            self._compute_preview_stations()
            self._status_label.setText(
                "Side view generated. Adjust stations and click 'Compute Sections'."
            )
            self._render_side_view()
            self._refresh_table()
        except Exception as e:
            QMessageBox.critical(self, "Image Generation Error", str(e))
            self._status_label.setText(f"Image generation failed: {e}")
        finally:
            self._btn_gen_img.setEnabled(True)

    def _on_image_visibility_changed(self, checked: bool) -> None:
        self._state.side_view_image_visible = checked
        self._render_side_view()

    def _overlay_reference_image(self, ax) -> None:
        import matplotlib.image as mpimg

        xlim = self._state.side_view_image_xlim
        ylim = self._state.side_view_image_ylim
        if xlim is None or ylim is None:
            return

        img = mpimg.imread(self._state.side_view_image_path)
        ax.imshow(img, extent=(xlim[0], xlim[1], ylim[0], ylim[1]),
                  aspect="auto", alpha=self._state.side_view_image_opacity,
                  zorder=0)

    def _plot_section_at(self, index: int) -> None:
        if not self._state.section_data or index >= len(self._state.section_data):
            return

        cut = self._state.section_data[index]
        ax = self._section_view.fresh_ax()

        for poly in cut.polygons:
            pts = np.array(list(poly.exterior.coords))
            ax.plot(pts[:, 0], pts[:, 1], color="#1f77b4", lw=1.5)
            ax.fill(pts[:, 0], pts[:, 1], color="#1f77b4", alpha=0.15)

        lf = self._state.length_factor
        u = self._state.length_label
        ba = self._state.beam_axis_label
        sh, sv = self._state.section_axis_labels
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v * lf:.4g}"))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v * lf:.4g}"))
        ax.set_aspect("equal")
        ax.set_xlabel(f"{sh} ({u})")
        ax.set_ylabel(f"{sv} ({u})")
        ax.set_title(f"Section at {ba} = {cut.x * lf:.2f} {u}")
        ax.grid(True, alpha=0.3)
        self._section_view.draw()

    def _refresh_table(self) -> None:
        lf = self._state.length_factor
        u = self._state.length_label
        ba = self._state.beam_axis_label

        if not self._state.section_data:
            xs = self._current_station_xs_si()
            self._table.setColumnCount(1)
            self._table.setHorizontalHeaderLabels([f"{ba} ({u})"])
            self._table.horizontalHeader().setStretchLastSection(True)
            self._table.setRowCount(len(xs))
            for r, x in enumerate(xs):
                item = QTableWidgetItem(f"{x * lf:.4g}")
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(r, 0, item)
            return

        from beam_analyzer.core.section_props import properties_from_polygons

        self._table.setColumnCount(11)
        af = self._state.area_factor
        inf = self._state.inertia_factor
        au = self._state.area_label
        iu = self._state.inertia_label
        sh, sv = self._state.section_axis_labels

        self._table.setHorizontalHeaderLabels([
            f"{ba} ({u})", f"Area ({au})", f"{sh}c ({u})", f"{sv}c ({u})",
            f"I{sh.lower()}{sh.lower()} ({iu})",
            f"I{sv.lower()}{sv.lower()} ({iu})",
            f"I{sh.lower()}{sv.lower()} ({iu})",
            f"{sh}_max ({u})", f"{sh}_min ({u})",
            f"{sv}_max ({u})", f"{sv}_min ({u})",
        ])
        self._table.horizontalHeader().setStretchLastSection(True)

        rows = []
        for cut in self._state.section_data:
            if not cut.polygons:
                continue
            try:
                props = properties_from_polygons(cut.polygons)
            except Exception:
                continue
            rows.append({
                "X": cut.x * lf,
                "A": props.A * af,
                "yc": props.yc * lf,
                "zc": props.zc * lf,
                "Iyy": props.Iyy * inf,
                "Izz": props.Izz * inf,
                "Iyz": props.Iyz * inf,
                "y_max": props.y_max * lf,
                "y_min": props.y_min * lf,
                "z_max": props.z_max * lf,
                "z_min": props.z_min * lf,
            })

        self._table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            keys = ["X", "A", "yc", "zc", "Iyy", "Izz", "Iyz", "y_max", "y_min", "z_max", "z_min"]
            for c, key in enumerate(keys):
                val = row[key]
                item = QTableWidgetItem(f"{val:.4g}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(r, c, item)

    def _on_axis_changed(self, index: int) -> None:
        self._state.beam_axis = index
        self._state.section_data = []
        self._state.x_stations_override = []
        self._state.side_view_image_path = ""
        self._state.side_view_image_xlim = None
        self._state.side_view_image_ylim = None
        self._station_xs = None
        self._img_visible_chk.setVisible(False)

        ba = self._state.beam_axis_label
        u = self._state.length_label
        self._lbl_xmin.setText(f"{ba} min ({u}):")
        self._lbl_xmax.setText(f"{ba} max ({u}):")

        self._compute_preview_stations()
        self._populate_station_combo()
        self._refresh_plots()
        self._refresh_table()
        if self._state.has_step():
            self._status_label.setText(
                f"Beam axis changed to {ba}. Generate side view, adjust positions, then click 'Compute Sections'."
            )

    def on_unit_changed(self, old_unit: str) -> None:
        new_unit = self._state.unit
        if old_unit == new_unit:
            return
        ratio = 25.4 if new_unit == "mm" else 1.0 / 25.4

        for spin in [self._xmin_spin, self._xmax_spin]:
            val = spin.value()
            if abs(val) < 1e5:
                spin.blockSignals(True)
                spin.setValue(val * ratio)
                spin.blockSignals(False)

        self._deflection_spin.blockSignals(True)
        self._deflection_spin.setValue(self._deflection_spin.value() * ratio)
        self._deflection_spin.blockSignals(False)

        ba = self._state.beam_axis_label
        u = self._state.length_label
        self._lbl_deflection.setText(f"Deflection tolerance ({u}):")
        self._lbl_xmin.setText(f"{ba} min ({u}):")
        self._lbl_xmax.setText(f"{ba} max ({u}):")

        self._populate_station_combo()
        self._refresh_plots()
        self._refresh_table()

    def refresh(self) -> None:
        self._populate_station_combo()
        self._refresh_plots()
        self._refresh_table()
