from __future__ import annotations

import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from engine_service import EngineConfig, EngineService


APP = QApplication.instance() or QApplication([])


def wait_until(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        APP.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return False


class FakeEngine:
    def __init__(self, config):
        self.config = config
        self.started = False
        self.stopped = False
        self.routes = []
        self.volumes = []
        self.levels = (0.1, 0.2)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def set_route(self, source, destination, enabled):
        self.routes.append((source, destination, enabled))

    def set_volume(self, channel, value):
        self.volumes.append((channel, value))

    def get_levels(self, destination):
        return self.levels


class FailingEngine(FakeEngine):
    def start(self):
        raise RuntimeError("device busy")


class EngineServiceTests(unittest.TestCase):
    def setUp(self):
        self.created = []

        def factory(config):
            engine = FakeEngine(config)
            self.created.append(engine)
            return engine

        self.service = EngineService(engine_factory=factory)
        self.config = EngineConfig(1, 2, 3, 4)

    def tearDown(self):
        if self.service.is_busy or self.service.is_running:
            self.service.stop()
            wait_until(lambda: not self.service.is_busy)

    def test_start_stop_and_parameter_forwarding(self):
        states = []
        self.service.running_changed.connect(states.append)

        self.assertTrue(self.service.start(self.config))
        self.assertTrue(
            wait_until(
                lambda: self.service.is_running and states == [True]
            )
        )

        engine = self.created[0]
        self.assertTrue(engine.started)
        self.assertEqual(engine.config, self.config)
        self.assertEqual(states, [True])
        self.assertEqual(self.service.get_levels("headphones"), (0.1, 0.2))

        self.assertTrue(self.service.set_route("mic", "headphones", True))
        self.assertTrue(self.service.set_volume("mic", 0.5))
        self.assertEqual(engine.routes, [("mic", "headphones", True)])
        self.assertEqual(engine.volumes, [("mic", 0.5)])

        self.assertTrue(self.service.stop())
        self.assertTrue(
            wait_until(
                lambda: not self.service.is_busy
                and states == [True, False]
            )
        )
        self.assertFalse(self.service.is_running)
        self.assertTrue(engine.stopped)
        self.assertEqual(states, [True, False])

    def test_shutdown_waits_until_the_engine_is_offline(self):
        self.assertTrue(self.service.start(self.config))
        self.assertTrue(wait_until(lambda: self.service.is_running))

        self.assertTrue(self.service.shutdown(timeout=2.0))
        self.assertEqual(self.service.state, "offline")
        self.assertFalse(self.service.is_busy)
        self.assertTrue(self.created[0].stopped)

    def test_start_failure_returns_to_offline(self):
        def factory(config):
            return FailingEngine(config)

        self.service = EngineService(engine_factory=factory)
        errors = []
        states = []
        self.service.error_occurred.connect(errors.append)
        self.service.running_changed.connect(states.append)

        self.assertTrue(self.service.start(self.config))
        self.assertTrue(
            wait_until(lambda: len(states) == 1 and len(errors) == 1)
        )
        self.assertFalse(self.service.is_busy)

        self.assertFalse(self.service.is_running)
        self.assertEqual(self.service.state, "offline")
        self.assertTrue(any("device busy" in error for error in errors))
        self.assertEqual(states, [False])
        self.assertEqual(self.service.get_levels("headphones"), (0.0, 0.0))

    def test_start_is_rejected_while_active(self):
        self.assertTrue(self.service.start(self.config))
        self.assertTrue(wait_until(lambda: self.service.is_running))

        self.assertFalse(self.service.start(self.config))
        self.assertEqual(len(self.created), 1)

    def test_parameters_are_rejected_while_offline(self):
        self.assertFalse(self.service.set_route("mic", "headphones", True))
        self.assertFalse(self.service.set_volume("mic", 0.5))
        self.assertEqual(self.service.get_levels("headphones"), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
