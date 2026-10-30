from __future__ import annotations

import math
import time
from pathlib import Path

from PySide6.QtCore import (
    QLineF,
    QRectF,
    QSize,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from theme import ThemeManager


_DEFAULT_THEME = ThemeManager().theme
BLACK = QColor(_DEFAULT_THEME["background"])
MINT = QColor(_DEFAULT_THEME["accent"])
AMBER = QColor(_DEFAULT_THEME["secondary"])
RED = QColor(_DEFAULT_THEME["alert"])
DIM = QColor(_DEFAULT_THEME["dim"])
TEXT = QColor(_DEFAULT_THEME["text"])


def _font(size: int) -> QFont:
    font = QFont()
    font.setFamilies(["Cascadia Mono", "Consolas"])
    font.setPointSize(size)
    return font


def _require_gui_thread(widget: QWidget) -> None:
    if QThread.currentThread() != widget.thread():
        raise RuntimeError(
            "Update widgets on their GUI thread; use a queued Qt signal"
        )


class SoundPadButton(QPushButton):
    fileDropped = Signal(str)
    doubleClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("padButton")
        self.setAcceptDrops(True)
        self.setMinimumHeight(46)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @staticmethod
    def _wav_path(mime):
        if not mime.hasUrls():
            return None

        for url in mime.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.suffix.casefold() == ".wav":
                return str(path)
        return None

    def dragEnterEvent(self, event):
        if self._wav_path(event.mimeData()) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._wav_path(event.mimeData()) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = self._wav_path(event.mimeData())
        if path is None:
            event.ignore()
            return

        self.fileDropped.emit(path)
        event.acceptProposedAction()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.doubleClicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class HotkeyCaptureDialog(QDialog):
    _MODIFIER_KEYS = (
        Qt.Key.Key_Control,
        Qt.Key.Key_Shift,
        Qt.Key.Key_Alt,
        Qt.Key.Key_Meta,
    )
    _SPECIAL_KEYS = {
        Qt.Key.Key_Space: "<space>",
        Qt.Key.Key_Tab: "<tab>",
        Qt.Key.Key_Return: "<enter>",
        Qt.Key.Key_Enter: "<enter>",
        Qt.Key.Key_Backspace: "<backspace>",
        Qt.Key.Key_Delete: "<delete>",
        Qt.Key.Key_Insert: "<insert>",
        Qt.Key.Key_Home: "<home>",
        Qt.Key.Key_End: "<end>",
        Qt.Key.Key_PageUp: "<page_up>",
        Qt.Key.Key_PageDown: "<page_down>",
        Qt.Key.Key_Up: "<up>",
        Qt.Key.Key_Down: "<down>",
        Qt.Key.Key_Left: "<left>",
        Qt.Key.Key_Right: "<right>",
    }

    def __init__(self, parent=None):
        super().__init__(parent)

        self.hotkey = None
        self.setWindowTitle("Bind Hotkey")
        self.setModal(True)
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)
        title = QLabel("BIND PAD HOTKEY")
        title.setObjectName("sectionTitle")
        prompt = QLabel("PRESS A KEY COMBINATION, THEN BIND")
        prompt.setObjectName("sectionMeta")
        prompt.setWordWrap(True)

        self._value_label = QLabel("WAITING FOR INPUT")
        self._value_label.setObjectName("stripLabel")
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value_label.setMinimumHeight(32)

        buttons = QHBoxLayout()
        cancel = QPushButton("CANCEL")
        cancel.clicked.connect(self.reject)
        self._bind_button = QPushButton("BIND")
        self._bind_button.setObjectName("primaryButton")
        self._bind_button.setEnabled(False)
        self._bind_button.clicked.connect(self.accept)

        for button in (cancel, self._bind_button):
            button.setAutoDefault(False)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(self._bind_button)

        layout.addWidget(title)
        layout.addWidget(prompt)
        layout.addWidget(self._value_label)
        layout.addLayout(buttons)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()

    @staticmethod
    def _modifier_parts(modifiers) -> list[str]:
        parts = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("<ctrl>")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("<alt>")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("<shift>")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append("<cmd>")
        return parts

    @classmethod
    def _key_name(cls, event) -> str | None:
        key = event.key()

        if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            return chr(int(key)).lower()
        if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            return chr(int(key))
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F12:
            return f"<f{int(key) - int(Qt.Key.Key_F1) + 1}>"

        special = cls._SPECIAL_KEYS.get(key)
        if special is not None:
            return special

        text = event.text()
        if len(text) == 1 and text.isprintable() and not text.isspace():
            return text.casefold()
        return None

    def keyPressEvent(self, event):
        key = event.key()

        if key == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return

        if key in self._MODIFIER_KEYS:
            parts = self._modifier_parts(event.modifiers())
            self._value_label.setText("+".join(parts + ["..."]) if parts else "...")
            event.accept()
            return

        key_name = self._key_name(event)
        if key_name is None:
            self._value_label.setText("UNSUPPORTED KEY")
            event.accept()
            return

        parts = self._modifier_parts(event.modifiers())
        self.hotkey = "+".join(parts + [key_name])
        self._value_label.setText(self.hotkey.upper())
        self._bind_button.setEnabled(True)
        event.accept()


