from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


THEMES: dict[str, dict[str, str]] = {
    "Pilot Mint": {
        "background": "#000000",
        "panel": "#050a07",
        "panel_raised": "#09130d",
        "border": "#1d4032",
        "accent": "#66ffc2",
        "accent_dark": "#2d7a5c",
        "secondary": "#ffc857",
        "alert": "#ff5566",
        "text": "#bdd8ca",
        "muted": "#60786b",
        "dim": "#173329",
        "disabled": "#52645c",
        "track": "#0b1711",
        "handle": "#14251c",
        "peak": "#effff7",
        "on_accent": "#000000",
    },
    "Pilot Cyan": {
        "background": "#00070a",
        "panel": "#040d11",
        "panel_raised": "#07171d",
        "border": "#164650",
        "accent": "#5de4ff",
        "accent_dark": "#23798c",
        "secondary": "#ffd166",
        "alert": "#ff5d7a",
        "text": "#b9dce4",
        "muted": "#5d7f88",
        "dim": "#122b33",
        "disabled": "#4d666d",
        "track": "#08181d",
        "handle": "#0e252c",
        "peak": "#f0ffff",
        "on_accent": "#000000",
    },
    "Pilot Amber": {
        "background": "#050300",
        "panel": "#0c0803",
        "panel_raised": "#150e05",
        "border": "#4a3713",
        "accent": "#ffc857",
        "accent_dark": "#8a6420",
        "secondary": "#ff9f43",
        "alert": "#ff5566",
        "text": "#e8d6b5",
        "muted": "#8a7a5f",
        "dim": "#33270f",
        "disabled": "#6b5c40",
        "track": "#1c1307",
        "handle": "#2b1e0b",
        "peak": "#fffbe8",
        "on_accent": "#000000",
    },
    "Pilot Light": {
        "background": "#f0f0f0",
        "panel": "#ffffff",
        "panel_raised": "#e6e6e6",
        "border": "#c4c4c4",
        "accent": "#0f9f7a",
        "accent_dark": "#0b6f55",
        "secondary": "#a86a00",
        "alert": "#c0392b",
        "text": "#1e2a26",
        "muted": "#5f6f69",
        "dim": "#d2dad6",
        "disabled": "#9aa8a2",
        "track": "#d8e0dc",
        "handle": "#ffffff",
        "peak": "#123b2d",
        "on_accent": "#ffffff",
    },
}

DEFAULT_THEME_NAME = "Pilot Mint"
CONFIG_PATH = Path(__file__).with_name("theme_config.json")
_THEME_ALIASES = {
    name.removeprefix("Pilot ").casefold(): name for name in THEMES
}
_LEGACY_GLOBALS = {
    "BLACK": "background",
    "PANEL": "panel",
    "PANEL_RAISED": "panel_raised",
    "BORDER": "border",
    "MINT": "accent",
    "MINT_DARK": "accent_dark",
    "AMBER": "secondary",
    "RED": "alert",
    "TEXT": "text",
    "MUTED": "muted",
}


