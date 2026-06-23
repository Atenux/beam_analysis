"""Tab 2 -- Results: properties table, plots vs X, CSV export."""

from __future__ import annotations

import pandas as pd

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from beam_analyzer.core.section_props import properties_from_polygons
from beam_analyzer.ui.plot_widget import PlotWithToolbar


class TabResults(QWidget):
    """Display section properties, plot against geometry, export CSV."""

    def __init__(self, state, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._props_list: list[dict] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        top_row = QHBoxLayout()

        btn_export = QPushButton("Export CSV...")
        btn_export.clicked.connect(self._export_csv)
        top_row.addWidget(btn_export)

        self._info_label = QLabel("No section data available.")
        self._info_label.setWordWrap(True)
        top_row.addWidget(self._info_label, stretch=1)

        root.addLayout(top_row)

        self._plot_group = QGroupBox("Properties vs Station")
        plot_group = self._plot_group
        plot_lay = QVBoxLayout(plot_group)

        self._plot_area = PlotWithToolbar(figsize=(10, 4))
        plot_lay.addWidget(self._plot_area)

        self._plot_inertia = PlotWithToolbar(figsize=(10, 4))
        plot_lay.addWidget(self._plot_inertia)

        root.addWidget(plot_group, stretch=2)

        table_group = QGroupBox("Section Properties Table")
        table_lay = QVBoxLayout(table_group)

        self._table = QTableWidget(0, 11)
        self._table.setHorizontalHeaderLabels([
            "X (mm)", "Area (mm^2)", "Yc (mm)", "Zc (mm)",
            "Iyy (mm^4)", "Izz (mm^4)", "Iyz (mm^4)",
            "Y_max (mm)", "Y_min (mm)", "Z_max (mm)", "Z_min (mm)",
        ])
        self._table.horizontalHeader().setStretchLastSection(True)
        table_lay.addWidget(self._table)

        root.addWidget(table_group, stretch=1)

    def _compute_properties(self) -> None:
        self._props_list = []
        for cut in self._state.section_data:
            if not cut.polygons:
                continue
            try:
                props = properties_from_polygons(cut.polygons)
                self._props_list.append({
                    "X": cut.x,
                    "A": props.A,
                    "yc": props.yc,
                    "zc": props.zc,
                    "Iyy": props.Iyy,
                    "Izz": props.Izz,
                    "Iyz": props.Iyz,
                    "I1": props.I1,
                    "I2": props.I2,
                    "theta_pp_deg": props.theta_pp_deg,
                    "y_max": props.y_max,
                    "y_min": props.y_min,
                    "z_max": props.z_max,
                    "z_min": props.z_min,
                })
            except Exception:
                continue

    def _export_csv(self) -> None:
        if not self._props_list:
            self._compute_properties()
        if not self._props_list:
            QMessageBox.information(self, "No Data", "No section properties to export.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "", "CSV Files (*.csv)"
        )
        if not path:
            return

        lf = self._state.length_factor
        af = self._state.area_factor
        inf = self._state.inertia_factor
        unit_factors = {
            "X": lf, "A": af, "yc": lf, "zc": lf,
            "Iyy": inf, "Izz": inf, "Iyz": inf,
            "I1": inf, "I2": inf, "theta_pp_deg": 1.0,
            "y_max": lf, "y_min": lf, "z_max": lf, "z_min": lf,
        }
        converted = [
            {k: v * unit_factors.get(k, 1.0) for k, v in row.items()}
            for row in self._props_list
        ]
        df = pd.DataFrame(converted)
        df.to_csv(path, index=False)
        QMessageBox.information(self, "Export Complete", f"Saved to:\n{path}")

    def _overlay_reference_image(self, ax) -> None:
        import os
        import matplotlib.image as mpimg

        if not (self._state.side_view_image_path
                and self._state.side_view_image_visible
                and os.path.isfile(self._state.side_view_image_path)):
            return

        xlim = self._state.side_view_image_xlim
        if xlim is None:
            return

        lf = self._state.length_factor

        if self._state.side_view_xlim is not None:
            x_min, x_max = self._state.side_view_xlim[0] * lf, self._state.side_view_xlim[1] * lf
        elif self._props_list:
            x_vals = [p["X"] for p in self._props_list]
            x_min, x_max = min(x_vals) * lf, max(x_vals) * lf
        else:
            x_min, x_max = xlim[0] * lf, xlim[1] * lf

        if self._state.side_view_ylim is not None:
            y_geo_min, y_geo_max = self._state.side_view_ylim[0] * lf, self._state.side_view_ylim[1] * lf
        else:
            y_geo_min, y_geo_max = ax.get_ylim()

        img = mpimg.imread(self._state.side_view_image_path)

        ax_img = ax.twinx()
        ax_img.imshow(img, extent=(x_min, x_max, y_geo_min, y_geo_max),
                      aspect="auto", alpha=self._state.side_view_image_opacity,
                      zorder=0)
        ax_img.set_ylim(y_geo_min, y_geo_max)
        ax_img.set_xlim(x_min, x_max)
        ax_img.set_yticks([])
        ax_img.set_zorder(ax.get_zorder() - 1)
        ax.set_zorder(ax.get_zorder() + 1)

    def _plot_properties(self) -> None:
        if not self._props_list:
            ax = self._plot_area.fresh_ax()
            ax.set_title("No data -- process a STEP file first")
            self._plot_area.draw()
            return

        lf = self._state.length_factor
        af = self._state.area_factor
        inf = self._state.inertia_factor
        u = self._state.length_label
        au = self._state.area_label
        iu = self._state.inertia_label
        ba = self._state.beam_axis_label
        sh, sv = self._state.section_axis_labels

        xs = [p["X"] * lf for p in self._props_list]

        ax = self._plot_area.fresh_ax()
        ax.plot(xs, [p["A"] * af for p in self._props_list], "o-", label="Area", lw=1.5)
        ax.set_xlabel(f"{ba} Station ({u})")
        ax.set_ylabel(f"Area ({au})")
        ax.set_title(f"Cross-Section Area vs {ba}")
        ax.grid(True, alpha=0.3)
        ax.legend()
        self._overlay_reference_image(ax)
        self._plot_area.draw()

        lbl_hh = f"I{sh.lower()}{sh.lower()}"
        lbl_vv = f"I{sv.lower()}{sv.lower()}"

        ax2 = self._plot_inertia.fresh_ax()
        ax2.plot(xs, [p["Iyy"] * inf for p in self._props_list], "o-", label=lbl_hh, lw=1.5)
        ax2.plot(xs, [p["Izz"] * inf for p in self._props_list], "s-", label=lbl_vv, lw=1.5)
        ax2.plot(xs, [p["I1"] * inf for p in self._props_list], "d-", label="I1 (principal)", lw=1.5)
        ax2.plot(xs, [p["I2"] * inf for p in self._props_list], "^-", label="I2 (principal)", lw=1.5)
        ax2.set_xlabel(f"{ba} Station ({u})")
        ax2.set_ylabel(f"Moment of Inertia ({iu})")
        ax2.set_title(f"Moments of Inertia vs {ba}")
        ax2.grid(True, alpha=0.3)
        ax2.legend()
        self._overlay_reference_image(ax2)
        self._plot_inertia.draw()

    def _refresh_table(self) -> None:
        lf = self._state.length_factor
        af = self._state.area_factor
        inf = self._state.inertia_factor
        u = self._state.length_label
        au = self._state.area_label
        iu = self._state.inertia_label

        ba = self._state.beam_axis_label
        sh, sv = self._state.section_axis_labels

        self._table.setHorizontalHeaderLabels([
            f"{ba} ({u})", f"Area ({au})", f"{sh}c ({u})", f"{sv}c ({u})",
            f"I{sh.lower()}{sh.lower()} ({iu})",
            f"I{sv.lower()}{sv.lower()} ({iu})",
            f"I{sh.lower()}{sv.lower()} ({iu})",
            f"{sh}_max ({u})", f"{sh}_min ({u})",
            f"{sv}_max ({u})", f"{sv}_min ({u})",
        ])

        factors = [lf, af, lf, lf, inf, inf, inf, lf, lf, lf, lf]
        keys = ["X", "A", "yc", "zc", "Iyy", "Izz", "Iyz", "y_max", "y_min", "z_max", "z_min"]

        self._table.setRowCount(len(self._props_list))
        for r, row in enumerate(self._props_list):
            for c, key in enumerate(keys):
                val = row[key] * factors[c]
                item = QTableWidgetItem(f"{val:.4g}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(r, c, item)

    def refresh(self) -> None:
        if not self._state.section_data:
            self._info_label.setText("No section data available. Process a STEP file first.")
            self._props_list = []
            self._plot_properties()
            self._table.setRowCount(0)
            return

        self._compute_properties()
        n = len(self._props_list)
        self._info_label.setText(f"{n} section(s) with computed properties.")
        self._plot_properties()
        self._refresh_table()
