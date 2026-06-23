"""beam_analyzer.main -- Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from beam_analyzer.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Beam Analyzer")
    app.setOrganizationName("BeamAnalyzer")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
