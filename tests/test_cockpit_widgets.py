from __future__ import annotations

import os
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from cockpit_widgets import MINT, RED, VUMeter, VerticalFader


APP = QApplication.instance() or QApplication([])


class VerticalFaderTests(unittest.TestCase):
    def setUp(self):
        self.fader = VerticalFader()

    def tearDown(self):
        self.fader.deleteLater()

    def test_value_is_clamped_and_emitted_only_on_change(self):
        changes = []
        self.fader.valueChanged.connect(changes.append)

        self.assertEqual(self.fader.value(), 1.0)
        self.fader.set_value(2.0)
        self.assertEqual(self.fader.value(), 1.0)
        self.assertEqual(changes, [])

        self.fader.set_value(-1.0)
        self.assertEqual(self.fader.value(), 0.0)
        self.assertEqual(changes, [0.0])

        self.fader.set_value(0.4)
        self.assertEqual(changes, [0.0, 0.4])

    def test_keyboard_adjusts_value_with_focus(self):
        self.fader.show()
        self.fader.activateWindow()
        self.fader.setFocus()
        APP.processEvents()
        self.fader.set_value(0.5)

        QTest.keyClick(self.fader, Qt.Key.Key_Up)
        self.assertAlmostEqual(self.fader.value(), 0.51, places=5)

        QTest.keyClick(
            self.fader,
            Qt.Key.Key_Up,
            Qt.KeyboardModifier.ShiftModifier,
        )
        self.assertAlmostEqual(self.fader.value(), 0.511, places=5)

    def test_mouse_press_maps_to_value_and_clamps(self):
        self.fader.resize(78, 300)
        self.fader.show()
        APP.processEvents()

        QTest.mouseClick(
            self.fader,
            Qt.MouseButton.LeftButton,
            pos=QPoint(39, 0),
        )
        self.assertEqual(self.fader.value(), 1.0)

        QTest.mouseClick(
            self.fader,
            Qt.MouseButton.LeftButton,
            pos=QPoint(39, 299),
        )
        self.assertEqual(self.fader.value(), 0.0)

    def test_cross_thread_update_is_rejected(self):
        errors = []

        def update():
            try:
                self.fader.set_value(0.2)
            except RuntimeError as exc:
                errors.append(str(exc))

        worker = threading.Thread(target=update)
        worker.start()
        worker.join()

        self.assertEqual(len(errors), 1)
        self.assertIn("GUI thread", errors[0])

    def test_paint_produces_accent_pixels(self):
        self.fader.resize(78, 300)
        self.fader.set_value(0.5)
        image = QImage(self.fader.size(), QImage.Format.Format_ARGB32)
        image.fill(QColor("black"))

        self.fader.render(image)

        accent_pixels = 0
        for y in range(image.height()):
            for x in range(image.width()):
                color = image.pixelColor(x, y)
                if color.green() > 150 and color.blue() > 100:
                    accent_pixels += 1

        self.assertGreater(accent_pixels, 10)


class VUMeterTests(unittest.TestCase):
    def setUp(self):
        self.meter = VUMeter()
        self.meter.resize(120, 280)

    def tearDown(self):
        self.meter.deleteLater()

    def test_levels_change_painted_meter(self):
        self.meter.set_level(1.0, 0.0)
        image = QImage(self.meter.size(), QImage.Format.Format_ARGB32)
        image.fill(QColor("black"))

        self.meter.render(image)

        filled = 0
        for y in range(image.height()):
            for x in range(image.width()):
                if image.pixelColor(x, y) in (MINT, RED):
                    filled += 1

        self.assertGreater(filled, 20)

    def test_peak_hold_does_not_drop_immediately(self):
        self.meter.set_level(0.5, 0.5)
        initial_peak = self.meter._peaks[0]

        self.assertAlmostEqual(initial_peak, -6.0206, places=2)
        self.meter._tick()
        self.assertAlmostEqual(
            self.meter._peaks[0],
            initial_peak,
            places=2,
        )

    def test_set_level_clamps_display_range_and_handles_nan(self):
        self.meter.set_level(float("nan"), -1.0)
        self.meter._tick()

        self.assertEqual(
            self.meter._levels,
            [self.meter.FLOOR_DB, self.meter.FLOOR_DB],
        )


if __name__ == "__main__":
    unittest.main()
