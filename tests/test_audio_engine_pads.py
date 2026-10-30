from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.io import wavfile

from audio_engine import AudioEngine


def make_engine() -> AudioEngine:
    return AudioEngine(
        0,
        1,
        2,
        3,
        sample_rate=48000,
        buffer_ms=30,
        max_callback_frames=1024,
    )


def write_tone(
    path: Path,
    *,
    rate: int = 44100,
    seconds: float = 1.0,
    amplitude: float = 0.25,
    frequency: float = 440.0,
) -> None:
    time = np.arange(int(rate * seconds), dtype=np.float64) / rate
    samples = amplitude * np.sin(2.0 * np.pi * frequency * time)
    pcm = np.round(samples * np.iinfo(np.int16).max).astype(np.int16)
    wavfile.write(path, rate, pcm)


class PadTriggerTests(unittest.TestCase):
    def test_trigger_pad_loads_resamples_and_scales_volume(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tone.wav"
            write_tone(path)
            engine = make_engine()

            engine.trigger_pad(str(path), volume=0.5)

            serial, sound = engine._sound
            self.assertGreater(serial, 0)
            self.assertIsNotNone(sound)
            self.assertEqual(sound.shape[1], 2)
            self.assertAlmostEqual(
                len(sound) / engine.sample_rate,
                1.0,
                delta=0.01,
            )
            self.assertAlmostEqual(
                float(np.max(np.abs(sound))),
                0.125,
                delta=0.005,
            )
            self.assertIsNone(engine.last_error)

    def test_trigger_pad_randomize_truncates_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tone.wav"
            write_tone(path)
            engine = make_engine()

            with patch("audio_engine.random.randint", return_value=11025):
                engine.trigger_pad(str(path), randomize=True)

            _, sound = engine._sound
            self.assertIsNotNone(sound)
            self.assertLess(len(sound), engine.sample_rate * 0.95)


if __name__ == "__main__":
    unittest.main()
