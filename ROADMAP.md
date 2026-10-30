# PilotMixer Roadmap

Date: 2026-10-30
Status: roadmap plus an integrated Pilot Terminal shell; live start/stop is verified, but capture stability and audible routing are not.

## Goal and scope

Build a fully local Windows 11 audio router, soundboard, and voice-processing rack with a dense Pilot Terminal interface. Use Python 3.11 through pyenv without a `.venv`, PySide6 for the desktop UI, and sounddevice as the initial PortAudio interface.

The shell and initial backend direction were approved. Voice mixing, voice changing, and Auto-Tune-style pitch correction are now in product scope. The definitions below are planning defaults, not evidence that a DSP implementation or its performance has been verified.

- **Voice mixer:** microphone gain/mute, dry/wet blend, and independent selection of dry or processed voice for monitoring and Discord.
- **Voice changer:** local effects such as EQ, compression, robotic modulation, pitch transposition, and formant shaping. Pitch shifting and formant shifting are separate capabilities; changing playback speed is not an acceptable substitute.
- **Pitch correction:** monophonic voice/singing correction to a chosen key and scale, with correction amount and retune speed. This is a feature category, not an integration with proprietary Auto-Tune software.
- **Not included initially:** AI voice cloning/conversion, cloud processing, VST hosting, a custom audio driver, polyphonic pitch correction, or an installer that silently changes Windows settings.

## Non-negotiable workflow

1. Build one reviewable slice at a time: failing test, minimal implementation, passing test, live verification where applicable, report, stop.
2. Keep Qt UI code separate from audio transport and DSP. No file decoding, device opening, or audio processing on the GUI thread.
3. No placeholder implementations, fake VU activity, or apparently usable controls for unavailable features.
4. Do not promise a latency target before measuring the unprocessed baseline. PortAudio latency requests and estimates are not round-trip measurements.
5. Do not change device defaults, microphone permissions, drivers, or exclusive access settings without approval.
6. Do not force-push, rewrite published history, or publish generated artifacts without a request. The repository is initialized for the agreed source release.
7. Start with stdlib `unittest` and PySide6.QtTest; add dependencies only when the relevant slice needs them and Windows support is verified.

## Verified baseline and current blocker

These are observations from this session, not permanent machine configuration:

| Check | Observation |
| --- | --- |
| Interpreter | Python 3.11.9 at the pyenv-win installation |
| Installed packages | sounddevice 0.5.6, PyAudio 0.2.14, PySide6 6.11.2, NumPy 2.3.5 |
| PortAudio | V19.7.0-devel, revision unknown |
| WASAPI devices | Seven endpoints enumerated, including USB audio and VB-Audio endpoints; all report a 48 kHz default |
| Silent USB output | 202 callbacks over a two-second probe; zero callback status flags; 480 frames per callback |
| Reported output latency | 22 ms; not an acoustic or loopback end-to-end measurement |
| USB microphone and cable capture | Opening fails with PortAudio -9996; host HRESULT 0x80070005, Access is denied |
| Duplex | Did not open; successful capture and routing have not been demonstrated |
| Windows consent values queried | Microphone Allow at HKCU/HKLM and desktop-app Allow at HKCU; denial cause still unknown |

Capture access blocks live input testing, not shell development or offline DSP tests. Enumeration and individual format checks are insufficient proof of usable duplex audio. No sounddevice-versus-PyAudio latency comparison has been performed.

## Backend boundaries

- **Control worker:** device discovery, stream lifecycle, configuration changes, file loading, and fault reporting. Communicates with Qt using signals/control messages, not audio blocks.
- **Capture callbacks:** feed bounded, preallocated input buffers. Neither block on downstream consumers nor call Qt.
- **Mix core:** owns channel mapping, gain ramps, routing, summation, and peak/RMS calculations; deterministic and testable without hardware.
- **Master output callback:** consumes prepared input at its clock, mixes destinations, writes the master output, and feeds bounded secondary-output buffers. It never waits for a capture or DSP worker.
- **Secondary outputs:** consume their own buffers with clock-drift compensation. Matching nominal rates do not synchronize independent devices.
- **Voice DSP worker:** streaming processors with persistent state and a declared delay; supplies processed microphone blocks through bounded buffers. It must not stall the dry path or master output.
- **GUI:** polls meter/status snapshots at approximately 30 Hz and sends parameter changes. Changing a Qt widget never directly opens or closes an audio stream.

