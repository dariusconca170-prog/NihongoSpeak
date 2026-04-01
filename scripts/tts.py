#!/usr/bin/env python3
"""Text-to-speech script using edge-tts."""
import sys
import asyncio
import edge_tts
import pygame
import os
import tempfile

async def speak(text: str, voice: str = "ja-JP-NanamiNeural", rate: str = "+0%"):
    fd, path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(path)
    
    pygame.mixer.init()
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)
    
    pygame.mixer.music.unload()
    if os.path.exists(path):
        os.remove(path)

def main():
    if len(sys.argv) < 2:
        print("Usage: tts.py <text> [voice] [rate]")
        return
    
    text = sys.argv[1]
    voice = sys.argv[2] if len(sys.argv) > 2 else "ja-JP-NanamiNeural"
    rate = sys.argv[3] if len(sys.argv) > 3 else "+0%"
    
    asyncio.run(speak(text, voice, rate))

if __name__ == "__main__":
    main()
