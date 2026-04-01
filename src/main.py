# This file is no longer used - the app is built with Rust/Slint
# Keeping for reference only - see main.rs for the actual application

# The Slint-based application is built and run via:
#     cargo run --release
# 
# Backend services (Whisper, TTS) are called from Rust via Python scripts:
#     scripts/record_audio.py   - Audio recording
#     scripts/transcribe.py     - Whisper transcription  
#     scripts/tts.py           - Text-to-speech

print("This module is deprecated. Use 'cargo run --release' instead.")