Start at 48 kHz float32 in WASAPI shared mode and support host-selected callback sizes. Use an actual streaming resampler for drift control; choose its implementation during the transport feasibility slice. Python callbacks remain soft realtime. If deadline or buffer-ownership tests fail, evaluate moving the critical transport/DSP portion to native code without rewriting the GUI.

Callback paths must avoid disk access, logging, unbounded allocation, and blocking locks. Buffers have explicit ownership; multiple consumers must not destructively read the same single-consumer queue. Fan out microphone data into separately owned dry and DSP input buffers. Overflow discards stale data according to a tested policy; underflow supplies silence and increments a diagnostic counter. Structural reconfiguration happens outside callbacks. Parameters update at block boundaries with smoothing where necessary.

A control thread keeps ordinary device operations off Qt, but cannot guarantee recovery from a driver call that hangs indefinitely. Test driver-failure behavior early; if native calls cannot be bounded, review audio-process isolation before claiming reliable shutdown. Do not forcibly terminate a Python audio thread.

## Routing and voice signal flow

```text
System apps -> cable A playback -> cable A recording -> SYSTEM source
Microphone -> DRY source ------------------------------+
           -> streaming voice rack -> WET source ------+-> route/mix -> headphones
Soundboard decoder -> bounded playback source --------+             -> cable B playback
                                                                        |
                                                              cable B recording -> Discord
```

Cable A and cable B must be independent virtual paths. The current enumeration does not establish that two independent paths are available. Never route a bus into the cable endpoint being captured as that bus's source. Device names alone are not proof of topology; validate selected endpoint pairs.

Users can monitor dry voice while sending wet voice to Discord. A blended dry/wet bus delays its dry branch to match the processed branch; separate dry-only monitoring need not inherit that delay. Bypass transitions need smoothing and explicit delay handling. If wet processing fails, mute wet output and flag the fault; do not unexpectedly transmit untreated microphone audio.

## Phases and acceptance gates

### P0 — Capture diagnostics and hardware readiness

**State:** blocked on capture access; can run alongside P1 and P2.

Scope: reproduce the host error, identify its actual cause, and verify explicitly selected input/output endpoints without changing system configuration automatically. Establish separate cable paths before system-audio-plus-Discord routing.

Acceptance:
- Input and duplex streams open, receive callbacks, stop, and close cleanly; silence-only output smoke tests precede audible monitoring.
- A consented known-signal test verifies that input data actually changes; callback count alone is insufficient.
- Access denial and unavailable-device failures preserve actionable host errors and never freeze the UI.
- No recording is persisted by default; no permission failure triggers fallback to another API or device to evade the denial.

### P1 — Pilot Terminal shell and one custom fader

**Dependency:** none. This remains the first implementation slice and stop point.

Scope: PySide6 main window, empty labeled input/routing/output/soundboard panels, truthful disconnected status, and one functional QPainter vertical fader. Black `#000000`, mint primary accent, amber warning state, Cascadia Mono with Consolas fallback, sharp edges, compact spacing. Reserve layout space for a future voice rack, but do not render fake effects controls.

Proposed files: `pilotmixer/__main__.py`, `pilotmixer/ui/window.py`, `pilotmixer/ui/theme.py`, `pilotmixer/ui/widgets/fader.py`, `tests/test_fader.py`, `tests/test_window.py`. Create package markers only where needed, not speculative backend modules.

Acceptance:
- Tests first for clamping, value-to-position mapping, mouse drag, keyboard adjustment, and value-change signaling without duplicate emissions.
- Verify minimum and maximum positions, resizing, focus, and disabled state using QtTest/offscreen rendering.
- Launch the native window and inspect it at normal and increased Windows scaling; check for clipping and shutdown errors. Offscreen screenshots alone do not establish interactive success.
- No device streams open on application launch. Stop for review before P2.

