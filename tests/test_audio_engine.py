from __future__ import annotations

import unittest

import numpy as np

from audio_engine import AudioEngine, _CaptureReader, _CaptureRing, _Output


def make_engine(buffer_ms: float = 30.0) -> AudioEngine:
    return AudioEngine(
        0,
        1,
        2,
        3,
        sample_rate=8000,
        buffer_ms=buffer_ms,
        max_callback_frames=64,
    )


class SettingsTests(unittest.TestCase):
    def test_routes_default_to_off_and_can_be_toggled(self):
        engine = make_engine()

        self.assertFalse(engine.routing_matrix["mic"]["headphones"])
        self.assertFalse(engine.routing_matrix["system"]["virtual_cable"])
        self.assertFalse(engine.routing_matrix["soundboard"]["headphones"])

        engine.set_route("mic", "headphones", True)

        self.assertTrue(engine.routing_matrix["mic"]["headphones"])
        self.assertFalse(engine.routing_matrix["mic"]["virtual_cable"])

        engine.set_route("mic", "headphones", False)
        self.assertFalse(engine.routing_matrix["mic"]["headphones"])

    def test_routes_and_volumes_reject_invalid_inputs(self):
        engine = make_engine()

        with self.assertRaises(ValueError):
            engine.set_route("bogus", "headphones", True)

        with self.assertRaises(ValueError):
            engine.set_route("mic", "bogus", True)

        with self.assertRaises(TypeError):
            engine.set_route("mic", "headphones", 1)

        for channel in ("mic", "system", "soundboard", "headphones", "virtual_cable"):
            for value in (0.0, 2.5, 4.0):
                engine.set_volume(channel, value)

        for channel, value in (
            ("mic", -0.01),
            ("mic", 4.01),
            ("mic", float("nan")),
            ("mic", float("inf")),
            ("bogus", 1.0),
        ):
            with self.subTest(channel=channel, value=value):
                with self.assertRaises(ValueError):
                    engine.set_volume(channel, value)

    def test_invalid_construction_is_rejected(self):
        with self.assertRaises(ValueError):
            AudioEngine(0, 0, 2, 3)

        with self.assertRaises(ValueError):
            AudioEngine(0, 1, 2, 2)

        with self.assertRaises(ValueError):
            AudioEngine(0, 1, 2, 3, sample_rate=7999)

        with self.assertRaises(ValueError):
            AudioEngine(-1, 1, 2, 3)


class SoundboardTests(unittest.TestCase):
    def test_soundboard_is_resampled_faded_and_copied(self):
        engine = AudioEngine(
            0,
            1,
            2,
            3,
            sample_rate=48000,
            buffer_ms=30,
            max_callback_frames=1024,
        )
        source = np.full((2400, 1), 0.5, dtype=np.float32)

        engine.play_soundboard(source, 24000)
        serial, sound = engine._sound

        self.assertGreater(serial, 0)
        self.assertEqual(sound.shape, (4800, 2))
        self.assertEqual(sound.dtype, np.float32)
        self.assertFalse(sound.flags.writeable)
        self.assertAlmostEqual(float(sound[1200, 0]), 0.5, places=3)
        self.assertAlmostEqual(float(sound[1200, 1]), 0.5, places=3)
        self.assertEqual(float(sound[0, 0]), 0.0)
        self.assertEqual(float(sound[-1, 0]), 0.0)
        self.assertFalse(np.shares_memory(source, sound))

        engine.stop_soundboard()
        self.assertIsNone(engine._sound[1])

    def test_soundboard_rejects_invalid_audio(self):
        engine = make_engine()

        with self.assertRaises(ValueError):
            engine.play_soundboard(np.zeros((10, 3), dtype=np.float32), 8000)

        with self.assertRaises(ValueError):
            engine.play_soundboard(np.zeros(0, dtype=np.float32), 8000)

        with self.assertRaises(TypeError):
            engine.play_soundboard(np.zeros(10, dtype=np.int16), 8000)

        with self.assertRaises(ValueError):
            engine.play_soundboard(
                np.array([0.0, np.nan], dtype=np.float32),
                8000,
            )


