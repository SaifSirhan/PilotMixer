from __future__ import annotations

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

    def start(self, config):
        return True

    def stop(self):
        return True

    def shutdown(self, timeout=2.0):
        return True

    def set_route(self, source, destination, enabled):
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
