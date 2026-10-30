from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cockpit_widgets import (
    HotkeyCaptureDialog,
    SoundPadButton,
    VUMeter,
    VerticalFader,
)
from engine_service import EngineConfig, EngineService
from hotkey_manager import HotkeyManager
from soundboard_model import SoundboardConfig, SoundPad
from theme import THEMES, ThemeManager
from tutorial_panel import TutorialPanel
from ui_config import load_ui_config


SOURCE_LABELS = (
    ("mic", "MIC"),
    ("system", "SYSTEM"),
    ("soundboard", "SOUNDBOARD"),
)
DEST_LABELS = (
    ("headphones", "HEADPHONES"),
    ("virtual_cable", "VIRTUAL CABLE"),
)
DEVICE_LABELS = (
    ("mic", "MIC CAPTURE"),
    ("system", "SYSTEM CAPTURE"),
    ("headphones", "HEADPHONES OUT"),
    ("virtual_cable", "CABLE OUT"),
)
PRESET_BUTTONS = (
    ("streamer", "STREAMER"),
    ("soundboard_only", "SOUNDBOARD ONLY"),
    ("local_only", "LOCAL ONLY"),
)
PRESET_ROUTES = {
    "streamer": frozenset(
        (source, destination)
        for source in ("mic", "system", "soundboard")
        for destination in ("headphones", "virtual_cable")
    ),
    "soundboard_only": frozenset(
        {
            ("soundboard", "headphones"),
            ("soundboard", "virtual_cable"),
        }
    ),
    "local_only": frozenset(
        {
            ("mic", "headphones"),
            ("system", "headphones"),
        }
    ),
}
DEFAULT_SOUNDBOARD_PATH = Path(__file__).with_name("soundboard_config.json")


