
# 日本語 Sensei — NihongoSpeak

An immersive Japanese language tutor built with **Slint** (Rust) for a native desktop UI, powered by **Llama-3.3-70b** via Groq for intelligent tutoring, **Faster-Whisper** for speech recognition, and **Edge-TTS** for natural Japanese voice synthesis.

**Stack:** Slint (Rust) · Llama-3.3-70b via Groq · Faster-Whisper STT · Edge-TTS · Python backend

---

## What It Does

日本語 Sensei is a desktop app that simulates a private Japanese tutor. You talk or type, and it responds in a mix of Japanese and English calibrated to your level — from absolute beginner (A0.1) to near-native (N1). It corrects your mistakes gently, tracks words you struggle with, and brings them back later using spaced repetition.

---

## Features

- **70/30 immersion method** — adjustable ratio slider from 50/50 to 100% Japanese so you're always slightly challenged but never lost
- **11 proficiency levels** — A0.1 through N1, each with tailored grammar, vocabulary, and kanji expectations
- **Push-to-talk voice input** — hold the mic button, speak in Japanese or English, and Whisper transcribes it instantly
- **Gentle error correction** — mistakes are caught and corrected inline with explanations, never punished
- **Spaced repetition vocabulary** — words you struggle with resurface on day 1, 3, and 7 intervals automatically
- **Session persistence** — every conversation is auto-saved and can be reloaded from the Session Review tab
- **Vocabulary tracker** — dedicated tab showing all tracked words, struggle counts, and next review dates
- **Japanese TTS** — responses are spoken aloud using Nanami or Keita voices with adjustable speed
- **Translation on demand** — click any message to get an instant English translation
- **Cultural context** — Sensei weaves in Japanese customs, etiquette, and real-world usage naturally
- **Animated tab transitions** — smooth fade animations between Chat, Sessions, Vocabulary, and Settings tabs
- **Native desktop performance** — compiled Rust binary with Slint UI, no Electron, no web overhead

---

## Quick Start

### 1. Clone

```bash
git clone https://github.com/dariusconca170-prog/NihongoSpeak.git
cd NihongoSpeak
```

### 2. Install Rust

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

On Windows, download and run [rustup-init.exe](https://rustup.rs/) instead.

### 3. Install Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
.venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

### 4. Set your Groq API key

Get a free key at [console.groq.com/keys](https://console.groq.com/keys).

```bash
# Linux / macOS
export GROQ_API_KEY="gsk_..."

# Windows (PowerShell)
$env:GROQ_API_KEY="gsk_..."

# Windows (CMD)
set GROQ_API_KEY=gsk_...
```

Or skip this step and enter it in the ⚙️ Settings tab after launch.

### 5. Run

```bash
python main.py
```

This builds the Rust binary automatically on first run, then launches the app.

Alternatively, build and run manually:

```bash
cargo build --release
./target/release/nihongo-sensei       # Linux/macOS
.\target\release\nihongo-sensei.exe   # Windows
```

---

## How It Works

1. **You speak or type** in Japanese or English
2. **Whisper** transcribes your voice input (if using mic)
3. **Llama-3.3-70b** generates a response calibrated to your level, correcting mistakes and introducing new vocabulary
4. **Edge-TTS** speaks the response aloud in natural Japanese
5. **Spaced repetition** tracks words you struggle with and reintroduces them in future conversations
6. **Sessions auto-save** so you never lose progress

---

## Level Guide

| Level | What You'll Practice |
|-------|---------------------|
| **A0.1** | Hiragana, greetings, self-introductions, numbers 1-10 |
| **A0.2** | Basic katakana, simple sentences, core particles (は が を に) |
| **A0.3** | First kanji (日 月 人), て-form basics, adjectives |
| **Beginner** | 100 kanji, all basic conjugations, past/negative forms |
| **Elementary** | 300+ kanji, conditionals, passive/causative forms |
| **N5** | JLPT N5 grammar, ~800 vocabulary, daily conversations |
| **N4** | JLPT N4 grammar, ~1500 vocabulary, intermediate politeness |
| **N3** | Complex grammar, ~3700 vocabulary, newspaper reading |
| **N2** | Business Japanese, ~6000 vocabulary, formal writing |
| **N1** | Near-native, academic/literary expressions, virtually all Japanese |

---

## Project Structure

```text
NihongoSpeak/
├── main.py                # Entry point: builds Rust and launches app
├── Cargo.toml             # Rust manifest & dependencies
├── build.rs               # Slint build script
├── ui/
│   ├── app.slint          # Slint entry point
│   └── main_window.slint  # Main UI layout & components
├── src/
│   ├── main.rs            # Core application logic (Rust)
│   ├── audio.rs           # Rust-side audio handling
│   ├── ai_engine.py       # Llama-3.3 integration (Python)
│   ├── tts_engine.py      # Edge-TTS integration (Python)
│   ├── vocab_tracker.py   # Spaced repetition logic (Python)
│   └── ...                # Other logic files (config, session, etc.)
├── scripts/
│   ├── record_audio.py    # Mic recording script
│   ├── stop_recording.py  # Recording termination
│   ├── transcribe.py      # Faster-Whisper interface
│   └── tts.py             # TTS execution script
├── resources/
│   └── system_prompt.txt  # AI personality & level rules
└── requirements.txt       # Python dependencies
```

---

## Audio Driver Requirements

### Windows

No extra drivers needed on Windows 10/11.

### macOS

```bash
brew install portaudio
```

### Linux (Ubuntu / Debian)

```bash
sudo apt install portaudio19-dev python3-dev
```

---

## Data Storage

All data stays on your machine in `~/.nihongo_sensei/`:

```text
~/.nihongo_sensei/
├── sessions/       # Auto-saved conversation JSON files
├── vocab.json      # Spaced repetition word tracking
└── config.json     # User settings (API key, preferences)
```

**Privacy:** No data is sent anywhere except your conversation turns directly to the Groq API. No telemetry, no analytics, no accounts.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| **"GROQ_API_KEY not set"** | Set the environment variable or enter it in ⚙️ Settings |
| **Rust not found** | Install from [rustup.rs](https://rustup.rs/) and restart your terminal |
| **Build fails on first run** | Run `cargo build --release` manually to see detailed errors |
| **No audio input** | Check your mic permissions and that Python `sounddevice` is installed |
| **TTS not working** | Install `edge-tts` and `pygame`: `pip install edge-tts pygame` |
| **Window too small** | Minimum size is 800×600 — resize or maximize the window |

---

## License

MIT — see [LICENSE](LICENSE) for details.
```

Key changes from your original:

- **Added "What It Does"** — one-paragraph explanation for people who land on the repo cold
- **Added "How It Works"** — numbered flow so people understand the architecture instantly
- **Added "Level Guide" table** — makes the 11 levels scannable instead of hidden
- **Added "Troubleshooting" table** — saves you from answering the same issues repeatedly
- **Fixed project structure** — matches your actual file layout, removed files that don't exist
- **Platform-specific key setup** — added Windows PowerShell and CMD variants
- **Clarified run instructions** — `python main.py` as primary, manual cargo as alternative
- **Privacy note** — explicitly states no telemetry since that matters to users
- **Removed "Slint Edition" framing** — it's just NihongoSpeak now, no need to reference the old Flet version
- **Removed window management section** — those are implementation details, not user-facing features
