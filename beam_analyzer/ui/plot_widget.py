"""beam_analyzer.ui.plot_widget -- Matplotlib canvas embedded in Qt."""

from __future__ import annotations

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qt import NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget


class PlotWidget(FigureCanvasQTAgg):
    """Matplotlib figure embedded as a Qt widget."""

    def __init__(self, figsize: tuple[float, float] = (6, 6),
                 dpi: int = 100, parent=None) -> None:
        self.fig = Figure(figsize=figsize, dpi=dpi, tight_layout=True)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.updateGeometry()

    def fresh_ax(self):
        """Clear figure and return a new Axes."""
        self.fig.clear()
        return self.fig.add_subplot(111)

    def fresh_axes(self, *args, **kwargs):
        """Clear figure and return subplots."""
        self.fig.clear()
        return self.fig.subplots(*args, **kwargs)


class PlotWithToolbar(QWidget):
    """PlotWidget with a Matplotlib navigation toolbar."""

    def __init__(self, figsize: tuple[float, float] = (6, 6),
                 dpi: int = 100, parent=None) -> None:
        super().__init__(parent)
        self.canvas = PlotWidget(figsize=figsize, dpi=dpi)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.fig = self.canvas.fig

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

    def fresh_ax(self):
        return self.canvas.fresh_ax()

    def fresh_axes(self, *args, **kwargs):
        return self.canvas.fresh_axes(*args, **kwargs)

    def draw(self):
        self.canvas.draw()