class VerticalFader(QWidget):
    valueChanged = Signal(float)

    def __init__(self, parent=None, *, value: float = 1.0):
        super().__init__(parent)
        self._value = 0.0

        self.setMinimumSize(70, 180)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Volume fader")
        self.set_value(value)

    def sizeHint(self) -> QSize:
        return QSize(78, 280)

    def value(self) -> float:
        return self._value

    @Slot(float)
    def set_value(self, value: float) -> None:
        _require_gui_thread(self)
        value = float(value)

        if not math.isfinite(value):
            raise ValueError("Fader value must be finite")

        value = max(0.0, min(1.0, value))
        if value == self._value:
            return

        self._value = value
        text = f"{value * 100:.0f}%"
        self.setToolTip(text)
        self.setAccessibleDescription(text)
        self.update()
        self.valueChanged.emit(value)

    def _track(self) -> tuple[float, float]:
        return 24.0, max(25.0, self.height() - 34.0)

    def _set_from_y(self, y: float) -> None:
        top, bottom = self._track()
        self.set_value((bottom - y) / (bottom - top))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._set_from_y(event.position().y())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._set_from_y(event.position().y())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def keyPressEvent(self, event) -> None:
        step = (
            0.001
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            else 0.01
        )
        key = event.key()

        if key in (Qt.Key.Key_Up, Qt.Key.Key_Right):
            self.set_value(self._value + step)
        elif key in (Qt.Key.Key_Down, Qt.Key.Key_Left):
            self.set_value(self._value - step)
        elif key == Qt.Key.Key_PageUp:
            self.set_value(self._value + 0.1)
        elif key == Qt.Key.Key_PageDown:
            self.set_value(self._value - 0.1)
        elif key == Qt.Key.Key_Home:
            self.set_value(0.0)
        elif key == Qt.Key.Key_End:
            self.set_value(1.0)
        else:
            super().keyPressEvent(event)
            return

        event.accept()

    def wheelEvent(self, event) -> None:
        if not self.hasFocus() or event.angleDelta().y() == 0:
            event.ignore()
            return

        self.set_value(
            self._value + event.angleDelta().y() / 120.0 * 0.01
        )
        event.accept()

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)

        try:
            colors = ThemeManager().theme
            background = QColor(colors["background"])
            text = QColor(colors["text"])
            dim = QColor(colors["dim"])
            track = QColor(colors["track"])
            handle = QColor(colors["handle"])
            accent = QColor(
                colors["accent"] if self.isEnabled() else colors["disabled"]
            )

            painter.fillRect(self.rect(), background)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            top, bottom = self._track()
            center = self.width() / 2.0
            handle_y = bottom - self._value * (bottom - top)

            painter.setFont(_font(8))
            painter.setPen(text)
            painter.drawText(
                QRectF(0, 0, self.width(), 20),
                Qt.AlignmentFlag.AlignCenter,
                "GAIN",
            )

            painter.setPen(QPen(dim, 1))
            for tick in range(11):
                y = bottom - tick / 10.0 * (bottom - top)
                length = 11 if tick % 5 == 0 else 6
                painter.drawLine(
                    QLineF(center - 20 - length, y, center - 20, y)
                )
                painter.drawLine(
                    QLineF(center + 20, y, center + 20 + length, y)
                )

            painter.fillRect(
                QRectF(center - 3, top, 6, bottom - top),
                track,
            )
            painter.fillRect(
                QRectF(center - 1, handle_y, 2, bottom - handle_y),
                accent,
            )

            handle_rect = QRectF(center - 17, handle_y - 8, 34, 16)
            painter.setPen(QPen(accent, 1))
            painter.setBrush(handle)
            painter.drawRect(handle_rect)
            painter.drawLine(
                QLineF(center - 12, handle_y, center + 12, handle_y)
            )

            painter.setPen(accent)
            painter.drawText(
                QRectF(0, self.height() - 25, self.width(), 22),
                Qt.AlignmentFlag.AlignCenter,
                f"{self._value * 100:.0f}%",
            )

            if self.hasFocus():
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(
                    QPen(accent, 1, Qt.PenStyle.DotLine)
                )
                painter.drawRect(
                    self.rect().adjusted(1, 1, -2, -2)
                )
        finally:
            painter.end()


