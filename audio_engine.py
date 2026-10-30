from __future__ import annotations

import math
import random
import threading
import time

import numpy as np
import sounddevice as sd
from scipy.io import wavfile
from scipy.signal import resample_poly


class _CaptureRing:
    def __init__(self, capacity: int):
        self.data = np.zeros((capacity, 2), dtype=np.float32)
        self.capacity = capacity
        self.written = 0
        self.generation = 0
        self.lock = threading.Lock()
        self.dropped_frames = 0
        self.status_events = 0

    def write(self, samples: np.ndarray) -> None:
        total = len(samples)

        if not self.lock.acquire(blocking=False):
            self.dropped_frames += total
            self.generation += 1
            return

        try:
            count = min(total, self.capacity)
            source = samples[-count:]
            start = (self.written + total - count) % self.capacity
            first = min(count, self.capacity - start)

            # A mono column broadcasts into both stereo channels.
            self.data[start:start + first] = source[:first]
            self.data[:count - first] = source[first:]
            self.written += total
        finally:
            self.lock.release()


class _CaptureReader:
    def __init__(
        self,
        ring: _CaptureRing,
        target_frames: int,
        max_frames: int,
    ):
        self.ring = ring
        self.target_frames = target_frames
        self.cursor = None
        self.generation = -1
        self.filtered_error = 0.0

        self.underflows = 0
        self.contentions = 0
        self.resyncs = 0

        self.steps = np.arange(max_frames, dtype=np.float64)
        self.positions = np.empty(max_frames, dtype=np.float64)
        self.fractions = np.empty(max_frames, dtype=np.float64)
        self.indices = np.empty(max_frames, dtype=np.int64)
        self.a = np.empty((max_frames, 2), dtype=np.float32)
        self.b = np.empty((max_frames, 2), dtype=np.float32)

    def read_into(self, destination: np.ndarray) -> None:
        destination.fill(0)
        frames = len(destination)
        ring = self.ring

        if not ring.lock.acquire(blocking=False):
            self.contentions += 1
            return

        try:
            target = max(
                self.target_frames,
                math.ceil(frames * 1.002) + 2,
            )
            written = ring.written

            if self.generation != ring.generation:
                self.cursor = None
                self.filtered_error = 0.0
                self.generation = ring.generation

            if written < target:
                self.underflows += 1
                return

            oldest = max(0, written - ring.capacity)

            if self.cursor is None:
                self.cursor = float(written - target)
            elif (
                self.cursor < oldest
                or written - self.cursor > target * 2
            ):
                self.cursor = float(written - target)
                self.filtered_error = 0.0
                self.resyncs += 1

            available = written - self.cursor
            error = (available - target) / target
            self.filtered_error += 0.01 * (
                error - self.filtered_error
            )
            correction = max(
                -0.002,
                min(0.002, self.filtered_error * 0.001),
            )
            step = 1.0 + correction

            last_position = self.cursor + (frames - 1) * step
            if math.floor(last_position) + 1 >= written:
                self.cursor = None
                self.underflows += 1
                return

            positions = self.positions[:frames]
            fractions = self.fractions[:frames]
            indices = self.indices[:frames]
            a = self.a[:frames]
            b = self.b[:frames]

            np.multiply(self.steps[:frames], step, out=positions)
            np.add(positions, self.cursor, out=positions)
            np.floor(positions, out=fractions)
            np.copyto(indices, fractions, casting="unsafe")
            np.subtract(positions, fractions, out=fractions)

            np.take(
                ring.data, indices, axis=0, mode="wrap", out=a
            )
            np.add(indices, 1, out=indices)
            np.take(
                ring.data, indices, axis=0, mode="wrap", out=b
            )

            np.subtract(b, a, out=b)
            np.multiply(b, fractions[:, None], out=b)
            np.add(a, b, out=destination)

            self.cursor += frames * step
        finally:
            ring.lock.release()


