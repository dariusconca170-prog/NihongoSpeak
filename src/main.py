#!/usr/bin/env python3
"""
日本語 Sensei — Immersive Japanese Language Learning App
========================================================
    export GROQ_API_KEY="gsk_…"
    python main.py
"""

from __future__ import annotations

import sys


def _check_deps() -> None:
    needed: dict[str, str] = {
        "customtkinter":  "customtkinter>=5.2.0",
        "groq":           "groq>=0.11.0",
        "faster_whisper":  "faster-whisper>=1.0.0",
        "sounddevice":    "sounddevice>=0.5.0",
        "numpy":          "numpy>=1.26.0",
        "edge_tts":       "edge-tts>=6.1.0",
        "pygame":         "pygame>=2.5.0",
    }
    missing: list[str] = []
    for mod, pip_name in needed.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pip_name)
    if missing:
        print("╔══════════════════════════════════════════════════╗")
        print("║  Missing Python packages — please install:       ║")
        print("╚══════════════════════════════════════════════════╝")
        print(f"  pip install {' '.join(missing)}\n")
        sys.exit(1)


def main() -> None:
    _check_deps()
    try:
        from .app import JapaneseTutorApp
    except ImportError:
        from app import JapaneseTutorApp
    app = JapaneseTutorApp()
    app.mainloop()


if __name__ == "__main__":
    main()