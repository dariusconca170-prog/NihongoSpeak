# 日本語 Sensei — NihongoSpeak (Slint Edition)

An immersive Japanese language tutor built with **Slint** (Rust) for the UI, with Python backend services for AI and audio processing.

**Stack:** Slint (Rust) · Llama-3.3-70b via Groq · Faster-Whisper STT · Edge-TTS · Python backend

---

## Features

- **70/30 comprehensible input method** with an adjustable ratio slider (50/50 to 100% Japanese)
- **Push-to-talk voice input** with live audio visualization
- **Pronunciation scoring** — mora-level feedback after every spoken turn
- **Spaced repetition** — difficult vocabulary resurfaces on day 1, 3, and 7 intervals
- **Persistent session memory** — previous session summary injected into every new session
- **Session review tab** — browse past conversations with corrections highlighted
- **Vocabulary tracker tab** — see all words you've struggled with and when they're due
- **Native window management** — proper window sizing without clipping issues

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/dariusconca170-prog/NihongoSpeak.git
cd NihongoSpeak/slint
```

### 2. Install Rust

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

### 3. Install Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Build the application

```bash
cargo build --release
```

### 5. Set your Groq API key

Get a free key at [console.groq.com/keys](https://console.groq.com/keys).

**Option A — environment variable (recommended):**

```bash
export GROQ_API_KEY="gsk_..."
```

**Option B — in-app dialog:**

Leave the variable unset. The app will prompt you for the key on startup.

### 6. Run

```bash
./target/release/nihongo-sensei
```

---

## Project Structure (Slint Edition)

```text
slint/
├── Cargo.toml           # Rust dependencies
├── build.rs             # Slint build script
├── src/
│   ├── main.rs           # Entry point (Rust/Slint)
│   ├── config.rs         # Configuration constants
│   ├── audio.rs          # Audio recording (placeholder)
│   ├── session.rs        # Session data structures
│   └── vocab.rs          # Vocabulary tracking structures
├── ui/
│   └── main_window.slint # UI definition
├── scripts/
│   ├── record_audio.py   # Audio recording
│   ├── transcribe.py     # Whisper transcription
│   └── tts.py            # Text-to-speech
├── resources/
│   └── system_prompt.txt # AI system prompt
└── README.md
```

---

## Audio driver requirements

### macOS

PortAudio is required by `sounddevice`. Install via Homebrew:

```bash
brew install portaudio
```

### Windows

No extra drivers needed on Windows 10/11.

### Linux (Ubuntu / Debian)

```bash
sudo apt install portaudio19-dev python3-dev
```

---

## Data storage

All session and vocabulary data is stored locally in `~/.nihongo_sensei/`:

```
~/.nihongo_sensei/
  sessions/          # auto-saved session JSON files
  vocab.json         # spaced repetition vocabulary data
  config.json        # user settings (API key)
```

No data is sent anywhere except directly to the Groq API (your conversation turns only).

---

## Window Management

This Slint edition fixes the window resizing and button clipping issues present in the Flet version. Features:

- **Proper window constraints** with minimum size (800x600)
- **Responsive layout** that adapts to window size
- **No fixed dimensions** — UI scales gracefully
- **Native window decorations** — standard title bar with close/minimize/maximize