class _Output:
    def __init__(
        self,
        engine: AudioEngine,
        index: int,
        readers: list[_CaptureReader],
    ):
        self.engine = engine
        self.index = index
        self.readers = readers

        maximum = engine.max_callback_frames
        self.scratch = np.empty((maximum, 2), dtype=np.float32)
        self.steps = np.arange(1, maximum + 1, dtype=np.float32)
        self.ramp = np.empty(maximum, dtype=np.float32)
        self.peaks = np.zeros(2, dtype=np.float32)
        self.previous_gains = [0.0, 0.0, 0.0, 1.0]

        self.sound_serial = -1
        self.sound_position = 0
        self.levels = (0.0, 0.0)
        self.last_update = 0.0

        self.status_events = 0
        self.oversized_callbacks = 0
        self.clipped_blocks = 0

    def _apply_gain(
        self,
        samples: np.ndarray,
        target: float,
        slot: int,
    ) -> None:
        previous = self.previous_gains[slot]

        if previous == target:
            np.multiply(samples, target, out=samples)
        else:
            frames = len(samples)
            ramp = self.ramp[:frames]
            np.multiply(
                self.steps[:frames],
                (target - previous) / frames,
                out=ramp,
            )
            np.add(ramp, previous, out=ramp)
            np.multiply(samples, ramp[:, None], out=samples)

        self.previous_gains[slot] = target

    def __call__(self, outdata, frames, timing, status) -> None:
        outdata.fill(0)

        if status:
            self.status_events += 1

        if frames > self.engine.max_callback_frames:
            self.oversized_callbacks += 1
            self.levels = (0.0, 0.0)
            self.last_update = time.monotonic()
            self.engine._last_error = (
                "Output callback exceeded max_callback_frames"
            )
            return

        try:
            routes, input_gains, output_gains = self.engine._settings
            serial, sound = self.engine._sound
            scratch = self.scratch[:frames]

            if serial != self.sound_serial:
                self.sound_serial = serial
                self.sound_position = 0

            for source in range(3):
                if source < 2:
                    self.readers[source].read_into(scratch)
                else:
                    scratch.fill(0)
                    if sound is not None:
                        remaining = len(sound) - self.sound_position
                        count = min(frames, max(0, remaining))
                        if count:
                            start = self.sound_position
                            scratch[:count] = sound[start:start + count]
                            self.sound_position += count

                target = (
                    input_gains[source]
                    if routes[source][self.index]
                    else 0.0
                )
                self._apply_gain(scratch, target, source)
                np.add(outdata, scratch, out=outdata)

            self._apply_gain(
                outdata, output_gains[self.index], 3
            )

            np.nan_to_num(
                outdata,
                copy=False,
                nan=0.0,
                posinf=0.0,
                neginf=0.0,
            )
            np.abs(outdata, out=scratch)
            np.max(scratch, axis=0, out=self.peaks)

            if max(self.peaks) > 1.0:
                self.clipped_blocks += 1

            np.clip(outdata, -1.0, 1.0, out=outdata)
            self.levels = (
                min(1.0, float(self.peaks[0])),
                min(1.0, float(self.peaks[1])),
            )
            self.last_update = time.monotonic()

        except Exception as exc:
            outdata.fill(0)
            self.engine._last_error = (
                f"{self.engine.OUTPUTS[self.index]} callback: {exc}"
            )
            raise sd.CallbackAbort from exc


