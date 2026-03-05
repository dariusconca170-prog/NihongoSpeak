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
        self._model = WhisperModel(
            self._model_size,
            device=self._device,
            compute_type=self._compute_type,
        )

    @property
    def ready(self) -> bool:
        return self._model is not None

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
    ) -> str:
        """Transcribe a WAV file to text.

        Parameters
        ----------
        audio_path : str
            Path to a 16-bit 16 kHz WAV file.
        language : str or None
            ``"ja"`` forces Japanese, ``"en"`` forces English,
            ``None`` auto-detects.
        """
        if self._model is None:
            raise RuntimeError("Model not loaded — call load() first.")

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

    Every call to ``send()`` injects the 70/30 ratio reminder as a
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

    # ── State ───────────────────────────────────────────────────

    def set_level(self, level: str) -> None:
        self._level = level
        self._history.clear()

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
        1. **System prompt** — persona + level + 70/30 rule
        2. **Conversation history** — last 30 messages
        3. **Ratio reminder** — a final system nudge reinforcing
           the 70/30 structure requirement

        This two-system-message sandwich ensures the model never
        "forgets" the ratio rule during long conversations.
        """
        self._history.append({"role": "user", "content": user_text})

        messages: list[dict[str, str]] = [
            # ── primary system prompt (persona + level + ratio rule)
            {
                "role": "system",
                "content": config.get_system_prompt(self._level),
            },
            # ── conversation context (sliding window)
            *self._history[-30:],
            # ── ratio enforcer (injected after user message)
            {
                "role": "system",
                "content": config.RATIO_REMINDER,
            },
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