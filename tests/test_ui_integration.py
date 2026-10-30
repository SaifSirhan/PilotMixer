from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main_window import MainWindow
from soundboard_model import SoundboardConfig
from theme import ThemeManager


APP = QApplication.instance() or QApplication([])

DEVICE_FIXTURE = [
    {
        "index": 10,
        "name": "Microphone (USB Audio)",
        "inputs": 2,
        "outputs": 0,
        "default_sample_rate": 48000.0,
    },
    {
        "index": 11,
        "name": "CABLE Output (VB-Audio Virtual Cable)",
        "inputs": 2,
        "outputs": 0,
        "default_sample_rate": 48000.0,
    },
    {
        "index": 12,
        "name": "Speakers (USB Audio)",
        "inputs": 0,
        "outputs": 2,
        "default_sample_rate": 48000.0,
    },
    {
        "index": 13,
        "name": "CABLE In 16ch (VB-Audio Virtual Cable)",
        "inputs": 0,
        "outputs": 2,
        "default_sample_rate": 48000.0,
    },
]


def write_wav(path: Path, frames: int = 800) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * frames)


class FakeService(QObject):
    running_changed = Signal(bool)
    status_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        self.trigger_calls = []
        self.routes = []

    def start(self, config):
        return True

    def stop(self):
        return True

    def shutdown(self, timeout=2.0):
        return True

    def set_route(self, source, destination, enabled):
        self.routes.append((source, destination, enabled))
        return True

    def set_volume(self, channel, value):
        return True

    def get_levels(self, destination):
        return 0.0, 0.0

    def trigger_pad(self, filepath, volume=1.0, randomize=False):
        self.trigger_calls.append((filepath, volume, randomize))
        return True


class FakeHotkeyManager:
    def __init__(self):
        self.start_calls = []
        self.update_calls = []
        self.stop_calls = 0
        self.mapping = {}

    def start(self, mapping):
        self.start_calls.append(dict(mapping))
        self.mapping = dict(mapping)

    def update_mapping(self, mapping):
        self.update_calls.append(dict(mapping))
        self.mapping = dict(mapping)

    def stop(self):
        self.stop_calls += 1
        self.mapping = {}


class FakeThemeManager:
    def __init__(self):
        self.current_theme_name = "Pilot Mint"
        self.set_calls = []

    def set_theme(self, name):
        self.set_calls.append(name)
        self.current_theme_name = name
        return name


class SoundboardUiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.wav_one = self.root / "pad-one.wav"
        self.wav_two = self.root / "pad-two.wav"
        write_wav(self.wav_one)
        write_wav(self.wav_two)

        self.service = FakeService()
        self.hotkeys = FakeHotkeyManager()
        self.theme = FakeThemeManager()
        self.config = SoundboardConfig()
        self.config_path = self.root / "soundboard.json"
        self.window = MainWindow(
            service=self.service,
            devices=[],
            soundboard_config=self.config,
            soundboard_path=self.config_path,
            hotkey_manager=self.hotkeys,
            theme_manager=self.theme,
        )
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()

    def test_loading_wav_updates_config_and_button_text(self):
        self.assertTrue(
            self.window._load_pad_file(0, str(self.wav_one))
        )

        pad = self.window.soundboard_config.banks[0][0]
        self.assertEqual(pad.filepath, str(self.wav_one))
        self.assertEqual(self.window.pad_buttons[0].text(), "pad-one.wav")
        self.assertTrue(self.config_path.exists())

    def test_clicking_loaded_pad_calls_engine_trigger(self):
        self.window._load_pad_file(0, str(self.wav_one))

        QTest.mouseClick(
            self.window.pad_buttons[0],
            Qt.MouseButton.LeftButton,
        )

        self.assertEqual(
            self.service.trigger_calls,
            [(str(self.wav_one), 1.0, False)],
        )

    def test_ui_config_aliases_endpoint_and_matrix_labels(self):
        config_path = self.root / "ui_config.json"
        config_path.write_text(
            json.dumps(
                {
                    "device_aliases": {
                        "Cable Output": "Discord Input",
                    },
                    "matrix_aliases": {
                        "VIRTUAL CABLE": "DISCORD INPUT",
                    },
                }
            ),
            encoding="utf-8",
        )

        window = MainWindow(
            service=FakeService(),
            devices=DEVICE_FIXTURE,
            soundboard_config=SoundboardConfig(),
            soundboard_path=self.root / "aliased_soundboard.json",
            hotkey_manager=FakeHotkeyManager(),
            theme_manager=FakeThemeManager(),
            ui_config_path=config_path,
        )
        try:
            combo = window.device_combos["system"]
            labels = [
                combo.itemText(index)
                for index in range(combo.count())
            ]
            self.assertTrue(
                any("Discord Input" in label for label in labels)
            )
            self.assertEqual(
                window.matrix_headers["virtual_cable"].text(),
                "DISCORD INPUT",
            )
        finally:
            window.close()
            window.deleteLater()
            APP.processEvents()

    def test_streamer_preset_sets_all_crosspoints(self):
        self.service.running_changed.emit(True)
        self.service.routes.clear()

        QTest.mouseClick(
            self.window.preset_buttons["streamer"],
            Qt.MouseButton.LeftButton,
        )

        for source in ("mic", "system", "soundboard"):
            for destination in ("headphones", "virtual_cable"):
                self.assertTrue(
                    self.window.route_buttons[
                        (source, destination)
                    ].isChecked()
                )
                self.assertIn(
                    (source, destination, True),
                    self.service.routes,
                )

    def test_monitor_toggle_forces_soundboard_headphones_route(self):
        self.service.running_changed.emit(True)
        self.service.routes.clear()
        matrix_route = self.window.route_buttons[
            ("soundboard", "headphones")
        ]
        self.assertFalse(matrix_route.isChecked())

        QTest.mouseClick(
            self.window.monitor_button,
            Qt.MouseButton.LeftButton,
        )

        self.assertTrue(self.window.monitor_button.isChecked())
        self.assertFalse(matrix_route.isChecked())
        self.assertIn(
            ("soundboard", "headphones", True),
            self.service.routes,
        )

        self.service.routes.clear()
        QTest.mouseClick(
            self.window.monitor_button,
            Qt.MouseButton.LeftButton,
        )

        self.assertFalse(self.window.monitor_button.isChecked())
        self.assertIn(
            ("soundboard", "headphones", False),
            self.service.routes,
        )

    def test_binding_hotkey_updates_manager_and_trigger_path(self):
        self.window._load_pad_file(0, str(self.wav_one))

        self.assertTrue(self.window._bind_hotkey(0, "<ctrl>+<f9>"))

        pad = self.window.soundboard_config.banks[0][0]
        self.assertEqual(pad.hotkey, "<ctrl>+<f9>")
        self.assertEqual(len(self.hotkeys.update_calls), 1)
        self.assertIn("<ctrl>+<f9>", self.hotkeys.mapping)

        worker = threading.Thread(
            target=self.hotkeys.mapping["<ctrl>+<f9>"]
        )
        worker.start()
        worker.join()
        APP.processEvents()

        self.assertEqual(
            self.service.trigger_calls,
            [(str(self.wav_one), 1.0, False)],
        )

    def test_hotkey_conflict_is_rejected(self):
        self.window._load_pad_file(0, str(self.wav_one))
        self.window._load_pad_file(1, str(self.wav_two))
        self.assertTrue(self.window._bind_hotkey(0, "<ctrl>+<f9>"))
        updates_before = len(self.hotkeys.update_calls)

        result = self.window._bind_hotkey(1, "<ctrl>+<f9>")

        self.assertFalse(result)
        pad = self.window.soundboard_config.banks[0][1]
        self.assertIsNone(pad.hotkey)
        self.assertIn("already bound", self.window.error_label.text())
        self.assertEqual(len(self.hotkeys.update_calls), updates_before)
        self.assertEqual(list(self.hotkeys.mapping), ["<ctrl>+<f9>"])

    def test_tutorial_button_opens_five_step_panel(self):
        QTest.mouseClick(
            self.window.tutorial_button,
            Qt.MouseButton.LeftButton,
        )
        APP.processEvents()

        panel = self.window.tutorial_panel
        self.assertIsNotNone(panel)
        self.assertTrue(panel.isVisible())
        self.assertEqual(len(panel.steps), 5)
        self.assertEqual(panel.title.text(), "Header / Gain")
        self.assertIs(
            panel.steps[0]["target"],
            self.window.input_faders["mic"],
        )
        self.assertIs(
            panel.steps[1]["target"],
            self.window.output_meters["headphones"],
        )
        self.assertIs(panel.steps[2]["target"], self.window.matrix_panel)
        self.assertIs(panel.steps[3]["target"], self.window.device_bar)
        self.assertIs(panel.steps[4]["target"], self.window.pad_buttons[0])
        panel.close_tutorial()

    def test_existing_hotkeys_are_initialized_at_startup(self):
        config = SoundboardConfig()
        config.banks[0][0].filepath = str(self.wav_one)
        config.banks[0][0].hotkey = "<ctrl>+<f8>"
        hotkeys = FakeHotkeyManager()

        window = MainWindow(
            service=FakeService(),
            devices=[],
            soundboard_config=config,
            soundboard_path=self.root / "second.json",
            hotkey_manager=hotkeys,
            theme_manager=FakeThemeManager(),
        )
        try:
            self.assertEqual(len(hotkeys.start_calls), 1)
            self.assertIn("<ctrl>+<f8>", hotkeys.start_calls[0])
        finally:
            window.close()
            window.deleteLater()
            APP.processEvents()


class ThemeIntegrationTests(unittest.TestCase):
    def test_theme_combo_updates_application_stylesheet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            theme_config = root / "theme.json"
            with patch("theme.CONFIG_PATH", theme_config):
                manager = ThemeManager(APP)
                manager.set_theme("Pilot Mint")

                window = MainWindow(
                    service=FakeService(),
                    devices=[],
                    soundboard_config=SoundboardConfig(),
                    soundboard_path=root / "soundboard.json",
                    hotkey_manager=FakeHotkeyManager(),
                    theme_manager=manager,
                )
                try:
                    self.assertEqual(
                        window.theme_combo.currentText(),
                        "Pilot Mint",
                    )

                    window.theme_combo.setCurrentText("Pilot Light")

                    self.assertEqual(
                        manager.current_theme_name,
                        "Pilot Light",
                    )
                    self.assertIn("#f0f0f0", APP.styleSheet())
                finally:
                    manager.set_theme("Pilot Mint")
                    window.close()
                    window.deleteLater()
                    APP.processEvents()


if __name__ == "__main__":
    unittest.main()
