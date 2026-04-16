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


def list_input_devices():
    """Return list of (index, name) for available input devices."""
    devices = []
    try:
        for idx, info in enumerate(sd.query_devices()):
            if info["max_input_channels"] > 0:
                name = info["name"]
                if len(name) > 55:
                    name = name[:52] + "…"
                devices.append((idx, name))
    except Exception as e:
        print(f"Error querying devices: {e}", file=sys.stderr)
    return devices


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
    # Parse optional device index from command line args
    device_index = None
    if len(sys.argv) > 1:
        try:
            device_index = int(sys.argv[1])
        except ValueError:
            pass

    # Validate device exists if specified
    if device_index is not None:
        try:
            info = sd.query_devices(device_index)
            if info["max_input_channels"] < 1:
                print("Error: Selected device has no input channels", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            print(f"Error: Selected microphone not found ({e})", file=sys.stderr)
            sys.exit(1)

    # Check that at least one input device exists
    input_devices = list_input_devices()
    if not input_devices:
        print("Error: No microphones found on this system", file=sys.stderr)
        sys.exit(1)

    # If no device specified, use default (None) or first available
    if device_index is None:
        # Try default device, fallback to first available
        try:
            default_info = sd.query_devices(kind='input')
            if default_info and default_info["max_input_channels"] > 0:
                device_index = None  # Use default
            else:
                device_index = input_devices[0][0]  # Use first available
        except Exception:
            device_index = input_devices[0][0]  # Use first available

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
            device=device_index,
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
