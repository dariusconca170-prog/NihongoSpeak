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

pygame: Optional[object] = None

class TTSEngine:
    def __init__(self):
        self.base_url = "http://127.0.0.1:50021"
        self._stop_flag = asyncio.Event()
        
        # Mapping Emotions to VOICEVOX Speaker Styles (Shikoku Metan)
        # ID 2: Normal, 3: Sweet (Excited), 4: Cool (Chill), 36: Whisper
        self.emotion_map = {
            "NORMAL": {"id": 2, "speed": 1.0, "int": 1.0},
            "EXCITED": {"id": 3, "speed": 1.2, "int": 1.3},
            "CHILL": {"id": 4, "speed": 0.9, "int": 0.8},
            "SURPRISED": {"id": 3, "speed": 1.1, "int": 1.6}
        }

    def initialize(self):
        global pygame
        import pygame as _pg
        pygame = _pg
        pygame.mixer.init()

    async def speak(self, text: str, emotion: str = "NORMAL"):
        self._stop_flag.clear()
        clean_text = self._extract_japanese(text)
        if not clean_text: return

        style = self.emotion_map.get(emotion, self.emotion_map["NORMAL"])

        try:
            # Step 1: Query
            q_res = requests.post(f"{self.base_url}/audio_query", 
                                  params={"text": clean_text, "speaker": style["id"]})
            query = q_res.json()
            
            # Step 2: Mod parameters
            query["speedScale"] = style["speed"]
            query["intonationScale"] = style["int"]

            # Step 3: Synthesis
            s_res = requests.post(f"{self.base_url}/synthesis", 
                                  params={"speaker": style["id"]}, 
                                  data=json.dumps(query))
            
            await self._play(s_res.content)
        except Exception as e:
            print(f"VOICEVOX Error: {e}")

    async def _play(self, data: bytes):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            f.write(data)
            path = f.name
        
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if self._stop_flag.is_set():
                pygame.mixer.music.stop()
                break
            await asyncio.sleep(0.05)
        pygame.mixer.music.unload()
        if os.path.exists(path): os.remove(path)

    def stop(self):
        self._stop_flag.set()

    def _extract_japanese(self, text: str) -> str:
        return "".join(re.findall(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\u30FC]+", text))