"""
ai_engine.py — Updated for Emotion Tagging
"""
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
        self._device = config.WHISPER_DEVICE
        self._compute_type = config.WHISPER_COMPUTE_TYPE
        self._model: Optional[WhisperModel] = None

    def load(self) -> None:
        if self._model is None:
            self._model = WhisperModel(
                self._model_size, device=self._device, compute_type=self._compute_type
            )

    def transcribe(self, audio_data: bytes) -> str:
        if self._model is None:
            return ""
        import io
        buffer = io.BytesIO(audio_data)
        segments, _ = self._model.transcribe(
            buffer, language="ja", initial_prompt=config.WHISPER_PROMPT_JA
        )
        text = "".join(s.text for s in segments).strip()
        return post_process_japanese(text)

class GroqChat:
    def __init__(self, api_key: str):
        self._client = Groq(api_key=api_key)
        self._model = config.CHAT_MODEL
        self._history: List[Dict[str, str]] = []

    def send(self, user_text: str) -> tuple[str, str]:
        """Returns (Clean_Reply, Detected_Emotion)"""
        # Rule to force AI to pick an emotion for VOICEVOX
        emotion_rule = (
            "\n\n[EMOTION RULE]: Always start your response with a tag: "
            "[NORMAL], [EXCITED], [CHILL], or [SURPRISED]. "
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

            # Extract emotion and clean text
            match = re.search(r"\[(EXCITED|CHILL|SURPRISED|NORMAL)\]", raw_reply)
            emotion = match.group(1) if match else "NORMAL"
            clean_text = re.sub(r"\[.*?\]", "", raw_reply).strip()
            
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