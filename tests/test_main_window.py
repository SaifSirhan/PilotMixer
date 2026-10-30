from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from engine_service import EngineService
from main_window import MainWindow


APP = QApplication.instance() or QApplication([])

DEVICES = [
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


class FakeService(QObject):
    running_changed = Signal(bool)
    status_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        self.start_calls = []
        self.stop_calls = 0
        self.routes = []
        self.volumes = []
        self.levels = {}

    def start(self, config):
        self.start_calls.append(config)
        self.status_changed.emit("STARTING // TEST")
        return True

    def stop(self):
        self.stop_calls += 1
        self.running_changed.emit(False)
        return True

    def set_route(self, source, destination, enabled):
        self.routes.append((source, destination, enabled))
        return True

    def set_volume(self, channel, value):
        self.volumes.append((channel, value))
        return True

    def get_levels(self, destination):
        return self.levels.get(destination, (0.0, 0.0))


class MainWindowTests(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()
        self.window = MainWindow(service=self.service, devices=DEVICES)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()

    def test_default_service_is_parented_to_the_window(self):
        window = MainWindow(devices=[])
        try:
            self.assertIsInstance(window.service, EngineService)
            self.assertIs(window.service.parent(), window)
        finally:
            window.close()

    def test_shell_starts_offline_without_opening_audio(self):
        self.assertIn("OFFLINE", self.window.status_label.text())
        self.assertEqual(self.service.start_calls, [])
        self.assertTrue(self.window.start_button.isEnabled())
        self.assertFalse(self.window.stop_button.isEnabled())
        self.assertFalse(self.window.input_faders["mic"].isEnabled())
        self.assertFalse(self.window.route_buttons[("mic", "headphones")].isEnabled())
        self.assertFalse(self.window.output_meters["headphones"].isEnabled())

        self.assertEqual(
            self.window.device_combos["mic"].currentData(),
            10,
        )
        self.assertEqual(
            self.window.device_combos["system"].currentData(),
            11,
        )
        self.assertEqual(
            self.window.device_combos["headphones"].currentData(),
            12,
        )
        self.assertEqual(
            self.window.device_combos["virtual_cable"].currentData(),
            13,
        )

    def test_start_uses_selected_devices_and_then_enables_controls(self):
        self.window.start_button.click()

        self.assertEqual(len(self.service.start_calls), 1)
        config = self.service.start_calls[0]
        self.assertEqual(
            (config.mic, config.system, config.headphones, config.virtual_cable),
            (10, 11, 12, 13),
        )
        self.assertFalse(self.window.start_button.isEnabled())
        self.assertTrue(self.window.stop_button.isEnabled())
        self.assertIn("STARTING", self.window.status_label.text())

        self.service.running_changed.emit(True)

        self.assertIn("ONLINE", self.window.status_label.text())
        self.assertTrue(self.window.input_faders["mic"].isEnabled())
        self.assertTrue(self.window.output_faders["headphones"].isEnabled())
        self.assertTrue(self.window.route_buttons[("mic", "headphones")].isEnabled())
        self.assertFalse(self.window.device_combos["mic"].isEnabled())
        self.assertFalse(self.window.start_button.isEnabled())
        self.assertTrue(self.window.stop_button.isEnabled())

    def test_route_and_fader_changes_are_forwarded(self):
        self.service.running_changed.emit(True)

        self.window.route_buttons[("mic", "headphones")].click()
        self.window.input_faders["mic"].set_value(0.42)
        self.window.output_faders["virtual_cable"].set_value(0.75)

        self.assertIn(
            ("mic", "headphones", True),
            self.service.routes,
        )
        self.assertIn(("mic", 0.42), self.service.volumes)
        self.assertIn(("virtual_cable", 0.75), self.service.volumes)

    def test_meter_polling_uses_real_service_levels(self):
        self.service.running_changed.emit(True)
        self.service.levels = {
            "headphones": (0.5, 0.25),
            "virtual_cable": (0.0, 0.0),
        }

        self.window._poll_meters()

        left = self.window.output_meters["headphones"]._levels[0]
        right = self.window.output_meters["headphones"]._levels[1]
        self.assertAlmostEqual(left, -6.0206, places=2)
        self.assertAlmostEqual(right, -12.0412, places=2)

    def test_stop_and_error_return_ui_to_safe_state(self):
        self.service.running_changed.emit(True)
        self.service.error_occurred.emit("route rejected")

        self.assertIn("route rejected", self.window.error_label.text())

        self.window.stop_button.click()
        self.assertEqual(self.service.stop_calls, 1)
        self.assertIn("OFFLINE", self.window.status_label.text())
        self.assertTrue(self.window.start_button.isEnabled())
        self.assertFalse(self.window.stop_button.isEnabled())
        self.assertFalse(self.window.input_faders["mic"].isEnabled())
        self.assertFalse(self.window.output_faders["headphones"].isEnabled())

    def test_close_stops_the_service(self):
        self.service.running_changed.emit(True)
        self.window.close()

        self.assertEqual(self.service.stop_calls, 1)

    def test_duplicate_capture_endpoints_are_rejected_before_start(self):
        self.window.device_combos["system"].setCurrentIndex(
            self.window.device_combos["mic"].currentIndex()
        )

        self.window.start_button.click()

        self.assertEqual(self.service.start_calls, [])
        self.assertIn("different", self.window.error_label.text())


if __name__ == "__main__":
    unittest.main()
