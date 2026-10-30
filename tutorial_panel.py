from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


_PANEL_STYLE = """
    QWidget#tutorialPanel {
        background: #050a07;
        color: #bdd8ca;
        border: 1px solid #66ffc2;
        font-family: 'Cascadia Mono', 'Consolas';
    }
    QLabel {
        background: transparent;
        border: none;
        color: #bdd8ca;
    }
    QLabel#title {
        color: #66ffc2;
        font-size: 14px;
        font-weight: 700;
        letter-spacing: 1px;
    }
    QLabel#desc {
        font-size: 10px;
    }
    QPushButton {
        background: #09130d;
        color: #bdd8ca;
        border: 1px solid #1d4032;
        padding: 5px 10px;
        font-size: 9px;
        font-weight: 700;
        letter-spacing: 1px;
    }
    QPushButton:hover {
        border-color: #66ffc2;
        color: #66ffc2;
    }
    QPushButton:disabled {
        color: #52645c;
        border-color: #1d4032;
    }
"""


class TutorialOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.target_rect = QRect()

    def set_target(self, rect: QRect) -> None:
        self.target_rect = QRect(rect)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)

        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            path = QPainterPath()
            path.setFillRule(Qt.FillRule.OddEvenFill)
            path.addRect(QRectF(self.rect()))

            if not self.target_rect.isNull():
                path.addRoundedRect(
                    QRectF(self.target_rect),
                    6.0,
                    6.0,
                )

            painter.fillPath(path, QColor(0, 0, 0, 180))

            if not self.target_rect.isNull():
                painter.setPen(QPen(QColor("#66ffc2"), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(
                    QRectF(self.target_rect),
                    6.0,
                    6.0,
                )
        finally:
            painter.end()


class TutorialPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("tutorialPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedWidth(380)
        self.setWindowTitle("PILOTMIXER // TUTORIAL")
        self.setStyleSheet(_PANEL_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.title = QLabel("Step Title")
        self.title.setObjectName("title")
        self.desc = QLabel("Description")
        self.desc.setObjectName("desc")
        self.desc.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)

        self.btn_prev = QPushButton("PREV")
        self.btn_next = QPushButton("NEXT")
        self.btn_close = QPushButton("CLOSE")

        for button in (self.btn_prev, self.btn_next, self.btn_close):
            button.setMinimumWidth(74)
            button.setCursor(Qt.CursorShape.PointingHandCursor)

        buttons.addWidget(self.btn_prev)
        buttons.addWidget(self.btn_next)
        buttons.addStretch(1)
        buttons.addWidget(self.btn_close)

        layout.addWidget(self.title)
        layout.addWidget(self.desc)
        layout.addLayout(buttons)

        self.steps = []
        self.current_idx = 0
        self.overlay = TutorialOverlay(parent)
        self.overlay.hide()

        self.btn_prev.clicked.connect(self._prev)
        self.btn_next.clicked.connect(self._next)
        self.btn_close.clicked.connect(self.close_tutorial)

        if parent is not None:
            parent.installEventFilter(self)

    def start(self, steps: list[dict]) -> None:
        self.steps = list(steps)
        self.current_idx = 0

        if not self.steps:
            self.close_tutorial()
            return

        self._sync_overlay()
        self.overlay.show()
        self.overlay.raise_()
        self._update_ui()
        self.show()
        self.raise_()

    def _update_ui(self) -> None:
        if not self.steps:
            self.close_tutorial()
            return

        step = self.steps[self.current_idx]
        self.title.setText(step["title"])
        self.desc.setText(step["desc"])
        self.btn_prev.setEnabled(self.current_idx > 0)
        self.btn_next.setEnabled(True)
        self.btn_next.setText(
            "FINISH"
            if self.current_idx == len(self.steps) - 1
            else "NEXT"
        )
        self._highlight_widget(step.get("target"))

    def _highlight_widget(self, widget) -> None:
        parent = self.parentWidget()

        if widget is None or parent is None:
            self.overlay.set_target(QRect())
            self._center_panel()
            return

        global_top_left = widget.mapToGlobal(QPoint(0, 0))
        widget_global = QRect(global_top_left, widget.size())
        local_top_left = self.overlay.mapFromGlobal(global_top_left)
        target_rect = QRect(
            local_top_left,
            widget.size(),
        ).adjusted(-6, -6, 6, 6)
        self.overlay.set_target(target_rect)
        self._place_panel(widget_global)

    def _place_panel(self, target_global: QRect) -> None:
        parent = self.parentWidget()
        if parent is None:
            return

        self.adjustSize()
        margin = 16
        bounds = QRect(
            parent.mapToGlobal(QPoint(0, 0)),
            parent.size(),
        )

        left = target_global.right() + margin
        top = target_global.bottom() + margin

        if left + self.width() > bounds.right():
            left = target_global.left() - self.width() - margin
        if top + self.height() > bounds.bottom():
            top = target_global.top() - self.height() - margin

        left = max(
            bounds.left() + 8,
            min(left, bounds.right() - self.width() - 8),
        )
        top = max(
            bounds.top() + 8,
            min(top, bounds.bottom() - self.height() - 8),
        )
        self.move(left, top)

    def _center_panel(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return

        self.adjustSize()
        center = parent.mapToGlobal(parent.rect().center())
        self.move(
            center.x() - self.width() // 2,
            center.y() - self.height() // 2,
        )

    def _sync_overlay(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.overlay.setGeometry(parent.rect())

    def _prev(self) -> None:
        if self.current_idx > 0:
            self.current_idx -= 1
            self._update_ui()

    def _next(self) -> None:
        if self.current_idx < len(self.steps) - 1:
            self.current_idx += 1
            self._update_ui()
        else:
            self.close_tutorial()

    def close_tutorial(self) -> None:
        self.overlay.hide()
        self.hide()

    def closeEvent(self, event) -> None:
        self.overlay.hide()
        super().closeEvent(event)

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is self.parentWidget()
            and self.isVisible()
            and event.type()
            in (
                QEvent.Type.Resize,
                QEvent.Type.Move,
                QEvent.Type.Show,
            )
        ):
            self._sync_overlay()
            self._update_ui()

        return super().eventFilter(watched, event)