class MainWindow(QMainWindow):
    pad_hotkey_triggered = Signal(int)

    def __init__(
        self,
        service=None,
        devices=None,
        parent=None,
        *,
        soundboard_config=None,
        soundboard_path=None,
        hotkey_manager=None,
        theme_manager=None,
        ui_config=None,
        ui_config_path=None,
    ):
        super().__init__(parent)

        self.service = service if service is not None else EngineService(parent=self)
        self._online = False
        self._devices = []
        self.input_faders = {}
        self.output_faders = {}
        self.output_meters = {}
        self.route_buttons = {}
        self.device_combos = {}
        self.matrix_headers = {}
        self.pad_buttons = []
        self.preset_buttons = {}
        self.monitor_button = None
        self.tutorial_panel = None

        self._soundboard_path = (
            Path(soundboard_path)
            if soundboard_path is not None
            else DEFAULT_SOUNDBOARD_PATH
        )
        self.soundboard_config = (
            soundboard_config
            if soundboard_config is not None
            else SoundboardConfig.load(self._soundboard_path)
        )
        self._ensure_pad_bank()

        self.hotkey_manager = (
            hotkey_manager
            if hotkey_manager is not None
            else HotkeyManager()
        )
        self.theme_manager = (
            theme_manager
            if theme_manager is not None
            else ThemeManager(QApplication.instance())
        )
        self.ui_config = (
            ui_config
            if ui_config is not None
            else load_ui_config(ui_config_path)
        )
        self.pad_hotkey_triggered.connect(self._trigger_pad)

        self.setWindowTitle("PILOTMIXER // CUSTOM AUDIO ROUTER")
        self.resize(1440, 900)
        self.setMinimumSize(1220, 760)
        self._build_ui()
        self._refresh_pads()
        self._refresh_hotkeys(initial=True)
        self._connect_service()

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._poll_meters)
        self._poll_count = 0

        if devices is None:
            self._set_status("SCANNING // WASAPI")
            self.start_button.setEnabled(False)
            QTimer.singleShot(0, self._refresh_devices)
        else:
            self._populate_devices(devices)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 14, 16, 12)
        outer.setSpacing(10)
        outer.addWidget(self._build_header())
        outer.addWidget(self._build_device_bar())

        body = QHBoxLayout()
        body.setSpacing(10)
        body.addWidget(self._build_inputs())
        body.addWidget(self._build_matrix(), 1)
        body.addWidget(self._build_outputs())
        body.addWidget(self._build_aux())
        outer.addLayout(body, 1)
        outer.addWidget(self._build_footer())

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("headerBar")

        outer = QVBoxLayout(header)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(8)

        layout = QHBoxLayout()
        layout.setSpacing(12)
        outer.addLayout(layout)

        brand_box = QVBoxLayout()
        brand_box.setSpacing(0)
        brand = QLabel("PILOTMIXER")
        brand.setObjectName("brand")
        sub = QLabel("CUSTOM AUDIO ROUTER // LOCAL COCKPIT")
        sub.setObjectName("subBrand")
        brand_box.addWidget(brand)
        brand_box.addWidget(sub)
        layout.addLayout(brand_box)
        layout.addStretch(1)

        theme_label = QLabel("THEME")
        theme_label.setObjectName("sectionMeta")
        layout.addWidget(theme_label)

        self.theme_combo = QComboBox()
        self.theme_combo.setObjectName("themeCombo")
        self.theme_combo.setMinimumWidth(140)
        self.theme_combo.setAccessibleName("Application theme")
        self.theme_combo.addItems(list(THEMES))
        current_theme = getattr(
            self.theme_manager,
            "current_theme_name",
            "",
        )
        theme_index = self.theme_combo.findText(current_theme)
        self.theme_combo.setCurrentIndex(
            theme_index if theme_index >= 0 else 0
        )
        self.theme_combo.currentTextChanged.connect(
            self._on_theme_selected
        )
        layout.addWidget(self.theme_combo)

        self.tutorial_button = QPushButton("TUTORIAL")
        self.tutorial_button.setMinimumWidth(92)
        self.tutorial_button.setToolTip("Open the cockpit tutorial")
        self.tutorial_button.setAccessibleName("Open cockpit tutorial")
        self.tutorial_button.clicked.connect(self._start_tutorial)
        layout.addWidget(self.tutorial_button)

        self.status_label = QLabel("OFFLINE")
        self.status_label.setObjectName("statusBadge")
        self.status_label.setProperty("online", False)
        layout.addWidget(self.status_label)

        self.start_button = QPushButton("ENGAGE")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setMinimumWidth(100)
        self.start_button.clicked.connect(self._start)
        layout.addWidget(self.start_button)

        self.stop_button = QPushButton("DISENGAGE")
        self.stop_button.setObjectName("dangerButton")
        self.stop_button.setMinimumWidth(110)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop)
        layout.addWidget(self.stop_button)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(8)
        preset_label = QLabel("PRESETS")
        preset_label.setObjectName("sectionMeta")
        preset_row.addWidget(preset_label)

        for key, label in PRESET_BUTTONS:
            button = QPushButton(label)
            button.setObjectName("presetButton")
            button.setMinimumHeight(24)
            button.setToolTip(f"Apply the {label} routing preset")
            button.clicked.connect(
                lambda checked=False, preset=key:
                self._apply_preset(preset)
            )
            self.preset_buttons[key] = button
            preset_row.addWidget(button)

        preset_row.addStretch(1)
        outer.addLayout(preset_row)
        return header

    def _build_device_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("deviceBar")

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        title = QLabel("ENDPOINTS")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        for key, label_text in DEVICE_LABELS:
            box = QVBoxLayout()
            box.setSpacing(3)
            label = QLabel(label_text)
            label.setObjectName("sectionMeta")
            combo = QComboBox()
            combo.setMinimumWidth(190)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            box.addWidget(label)
            box.addWidget(combo)
            self.device_combos[key] = combo
            layout.addLayout(box, 1)

        self.refresh_button = QPushButton("SCAN")
        self.refresh_button.clicked.connect(self._refresh_devices)
        layout.addWidget(self.refresh_button, 0, Qt.AlignmentFlag.AlignBottom)
        self.device_bar = bar
        return bar

    def _new_panel(self, title_text: str, meta_text: str):
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(9)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel(title_text)
        title.setObjectName("sectionTitle")
        meta = QLabel(meta_text)
        meta.setObjectName("sectionMeta")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(meta)
        layout.addLayout(header)
        return panel, layout

    def _build_inputs(self) -> QFrame:
        panel, layout = self._new_panel("INPUT BUS", "GAIN // PRE-ROUTE")
        panel.setMinimumWidth(300)
        strips = QHBoxLayout()
        strips.setSpacing(8)

        for key, title_text in SOURCE_LABELS:
            strip = QFrame()
            strip.setObjectName("strip")
            strip_layout = QVBoxLayout(strip)
            strip_layout.setContentsMargins(8, 8, 8, 8)
            strip_layout.setSpacing(6)

            label = QLabel(title_text)
            label.setObjectName("stripLabel")
            meta = QLabel("INPUT // GAIN")
            meta.setObjectName("stripMeta")
            fader = VerticalFader(value=1.0)
            fader.setEnabled(False)
            fader.valueChanged.connect(
                lambda value, source=key: self._on_input_volume(source, value)
            )

            strip_layout.addWidget(label)
            strip_layout.addWidget(meta)
            strip_layout.addWidget(fader, 1)

            if key == "soundboard":
                monitor = QPushButton("MONITOR")
                monitor.setObjectName("monitorButton")
                monitor.setCheckable(True)
                monitor.setMinimumHeight(24)
                monitor.setToolTip(
                    "Force soundboard audio to headphones "
                    "regardless of the matrix"
                )
                monitor.setAccessibleName("Monitor soundboard")
                monitor.toggled.connect(self._on_monitor_toggled)
                strip_layout.addWidget(monitor)
                self.monitor_button = monitor

            self.input_faders[key] = fader
            strips.addWidget(strip, 1)

        layout.addLayout(strips, 1)
        return panel

    def _build_matrix(self) -> QFrame:
        panel, layout = self._new_panel("ROUTING MATRIX", "CROSSPOINT // POST-GAIN")
        panel.setMinimumWidth(320)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        corner = QLabel("SRC / DST")
        corner.setObjectName("sectionMeta")
        grid.addWidget(corner, 0, 0)

        for column, (destination, label_text) in enumerate(
            DEST_LABELS,
            start=1,
        ):
            head = QLabel(self.ui_config.matrix_label(label_text))
            head.setObjectName("matrixHead")
            head.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(head, 0, column)
            self.matrix_headers[destination] = head

        for row, (source, label_text) in enumerate(SOURCE_LABELS, start=1):
            row_label = QLabel(label_text)
            row_label.setObjectName("matrixRow")
            grid.addWidget(row_label, row, 0)

            for column, (destination, _) in enumerate(DEST_LABELS, start=1):
                button = QPushButton("LINK")
                button.setObjectName("routeButton")
                button.setCheckable(True)
                button.setEnabled(False)
                button.setMinimumHeight(34)
                button.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Fixed,
                )
                button.toggled.connect(
                    lambda checked, src=source, dst=destination:
                    self._on_route_changed(src, dst, checked)
                )
                self.route_buttons[(source, destination)] = button
                grid.addWidget(button, row, column)

        layout.addLayout(grid)
        layout.addWidget(
            self._label(
                "CROSSPOINTS OPEN ONLY WHILE ENGINE IS ONLINE. START WITH SILENCE.",
                "matrixNote",
            )
        )
        layout.addSpacing(6)
        layout.addWidget(self._label("ENGINE TELEMETRY", "sectionTitle"))
        self.telemetry_label = QLabel(
            "ENGINE OFFLINE\nNO CALLBACK DATA\nAWAITING ENGAGE"
        )
        self.telemetry_label.setObjectName("telemetry")
        self.telemetry_label.setWordWrap(False)
        self.telemetry_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.telemetry_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.telemetry_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self.telemetry_label, 1)
        self.matrix_panel = panel
        return panel

    def _build_outputs(self) -> QFrame:
        panel, layout = self._new_panel("OUTPUTS", "MASTER // POST-FADER")
        panel.setMinimumWidth(280)
        strips = QHBoxLayout()
        strips.setSpacing(8)

        for key, title_text in DEST_LABELS:
            strip = QFrame()
            strip.setObjectName("strip")
            strip_layout = QVBoxLayout(strip)
            strip_layout.setContentsMargins(8, 8, 8, 8)
            strip_layout.setSpacing(6)

            label = QLabel(title_text)
            label.setObjectName("stripLabel")
            meta = QLabel("METER // MASTER")
            meta.setObjectName("stripMeta")
            meter = VUMeter()
            meter.setEnabled(False)
            fader = VerticalFader(value=1.0)
            fader.setEnabled(False)
            fader.valueChanged.connect(
                lambda value, output=key: self._on_output_volume(output, value)
            )

            strip_layout.addWidget(label)
            strip_layout.addWidget(meta)
            strip_layout.addWidget(meter, 1)
            strip_layout.addWidget(fader)
            self.output_meters[key] = meter
            self.output_faders[key] = fader
            strips.addWidget(strip, 1)

        layout.addLayout(strips, 1)
        return panel

    def _build_aux(self) -> QFrame:
        panel, layout = self._new_panel(
            "AUX BAY",
            "SOUNDBOARD // HOTKEYS",
        )
        panel.setMinimumWidth(220)

        layout.addWidget(self._label("SOUNDBOARD", "stripLabel"))
        pads = QGridLayout()
        pads.setSpacing(5)
        for slot in range(8):
            pad = SoundPadButton()
            pad.clicked.connect(
                lambda checked=False, index=slot: self._trigger_pad(index)
            )
            pad.doubleClicked.connect(
                lambda index=slot: self._choose_pad_file(index)
            )
            pad.fileDropped.connect(
                lambda filepath, index=slot: self._load_pad_file(
                    index,
                    filepath,
                )
            )
            pad.setContextMenuPolicy(
                Qt.ContextMenuPolicy.CustomContextMenu
            )
            pad.customContextMenuRequested.connect(
                lambda position, index=slot: self._show_pad_menu(
                    index,
                    position,
                )
            )
            self.pad_buttons.append(pad)
            pads.addWidget(pad, slot // 4, slot % 4)
        layout.addLayout(pads)
        self.pad_bank_label = self._label(
            "BANK 00 // 0/8 LOADED",
            "matrixNote",
        )
        layout.addWidget(self.pad_bank_label)

        layout.addSpacing(10)
        layout.addWidget(self._label("VOICE RACK", "stripLabel"))
        layout.addWidget(
            self._label(
                "PITCH / FORMANT // NOT INSTALLED",
                "matrixNote",
            )
        )
        layout.addStretch(1)
        return panel

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("footerBar")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(12)

        self.detail_label = QLabel("WASAPI SHARED // 48 kHz // 30 ms")
        self.detail_label.setObjectName("sectionMeta")
        layout.addWidget(self.detail_label)
        layout.addStretch(1)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setMaximumWidth(760)
        layout.addWidget(self.error_label)
        return footer

    def _ensure_pad_bank(self) -> None:
        if not self.soundboard_config.banks:
            self.soundboard_config.banks.append([])

        bank = self.soundboard_config.banks[0]
        while len(bank) < 8:
            bank.append(SoundPad())
        if len(bank) > 8:
            del bank[8:]

    def _pads(self) -> list[SoundPad]:
        return self.soundboard_config.banks[0]

    @staticmethod
    def _pad_label(filepath: str | None) -> str:
        if not filepath:
            return "EMPTY"

        name = Path(filepath).name
        if len(name) <= 16:
            return name

        suffix = Path(name).suffix
        stem_length = max(1, 16 - len(suffix) - 3)
        return f"{name[:stem_length]}...{suffix}"

    def _refresh_pads(self) -> None:
        loaded = sum(1 for pad in self._pads() if pad.filepath)
        self.pad_bank_label.setText(f"BANK 00 // {loaded}/8 LOADED")
        for slot in range(8):
            self._refresh_pad(slot)

    def _refresh_pad(self, slot: int) -> None:
        pad = self._pads()[slot]
        button = self.pad_buttons[slot]
        label = self._pad_label(pad.filepath)
        hotkey = pad.hotkey or "UNBOUND"

        button.setText(label)
        button.setToolTip(
            f"PAD {slot + 1:02d} // {label}\n"
            f"{pad.filepath or 'NO FILE'}\n"
            f"HOTKEY: {hotkey}"
        )
        button.setAccessibleName(
            f"Soundboard pad {slot + 1:02d}: {label}"
        )
        button.setProperty("loaded", bool(pad.filepath))
        button.style().unpolish(button)
        button.style().polish(button)

    def _load_pad_file(self, slot: int, filepath: str) -> bool:
        if not 0 <= slot < len(self._pads()):
            return False

        path = Path(filepath)
        if path.suffix.casefold() != ".wav":
            self._show_error("Only .wav files can be loaded into pads.")
            return False
        if not path.is_file():
            self._show_error(f"Soundboard file not found: {path}")
            return False

        self._pads()[slot].filepath = str(path)
        self._refresh_pads()
        self._save_soundboard()
        self._refresh_hotkeys()
        return True

    def _choose_pad_file(self, slot: int) -> None:
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            f"Load Pad {slot + 1:02d}",
            "",
            "WAV audio (*.wav)",
        )
        if filepath:
            self._load_pad_file(slot, filepath)

    def _clear_pad(self, slot: int) -> bool:
        if not 0 <= slot < len(self._pads()):
            return False

        self._pads()[slot] = SoundPad()
        self._refresh_pads()
        self._save_soundboard()
        self._refresh_hotkeys()
        return True

    def _show_pad_menu(self, slot: int, position) -> None:
        pad = self._pads()[slot]
        menu = QMenu(self)

        bind = menu.addAction("Bind Hotkey")
        bind.setEnabled(bool(pad.filepath))
        bind.triggered.connect(
            lambda checked=False, index=slot: self._capture_hotkey(index)
        )

        clear = menu.addAction("Clear Pad")
        clear.setEnabled(bool(pad.filepath or pad.hotkey))
        clear.triggered.connect(
            lambda checked=False, index=slot: self._clear_pad(index)
        )

        menu.exec(self.pad_buttons[slot].mapToGlobal(position))

    def _capture_hotkey(self, slot: int) -> None:
        dialog = HotkeyCaptureDialog(self)
        if (
            dialog.exec() == QDialog.DialogCode.Accepted
            and dialog.hotkey
        ):
            self._bind_hotkey(slot, dialog.hotkey)

    def _bind_hotkey(self, slot: int, hotkey: str) -> bool:
        if not 0 <= slot < len(self._pads()):
            return False

        hotkey = (hotkey or "").strip()
        if not hotkey:
            self._show_error("No hotkey captured.")
            return False

        pad = self._pads()[slot]
        if not pad.filepath:
            self._show_error("Load a WAV file before binding a hotkey.")
            return False

        normalized = hotkey.casefold()
        for index, other in enumerate(self._pads()):
            if index == slot or not other.hotkey:
                continue
            if other.hotkey.strip().casefold() == normalized:
                self._show_error(
                    f"Hotkey {hotkey} is already bound to "
                    f"pad {index + 1:02d}."
                )
                return False

        pad.hotkey = hotkey
        self._refresh_pad(slot)
        self._save_soundboard()
        self._refresh_hotkeys()
        return True

    def _build_hotkey_mapping(self) -> dict:
        mapping = {}
        assigned = {}

        for index, pad in enumerate(self._pads()):
            hotkey = (pad.hotkey or "").strip()
            if not pad.filepath or not hotkey:
                continue

            normalized = hotkey.casefold()
            if normalized in assigned:
                self._show_error(
                    f"Hotkey {hotkey} is assigned to multiple pads; "
                    f"pad {index + 1:02d} ignored."
                )
                continue

            assigned[normalized] = index
            mapping[hotkey] = (
                lambda pad_index=index: self.pad_hotkey_triggered.emit(
                    pad_index
                )
            )

        return mapping

    def _refresh_hotkeys(self, *, initial: bool = False) -> None:
        mapping = self._build_hotkey_mapping()
        try:
            if not mapping:
                self.hotkey_manager.stop()
            elif initial:
                self.hotkey_manager.start(mapping)
            else:
                self.hotkey_manager.update_mapping(mapping)
        except Exception as exc:
            self._show_error(f"Hotkey setup failed: {exc}")

    @Slot(int)
    def _trigger_pad(self, slot: int) -> bool:
        if not 0 <= slot < len(self._pads()):
            return False

        pad = self._pads()[slot]
        if not pad.filepath:
            self._show_error(
                f"PAD {slot + 1:02d} EMPTY // DOUBLE-CLICK TO LOAD"
            )
            return False

        trigger = getattr(self.service, "trigger_pad", None)
        if trigger is None:
            self._show_error("Audio engine cannot trigger pads.")
            return False

        try:
            started = trigger(pad.filepath, pad.volume, pad.randomize)
        except Exception as exc:
            self._show_error(f"Pad trigger failed: {exc}")
            return False

        if not started and not self._online:
            self._show_error("ENGAGE THE ENGINE BEFORE TRIGGERING PADS")
        return bool(started)

    @Slot(str)
    def _on_theme_selected(self, name: str) -> None:
        try:
            self.theme_manager.set_theme(name)
        except Exception as exc:
            self._show_error(f"Theme change failed: {exc}")
            return

        for widget in self.findChildren(QWidget):
            widget.update()

    def _save_soundboard(self) -> bool:
        try:
            self._soundboard_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            self.soundboard_config.save(self._soundboard_path)
            return True
        except (OSError, TypeError) as exc:
            self._show_error(f"Soundboard save failed: {exc}")
            return False

    def _start_tutorial(self) -> None:
        if self.tutorial_panel is None:
            self.tutorial_panel = TutorialPanel(self)
        self.tutorial_panel.start(self._tutorial_steps())

    def _tutorial_steps(self) -> list[dict]:
        return [
            {
                "title": "Header / Gain",
                "desc": (
                    "This is your Input Gain. Adjust this until your mic "
                    "peaks around -6 dB on the VU meter. Too high, and it "
                    "distorts."
                ),
                "target": self.input_faders["mic"],
            },
            {
                "title": "VU Meter",
                "desc": (
                    "dBFS (Decibels relative to Full Scale). 0 is maximum "
                    "volume (clipping). Watch the PEAK marker to ensure you "
                    "never hit 0."
                ),
                "target": self.output_meters["headphones"],
            },
            {
                "title": "Routing Matrix",
                "desc": (
                    "Src is Source (Mic, System, Soundboard), Dst is "
                    "Destination. A LINK routes audio. To send your mic to "
                    "Discord, link 'MIC' to 'VIRTUAL CABLE'."
                ),
                "target": self.matrix_panel,
            },
            {
                "title": "Endpoints",
                "desc": (
                    "Cable Output is the input Discord/OBS uses. Cable "
                    "Speaker is for monitoring. Select 'Cable In 16ch' for "
                    "advanced multi-channel routing."
                ),
                "target": self.device_bar,
            },
            {
                "title": "Aux Bay",
                "desc": (
                    "Right-click a pad to bind a global hotkey or load a "
                    "WAV. Pressing the hotkey triggers the sound on the "
                    "Soundboard bus."
                ),
                "target": self.pad_buttons[0],
            },
        ]

    @staticmethod
    def _label(text: str, object_name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        return label

    def _connect_service(self) -> None:
        self.service.running_changed.connect(self._on_running_changed)
        self.service.status_changed.connect(self._on_status_changed)
        self.service.error_occurred.connect(self._on_error)

    def _populate_devices(self, devices: list[dict]) -> None:
        self._devices = list(devices)
        inputs = [device for device in self._devices if device.get("inputs", 0) > 0]
        outputs = [device for device in self._devices if device.get("outputs", 0) >= 2]
        choices = {
            "mic": inputs,
            "system": inputs,
            "headphones": outputs,
            "virtual_cable": outputs,
        }
        previous = {
            key: combo.currentData()
            for key, combo in self.device_combos.items()
        }

        for key, values in choices.items():
            combo = self.device_combos[key]
            combo.blockSignals(True)
            combo.clear()
            for device in values:
                display_name = self.ui_config.device_label(
                    device["name"]
                )
                combo.addItem(
                    f"{device['index']:02d}  {display_name}",
                    int(device["index"]),
                )
            combo.blockSignals(False)

        defaults = {
            "mic": self._default_index(
                inputs,
                ("usb audio", "microphone"),
                previous.get("mic"),
                None,
            ),
            "system": self._default_index(
                inputs,
                ("cable output", "vb-audio", "virtual cable"),
                previous.get("system"),
                None,
            ),
            "headphones": self._default_index(
                outputs,
                ("speakers", "usb audio"),
                previous.get("headphones"),
                None,
            ),
            "virtual_cable": self._default_index(
                outputs,
                ("cable in", "vb-audio", "virtual cable"),
                previous.get("virtual_cable"),
                None,
            ),
        }

        for key, index in defaults.items():
            combo = self.device_combos[key]
            if index is not None:
                position = combo.findData(index)
                if position >= 0:
                    combo.setCurrentIndex(position)

        if not inputs or not outputs:
            self.start_button.setEnabled(False)
            self._set_status("OFFLINE // NO WASAPI ENDPOINTS")
            self._show_error("WASAPI endpoint pair not found.")
        else:
            self.start_button.setEnabled(not self._online)
            self._set_status("OFFLINE // READY")

    @staticmethod
    def _default_index(
        devices: list[dict],
        fragments: tuple[str, ...],
        previous,
        exclude,
    ):
        if previous is not None:
            for device in devices:
                if device["index"] == previous:
                    return previous

        candidates = [
            device for device in devices
            if device["index"] != exclude
        ] or devices
        for fragment in fragments:
            for device in candidates:
                if fragment in device["name"].lower():
                    return int(device["index"])
        return int(candidates[0]["index"]) if candidates else None

    def _selected_config(self) -> EngineConfig | None:
        data = {}
        for key, combo in self.device_combos.items():
            value = combo.currentData()
            if value is None:
                return None
            data[key] = int(value)
        return EngineConfig(**data)

    def _has_endpoints(self) -> bool:
        return all(combo.count() > 0 for combo in self.device_combos.values())

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self.status_label.setProperty("online", text.startswith("AUDIO ONLINE"))
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _show_error(self, text: str) -> None:
        self.error_label.setText(text)

    def _start(self) -> None:
        config = self._selected_config()
        if config is None:
            self._show_error("Select all four endpoints before engaging.")
            return
        if config.mic == config.system:
            self._show_error("MIC and SYSTEM must use different endpoints.")
            return
        if config.headphones == config.virtual_cable:
            self._show_error(
                "HEADPHONES and VIRTUAL CABLE must use different endpoints."
            )
            return

        self.error_label.clear()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self._set_status("STARTING // REQUESTING ENGINE")

        if not self.service.start(config):
            self._show_error("Engine is busy; stop before restarting.")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self._set_status("OFFLINE // BUSY")

    def _stop(self) -> None:
        self._set_status("STOPPING // RELEASING")
        self.stop_button.setEnabled(False)
        if not self.service.stop():
            self._show_error("Engine did not acknowledge stop.")
            self.stop_button.setEnabled(True)

    @Slot(bool)
    def _on_running_changed(self, online: bool) -> None:
        self._online = bool(online)
        if self._online:
            self._set_status("AUDIO ONLINE")
            self._set_controls_enabled(True)
            self._sync_ui_to_engine()
            self._poll_count = 0
            self._update_telemetry()
            self._timer.start()
            self._poll_meters()
        else:
            self._timer.stop()
            self._set_status("OFFLINE // STOPPED")
            self._set_controls_enabled(False)
            for meter in self.output_meters.values():
                meter.set_level(0.0, 0.0)
            self._update_telemetry()
            self.start_button.setEnabled(self._has_endpoints())
            self.stop_button.setEnabled(False)

    def _set_controls_enabled(self, online: bool) -> None:
        for fader in self.input_faders.values():
            fader.setEnabled(online)
        for fader in self.output_faders.values():
            fader.setEnabled(online)
        for button in self.route_buttons.values():
            button.setEnabled(online)
        for meter in self.output_meters.values():
            meter.setEnabled(online)
        for combo in self.device_combos.values():
            combo.setEnabled(not online)
        self.refresh_button.setEnabled(not online)
        self.start_button.setEnabled(not online and self._has_endpoints())
        self.stop_button.setEnabled(online)

    def _sync_ui_to_engine(self) -> None:
        for key, fader in self.input_faders.items():
            self.service.set_volume(key, fader.value())
        for key, fader in self.output_faders.items():
            self.service.set_volume(key, fader.value())
        for source, destination in self.route_buttons:
            self.service.set_route(
                source,
                destination,
                self._effective_route((source, destination)),
            )

    @Slot(str)
    def _on_status_changed(self, text: str) -> None:
        self._set_status(text)

    @Slot(str)
    def _on_error(self, text: str) -> None:
        self.error_label.setToolTip(text)
        self._show_error(
            text if len(text) <= 220 else text[:217] + "..."
        )

    def _on_input_volume(self, source: str, value: float) -> None:
        if self._online and not self.service.set_volume(source, value):
            self._show_error(f"Volume rejected for {source}.")

    def _on_output_volume(self, output: str, value: float) -> None:
        if self._online and not self.service.set_volume(output, value):
            self._show_error(f"Volume rejected for {output}.")

    def _on_route_changed(self, source: str, destination: str, checked: bool) -> None:
        if not self._online:
            return

        crosspoint = (source, destination)
        if not self.service.set_route(
            source,
            destination,
            self._effective_route(crosspoint),
        ):
            button = self.route_buttons[crosspoint]
            button.blockSignals(True)
            button.setChecked(not checked)
            button.blockSignals(False)
            self._show_error("Route rejected by engine.")
            return

        button = self.route_buttons[crosspoint]
        button.setText("OPEN" if checked else "LINK")

    def _effective_route(self, crosspoint: tuple[str, str]) -> bool:
        enabled = self.route_buttons[crosspoint].isChecked()
        if (
            crosspoint == ("soundboard", "headphones")
            and self.monitor_button is not None
            and self.monitor_button.isChecked()
        ):
            return True
        return enabled

    def _apply_preset(self, name: str) -> bool:
        active = PRESET_ROUTES.get(name)
        if active is None:
            return False

        for crosspoint, button in self.route_buttons.items():
            enabled = crosspoint in active
            button.blockSignals(True)
            button.setChecked(enabled)
            button.blockSignals(False)
            button.setText("OPEN" if enabled else "LINK")

            if self._online:
                source, destination = crosspoint
                if not self.service.set_route(
                    source,
                    destination,
                    self._effective_route(crosspoint),
                ):
                    self._show_error(
                        f"Preset {name.upper()} rejected by engine."
                    )
                    return False

        return True

    def _on_monitor_toggled(self, checked: bool) -> None:
        if not self._online:
            return

        if not self.service.set_route(
            "soundboard",
            "headphones",
            self._effective_route(("soundboard", "headphones")),
        ):
            self._show_error("Monitor routing rejected by engine.")

    @Slot()
    def _poll_meters(self) -> None:
        if not self._online:
            return
        for key, meter in self.output_meters.items():
            left, right = self.service.get_levels(key)
            meter.set_level(left, right)
        self._poll_count += 1
        if self._poll_count % 10 == 0:
            self._update_telemetry()

    def _update_telemetry(self) -> None:
        if not self._online:
            self.telemetry_label.setText(
                "ENGINE OFFLINE\nNO CALLBACK DATA\nAWAITING ENGAGE"
            )
            return

        provider = getattr(self.service, "diagnostics", None)
        if provider is None:
            self.telemetry_label.setText(
                "ENGINE ONLINE\nTELEMETRY UNAVAILABLE"
            )
            return

        try:
            data = provider()
        except Exception as exc:
            self.telemetry_label.setText(f"TELEMETRY ERROR\n{exc}")
            return

        lines = [
            "HEALTH // " + ("OK" if data.get("healthy") else "FAULT")
        ]
        for key, label in (("mic", "MIC"), ("system", "SYS")):
            info = data.get("capture", {}).get(key, {})
            lines.append(
                f"{label:<4} DROP {info.get('dropped_frames', 0):>5}"
                f"  STAT {info.get('status_events', 0):>3}"
            )
        for key, label in (
            ("headphones", "PHONES"),
            ("virtual_cable", "CABLE "),
        ):
            info = data.get("outputs", {}).get(key, {})
            readers = info.get("readers", [])
            underflows = sum(
                reader.get("underflows", 0)
                for reader in readers
            )
            lines.append(
                f"{label:<6} UF {underflows:>4}"
                f" CLIP {info.get('clipped_blocks', 0):>3}"
                f" OVR {info.get('status_events', 0):>3}"
            )
        error = data.get("last_error")
        if error:
            lines.append("ERR " + str(error)[:46])
        self.telemetry_label.setText("\n".join(lines))

    def _refresh_devices(self) -> None:
        self._set_status("SCANNING // WASAPI")
        self.start_button.setEnabled(False)
        try:
            devices = self.service.list_devices()
        except Exception as exc:
            self._show_error(f"Endpoint scan failed: {exc}")
            self._set_status("OFFLINE // SCAN FAILED")
            return
        self._populate_devices(devices)

    def closeEvent(self, event) -> None:
        self._timer.stop()
        if self.tutorial_panel is not None:
            self.tutorial_panel.close_tutorial()

        try:
            self.hotkey_manager.stop()
        except Exception as exc:
            self._show_error(f"Hotkey shutdown failed: {exc}")

        shutdown = getattr(self.service, "shutdown", None)
        if shutdown is not None:
            shutdown(timeout=2.0)
        else:
            self.service.stop()
        super().closeEvent(event)
