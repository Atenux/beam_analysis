"""beam_analyzer.ui.worker -- QThread background workers for STEP loading and slicing."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from beam_analyzer.core.step_slicer import (
    NamedShape,
    StationCut,
    read_step_with_names,
    slice_assembly,
)


class StepLoaderWorker(QThread):
    """Load a STEP file in a background thread."""
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            parts = read_step_with_names(self.path)
            self.finished.emit(parts)
        except Exception as e:
            self.error.emit(str(e))


class SliceWorker(QThread):
    """Slice an assembly at stations along the beam axis in a background thread."""
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, named_shapes: list[NamedShape],
                 x_stations: list[float],
                 axis: int = 0,
                 deflection: float = 0.5, parent=None):
        super().__init__(parent)
        self.named_shapes = named_shapes
        self.x_stations = x_stations
        self.axis = axis
        self.deflection = deflection

    def run(self):
        try:
            cuts = slice_assembly(
                self.named_shapes, self.x_stations,
                axis=self.axis, deflection=self.deflection,
            )
            self.finished.emit(cuts)
        except Exception as e:
            self.error.emit(str(e))
