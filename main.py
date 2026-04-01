#!/usr/bin/env python3
"""
日本語 Sensei — Slint Edition Entry Point
========================================================
This runs the Rust/Slint application. Backend services (Whisper, TTS)
are called via the Rust app.

    export GROQ_API_KEY="gsk_..."
    cargo run --release

Or run directly:
    python main.py
"""

import subprocess
import sys
import os


def main():
    # Check for Rust toolchain
    try:
        result = subprocess.run(
            ["rustc", "--version"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print("Rust not found. Please install Rust: https://rustup.rs/")
            sys.exit(1)
        print(f"Found: {result.stdout.strip()}")
    except FileNotFoundError:
        print("Rust not found. Please install Rust: https://rustup.rs/")
        sys.exit(1)

    # Check for API key
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        print("⚠️  GROQ_API_KEY not set.")
        print("   Set it with: export GROQ_API_KEY='gsk_...'")
        print("   Or enter it in the app settings.")

    # Build and run the Rust/Slint app
    print("Building 日本語 Sensei (Slint Edition)...")
    
    build_result = subprocess.run(
        ["cargo", "build", "--release"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    
    if build_result.returncode != 0:
        print("Build failed!")
        sys.exit(1)
    
    print("Launching 日本語 Sensei...")
    
    # Run the compiled binary
    bin_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "target", "release", "nihongo-sensei"
    )
    
    # On Windows, add .exe extension
    if sys.platform == "win32":
        bin_path += ".exe"
    
    subprocess.run([bin_path])


if __name__ == "__main__":
    main()
