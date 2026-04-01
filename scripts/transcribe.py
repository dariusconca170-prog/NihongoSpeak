#!/usr/bin/env python3
"""Transcription script using faster-whisper."""
import sys
import json

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No audio file provided"}))
        return
    
    audio_path = sys.argv[1]
    
    try:
        from faster_whisper import WhisperModel
        
        model_size = "medium"
        model = WhisperModel(model_size, device="auto", compute_type="default")
        
        segments, info = model.transcribe(audio_path, language="ja")
        text = "".join(s.text for s in segments)
        
        result = {
            "text": text.strip(),
            "language": info.language
        }
        print(json.dumps(result))
        
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()
