#!/usr/bin/env python3
"""
日本語 Sensei — Immersive Japanese Language Learning App
========================================================
    export GROQ_API_KEY="gsk_…"
    python main.py
"""

from __future__ import annotations

import sys


def safe_print(text: str) -> None:
    print(text)

def _check_deps() -> None:
    needed: dict[str, str] = {
        "flet":           "flet>=0.21.0",
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
        safe_print("╔══════════════════════════════════════════════════╗")
        safe_print("║  Missing Python packages — please install:       ║")
        safe_print("╚══════════════════════════════════════════════════╝")
        safe_print(f"  pip install {' '.join(missing)}\n")
        sys.exit(1)


def main() -> None:
    _check_deps()
    import flet as ft
    try:
        from .flet_app import NihongoSenseiApp
    except ImportError:
        from flet_app import NihongoSenseiApp
    
    def start_flet(page: ft.Page):
        NihongoSenseiApp(page)
        
    ft.app(target=start_flet)


if __name__ == "__main__":
    main()