class CaptureTests(unittest.TestCase):
    def test_ring_broadcasts_mono_and_reader_follows_absolute_wrap(self):
        ring = _CaptureRing(capacity=8)
        mono = np.arange(10, dtype=np.float32)[:, None]
        ring.write(mono)
        reader = _CaptureReader(ring, target_frames=4, max_frames=8)
        output = np.empty((4, 2), dtype=np.float32)

        reader.read_into(output)

        np.testing.assert_allclose(output[:, 0], [3.0, 4.0, 5.0, 6.0])
        np.testing.assert_allclose(output[:, 1], output[:, 0])

    def test_reader_outputs_silence_on_underflow_and_recovers(self):
        ring = _CaptureRing(capacity=512)
        reader = _CaptureReader(ring, target_frames=40, max_frames=64)
        first = np.empty((32, 2), dtype=np.float32)
        second = np.empty((32, 2), dtype=np.float32)
        third = np.empty((32, 2), dtype=np.float32)

        ring.write(np.full((100, 1), 0.25, dtype=np.float32))
        reader.read_into(first)
        reader.read_into(second)

        np.testing.assert_allclose(first, 0.25)
        np.testing.assert_allclose(second, 0.0)
        self.assertGreater(reader.underflows, 0)

        ring.write(np.full((100, 1), 0.5, dtype=np.float32))
        reader.read_into(third)

        np.testing.assert_allclose(third, 0.5)

    def test_ring_drops_samples_instead_of_blocking(self):
        ring = _CaptureRing(capacity=8)
        ring.lock.acquire()
        try:
            ring.write(np.ones((4, 2), dtype=np.float32))
        finally:
            ring.lock.release()

        self.assertEqual(ring.written, 0)
        self.assertEqual(ring.dropped_frames, 4)


class MixingTests(unittest.TestCase):
    def make_output(self, engine: AudioEngine, index: int):
        rings = []
        readers = []
        for _ in range(2):
            ring = _CaptureRing(engine._capacity)
            rings.append(ring)
            readers.append(
                _CaptureReader(ring, engine._target_frames, 64)
            )
        return rings, readers, _Output(engine, index, readers)

    def test_mic_route_reaches_only_its_destination_with_gains(self):
        engine = make_engine()
        rings, readers, headphones = self.make_output(engine, 0)
        _, cable_readers, cable = self.make_output(engine, 1)

        rings[0].write(np.full((800, 1), 0.5, dtype=np.float32))
        rings[1].write(np.zeros((800, 2), dtype=np.float32))
        engine.set_route("mic", "headphones", True)
        engine.set_volume("mic", 0.5)
        engine.set_volume("headphones", 2.0)

        head_data = np.empty((32, 2), dtype=np.float32)
        cable_data = np.empty((32, 2), dtype=np.float32)

        headphones(head_data, 32, None, None)
        cable(cable_data, 32, None, None)
        headphones(head_data, 32, None, None)
        cable(cable_data, 32, None, None)

        np.testing.assert_allclose(head_data, 0.5, atol=1e-5)
        np.testing.assert_allclose(cable_data, 0.0, atol=1e-5)
        self.assertAlmostEqual(headphones.levels[0], 0.5, places=5)
        self.assertEqual(cable.levels, (0.0, 0.0))

    def test_soundboard_plays_without_capture_and_is_independent(self):
        engine = make_engine()
        rings, readers, output = self.make_output(engine, 0)

        engine._sound = (1, np.full((800, 2), 0.25, dtype=np.float32))
        engine.set_route("soundboard", "headphones", True)

        data = np.empty((32, 2), dtype=np.float32)
        output(data, 32, None, None)
        output(data, 32, None, None)

        np.testing.assert_allclose(data, 0.25, atol=1e-5)
        self.assertAlmostEqual(output.levels[0], 0.25, places=5)

    def test_missing_audio_is_silent_not_stale(self):
        engine = make_engine()
        rings, readers, output = self.make_output(engine, 0)
        engine.set_route("mic", "headphones", True)

        data = np.empty((32, 2), dtype=np.float32)
        output(data, 32, None, None)

        np.testing.assert_allclose(data, 0.0)
        self.assertGreater(output.readers[0].underflows, 0)


if __name__ == "__main__":
    unittest.main()
