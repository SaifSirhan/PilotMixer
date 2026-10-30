from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from audio_engine import AudioEngine


def _initialize_com() -> bool:
    if sys.platform != "win32":
        return False

    import ctypes

    result = ctypes.windll.ole32.CoInitializeEx(None, 0)
    if result < 0:
        raise RuntimeError(
            f"COM initialization failed: 0x{result & 0xFFFFFFFF:08X}"
        )
    return True


def _uninitialize_com() -> None:
    if sys.platform != "win32":
        return

    import ctypes

    ctypes.windll.ole32.CoUninitialize()


@dataclass(frozen=True)
class EngineConfig:
    mic: int
    system: int
    headphones: int
    virtual_cable: int
    sample_rate: int = 48000
    buffer_ms: float = 30.0


def _default_engine_factory(config: EngineConfig) -> AudioEngine:
    return AudioEngine(
        config.mic,
        config.system,
        config.headphones,
        config.virtual_cable,
        sample_rate=config.sample_rate,
        buffer_ms=config.buffer_ms,
    )


class EngineService(QObject):
    running_changed = Signal(bool)
    status_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, engine_factory=None, parent=None):
        super().__init__(parent)
        self._engine_factory = engine_factory or _default_engine_factory
        self._mutex = threading.Lock()
        self._state = "offline"
        self._engine = None
        self._last_error = None
        self._stop_requested = False
        self._stop_event = threading.Event()

    @staticmethod
    def list_devices() -> list[dict]:
        return AudioEngine.list_wasapi_devices()

    @property
    def state(self) -> str:
        with self._mutex:
            return self._state

    @property
    def is_running(self) -> bool:
        return self.state == "online"

    @property
    def is_busy(self) -> bool:
        return self.state in ("starting", "stopping")

    @property
    def last_error(self) -> str | None:
        with self._mutex:
            return self._last_error

    def start(self, config: EngineConfig) -> bool:
        with self._mutex:
            if self._state != "offline":
                return False

            self._state = "starting"
            self._last_error = None
            self._stop_requested = False
            self._stop_event.clear()

        self.status_changed.emit("STARTING // NEGOTIATING WASAPI")
        threading.Thread(
            target=self._start_worker,
            args=(config,),
            name="PilotMixerEngine",
            daemon=True,
        ).start()
        return True

    def _start_worker(self, config: EngineConfig) -> None:
        com_initialized = False
        try:
            # PortAudio's WASAPI backend needs COM on this thread. Keeping
            # this worker alive retains the apartment for the engine.
            com_initialized = _initialize_com()
            engine = self._engine_factory(config)
            engine.start()
        except Exception as exc:
            message = str(exc)
            with self._mutex:
                self._engine = None
                self._state = "offline"
                self._last_error = message

            self.error_occurred.emit(message)
            self.running_changed.emit(False)
            self.status_changed.emit("OFFLINE // START FAILED")
            if com_initialized:
                _uninitialize_com()
            return

        with self._mutex:
            self._engine = engine
            stop_requested = (
                self._stop_requested or self._stop_event.is_set()
            )
            self._stop_requested = False
            self._state = "stopping" if stop_requested else "online"

        if not stop_requested:
            self.running_changed.emit(True)
            self.status_changed.emit("AUDIO ONLINE")
            self._stop_event.wait()
            with self._mutex:
                self._state = "stopping"

        error = None
        try:
            engine.stop()
        except Exception as exc:
            error = str(exc)

        self._finish_stop(error)
        if com_initialized:
            _uninitialize_com()

    def stop(self) -> bool:
        with self._mutex:
            if self._state == "offline":
                return True

            if self._state == "stopping":
                return True

            stopping_after_start = self._state == "starting"
            self._stop_requested = True
            self._stop_event.set()
            if not stopping_after_start:
                self._state = "stopping"

        if stopping_after_start:
            self.status_changed.emit("STOPPING // AFTER START")
        else:
            self.status_changed.emit("STOPPING // RELEASING DEVICES")
        return True

    def _finish_stop(self, error: str | None) -> None:
        with self._mutex:
            self._engine = None
            self._state = "offline"
            self._last_error = error

        if error:
            self.error_occurred.emit(f"STOP FAILED: {error}")
            self.status_changed.emit("OFFLINE // STOP FAILED")
        else:
            self.status_changed.emit("OFFLINE // STOPPED")
        self.running_changed.emit(False)

    def set_route(
        self,
        source: str,
        destination: str,
        enabled: bool,
    ) -> bool:
        engine = self._online_engine()
        if engine is None:
            return False

        try:
            engine.set_route(source, destination, enabled)
            return True
        except Exception as exc:
            self._report_operation_error(str(exc))
            return False

    def set_volume(self, channel: str, value: float) -> bool:
        engine = self._online_engine()
        if engine is None:
            return False

        try:
            engine.set_volume(channel, value)
            return True
        except Exception as exc:
            self._report_operation_error(str(exc))
            return False

    def trigger_pad(
        self,
        filepath: str,
        volume: float = 1.0,
        randomize: bool = False,
    ) -> bool:
        engine = self._online_engine()
        if engine is None:
            return False

        try:
            engine.trigger_pad(filepath, volume, randomize)
            return True
        except Exception as exc:
            self._report_operation_error(str(exc))
            return False

    def get_levels(self, destination: str) -> tuple[float, float]:
        engine = self._online_engine()
        if engine is None:
            return 0.0, 0.0

        try:
            return engine.get_levels(destination)
        except Exception:
            return 0.0, 0.0

    def shutdown(self, timeout: float = 2.0) -> bool:
        if self.state == "offline":
            return True

        self.stop()
        deadline = time.monotonic() + max(0.0, float(timeout))
        while time.monotonic() < deadline:
            if self.state == "offline":
                return True
            time.sleep(0.01)
        return self.state == "offline"

    def diagnostics(self) -> dict:
        engine = self._online_engine()
        if engine is None:
            with self._mutex:
                return {
                    "healthy": False,
                    "last_error": self._last_error,
                    "capture": {},
                    "outputs": {},
                }

        try:
            return engine.diagnostics()
        except Exception as exc:
            return {
                "healthy": False,
                "last_error": str(exc),
                "capture": {},
                "outputs": {},
            }

    def _online_engine(self):
        with self._mutex:
            if self._state != "online":
                return None
            return self._engine

    def _report_operation_error(self, message: str) -> None:
        with self._mutex:
            self._last_error = message
        self.error_occurred.emit(message)
