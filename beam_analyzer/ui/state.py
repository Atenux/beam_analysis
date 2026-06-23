"""beam_analyzer.ui.state -- Central application state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppState:
    """Shared state across all tabs."""
    step_path: str = ""
    step_name: str = ""
    parts: list = field(default_factory=list)
    all_part_names: list[str] = field(default_factory=list)
    all_part_x_ranges: list = field(default_factory=list)

    n_stations: int = 10
    deflection: float = 0.5
    x_stations_override: list[float] = field(default_factory=list)

    section_data: list = field(default_factory=list)
    props_df: Any = None

    side_view_image_path: str = ""
    side_view_image_visible: bool = True
    side_view_image_xlim: tuple[float, float] | None = None
    side_view_image_ylim: tuple[float, float] | None = None
    side_view_image_opacity: float = 0.5
    side_view_xlim: tuple[float, float] | None = None
    side_view_ylim: tuple[float, float] | None = None

    unit: str = "mm"
    beam_axis: int = 0

    def has_step(self) -> bool:
        return bool(self.step_path) and bool(self.parts)

    @property
    def length_factor(self) -> float:
        return 1.0 if self.unit == "mm" else 1.0 / 25.4

    @property
    def area_factor(self) -> float:
        return self.length_factor ** 2

    @property
    def inertia_factor(self) -> float:
        return self.length_factor ** 4

    @property
    def length_label(self) -> str:
        return "mm" if self.unit == "mm" else "in"

    @property
    def area_label(self) -> str:
        return "mm^2" if self.unit == "mm" else "in^2"

    @property
    def inertia_label(self) -> str:
        return "mm^4" if self.unit == "mm" else "in^4"

    @property
    def force_label(self) -> str:
        return "N" if self.unit == "mm" else "lbf"

    @property
    def dist_load_label(self) -> str:
        return "N/mm" if self.unit == "mm" else "lbf/in"

    @property
    def stress_label(self) -> str:
        return "MPa" if self.unit == "mm" else "psi"

    @property
    def beam_axis_label(self) -> str:
        return "XYZ"[self.beam_axis]

    @property
    def section_axis_labels(self) -> tuple[str, str]:
        return {0: ("Y", "Z"), 1: ("X", "Z"), 2: ("X", "Y")}[self.beam_axis]
