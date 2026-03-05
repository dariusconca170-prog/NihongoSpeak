"""
audio_manager.py — Microphone enumeration, push-to-talk recording,
and real-time audio-level metering for the volume visualiser.

Uses *sounddevice* (PortAudio) with a callback-based InputStream so
the main thread is never blocked while audio data is being captured.
"""

from __future__ import annotations

import collections
import math
import os
import tempfile
import time
import wave
from typing import Optional

import numpy as np
import sounddevice as sd

import config


class AudioManager:
    """Record audio from a selectable input device via push-to-talk,
    while exposing live RMS levels and a waveform buffer for
    real-time visualisation."""

    def __init__(
        self,
        sample_rate: int = config.SAMPLE_RATE,
        channels: int = config.CHANNELS,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels

        self.is_recording: bool = False
        self._chunks: list[np.ndarray] = []
        self._device_index: Optional[int] = None
        self._stream: Optional[sd.InputStream] = None
        self._start_time: float = 0.0

        # ── metering state ──────────────────────────────────────
        self._rms_level: float = 0.0
        self._peak_level: float = 0.0
        self._peak_decay: float = 0.0
        self._waveform_buf: collections.deque[float] = collections.deque(
            maxlen=config.WAVEFORM_BUF_LEN,
        )

    # ── Device helpers ──────────────────────────────────────────

    @staticmethod
    def list_input_devices() -> list[tuple[int, str]]:
        """Return ``[(index, display_name), …]`` for every input device."""
        devices: list[tuple[int, str]] = []
        for idx, info in enumerate(sd.query_devices()):
            if info["max_input_channels"] > 0:
                name = str(info["name"])
                if len(name) > 55:
                    name = name[:52] + "…"
                devices.append((idx, name))
        return devices

    def set_device(self, device_index: int) -> None:
        self._device_index = device_index

    # ── Recording lifecycle ─────────────────────────────────────

    def start_recording(self) -> None:
        """Open a non-blocking input stream and start capturing audio."""
        self._chunks.clear()
        self._waveform_buf.clear()
        self._rms_level = 0.0
        self._peak_level = 0.0
        self._peak_decay = 0.0
        self.is_recording = True
        self._start_time = time.monotonic()

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                device=self._device_index,
                dtype="float32",
                blocksize=1024,
                callback=self._callback,
            )
            self._stream.start()
        except Exception as exc:
            self.is_recording = False
            raise RuntimeError(f"Cannot open mic: {exc}") from exc

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        if not self.is_recording:
            return

        self._chunks.append(indata.copy())

        # ── mono channel ────────────────────────────────────────
        mono = indata[:, 0] if indata.ndim > 1 else indata.flatten()

        # ── RMS ─────────────────────────────────────────────────
        rms = float(np.sqrt(np.mean(mono ** 2)))
        self._rms_level = rms

        # ── peak with slow decay ────────────────────────────────
        chunk_peak = float(np.max(np.abs(mono)))
        if chunk_peak > self._peak_level:
            self._peak_level = chunk_peak
        else:
            self._peak_level *= 0.95          # decay

        # ── waveform buffer (down-sampled for display) ──────────
        step = config.WAVEFORM_DOWNSAMPLE
        self._waveform_buf.extend(mono[::step].tolist())

    def stop_recording(self) -> Optional[str]:
        """
        Stop capturing, save to a temporary 16-bit WAV, and return its path.
        Returns ``None`` when the recording is too short or silent.
        """
        self.is_recording = False
        elapsed = time.monotonic() - self._start_time

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        if not self._chunks or elapsed < config.MIN_RECORD_SECONDS:
            return None

        audio = np.concatenate(self._chunks, axis=0)

        if float(np.sqrt(np.mean(audio ** 2))) < config.SILENCE_RMS_FLOOR:
            return None

        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        pcm = np.clip(audio * 32_767, -32_768, 32_767).astype(np.int16)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm.tobytes())
        return path

    # ── Metering API (called from GUI thread) ───────────────────

    def get_level(self) -> float:
        """Normalised RMS level in ``[0.0, 1.0]``.

        Speech typically sits at RMS 0.01-0.08; we scale so that
        comfortable speech sits around 0.5-0.7."""
        return min(1.0, self._rms_level * 12.0)

    def get_peak(self) -> float:
        """Normalised peak level with slow decay, in ``[0.0, 1.0]``."""
        return min(1.0, self._peak_level * 6.0)

    def get_level_db(self) -> float:
        """RMS level in dBFS (clamped to -60)."""
        if self._rms_level < 1e-10:
            return -60.0
        return max(-60.0, 20.0 * math.log10(self._rms_level))

    def get_waveform(self, n_points: int = config.WAVEFORM_DISPLAY_PTS) -> np.ndarray:
        """Return the most recent *n_points* samples for waveform display.

        Returns a 1-D numpy array; zero-padded on the left when the
        buffer contains fewer samples than requested."""
        buf = list(self._waveform_buf)
        if len(buf) >= n_points:
            return np.array(buf[-n_points:], dtype=np.float32)
        pad = np.zeros(n_points - len(buf), dtype=np.float32)
        return np.concatenate([pad, np.array(buf, dtype=np.float32)])

    # ── Helpers ─────────────────────────────────────────────────

    def elapsed(self) -> float:
        """Seconds since *start_recording* was called (while recording)."""
        if self.is_recording:
            return time.monotonic() - self._start_time
        return 0.0