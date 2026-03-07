# 日本語 Sensei — NihongoSpeak

An immersive Japanese language tutor built with Python.

**Stack:** Llama-3.3-70b via Groq · Faster-Whisper STT · Edge-TTS · CustomTkinter

---

## Features

- **70/30 comprehensible input method** with an adjustable ratio slider (50/50 to 100% Japanese)
- **Push-to-talk voice input** with live audio visualisation
- **Pronunciation scoring** — mora-level feedback after every spoken turn
- **Spaced repetition** — difficult vocabulary resurfaces on day 1, 3, and 7 intervals
- **Persistent session memory** — previous session summary injected into every new session
- **Session review tab** — browse past conversations with corrections highlighted
- **Vocabulary tracker tab** — see all words you've struggled with and when they're due

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/dariusconca170-prog/NihongoSpeak.git
cd NihongoSpeak
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set your Groq API key

Get a free key at [console.groq.com/keys](https://console.groq.com/keys).

**Option A — environment variable (recommended):**

```bash
# macOS / Linux
export GROQ_API_KEY="gsk_..."

# Windows (PowerShell)
$env:GROQ_API_KEY="gsk_..."
```

**Option B — .env file:**

```bash
cp .env.example .env
# Edit .env and replace the placeholder with your key
```

Then load it before running:

```bash
# macOS / Linux
set -a && source .env && set +a
```

**Option C — in-app dialog:**

Leave the variable unset. The app will prompt you for the key on startup.
The key is held in memory only and never written to disk.

### 5. Run

```bash
python main.py
```

---

## Audio driver requirements

### macOS

PortAudio is required by `sounddevice`. Install via Homebrew:

```bash
brew install portaudio
```

If you see `OSError: [Errno -9996] Invalid input device`, check System Settings > Privacy > Microphone and grant access to Terminal / your Python environment.

### Windows

No extra drivers needed on Windows 10/11. If your mic is not detected, check Settings > Privacy > Microphone and ensure microphone access is on.

If you hear no TTS audio, install or update your audio drivers and ensure pygame can initialise a mixer (the app falls back gracefully if it cannot).

### Linux (Ubuntu / Debian)

```bash
sudo apt install portaudio19-dev python3-dev
```

For TTS playback, pygame requires SDL2:

```bash
sudo apt install libsdl2-mixer-2.0-0
```

---

## Data storage

All session and vocabulary data is stored locally in `~/.nihongo_sensei/`:

```
~/.nihongo_sensei/
  sessions/          # auto-saved session JSON files
  vocab.json         # spaced repetition vocabulary data
```

No data is sent anywhere except directly to the Groq API (your conversation turns only).

---

## Whisper model sizes

Edit `config.py` to change the local STT model:

| `WHISPER_MODEL_SIZE` | RAM   | Speed  | Accuracy |
|----------------------|-------|--------|----------|
| `tiny`               | ~1 GB | Fast   | Basic    |
| `base`               | ~1 GB | Fast   | Good     |
| `small`              | ~2 GB | Medium | Better   |
| `medium`             | ~5 GB | Slower | Best     |

The default is `medium`. On GPU with `int8` quantisation it loads in under seconds.
