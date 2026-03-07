"""
ai_engine.py — Speech-to-text (faster-whisper), LLM chat (Groq),
and on-demand translation (Groq).

All public methods are **synchronous**; the GUI layer wraps every
call in a daemon thread so the event-loop is never blocked.

The ``send()`` method enforces the 70/30 comprehensible-input ratio
by injecting a reminder into the message list before each API call.
"""

from __future__ import annotations

import re
from typing import Optional

from faster_whisper import WhisperModel
from groq import Groq

import config


# ═══════════════════════════════════════════════════════════════
#  JAPANESE NUMBER POST-PROCESSING
# ═══════════════════════════════════════════════════════════════

_JP_NUMBER_MAP: list[tuple[str, str]] = [
    ("100000", "じゅうまん"),
    ("10000",  "いちまん"),
    ("1000",   "せん"),
    ("100",    "ひゃく"),
    ("20",     "にじゅう"),
    ("30",     "さんじゅう"),
    ("40",     "よんじゅう"),
    ("50",     "ごじゅう"),
    ("60",     "ろくじゅう"),
    ("70",     "ななじゅう"),
    ("80",     "はちじゅう"),
    ("90",     "きゅうじゅう"),
    ("11",     "じゅういち"),
    ("12",     "じゅうに"),
    ("13",     "じゅうさん"),
    ("14",     "じゅうよん"),
    ("15",     "じゅうご"),
    ("16",     "じゅうろく"),
    ("17",     "じゅうなな"),
    ("18",     "じゅうはち"),
    ("19",     "じゅうきゅう"),
    ("10",     "じゅう"),
    ("0",      "ゼロ"),
    ("1",      "いち"),
    ("2",      "に"),
    ("3",      "さん"),
    ("4",      "よん"),
    ("5",      "ご"),
    ("6",      "ろく"),
    ("7",      "なな"),
    ("8",      "はち"),
    ("9",      "きゅう"),
]

_JP_CHAR_PATTERN = re.compile(
    r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\u3400-\u4DBF]"
)


def _replace_digits_with_japanese(text: str) -> str:
    if not re.search(r"\d", text):
        return text

    def _num_to_jp(match: re.Match) -> str:
        result = ""
        remaining = match.group(0)
        while remaining:
            matched = False
            for arabic, japanese in _JP_NUMBER_MAP:
                if remaining.startswith(arabic):
                    result += japanese
                    remaining = remaining[len(arabic):]
                    matched = True
                    break
            if not matched:
                result += remaining[0]
                remaining = remaining[1:]
        return result

    return re.sub(r"\d+", _num_to_jp, text)


