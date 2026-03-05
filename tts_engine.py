"""
tts_engine.py — Text-to-Speech via Microsoft Edge neural voices (edge-tts)
with local pygame playback.  Entirely free, no API key required.

Key behaviour: the TTS voice (Nanami / Keita) speaks ONLY the
Japanese portions of the AI reply.  English explanations, romaji,
markdown, and emoji are stripped so the learner hears natural
Japanese pronunciation exclusively.
"""

from __future__ import annotations

import asyncio
import os
import queue
import re
import tempfile
import threading
from typing import Callable, Optional

import config

# ── Lazy imports ────────────────────────────────────────────────
edge_tts: Optional[object] = None
pygame: Optional[object] = None


def _ensure_imports() -> bool:
    global edge_tts, pygame
    try:
        import edge_tts as _et       # type: ignore[import-untyped]
        import pygame as _pg         # type: ignore[import-untyped]
        edge_tts = _et
        pygame = _pg
        return True
    except ImportError:
        return False


# ── Japanese character ranges ───────────────────────────────────
#    Used by both _clean_for_speech and _extract_japanese.

_JP_CHARS = (
    r"\u3040-\u309F"     # Hiragana
    r"\u30A0-\u30FF"     # Katakana  (includes ー \u30FC and ・ \u30FB)
    r"\u4E00-\u9FFF"     # CJK Unified Ideographs (common kanji)
    r"\u3400-\u4DBF"     # CJK Extension A
)

_JP_PUNCT = (
    r"\u3000-\u303F"     # CJK Symbols & Punctuation (。、「」〜 etc.)
    r"\uFF01-\uFF60"     # Fullwidth Forms (！？：　etc.)
    r"\uFF65-\uFF9F"     # Half-width Katakana
)

_HAS_JP = re.compile(rf"[{_JP_CHARS}]")


# ── Text processing pipeline ───────────────────────────────────

