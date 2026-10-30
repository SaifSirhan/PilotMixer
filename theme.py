from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


BLACK = "#000000"
PANEL = "#050a07"
PANEL_RAISED = "#09130d"
BORDER = "#1d4032"
MINT = "#66ffc2"
MINT_DARK = "#2d7a5c"
AMBER = "#ffc857"
RED = "#ff5566"
TEXT = "#bdd8ca"
MUTED = "#60786b"


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    font = QFont()
    font.setFamilies(["Cascadia Mono", "Consolas"])
    font.setPointSize(9)
    app.setFont(font)
    app.setStyleSheet(
        f"""
        QMainWindow, QWidget#root {{
            background: {BLACK};
            color: {TEXT};
        }}
        QWidget {{
            font-family: 'Cascadia Mono', 'Consolas';
            color: {TEXT};
        }}
        QFrame#headerBar, QFrame#deviceBar, QFrame#footerBar {{
            background: {PANEL};
            border: 1px solid {BORDER};
        }}
        QFrame#panel {{
            background: {PANEL};
            border: 1px solid {BORDER};
        }}
        QFrame#strip {{
            background: {PANEL_RAISED};
            border: 1px solid {BORDER};
        }}
        QLabel {{
            background: transparent;
        }}
        QLabel#brand {{
            color: {MINT};
            font-size: 27px;
            font-weight: 700;
            letter-spacing: 7px;
        }}
        QLabel#subBrand {{
            color: {MUTED};
            font-size: 9px;
            letter-spacing: 2px;
        }}
        QLabel#sectionTitle {{
            color: {MINT};
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 2px;
        }}
        QLabel#sectionMeta {{
            color: {MUTED};
            font-size: 8px;
            letter-spacing: 1px;
        }}
        QLabel#stripLabel {{
            color: {TEXT};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1px;
        }}
        QLabel#stripMeta {{
            color: {MUTED};
            font-size: 8px;
        }}
        QLabel#matrixHead {{
            color: {MINT};
            font-size: 8px;
            font-weight: 700;
            letter-spacing: 1px;
        }}
        QLabel#matrixRow {{
            color: {TEXT};
            font-size: 9px;
            font-weight: 700;
        }}
        QLabel#matrixNote {{
            color: {MUTED};
            font-size: 8px;
        }}
        QLabel#statusBadge {{
            color: {AMBER};
            border: 1px solid {AMBER};
            padding: 4px 9px;
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 1px;
        }}
        QLabel#statusBadge[online="true"] {{
            color: {MINT};
            border-color: {MINT};
        }}
        QLabel#errorLabel {{
            color: {RED};
            font-size: 9px;
        }}
        QLabel#telemetry {{
            color: {MUTED};
            background: {BLACK};
            border: 1px solid {BORDER};
            padding: 8px;
            font-size: 8px;
        }}
        QLabel#padSlot {{
            color: {MUTED};
            background: {BLACK};
            border: 1px dashed {BORDER};
            min-height: 30px;
            font-size: 8px;
        }}
        QPushButton {{
            background: {PANEL_RAISED};
            color: {TEXT};
            border: 1px solid {BORDER};
            padding: 7px 12px;
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 1px;
        }}
        QPushButton:hover {{
            border-color: {MINT};
            color: {MINT};
        }}
        QPushButton:pressed {{
            background: {MINT_DARK};
            color: {BLACK};
        }}
        QPushButton:disabled {{
            color: {MUTED};
            border-color: {BORDER};
            background: {BLACK};
        }}
        QPushButton#primaryButton {{
            color: {MINT};
            border-color: {MINT_DARK};
        }}
        QPushButton#primaryButton:hover {{
            border-color: {MINT};
        }}
        QPushButton#dangerButton {{
            color: {AMBER};
            border-color: {AMBER};
        }}
        QPushButton#primaryButton:disabled,
        QPushButton#dangerButton:disabled {{
            color: {MUTED};
            border-color: {BORDER};
            background: {BLACK};
        }}
        QPushButton#routeButton {{
            color: {MUTED};
            border-color: {BORDER};
            padding: 8px 10px;
        }}
        QPushButton#routeButton:checked {{
            color: {BLACK};
            background: {MINT};
            border-color: {MINT};
        }}
        QPushButton#routeButton:disabled {{
            color: {MUTED};
            background: {BLACK};
        }}
        QComboBox {{
            background: {BLACK};
            color: {TEXT};
            border: 1px solid {BORDER};
            padding: 4px 8px;
            min-height: 22px;
            font-size: 9px;
        }}
        QComboBox:hover {{
            border-color: {MINT_DARK};
        }}
        QComboBox:disabled {{
            color: {MUTED};
        }}
        QComboBox QAbstractItemView {{
            background: {BLACK};
            color: {TEXT};
            border: 1px solid {MINT_DARK};
            selection-background-color: {MINT};
            selection-color: {BLACK};
        }}
        QToolTip {{
            background: {BLACK};
            color: {MINT};
            border: 1px solid {MINT_DARK};
        }}
        """
    )