def _post_process_japanese(text: str) -> str:
    text = _replace_digits_with_japanese(text)
    text = re.sub(r"([。、！？])\1+", r"\1", text)
    text = re.sub(
        r"([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF])"
        r"\s+"
        r"([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF])",
        r"\1\2",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ═══════════════════════════════════════════════════════════════
#  WHISPER INITIAL PROMPTS
# ═══════════════════════════════════════════════════════════════

_WHISPER_PROMPT_JA: str = (
    "こんにちは。いち、に、さん、よん、ご、ろく、なな、はち、きゅう、じゅう。"
    "はい、いいえ。ありがとうございます。すみません。おはようございます。"
    "わたしはにほんごをべんきょうしています。"
    "いちがつ、にがつ、さんがつ。げつようび、かようび、すいようび。"
    "ひとつ、ふたつ、みっつ、よっつ、いつつ。"
)

_WHISPER_PROMPT_EN: str = (
    "Hello. One, two, three, four, five, six, seven, eight, nine, ten. "
    "Yes, no. Thank you. Excuse me. Good morning. "
    "I am studying Japanese."
)


# ═══════════════════════════════════════════════════════════════
#  LOCAL WHISPER TRANSCRIBER
# ═══════════════════════════════════════════════════════════════

class WhisperTranscriber:
    """Offline speech-to-text powered by *faster-whisper*."""

    def __init__(
        self,
        model_size: str = config.WHISPER_MODEL_SIZE,
        device: str = config.WHISPER_DEVICE,
        compute_type: str = config.WHISPER_COMPUTE_TYPE,
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model: Optional[WhisperModel] = None

    def load(self) -> None:
        """Load the Whisper model with device detection and a warm-up test."""
        # Try CUDA first if 'auto' or 'cuda' is selected
        use_cuda = self._device in ("auto", "cuda")
        
        if use_cuda:
            try:
                # 1. Try CUDA with int8_float16 (often more robust than float16)
                print(f"--- Attempting Whisper load (CUDA, int8_float16) ---")
                self._model = WhisperModel(
                    self._model_size,
                    device="cuda",
                    compute_type="int8_float16"
                )
                
                # 2. Warm-up test: transcribe a tiny silence buffer to verify the CUDA pipeline
                # 16kHz, 0.5s of silence
                import numpy as np
                silence = np.zeros(8000, dtype=np.float32)
                list(self._model.transcribe(silence)[0]) # consume the generator
                
                self._device = "cuda"
                self._compute_type = "int8_float16"
                print("--- Whisper loaded and verified on CUDA ---")
                return
            except Exception as exc:
                print(f"--- CUDA load or warm-up failed: {exc} ---")
                self._model = None # Clean up failed init
        
        # CPU Fallback
        try:
            target_compute = "int8" if self._compute_type in ("auto", "default") else self._compute_type
            print(f"--- Loading Whisper on CPU ({self._model_size}, {target_compute}) ---")
            self._model = WhisperModel(
                self._model_size,
                device="cpu",
                compute_type=target_compute
            )
            self._device = "cpu"
            self._compute_type = target_compute
            print("--- Whisper loaded on CPU ---")
        except Exception as exc:
            print(f"--- CPU load failed: {exc} ---")
            # Last resort: tiny model
            if self._model_size != "tiny":
                print("--- Attempting tiny model fallback on CPU ---")
                self._model = WhisperModel("tiny", device="cpu", compute_type="int8")
                self._model_size = "tiny"
                self._device = "cpu"
                self._compute_type = "int8"
            else:
                raise exc

    @property
    def ready(self) -> bool:
        return self._model is not None

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
    ) -> str:
        """Transcribe a WAV file with an automatic runtime fallback to CPU if CUDA fails."""
        if self._model is None:
            raise RuntimeError("Model not loaded — call load() first.")

        try:
            return self._perform_transcribe(audio_path, language)
        except Exception as exc:
            # If CUDA fails at runtime, immediately try to reload on CPU and retry once
            if self._device == "cuda":
                print(f"--- Runtime CUDA transcription failed: {exc} ---")
                print("--- Emergency fallback to CPU and retrying... ---")
                try:
                    self._model = WhisperModel(
                        self._model_size,
                        device="cpu",
                        compute_type="int8"
                    )
                    self._device = "cpu"
                    self._compute_type = "int8"
                    return self._perform_transcribe(audio_path, language)
                except Exception as cpu_exc:
                    print(f"--- Emergency CPU fallback failed: {cpu_exc} ---")
                    raise cpu_exc
            else:
                # If it failed on CPU already, just re-raise
                raise exc

    def _perform_transcribe(self, audio_path: str, language: Optional[str] = None) -> str:
        """Internal transcription logic."""
        if language == "ja":
            initial_prompt = _WHISPER_PROMPT_JA
        elif language == "en":
            initial_prompt = _WHISPER_PROMPT_EN
        else:
            initial_prompt = None

        segments, _info = self._model.transcribe(
            audio_path,
            beam_size=5,
            language=language,
            initial_prompt=initial_prompt,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        raw_text = " ".join(seg.text for seg in segments).strip()

        if language == "ja" or (
            language is None and _JP_CHAR_PATTERN.search(raw_text)
        ):
            raw_text = _post_process_japanese(raw_text)

        return raw_text


# ═══════════════════════════════════════════════════════════════
#  GROQ LLM CHAT  (with 70/30 ratio enforcement)
# ═══════════════════════════════════════════════════════════════

class GroqChat:
    """Stateful conversation wrapper around the Groq chat-completions API.

    Every call to ``send()`` injects the ratio reminder as a
    final system message so the model consistently structures its
    replies as comprehensible input + output task.

    Security
    --------
    The ``api_key`` is accepted **only** as a runtime parameter.
    It is held in memory for the session and never written to disk.
    """

    def __init__(
        self,
        api_key: str,
        model: str = config.GROQ_MODEL,
    ) -> None:
        if not api_key:
            raise ValueError(
                "A Groq API key is required.  Set the GROQ_API_KEY "
                "environment variable or enter it in the app dialog."
            )
        self._client = Groq(api_key=api_key)
        self._model = model
        self._history: list[dict[str, str]] = []
        self._level: str = "A0.1"
        self._japanese_pct: int = 70
        self._session_summary: str = ""
        self._vocab_review: str = ""

    # ── State ───────────────────────────────────────────────────

    def set_level(self, level: str) -> None:
        self._level = level
        self._history.clear()

    def set_ratio(self, japanese_pct: int) -> None:
        """Set the Japanese percentage (50-100)."""
        self._japanese_pct = max(50, min(100, japanese_pct))

    def set_session_context(
        self,
        session_summary: str = "",
        vocab_review: str = "",
    ) -> None:
        """Inject previous-session summary and SRS words into the prompt."""
        self._session_summary = session_summary
        self._vocab_review = vocab_review

    def clear_history(self) -> None:
        self._history.clear()

    def load_history(
        self,
        messages: list[dict[str, str]],
        level: str,
    ) -> None:
        self._level = level
        self._history = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m.get("role") in ("user", "assistant")
        ]

    # ── Chat ────────────────────────────────────────────────────

    def send(self, user_text: str) -> str:
        """Send *user_text* and return the assistant reply.

        The message list sent to Groq is structured as:
        1. **System prompt** — persona + level + ratio rule + session context
        2. **Conversation history** — last 30 messages
        3. **Ratio reminder** — a final system nudge reinforcing
           the ratio structure requirement

        This two-system-message sandwich ensures the model never
        "forgets" the ratio rule during long conversations.
        """
        self._history.append({"role": "user", "content": user_text})

        # Groq requires all system messages to appear before user/assistant turns.
        # We merge the ratio reminder into the primary system prompt instead of
        # appending a second system message after the conversation history.
        system_content = (
            config.get_system_prompt(
                self._level,
                japanese_pct=self._japanese_pct,
                session_summary=self._session_summary,
                vocab_review=self._vocab_review,
            )
            + "\n\n"
            + config.build_ratio_reminder(self._japanese_pct)
        )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_content},
            *self._history[-30:],
        ]

        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.7,
                max_tokens=700,
                top_p=0.9,
            )
            reply = resp.choices[0].message.content or ""
            self._history.append({"role": "assistant", "content": reply})
            return reply
        except Exception:
            self._history.pop()
            raise

    # ── Translation ─────────────────────────────────────────────

    def translate(self, text: str) -> str:
        """Stateless translation — does NOT touch conversation history."""
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": config.TRANSLATE_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.25,
            max_tokens=500,
        )
        return (resp.choices[0].message.content or "").strip()