### P2 — Deterministic offline mix core

**Dependency:** P1 review; hardware not required.

Scope: frame/channel mapping, per-route gain and mute, independent destination sums, gain ramps, output headroom, peak/RMS snapshots, and a final sample-peak clamp. A clamp is not a transparent limiter or a hearing-safety guarantee.

Acceptance: synthetic tests cover silence, mono-to-stereo mapping, multiple-source sums, destination isolation, invalid channel indices and configured gain limits, variable frame sizes, mute ramps across blocks, clipping counts, and non-finite audio at ingress. Negative audio samples remain valid. No Qt or sounddevice imports in the mix core.

### P3 — Live transport, then independent device clocks

**Dependency:** P0 capture gate and P2.

**P3a:** one selected input/output path, start/stop state, output silence before routing is enabled, conservative initial gain, no disk work in callbacks. Measure an unprocessed known-signal path with a documented fixture and repeated trials; report the measurement method and uncertainty.

**P3b:** add the system capture and secondary Discord output one at a time. Implement bounded buffers, defined ownership, adaptive drift compensation, and counters for underflow, overflow, clipping, and processing overruns.

Acceptance:
- Inject clock skew in offline tests and demonstrate bounded occupancy, correct overflow/underflow policy, and no unbounded delay growth.
- Verify channel/rate negotiation, disconnect/reconnect, busy devices, failed startup cleanup, repeated start/stop, and bounded shutdown.
- Run a 30-minute physical multi-endpoint test with statistics and repeatable content. This is a test duration, not a latency promise. Investigate unexplained discontinuities before expanding scope.
- Review P3a and P3b separately. Do not claim zero-dropout multi-device routing from the silent output probe.

### P4 — Live routing matrix and meters

**Dependency:** P3.

Scope: bind faders, route toggles, device selectors, and QPainter VU meters to the real engine. Expose disconnected/fault/muted states and diagnostics without flooding Qt with audio-rate signals.

Acceptance: clicking a route changes only that destination; a rejected configuration rolls back visibly; faders produce smooth changes; feedback paths are rejected; meters match deterministic peak/RMS fixtures and show no fabricated signal. Verify mouse/keyboard use and UI responsiveness during route changes and device failures.

### P5 — Soundboard playback

**Dependency:** P3 and P4.

Scope: configurable in-app pads, local PCM WAV loading first, per-pad gain, overlapping playback, stop-all, and independent output routing. Decode/load outside callbacks; prepare data for the engine's format before playback. Introduce a local file-decoding dependency only after checking supported formats and Windows compatibility.

Acceptance: exact sample ordering in offline tests; overlapping pads sum correctly; stop-all takes effect with a short ramp; missing/corrupt files produce visible errors; an over-budget file is rejected against a documented memory cap rather than fully loaded first. Confirm actual playback through each intended destination. Global hotkeys and compressed formats are separate review decisions, not implicit additions.

### P6 — Voice mixer and conventional effects rack

**Dependency:** P3 and P4; independent of P5 implementation.

Scope: dry/wet routing and blend, per-effect bypass, input/output gain, EQ, compressor, and robotic modulation, introduced as separate tested slices. No pitch/formant controls until P7 passes. Use a bounded worker pipeline and report added processing delay.

Acceptance: impulse/sweep/step fixtures verify effect behavior, persistent state across block boundaries, delay-aligned blending, smooth enable/bypass transitions, and output bounds. Dry-only monitoring remains independent of wet delay. Simulated overload/failure mutes only the affected wet path, reports the fault, and never stalls routing. Listening tests check speech intelligibility and objectionable artifacts; synthetic checks alone do not establish quality.

### P7 — Streaming voice changer: pitch and formants

**Dependency:** P6; feasibility gate before choosing a library or shipping controls.

Compare candidate streaming DSP implementations using official API evidence: Windows x64/Python 3.11 support, streaming rather than whole-file processing, persistent state, delay reporting, arbitrary host block sizes, CPU/GIL behavior, runtime binaries, and distribution license. Compare native standalone DSP with a vetted native Python binding; do not assume either is available or suitable.

