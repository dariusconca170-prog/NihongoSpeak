#!/usr/bin/env python3
"""Audio recording script for Nihongo Sensei - event-driven with shared state."""
import sounddevice as sd
import numpy as np
import tempfile
import os
import wave
import sys
import time
import json

SAMPLE_RATE = 16000
CHANNELS = 1
STATE_FILE = os.path.join(tempfile.gettempdir(), "nihongo_recording_state.json")


def load_state():
    """Load state from JSON file."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"status": "idle", "audio_path": ""}


def save_state(state):
    """Save state to JSON file."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def is_recording():
    """Check if recording should continue based on state file."""
    state = load_state()
    return state.get("status") == "recording"


def main():
    # Create temp file path and store in state
    fd, audio_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    state = {
        "status": "recording",
        "audio_path": audio_path
    }
    save_state(state)

    # Signal that we're ready (this goes to Rust's stdout)
    print("READY")

    chunks = []

    def callback(indata, frames, time_info, status):
        if status:
            print(f"Status: {status}", file=sys.stderr)
        chunks.append(indata.copy())

    try:
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype='float32',
            blocksize=1024,
            callback=callback
        )

        with stream:
            # Poll for stop signal every 100ms
            while is_recording():
                time.sleep(0.1)

            # Stop recording
            stream.stop()

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        save_state({"status": "idle", "audio_path": ""})
        sys.exit(1)

    # Update state to idle
    save_state({"status": "idle", "audio_path": ""})

    if not chunks:
        print("")
        sys.exit(0)

    audio = np.concatenate(chunks, axis=0)

    # Check if too short or silent
    rms = np.sqrt(np.mean(audio ** 2))
    if rms < 0.001 or len(audio) / SAMPLE_RATE < 0.4:
        print("")
        if os.path.exists(audio_path):
            os.remove(audio_path)
        sys.exit(0)

    # Write audio to the temp file
    pcm = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
    with wave.open(audio_path, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())

    print(audio_path)


if __name__ == "__main__":
    main()
