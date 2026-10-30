from __future__ import annotations

import time
import unittest

from hotkey_manager import HotkeyManager


class TestHotkeyManager(unittest.TestCase):
    def setUp(self):
        self.mgr = HotkeyManager()
        self.called = False

    def tearDown(self):
        self.mgr.stop()

    def _dummy_callback(self):
        self.called = True

    def test_malformed_hotkey_is_rejected_before_hook_start(self):
        with self.assertRaises(RuntimeError):
            self.mgr.start(
                {"not_a_real_hotkey_12345": self._dummy_callback}
            )

        self.assertIsNone(self.mgr._listener)
        self.assertEqual(self.mgr._mapping, {})

    def test_start_and_stop_do_not_hang_or_leave_an_orphaned_thread(self):
        started_at = time.monotonic()
        self.mgr.start({"<ctrl>+<f12>": self._dummy_callback})
        start_elapsed = time.monotonic() - started_at

        listener = self.mgr._listener
        self.assertIsNotNone(listener)
        self.assertTrue(listener.is_alive())
        self.assertTrue(listener.daemon)

        stopped_at = time.monotonic()
        self.mgr.stop()
        stop_elapsed = time.monotonic() - stopped_at

        self.assertIsNone(self.mgr._listener)
        self.assertEqual(self.mgr._mapping, {})
        self.assertFalse(listener.is_alive())
        self.assertLess(start_elapsed, 2.0)
        self.assertLess(stop_elapsed, 2.0)

    def test_update_mapping_stops_old_listener_and_starts_new_one(self):
        self.mgr.start({"<ctrl>+<f12>": self._dummy_callback})
        first_listener = self.mgr._listener

        self.mgr.update_mapping({"<ctrl>+<f11>": self._dummy_callback})
        second_listener = self.mgr._listener

        self.assertIsNot(first_listener, second_listener)
        self.assertFalse(first_listener.is_alive())
        self.assertTrue(second_listener.is_alive())
        self.assertTrue(second_listener.daemon)
        self.assertEqual(list(self.mgr._mapping), ["<ctrl>+<f11>"])

        self.mgr.stop()
        self.assertFalse(second_listener.is_alive())


if __name__ == "__main__":
    unittest.main()