class ThemeManager:
    _instance: ThemeManager | None = None

    def __new__(cls, app: QApplication | None = None):
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._ready = False
            cls._instance = instance
        return cls._instance

    def __init__(self, app: QApplication | None = None):
        if app is not None:
            self._app = app
            self._load()
            self._refresh_legacy_globals()
            self._apply()
            self._ready = True
            return

        if self._ready:
            return

        self._app = QApplication.instance()
        self._set_theme(DEFAULT_THEME_NAME)
        if self._app is not None:
            self._apply()
        self._ready = True

    @property
    def current_theme_name(self) -> str:
        return self._current_theme_name

    @property
    def theme(self) -> Mapping[str, str]:
        return self._theme

    def set_theme(self, name: str) -> str:
        canonical = self._canonical_name(name)
        if canonical is None:
            raise ValueError(f"Unknown PilotMixer theme: {name!r}")

        self._set_theme(canonical)
        self._save()
        self._apply()
        return canonical

    @staticmethod
    def _canonical_name(name: str) -> str | None:
        if not isinstance(name, str):
            return None

        candidate = name.strip()
        if candidate in THEMES:
            return candidate
        return _THEME_ALIASES.get(candidate.casefold())

    def _set_theme(self, name: str) -> None:
        self._current_theme_name = name
        self._theme = MappingProxyType(dict(THEMES[name]))
        self._refresh_legacy_globals()

    def _load(self) -> None:
        name = DEFAULT_THEME_NAME
        try:
            raw = CONFIG_PATH.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, UnicodeError, json.JSONDecodeError):
            data = None

        stored = data.get("theme") if isinstance(data, dict) else data
        if isinstance(stored, str):
            name = self._canonical_name(stored) or DEFAULT_THEME_NAME

        self._set_theme(name)

    def _save(self) -> None:
        payload = json.dumps(
            {"theme": self._current_theme_name},
            indent=2,
        )
        try:
            CONFIG_PATH.write_text(payload + "\n", encoding="utf-8")
        except OSError:
            pass

    def _refresh_legacy_globals(self) -> None:
        # Existing modules import these names directly.
        for legacy_name, token in _LEGACY_GLOBALS.items():
            globals()[legacy_name] = self._theme[token]

    def _apply(self) -> None:
        app = self._app
        if app is None:
            app = QApplication.instance()
            self._app = app
        if app is None:
            return

        app.setStyle("Fusion")
        font = QFont()
        font.setFamilies(["Cascadia Mono", "Consolas"])
        font.setPointSize(9)
        app.setFont(font)
        app.setStyleSheet(self._stylesheet())

    def _stylesheet(self) -> str:
        colors = self._theme
        return f"""
        QMainWindow, QWidget#root {{
            background: {colors["background"]};
            color: {colors["text"]};
        }}
        QWidget {{
            font-family: 'Cascadia Mono', 'Consolas';
            color: {colors["text"]};
        }}
        QFrame#headerBar, QFrame#deviceBar, QFrame#footerBar {{
            background: {colors["panel"]};
            border: 1px solid {colors["border"]};
        }}
        QFrame#panel {{
            background: {colors["panel"]};
            border: 1px solid {colors["border"]};
        }}
        QFrame#strip {{
            background: {colors["panel_raised"]};
            border: 1px solid {colors["border"]};
        }}
        QLabel {{
            background: transparent;
        }}
        QLabel#brand {{
            color: {colors["accent"]};
            font-size: 27px;
            font-weight: 700;
            letter-spacing: 7px;
        }}
        QLabel#subBrand {{
            color: {colors["muted"]};
            font-size: 9px;
            letter-spacing: 2px;
        }}
        QLabel#sectionTitle {{
            color: {colors["accent"]};
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 2px;
        }}
        QLabel#sectionMeta {{
            color: {colors["muted"]};
            font-size: 8px;
            letter-spacing: 1px;
        }}
        QLabel#stripLabel {{
            color: {colors["text"]};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1px;
        }}
        QLabel#stripMeta {{
            color: {colors["muted"]};
            font-size: 8px;
        }}
        QLabel#matrixHead {{
            color: {colors["accent"]};
            font-size: 8px;
            font-weight: 700;
            letter-spacing: 1px;
        }}
        QLabel#matrixRow {{
            color: {colors["text"]};
            font-size: 9px;
            font-weight: 700;
        }}
        QLabel#matrixNote {{
            color: {colors["muted"]};
            font-size: 8px;
        }}
        QLabel#statusBadge {{
            color: {colors["secondary"]};
            border: 1px solid {colors["secondary"]};
            padding: 4px 9px;
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 1px;
        }}
        QLabel#statusBadge[online="true"] {{
            color: {colors["accent"]};
            border-color: {colors["accent"]};
        }}
        QLabel#errorLabel {{
            color: {colors["alert"]};
            font-size: 9px;
        }}
        QLabel#telemetry {{
            color: {colors["muted"]};
            background: {colors["background"]};
            border: 1px solid {colors["border"]};
            padding: 8px;
            font-size: 8px;
        }}
        QLabel#padSlot {{
            color: {colors["muted"]};
            background: {colors["background"]};
            border: 1px dashed {colors["border"]};
            min-height: 30px;
            font-size: 8px;
        }}
        QPushButton#padButton {{
            color: {colors["muted"]};
            background: {colors["background"]};
            border: 1px dashed {colors["border"]};
            min-height: 44px;
            padding: 4px;
            font-size: 8px;
            font-weight: 700;
        }}
        QPushButton#padButton[loaded="true"] {{
            color: {colors["text"]};
            background: {colors["panel_raised"]};
            border: 1px solid {colors["accent_dark"]};
        }}
        QPushButton#padButton:hover {{
            color: {colors["accent"]};
            border-color: {colors["accent"]};
        }}
        QPushButton#monitorButton {{
            color: {colors["muted"]};
            background: {colors["background"]};
            border: 1px solid {colors["border"]};
            padding: 3px 6px;
            font-size: 8px;
            font-weight: 700;
            letter-spacing: 1px;
        }}
        QPushButton#monitorButton:hover {{
            color: {colors["accent"]};
            border-color: {colors["accent"]};
        }}
        QPushButton#monitorButton:checked {{
            color: {colors["on_accent"]};
            background: {colors["accent"]};
            border-color: {colors["accent"]};
        }}
        QPushButton#presetButton {{
            color: {colors["muted"]};
            background: {colors["panel_raised"]};
            border: 1px solid {colors["border"]};
            padding: 3px 8px;
            font-size: 8px;
            font-weight: 700;
            letter-spacing: 1px;
        }}
        QPushButton#presetButton:hover {{
            color: {colors["accent"]};
            border-color: {colors["accent"]};
        }}
        QPushButton {{
            background: {colors["panel_raised"]};
            color: {colors["text"]};
            border: 1px solid {colors["border"]};
            padding: 7px 12px;
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 1px;
        }}
        QPushButton:hover {{
            border-color: {colors["accent"]};
            color: {colors["accent"]};
        }}
        QPushButton:pressed {{
            background: {colors["accent_dark"]};
            color: {colors["on_accent"]};
        }}
        QPushButton:disabled {{
            color: {colors["muted"]};
            border-color: {colors["border"]};
            background: {colors["background"]};
        }}
        QPushButton#primaryButton {{
            color: {colors["accent"]};
            border-color: {colors["accent_dark"]};
        }}
        QPushButton#primaryButton:hover {{
            border-color: {colors["accent"]};
        }}
        QPushButton#dangerButton {{
            color: {colors["secondary"]};
            border-color: {colors["secondary"]};
        }}
        QPushButton#primaryButton:disabled,
        QPushButton#dangerButton:disabled {{
            color: {colors["muted"]};
            border-color: {colors["border"]};
            background: {colors["background"]};
        }}
        QPushButton#routeButton {{
            color: {colors["muted"]};
            border-color: {colors["border"]};
            padding: 8px 10px;
        }}
        QPushButton#routeButton:checked {{
            color: {colors["on_accent"]};
            background: {colors["accent"]};
            border-color: {colors["accent"]};
        }}
        QPushButton#routeButton:disabled {{
            color: {colors["muted"]};
            background: {colors["background"]};
        }}
        QComboBox {{
            background: {colors["background"]};
            color: {colors["text"]};
            border: 1px solid {colors["border"]};
            padding: 4px 8px;
            min-height: 22px;
            font-size: 9px;
        }}
        QComboBox:hover {{
            border-color: {colors["accent_dark"]};
        }}
        QComboBox:disabled {{
            color: {colors["muted"]};
        }}
        QComboBox QAbstractItemView {{
            background: {colors["background"]};
            color: {colors["text"]};
            border: 1px solid {colors["accent_dark"]};
            selection-background-color: {colors["accent"]};
            selection-color: {colors["on_accent"]};
        }}
        QToolTip {{
            background: {colors["background"]};
            color: {colors["accent"]};
            border: 1px solid {colors["accent_dark"]};
        }}
        """


def apply_theme(app: QApplication) -> ThemeManager:
    return ThemeManager(app)


_DEFAULT_COLORS = THEMES[DEFAULT_THEME_NAME]
BLACK = _DEFAULT_COLORS["background"]
PANEL = _DEFAULT_COLORS["panel"]
PANEL_RAISED = _DEFAULT_COLORS["panel_raised"]
BORDER = _DEFAULT_COLORS["border"]
MINT = _DEFAULT_COLORS["accent"]
MINT_DARK = _DEFAULT_COLORS["accent_dark"]
AMBER = _DEFAULT_COLORS["secondary"]
RED = _DEFAULT_COLORS["alert"]
TEXT = _DEFAULT_COLORS["text"]
MUTED = _DEFAULT_COLORS["muted"]
