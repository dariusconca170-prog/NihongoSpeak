""" ai_engine.py — Updated for Emotion Tagging """
from __future__ import annotations
import re
import threading
from typing import Optional, List, Dict
from faster_whisper import WhisperModel
from groq import Groq
import config
from utils.japanese_utils import post_process_japanese
from utils import safe_print


class WhisperTranscriber:
    def __init__(self):
        self._model_size = config.WHISPER_MODEL_SIZE
        self._device = config.WHISPER_DEVICE  # Will be updated after load()
        self._compute_type = config.WHISPER_COMPUTE_TYPE
        self._language = config.WHISPER_LANGUAGE
        self._model: Optional[WhisperModel] = None
        self._ready = False
        self._on_ready_callbacks: List[callable] = []

    @property
    def ready(self) -> bool:
        """Returns True if the model is loaded and ready for transcription."""
        return self._model is not None and self._ready

    def load(self) -> None:
        if self._model is None:
            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
            )
            # Update device after loading (faster-whisper may change it)
            self._device = self._model.device.type if hasattr(self._model.device, 'type') else str(self._model.device)
            self._ready = True
            # Notify all callbacks
            for cb in self._on_ready_callbacks:
                try:
                    cb(self._device)
                except Exception:
                    pass

    def set_model_size(self, size: str) -> None:
        """Change model size and reload if needed."""
        self._model_size = size
        self._model = None
        self._ready = False

    def set_language(self, lang: str) -> None:
        """Change transcription language."""
        self._language = lang

    def on_ready(self, callback: callable) -> None:
        """Register a callback to be called when model is ready."""
        self._on_ready_callbacks.append(callback)

    def transcribe(self, audio_data: bytes) -> tuple[str, str]:
        if self._model is None:
            return ("", "")
        import io
        buffer = io.BytesIO(audio_data)
        segments, info = self._model.transcribe(
            buffer,
            language=self._language,
            initial_prompt=config.WHISPER_PROMPT_JA
        )
        text = "".join(s.text for s in segments).strip()
        detected_lang = info.language if hasattr(info, 'language') else self._language
        return post_process_japanese(text), detected_lang


class GroqChat:
    def __init__(self, api_key: str):
        self._client = Groq(api_key=api_key)
        self._model = config.CHAT_MODEL
        self._history: List[Dict[str, str]] = []
        self._ratio = 70
        self._level = "A0.1"
        self._session_summary = ""
        self._vocab_review = ""

    def send(self, user_text: str) -> tuple[str, str]:
        """Returns (Clean_Reply, Detected_Emotion)"""
        emotion_rule = (
            "\n\n[EMOTION RULE]: Always start your response with one of the following "
            "emotion tags, in this order of priority: [NORMAL], [EXCITED], [CHILL], [SURPRISED]. "
            "Example: '[EXCITED] すごい！'"
        )
        system_content = config.BASE_SYSTEM_PROMPT + emotion_rule
        messages = [
            {"role": "system", "content": system_content},
            *self._history[-20:],
            {"role": "user", "content": user_text}
        ]
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.8
            )
            raw_reply = resp.choices[0].message.content or ""
            self._history.append({"role": "assistant", "content": raw_reply})
            match = re.search(r"\[(NORMAL|EXCITED|CHILL|SURPRISED)\]", raw_reply)
            emotion = match.group(1) if match else "NORMAL"
            clean_text = re.sub(r"\[(NORMAL|EXCITED|CHILL|SURPRISED)\]", "", raw_reply).strip()
            return clean_text, emotion
        except Exception as e:
            safe_print(f"AI Error: {e}")
            return "すみません、エラーが発生しました。", "NORMAL"

    def translate(self, text: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": config.TRANSLATE_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.2
        )
        return resp.choices[0].message.content or ""

    def set_ratio(self, ratio: int) -> None:
        self._ratio = ratio

    def set_level(self, level: str) -> None:
        self._level = level

    def set_session_context(self, session_summary: str = "", vocab_review: str = "") -> None:
        self._session_summary = session_summary
        self._vocab_review = vocab_review

    def clear_history(self) -> None:
        self._history = []

    def load_history(self, messages: List[Dict], level: str) -> None:
        self._history = messages.copy()
        self._level = level
