from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from main_window import MainWindow
from theme import ThemeManager


def main() -> int:
    app = QApplication(sys.argv)
    ThemeManager(app)
    app.setApplicationName("PilotMixer")
    app.setOrganizationName("PilotMixer")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
