"""
tts_engine.py — Local VOICEVOX Implementation
"""
import asyncio
import os
import re
import json
import tempfile
import requests
from typing import Optional

import pygame

class TTSEngine:
    def __init__(self):
        self.base_url = "http://127.0.0.1:50021"
        self._stop_flag = asyncio.Event()
        self.enabled = True  # Control if TTS is active
        self.available = False # Flag to check if VOICEVOX is reachable
        self.is_playing = False # Track if currently playing

        # Mapping Emotions to VOICEVOX Speaker Styles
        self.emotion_map = {
            "NORMAL": {"id": 2, "speed": 1.0, "int": 1.0},
            "EXCITED": {"id": 3, "speed": 1.2, "int": 1.3},
            "CHILL": {"id": 4, "speed": 0.9, "int": 0.8},
            "SURPRISED": {"id": 3, "speed": 1.1, "int": 1.6} # Example, adjust as needed
        }

    def initialize(self):
        try:
            pygame.mixer.init()
            self.available = True # Assume available if mixer init succeeds
            print("TTS Engine initialized.")
        except Exception as e:
            print(f"TTS Initialization failed: {e}")
            self.available = False

    async def speak(self, text: str, emotion: str = "NORMAL", on_done: Optional[callable] = None):
        if not self.available or not self.enabled:
            if on_done: on_done()
            return

        self._stop_flag.clear()
        clean_text = self._extract_japanese(text)
        if not clean_text:
            if on_done: on_done()
            return

        style = self.emotion_map.get(emotion, self.emotion_map["NORMAL"])

        try:
            # Step 1: Query VOICEVOX for audio query
            q_res = requests.post(f"{self.base_url}/audio_query",
                                  params={"text": clean_text, "speaker": style["id"]})
            if q_res.status_code != 200:
                print(f"VOICEVOX /audio_query error: {q_res.status_code} - {q_res.text}")
                self.available = False
                if on_done: on_done()
                return
            query = q_res.json()

            # Step 2: Adjust parameters
            query["speedScale"] = style["speed"]
            query["intonationScale"] = style["int"]

            # Step 3: Synthesize audio
            s_res = requests.post(f"{self.base_url}/synthesis",
                                  params={"speaker": style["id"]},
                                  data=json.dumps(query))
            if s_res.status_code != 200:
                print(f"VOICEVOX /synthesis error: {s_res.status_code} - {s_res.text}")
                self.available = False
                if on_done: on_done()
                return

            await self._play(s_res.content, on_done)
        except requests.exceptions.RequestException as e:
            print(f"VOICEVOX Connection Error: {e}")
            self.available = False
            if on_done: on_done()
        except Exception as e:
            print(f"VOICEVOX Unexpected Error: {e}")
            if on_done: on_done()

    async def _play(self, data: bytes, on_done: Optional[callable] = None):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            f.write(data)
            path = f.name

        self.is_playing = True
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                if self._stop_flag.is_set():
                    pygame.mixer.music.stop()
                    break
                await asyncio.sleep(0.05)
        finally:
            pygame.mixer.music.unload()
            if os.path.exists(path):
                os.remove(path)
            self.is_playing = False
            if on_done:
                on_done()

    def stop(self):
        self._stop_flag.set()

    def _extract_japanese(self, text: str) -> str:
        # Keep only Japanese characters, punctuation, and common symbols
        return "".join(re.findall(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\u3000-\u303F\u30FC\uFF01-\uFF0F\uFF1A-\uFF20\uFF3B-\uFF40\uFF5B-\uFF65]+", text))

    def shutdown(self):
        if pygame.mixer.get_init():
            pygame.mixer.quit()
        print("TTS Engine shut down.")

    def set_voice(self, voice_name: str):
        # This would typically map voice_name to speaker ID, speed, etc.
        # For now, we'll just acknowledge the change.
        print(f"TTS Voice set to: {voice_name}")
        pass

    def set_rate(self, rate_name: str):
        # This would typically map rate_name to speedScale and intonationScale.
        # For now, we'll just acknowledge the change.
        print(f"TTS Rate set to: {rate_name}")
        pass
