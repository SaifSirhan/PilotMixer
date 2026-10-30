from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication, QWidget

from tutorial_panel import TutorialPanel


APP = QApplication.instance() or QApplication([])


class TutorialPanelTests(unittest.TestCase):
    def setUp(self):
        self.parent = QWidget()
        self.parent.resize(900, 650)
        self.parent.show()

        self.first_target = QWidget(self.parent)
        self.first_target.setGeometry(80, 70, 130, 40)
        self.first_target.show()

        self.second_target = QWidget(self.parent)
        self.second_target.setGeometry(400, 300, 160, 60)
        self.second_target.show()

        self.panel = TutorialPanel(self.parent)
        self.steps = [
            {
                "title": "Header / Gain",
                "desc": "First step",
                "target": self.first_target,
            },
            {
                "title": "VU Meter",
                "desc": "Second step",
                "target": self.second_target,
            },
        ]
        APP.processEvents()

    def tearDown(self):
        self.panel.close_tutorial()
        self.panel.deleteLater()
        self.parent.close()
        self.parent.deleteLater()
        APP.processEvents()

    def test_start_shows_first_step_and_resets_navigation(self):
        self.panel.start(self.steps)
        APP.processEvents()

        self.assertTrue(self.panel.isVisible())
        self.assertTrue(self.panel.overlay.isVisible())
        self.assertEqual(self.panel.current_idx, 0)
        self.assertEqual(self.panel.title.text(), "Header / Gain")
        self.assertEqual(self.panel.desc.text(), "First step")
        self.assertFalse(self.panel.btn_prev.isEnabled())
        self.assertTrue(self.panel.btn_next.isEnabled())
        self.assertEqual(self.panel.btn_next.text(), "NEXT")
        self.assertFalse(self.panel.overlay.target_rect.isNull())

        self.panel._next()
        APP.processEvents()

        self.assertEqual(self.panel.current_idx, 1)
        self.assertEqual(self.panel.title.text(), "VU Meter")
        self.assertTrue(self.panel.btn_prev.isEnabled())
        self.assertTrue(self.panel.btn_next.isEnabled())
        self.assertEqual(self.panel.btn_next.text(), "FINISH")

        self.panel.start(self.steps)
        APP.processEvents()

        self.assertEqual(self.panel.current_idx, 0)
        self.assertEqual(self.panel.title.text(), "Header / Gain")

    def test_highlight_widget_places_cutout_and_panel_near_target(self):
        self.panel.start(self.steps)
        self.panel._highlight_widget(self.second_target)
        APP.processEvents()

        target_rect = self.panel.overlay.target_rect
        expected = QRect(self.second_target.pos(), self.second_target.size())
        self.assertFalse(target_rect.isNull())
        self.assertTrue(target_rect.contains(expected))
        self.assertGreater(target_rect.width(), expected.width())
        self.assertGreater(target_rect.height(), expected.height())

        parent_global = QRect(
            self.parent.mapToGlobal(QPoint(0, 0)),
            self.parent.size(),
        )
        self.assertTrue(parent_global.contains(self.panel.frameGeometry()))

    def test_finish_on_last_step_closes_panel_and_overlay(self):
        self.panel.start(self.steps)
        self.panel._next()
        self.panel.btn_next.click()
        APP.processEvents()

        self.assertFalse(self.panel.isVisible())
        self.assertFalse(self.panel.overlay.isVisible())

    def test_close_hides_panel_and_overlay(self):
        self.panel.start(self.steps)
        self.panel.close_tutorial()
        APP.processEvents()

        self.assertFalse(self.panel.isVisible())
        self.assertFalse(self.panel.overlay.isVisible())


if __name__ == "__main__":
    unittest.main()