class AudioEngine:
    INPUTS = ("mic", "system", "soundboard")
    OUTPUTS = ("headphones", "virtual_cable")

    def __init__(
        self,
        mic_device: int,
        system_device: int,
        headphones_device: int,
        virtual_device: int,
        *,
        sample_rate: int = 48000,
        buffer_ms: float = 30.0,
        max_callback_frames: int = 2048,
    ):
        rate = int(sample_rate)
        if rate != sample_rate or not 8000 <= rate <= 192000:
            raise ValueError("sample_rate must be 8000..192000 Hz")

        if not math.isfinite(buffer_ms) or not 5 <= buffer_ms <= 100:
            raise ValueError("buffer_ms must be 5..100")

        if (
            not isinstance(max_callback_frames, int)
            or max_callback_frames < 64
        ):
            raise ValueError("max_callback_frames must be an integer >= 64")

        devices = (
            mic_device,
            system_device,
            headphones_device,
            virtual_device,
        )
        if any(
            not isinstance(device, int) or device < 0
            for device in devices
        ):
            raise ValueError("Supply nonnegative PortAudio device indices")

        if mic_device == system_device:
            raise ValueError("Mic and system capture must be different devices")
        if headphones_device == virtual_device:
            raise ValueError("Outputs must be different devices")

        self.sample_rate = rate
        self.max_callback_frames = max_callback_frames
        self._devices = devices
        self._target_frames = math.ceil(rate * buffer_ms / 1000)
        self._capacity = max(
            rate // 4,
            max_callback_frames * 4 + 4,
            self._target_frames * 3,
        )

        self._config_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()

        self._settings = (
            ((False, False), (False, False), (False, False)),
            (1.0, 1.0, 1.0),
            (1.0, 1.0),
        )
        self._sound = (0, None)
        self._streams = []
        self._rings = []
        self._outputs = {}
        self._last_error = None

    @staticmethod
    def list_wasapi_devices() -> list[dict]:
        hosts = sd.query_hostapis()
        result = []

        for index, device in enumerate(sd.query_devices()):
            if hosts[device["hostapi"]]["name"] == "Windows WASAPI":
                result.append(
                    {
                        "index": index,
                        "name": device["name"],
                        "inputs": device["max_input_channels"],
                        "outputs": device["max_output_channels"],
                        "default_sample_rate": device["default_samplerate"],
                    }
                )

        return result

    @property
    def routing_matrix(self) -> dict:
        routes = self._settings[0]
        return {
            source: {
                destination: routes[i][j]
                for j, destination in enumerate(self.OUTPUTS)
            }
            for i, source in enumerate(self.INPUTS)
        }

    def set_route(
        self,
        source: str,
        destination: str,
        enabled: bool,
    ) -> None:
        i = self.INPUTS.index(source)
        j = self.OUTPUTS.index(destination)

        if not isinstance(enabled, bool):
            raise TypeError("enabled must be bool")

        with self._config_lock:
            routes, inputs, outputs = self._settings
            updated = [list(row) for row in routes]
            updated[i][j] = enabled
            self._settings = (
                tuple(tuple(row) for row in updated),
                inputs,
                outputs,
            )

    def set_volume(self, channel: str, multiplier: float) -> None:
        value = float(multiplier)
        if not math.isfinite(value) or not 0.0 <= value <= 4.0:
            raise ValueError("Volume must be finite and between 0 and 4")

        if channel not in self.INPUTS + self.OUTPUTS:
            raise ValueError(f"Unknown channel: {channel}")

        with self._config_lock:
            routes, inputs, outputs = self._settings
            inputs = list(inputs)
            outputs = list(outputs)

            if channel in self.INPUTS:
                inputs[self.INPUTS.index(channel)] = value
            else:
                outputs[self.OUTPUTS.index(channel)] = value

            self._settings = (routes, tuple(inputs), tuple(outputs))

    def play_soundboard(
        self,
        pcm: np.ndarray,
        sample_rate: int,
    ) -> None:
        rate = int(sample_rate)
        if rate != sample_rate or not 8000 <= rate <= 192000:
            raise ValueError("Invalid soundboard sample rate")

        if not isinstance(pcm, np.ndarray) or pcm.dtype.kind != "f":
            raise TypeError("pcm must be a floating-point NumPy array")

        if pcm.ndim not in (1, 2):
            raise ValueError("Expected mono or stereo PCM")
        if pcm.ndim == 2 and pcm.shape[1] not in (1, 2):
            raise ValueError("Expected one or two channels")
        if not 0 < len(pcm) <= rate * 30:
            raise ValueError("Soundboard clips must be nonempty and <= 30 seconds")

        audio = np.array(pcm, dtype=np.float32, order="C", copy=True)
        if not np.isfinite(audio).all():
            raise ValueError("PCM contains NaN or infinity")

        if audio.ndim == 1:
            audio = audio[:, None]
        if audio.shape[1] == 1:
            audio = np.repeat(audio, 2, axis=1)

        if rate != self.sample_rate:
            divisor = math.gcd(rate, self.sample_rate)
            audio = resample_poly(
                audio,
                self.sample_rate // divisor,
                rate // divisor,
                axis=0,
            )

        audio = np.ascontiguousarray(audio, dtype=np.float32)

        fade = min(int(self.sample_rate * 0.005), len(audio) // 2)
        if fade:
            envelope = np.linspace(0, 1, fade, dtype=np.float32)
            audio[:fade] *= envelope[:, None]
            audio[-fade:] *= envelope[::-1, None]

        audio.setflags(write=False)

        with self._config_lock:
            self._sound = (self._sound[0] + 1, audio)

    def trigger_pad(
        self,
        filepath: str,
        volume: float = 1.0,
        randomize: bool = False,
    ) -> None:
        sample_rate, pcm = wavfile.read(filepath)
        audio = self._wav_to_float(pcm)

        gain = float(volume)
        if not math.isfinite(gain):
            raise ValueError("Pad volume must be finite")
        gain = max(0.0, min(1.0, gain))

        if randomize and len(audio) > 1:
            offset = random.randint(0, len(audio) - 1)
            audio = audio[offset:]

        audio = np.ascontiguousarray(audio * gain, dtype=np.float32)
        self.play_soundboard(audio, int(sample_rate))

    @staticmethod
    def _wav_to_float(pcm: np.ndarray) -> np.ndarray:
        if pcm.dtype.kind == "f":
            return np.asarray(pcm, dtype=np.float32)

        if pcm.dtype.kind == "i":
            scale = float(np.iinfo(pcm.dtype).max) + 1.0
            return pcm.astype(np.float32) / scale

        if pcm.dtype.kind == "u":
            midpoint = (float(np.iinfo(pcm.dtype).max) + 1.0) / 2.0
            return (pcm.astype(np.float32) - midpoint) / midpoint

        raise ValueError(f"Unsupported WAV sample type: {pcm.dtype}")

    def stop_soundboard(self) -> None:
        with self._config_lock:
            self._sound = (self._sound[0] + 1, None)

    def _capture_callback(self, ring: _CaptureRing, name: str):
        def callback(indata, frames, timing, status):
            try:
                if status:
                    ring.status_events += 1
                    if status.input_overflow:
                        ring.generation += 1
                ring.write(indata)
            except Exception as exc:
                self._last_error = f"{name} callback: {exc}"
                raise sd.CallbackAbort from exc

        return callback

    def _close_streams(self) -> list[Exception]:
        errors = []
        remaining = []

        for stream in reversed(self._streams):
            try:
                if stream.active:
                    stream.abort()
            except Exception as exc:
                errors.append(exc)

            try:
                stream.close()
            except Exception as exc:
                errors.append(exc)
                remaining.append(stream)

        self._streams = list(reversed(remaining))
        return errors

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._streams:
                raise RuntimeError("Stop existing streams before starting")

            self._last_error = None
            self._rings = [
                _CaptureRing(self._capacity),
                _CaptureRing(self._capacity),
            ]
            self._outputs = {}

            try:
                information = [
                    sd.query_devices(device)
                    for device in self._devices
                ]

                for info in information:
                    host = sd.query_hostapis(info["hostapi"])
                    if host["name"] != "Windows WASAPI":
                        raise ValueError("All devices must use Windows WASAPI")

                for info in information[:2]:
                    if info["max_input_channels"] < 1:
                        raise ValueError("Selected capture device has no input")

                for info in information[2:]:
                    if info["max_output_channels"] < 2:
                        raise ValueError("Selected output must support stereo")

                settings = sd.WasapiSettings(
                    exclusive=False,
                    auto_convert=True,
                )

                input_channels = tuple(
                    min(2, info["max_input_channels"])
                    for info in information[:2]
                )

                for index in range(2):
                    stream = sd.InputStream(
                        device=self._devices[index],
                        samplerate=self.sample_rate,
                        channels=input_channels[index],
                        dtype="float32",
                        blocksize=0,
                        latency="low",
                        extra_settings=settings,
                        callback=self._capture_callback(
                            self._rings[index],
                            self.INPUTS[index],
                        ),
                    )
                    self._streams.append(stream)

                for index, name in enumerate(self.OUTPUTS):
                    readers = [
                        _CaptureReader(
                            ring,
                            self._target_frames,
                            self.max_callback_frames,
                        )
                        for ring in self._rings
                    ]
                    output = _Output(self, index, readers)
                    self._outputs[name] = output

                    stream = sd.OutputStream(
                        device=self._devices[index + 2],
                        samplerate=self.sample_rate,
                        channels=2,
                        dtype="float32",
                        blocksize=0,
                        latency="low",
                        extra_settings=settings,
                        callback=output,
                    )
                    self._streams.append(stream)

                for stream in self._streams:
                    stream.start()

            except BaseException as exc:
                self._last_error = str(exc)
                cleanup_errors = self._close_streams()
                if cleanup_errors:
                    exc.add_note(
                        "Cleanup errors: "
                        + "; ".join(str(error) for error in cleanup_errors)
                    )
                raise

    def stop(self) -> None:
        with self._lifecycle_lock:
            errors = self._close_streams()
            if errors:
                raise RuntimeError(
                    "Audio shutdown failed: "
                    + "; ".join(str(error) for error in errors)
                ) from errors[0]

    @property
    def healthy(self) -> bool:
        streams = tuple(self._streams)
        if len(streams) != 4 or self._last_error is not None:
            return False
        try:
            return all(stream.active for stream in streams)
        except sd.PortAudioError:
            return False

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def get_levels(self, destination: str) -> tuple[float, float]:
        if destination not in self.OUTPUTS:
            raise ValueError(f"Unknown output: {destination}")

        output = self._outputs.get(destination)
        if (
            not self._streams
            or output is None
            or time.monotonic() - output.last_update > 0.25
        ):
            return 0.0, 0.0
        return output.levels

    def diagnostics(self) -> dict:
        return {
            "healthy": self.healthy,
            "last_error": self._last_error,
            "capture": {
                name: {
                    "dropped_frames": ring.dropped_frames,
                    "status_events": ring.status_events,
                }
                for name, ring in zip(self.INPUTS[:2], self._rings)
            },
            "outputs": {
                name: {
                    "status_events": output.status_events,
                    "clipped_blocks": output.clipped_blocks,
                    "oversized_callbacks": output.oversized_callbacks,
                    "readers": [
                        {
                            "underflows": reader.underflows,
                            "contentions": reader.contentions,
                            "resyncs": reader.resyncs,
                        }
                        for reader in output.readers
                    ],
                }
                for name, output in self._outputs.items()
            },
        }