def _clean_for_speech(text: str) -> str:
    """Strip markdown formatting and emoji (general first pass)."""
    text = re.sub(r"\*{1,3}", "", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[•·\-]\s+", "", text, flags=re.MULTILINE)
    # Supplementary emoji (🎌 etc.)
    text = re.sub(r"[\U0001F000-\U0001FFFF]", " ", text)
    # Misc Symbols & Dingbats (☀ ✨ etc.)
    text = re.sub(r"[\u2600-\u27BF]", " ", text)
    # Variation selectors
    text = re.sub(r"[\uFE00-\uFE0F]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_japanese(text: str) -> str:
    """From already-cleaned text, strip English words, romaji,
    and ASCII punctuation.  Keep only Japanese characters,
    Japanese punctuation, and digits.

    Returns an empty string when no Japanese content is found,
    signalling the caller to skip TTS entirely.

    Examples
    --------
    >>> _extract_japanese("こんにちは！ Hello! How are you?")
    'こんにちは！'

    >>> _extract_japanese("今日は天気がいいですね。(It's nice weather.)")
    '今日は天気がいいですね。'

    >>> _extract_japanese("食べる(たべる) means 'to eat'.")
    '食べるたべる'

    >>> _extract_japanese("Good job! よくできました！ Keep going!")
    'よくできました！'

    >>> _extract_japanese("No Japanese at all here.")
    ''
    """

    # ── 1. Parenthesized content ────────────────────────────────
    #    • (English explanation) → remove entirely
    #    • (にほん) furigana      → keep inner text, drop parens
    def _paren_filter(m: re.Match) -> str:                   # type: ignore[type-arg]
        inner = m.group(1)
        if _HAS_JP.search(inner):
            return inner            # keep Japanese furigana / content
        return " "                  # drop English explanations

    text = re.sub(r"[（(]([^）)]*)[）)]", _paren_filter, text)

    # ── 2. Remove ALL runs of ASCII letters ─────────────────────
    #    This strips English words AND romaji (arigatou, taberu …)
    text = re.sub(r"[A-Za-z]+", " ", text)

    # ── 3. Remove ASCII punctuation ─────────────────────────────
    #    Keeps digits (TTS reads 3 as さん in context)
    #    Keeps full-width JP punctuation (。、！？「」 etc.)
    text = re.sub(
        r"""[!"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~]""",
        " ",
        text,
    )

    # ── 4. Collapse whitespace ──────────────────────────────────
    text = re.sub(r"\s+", " ", text).strip()

    # ── 5. Remove stray lone digits with no Japanese neighbours ─
    #    e.g. "  3  " left over from "N3" after letter removal
    #    but keep "3つ" or "10月" where a digit touches JP text
    text = re.sub(
        rf"(?<![{_JP_CHARS}{_JP_PUNCT}\d])\d+(?![{_JP_CHARS}{_JP_PUNCT}\d])",
        " ",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip()

    # ── 6. Final check: any real Japanese left? ─────────────────
    if not _HAS_JP.search(text):
        return ""

    return text


# ═══════════════════════════════════════════════════════════════
#  TTS ENGINE
# ═══════════════════════════════════════════════════════════════

_QueueItem = Optional[tuple[str, Optional[Callable[[], None]]]]


class TTSEngine:
    """Queue-based, threaded TTS with edge-tts + pygame.

    The ``speak()`` method automatically extracts only Japanese
    text before synthesis so the neural voice never attempts to
    read English sentences.
    """

    def __init__(self) -> None:
        self._voice: str = config.TTS_DEFAULT_VOICE
        self._rate: str = config.TTS_DEFAULT_RATE
        self._enabled: bool = True
        self._initialized: bool = False
        self._playing: bool = False
        self._stop_flag: threading.Event = threading.Event()
        self._queue: queue.Queue[_QueueItem] = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        self._current_file: Optional[str] = None

    # ── Initialisation ──────────────────────────────────────────

    def initialize(self) -> bool:
        if not _ensure_imports():
            return False
        try:
            pygame.mixer.init(                         # type: ignore[union-attr]
                frequency=24000, size=-16, channels=1, buffer=2048,
            )
        except Exception:
            try:
                pygame.mixer.init()                    # type: ignore[union-attr]
            except Exception:
                return False
        self._initialized = True
        self._worker = threading.Thread(
            target=self._worker_loop, daemon=True,
        )
        self._worker.start()
        return True

    # ── Public API ──────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._initialized

    @property
    def enabled(self) -> bool:
        return self._enabled and self._initialized

    @enabled.setter
    def enabled(self, val: bool) -> None:
        self._enabled = val
        if not val:
            self.stop()

    @property
    def is_playing(self) -> bool:
        return self._playing

    def set_voice(self, voice_key: str) -> None:
        self._voice = config.TTS_VOICES.get(voice_key, config.TTS_DEFAULT_VOICE)

    def set_rate(self, rate_key: str) -> None:
        self._rate = config.TTS_RATES.get(rate_key, "+0%")

    def speak(
        self,
        text: str,
        on_done: Optional[Callable[[], None]] = None,
    ) -> None:
        """Enqueue *text* for synthesis + playback.

        Only Japanese portions are sent to the TTS voice.
        If no Japanese is found the call completes immediately
        (``on_done`` is still invoked).
        """
        if not self.enabled:
            if on_done:
                on_done()
            return

        # ── extract Japanese only ───────────────────────────────
        cleaned = _clean_for_speech(text)
        jp_only = _extract_japanese(cleaned)

        if not jp_only:
            # nothing to say — finish silently
            if on_done:
                on_done()
            return

        self._queue.put((jp_only, on_done))

    def stop(self) -> None:
        self._stop_flag.set()
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
                if item is not None:
                    _, cb = item
                    if cb:
                        try:
                            cb()
                        except Exception:
                            pass
            except queue.Empty:
                break
        try:
            if pygame.mixer.get_init() and pygame.mixer.music.get_busy():  # type: ignore[union-attr]
                pygame.mixer.music.stop()                                   # type: ignore[union-attr]
        except Exception:
            pass
        self._playing = False

    def shutdown(self) -> None:
        self.stop()
        self._queue.put(None)
        self._cleanup_temp()
        try:
            pygame.mixer.quit()         # type: ignore[union-attr]
        except Exception:
            pass

    # ── Worker thread ───────────────────────────────────────────

    def _worker_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while True:
            item: _QueueItem = self._queue.get()
            if item is None:
                break

            text, on_done = item
            if not self._enabled:
                if on_done:
                    on_done()
                continue

            self._stop_flag.clear()
            self._playing = True
            try:
                loop.run_until_complete(self._synth_and_play(text))
            except Exception:
                pass
            finally:
                self._playing = False
                self._cleanup_temp()
                if on_done:
                    try:
                        on_done()
                    except Exception:
                        pass

    async def _synth_and_play(self, text: str) -> None:
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        self._current_file = path

        comm = edge_tts.Communicate(                   # type: ignore[union-attr]
            text=text,
            voice=self._voice,
            rate=self._rate,
        )
        await comm.save(path)

        if self._stop_flag.is_set():
            return

        try:
            mixer = pygame.mixer                       # type: ignore[union-attr]
            if not mixer.get_init():
                return
            mixer.music.load(path)
            mixer.music.play()

            while mixer.music.get_busy():
                if self._stop_flag.is_set():
                    mixer.music.stop()
                    return
                await asyncio.sleep(0.05)
        except Exception:
            pass

    def _cleanup_temp(self) -> None:
        if not self._current_file:
            return
        try:
            mixer = pygame.mixer                       # type: ignore[union-attr]
            if mixer.get_init():
                mixer.music.unload()
        except (AttributeError, Exception):
            pass
        try:
            os.unlink(self._current_file)
        except OSError:
            pass
        self._current_file = None