class VUMeter(QWidget):
    FLOOR_DB = -60.0
    HOLD_SECONDS = 0.8
    RELEASE_DB_PER_SECOND = 24.0
    PEAK_RELEASE_DB_PER_SECOND = 12.0

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMinimumSize(110, 180)
        self.setAccessibleName("Stereo audio level meter")

        self._targets = [self.FLOOR_DB, self.FLOOR_DB]
        self._levels = [self.FLOOR_DB, self.FLOOR_DB]
        self._peaks = [self.FLOOR_DB, self.FLOOR_DB]
        self._hold_until = [0.0, 0.0]

        now = time.monotonic()
        self._last_input = now
        self._last_tick = now

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def sizeHint(self) -> QSize:
        return QSize(120, 280)

    @staticmethod
    def _to_db(amplitude: float) -> float:
        amplitude = float(amplitude)
        if not math.isfinite(amplitude) or amplitude <= 0:
            return VUMeter.FLOOR_DB

        amplitude = min(1.0, amplitude)
        return max(VUMeter.FLOOR_DB, 20.0 * math.log10(amplitude))

    @Slot(float, float)
    def set_level(self, left: float, right: float) -> None:
        _require_gui_thread(self)
        now = time.monotonic()
        self._last_input = now

        for channel, amplitude in enumerate((left, right)):
            db = self._to_db(amplitude)
            self._targets[channel] = db
            self._levels[channel] = max(self._levels[channel], db)

            if db >= self._peaks[channel]:
                self._peaks[channel] = db
                self._hold_until[channel] = now + self.HOLD_SECONDS

        self.update()

    @Slot()
    def _tick(self) -> None:
        now = time.monotonic()
        previous = self._last_tick
        elapsed = max(0.0, now - previous)
        self._last_tick = now
        stale = now - self._last_input > 0.25

        for channel in range(2):
            target = (
                self.FLOOR_DB
                if stale
                else self._targets[channel]
            )
            self._levels[channel] = max(
                target,
                self._levels[channel]
                - self.RELEASE_DB_PER_SECOND * elapsed,
            )

            decay_time = max(
                0.0,
                now - max(previous, self._hold_until[channel]),
            )
            self._peaks[channel] = max(
                self._levels[channel],
                self._peaks[channel]
                - self.PEAK_RELEASE_DB_PER_SECOND * decay_time,
            )

        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)

        try:
            colors = ThemeManager().theme
            background = QColor(colors["background"])
            text = QColor(colors["text"])
            accent = QColor(colors["accent"])
            secondary = QColor(colors["secondary"])
            alert = QColor(colors["alert"])
            dim = QColor(colors["dim"])
            peak = QColor(colors["peak"])

            painter.fillRect(self.rect(), background)
            painter.setFont(_font(8))

            if not self.isEnabled():
                painter.setOpacity(0.4)

            top = 24.0
            bottom = self.height() - 24.0
            height = bottom - top
            meter_width = self.width() - 44.0
            bar_width = (meter_width - 6.0) / 2.0
            segment_height = height / 30.0

            def y_for_db(db: float) -> float:
                return bottom - (
                    (db - self.FLOOR_DB) / -self.FLOOR_DB
                ) * height

            for channel, label in enumerate(("L", "R")):
                x = 6.0 + channel * (bar_width + 6.0)

                painter.setPen(text)
                painter.drawText(
                    QRectF(x, 0, bar_width, 20),
                    Qt.AlignmentFlag.AlignCenter,
                    label,
                )

                for segment in range(30):
                    threshold = self.FLOOR_DB + (segment + 1) * 2.0

                    if threshold >= -2:
                        color = alert
                    elif threshold >= -12:
                        color = secondary
                    else:
                        color = accent

                    if self._levels[channel] < threshold:
                        color = dim

                    y = bottom - (segment + 1) * segment_height
                    painter.fillRect(
                        QRectF(
                            x,
                            y,
                            bar_width,
                            max(1.0, segment_height - 2.0),
                        ),
                        color,
                    )

                if self._peaks[channel] > self.FLOOR_DB:
                    painter.setPen(QPen(peak, 2))
                    y = y_for_db(self._peaks[channel])
                    painter.drawLine(
                        QLineF(x, y, x + bar_width, y)
                    )

            painter.setPen(text)
            for db in (0, -6, -12, -24, -36, -48, -60):
                painter.drawText(
                    QRectF(
                        self.width() - 32,
                        y_for_db(db) - 7,
                        30,
                        14,
                    ),
                    Qt.AlignmentFlag.AlignRight
                    | Qt.AlignmentFlag.AlignVCenter,
                    str(db),
                )

            painter.drawText(
                QRectF(0, self.height() - 20, self.width(), 18),
                Qt.AlignmentFlag.AlignCenter,
                "dBFS / PEAK",
            )
        finally:
            painter.end()
