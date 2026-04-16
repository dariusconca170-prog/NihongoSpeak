#!/usr/bin/env python3
"""Stop recording and return audio path."""
import sys
import os
import tempfile
import json

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


def main():
    state = load_state()

    # Signal recording to stop
    if state.get("status") == "recording":
        state["status"] = "stop"
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)

    # Return the audio path so Rust knows where the file is
    audio_path = state.get("audio_path", "")
    print(audio_path)


if __name__ == "__main__":
    main()
