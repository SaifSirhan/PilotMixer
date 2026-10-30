from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from typing import Callable

from pynput import keyboard


_START_TIMEOUT_SECONDS = 1.0
_STOP_TIMEOUT_SECONDS = 1.0


class HotkeyManager:
    def __init__(self):
        self._listener = None
        self._lock = threading.Lock()
        self._mapping: dict[str, Callable] = {}

    def _validate_mapping(self, mapping: Mapping[str, Callable]) -> None:
        if not isinstance(mapping, Mapping):
            raise TypeError("Hotkey mapping must be a mapping.")

        keys = list(mapping.keys())
        if len(keys) != len(set(keys)):
            # A dict cannot hold duplicates; this guards mapping-like inputs.
            raise ValueError("Duplicate hotkeys detected in mapping.")

        if any(not isinstance(key, str) or not key.strip() for key in keys):
            raise ValueError("Hotkey keys must be non-empty strings.")

        if any(not callable(callback) for callback in mapping.values()):
            raise TypeError("Hotkey callbacks must be callable.")

    def start(self, mapping: Mapping[str, Callable]) -> None:
        with self._lock:
            self._validate_mapping(mapping)
            self._stop_listener_locked()
            self._start_listener_locked(mapping)

    def stop(self) -> None:
        with self._lock:
            self._stop_listener_locked()

    def update_mapping(self, mapping: Mapping[str, Callable]) -> None:
        with self._lock:
            self._validate_mapping(mapping)
            self._stop_listener_locked()
            self._start_listener_locked(mapping)

    def _start_listener_locked(
        self,
        mapping: Mapping[str, Callable],
    ) -> None:
        self._mapping = dict(mapping)
        listener = None

        try:
            listener = keyboard.GlobalHotKeys(self._mapping)
            listener.daemon = True
            listener.start()

            deadline = time.monotonic() + _START_TIMEOUT_SECONDS
            while not listener.running and time.monotonic() < deadline:
                time.sleep(0.005)

            if not listener.running:
                raise RuntimeError("Listener thread did not become active.")
        except Exception as exc:
            self._mapping.clear()
            if listener is not None:
                try:
                    listener.stop()
                except Exception:
                    pass
                finally:
                    self._join_listener(listener)
            raise RuntimeError(
                f"Failed to start hotkey listener: {exc}"
            ) from exc

        self._listener = listener

    def _stop_listener_locked(self) -> None:
        listener = self._listener
        self._listener = None
        self._mapping.clear()

        if listener is None:
            return

        try:
            listener.stop()
        finally:
            self._join_listener(listener)

    @staticmethod
    def _join_listener(listener) -> None:
        if (
            listener.is_alive()
            and listener is not threading.current_thread()
        ):
            listener.join(timeout=_STOP_TIMEOUT_SECONDS)