Acceptance: demonstrate pitch transposition without changing duration, independent formant shaping, ratio changes without state resets or clicks, bounded buffering, and separately measured added delay. Test tones, speech, low-pitched voices, silence, and sustained vowels. Select an implementation only after measured quality/latency trade-offs are reviewed. If the candidates fail, report the blocker rather than substituting offline processing or dead controls.

### P8 — Key/scale pitch correction

**Dependency:** P7's verified streaming transposition path.

Scope: monophonic pitch tracking, voiced/unvoiced confidence handling, key/scale targeting, adjustable correction amount and retune speed, and bypass. Formant preservation remains explicit; changing pitch must not silently redefine timbre controls.

Acceptance: known-frequency fixtures verify pitch estimation, note targets, cents error, correction amount, and sustained-note stability. Test octave ambiguity, vibrato, consonants, breaths, silence, out-of-range pitch, and scale changes without forced tracking of noise. Confident voiced frames are corrected; unvoiced material is not forced onto notes. Compare dry/processed recordings only with consent and report added latency independently from transport latency. Review whether measured delay is acceptable for singing and conversational monitoring before calling it usable.

### P9 — Profiles, customization, resilience, and local distribution

**Dependency:** previous feature gates; lifecycle/error tests also run in every earlier phase.

Scope: save/load routing, pad assignments, effect presets, and selected accent/layout preferences locally; provide an effects rack with custom knobs; validate profiles at load boundaries; test restore without silently attaching to a similarly named endpoint. Persist endpoint descriptors and require confirmation when ambiguous rather than trusting ephemeral device indices.

Acceptance: malformed profiles, missing files, changed devices, sample-rate changes, Bluetooth profile changes, suspended/resumed Windows sessions, worker faults, and repeated startup/shutdown produce controlled outcomes. Re-run the multi-endpoint soak with soundboard and effects active and record memory growth, buffer occupancy, discontinuity counts, and measured latency. Test packaging on Windows without a development environment. Missing external cable drivers must produce guidance, not automatic installation or configuration changes.

## Shell integration status

Implemented on 2026-10-30: `engine_service.py`, `theme.py`, `main_window.py`, and `run.py`, plus 32 passing tests. The native shell launches at 1800x1055 (125% scaling), starts offline, and opens no streams until Engage is pressed. The online layout, faders, routing controls, meters, telemetry, and clean close were exercised against the real endpoints.

Live findings:
- A four-stream start initially failed on a worker thread with `WdmSyncIoctl ... DeviceIoControl GLE = 0x00000490`. Calling `CoInitializeEx` on the persistent engine worker fixed startup; start/stop now remain on that COM-initialized thread.
- The engine reached `AUDIO ONLINE`; no routes were enabled and output remained silent. Clean shutdown returned the service to offline with no residual streams.
- Capture drops continue while running: 15,360 mic frames and 3,840 system frames over a four-second sample; output underflows were 9 and 13 and did not grow after startup. This is not acceptable for live routing.
- No known-signal capture test, audible route test, or end-to-end latency measurement has been completed.

Next implementation gate: fix capture-ring contention (single mixer fan-out or a lock-free producer/consumer design), then run the P0 known-signal test and a documented latency measurement. Do not add soundboard or voice DSP until that gate passes.

Each phase needs a small implementation plan at its start against the actual files and verified APIs, not a speculative full-app code dump. Current commands: `python -m unittest discover -s tests -v` and `python run.py`, using the selected pyenv Python 3.11 interpreter. The suite passes and the shell has been launched; live-audio verification remains gated as above.

## Reference contracts checked during initial research

- sounddevice device queries/checks: https://python-sounddevice.readthedocs.io/en/0.5.6/api/checking-hardware.html
- sounddevice streams/callback constraints: https://python-sounddevice.readthedocs.io/en/0.5.6/api/streams.html
- sounddevice WASAPI settings: https://python-sounddevice.readthedocs.io/en/0.5.6/api/platform-specific-settings.html
- PortAudio host/device model: https://files.portaudio.com/docs/v19-doxydocs-dev/api_overview.html
