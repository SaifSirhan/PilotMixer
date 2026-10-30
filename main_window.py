from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cockpit_widgets import VUMeter, VerticalFader
from engine_service import EngineConfig, EngineService


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


class MainWindow(QMainWindow):
    def __init__(self, service=None, devices=None, parent=None):
        super().__init__(parent)

        self.service = service if service is not None else EngineService(parent=self)
        self._online = False
        self._devices = []
        self.input_faders = {}
        self.output_faders = {}
        self.output_meters = {}
        self.route_buttons = {}
        self.device_combos = {}

        self.setWindowTitle("PILOTMIXER // CUSTOM AUDIO ROUTER")
        self.resize(1440, 900)
        self.setMinimumSize(1220, 760)
        self._build_ui()
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
        from theme import BLACK

        root = QWidget()
        root.setObjectName("root")
        root.setStyleSheet(f"background: {BLACK};")
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

        layout = QHBoxLayout(header)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

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

        for column, (_, label_text) in enumerate(DEST_LABELS, start=1):
            head = QLabel(label_text)
            head.setObjectName("matrixHead")
            head.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(head, 0, column)

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
        panel, layout = self._new_panel("AUX BAY", "DEFERRED MODULES")
        panel.setMinimumWidth(220)

        layout.addWidget(self._label("SOUNDBOARD", "stripLabel"))
        pads = QGridLayout()
        pads.setSpacing(5)
        for slot in range(8):
            pad = QLabel(f"{slot + 1:02d}")
            pad.setObjectName("padSlot")
            pad.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pads.addWidget(pad, slot // 4, slot % 4)
        layout.addLayout(pads)
        layout.addWidget(
            self._label("BANK 00 // NO PAD SOURCE", "matrixNote")
        )

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
                combo.addItem(
                    f"{device['index']:02d}  {device['name']}",
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
        for (source, destination), button in self.route_buttons.items():
            self.service.set_route(source, destination, button.isChecked())

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
        if not self.service.set_route(source, destination, checked):
            button = self.route_buttons[(source, destination)]
            button.blockSignals(True)
            button.setChecked(not checked)
            button.blockSignals(False)
            self._show_error("Route rejected by engine.")
            return
        button = self.route_buttons[(source, destination)]
        button.setText("OPEN" if checked else "LINK")

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
        shutdown = getattr(self.service, "shutdown", None)
        if shutdown is not None:
            shutdown(timeout=2.0)
        else:
            self.service.stop()
        super().closeEvent(event)
