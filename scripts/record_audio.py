#!/usr/bin/env python3
"""Audio recording script for Nihongo Sensei."""
import sounddevice as sd
import numpy as np
import tempfile
import os
import wave

SAMPLE_RATE = 16000
CHANNELS = 1

def record_audio():
    chunks = []
    recording = True
    
    def callback(indata, frames, time, status):
        if status:
            print(status)
        chunks.append(indata.copy())
    
    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype='float32',
        blocksize=1024,
        callback=callback
    )
    
    with stream:
        print("Recording... Press Enter to stop")
        input()
    
    if not chunks:
        print("")
        exit()
    
    audio = np.concatenate(chunks, axis=0)
    
    # Check if too short or silent
    rms = np.sqrt(np.mean(audio ** 2))
    if rms < 0.001 or len(audio) / SAMPLE_RATE < 0.4:
        print("")
        exit()
    
    # Save to temp file
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    
    pcm = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())
    
    print(path)

if __name__ == "__main__":
    record_audio()
