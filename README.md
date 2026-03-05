# 🌸 NihongoSpeak (日本語 Sensei)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![AI-Powered](https://img.shields.io/badge/AI-Llama%203.3%20%2B%20Whisper-orange.svg)]()

**NihongoSpeak** is an AI-powered immersive Japanese language tutor. Unlike standard chat apps, it acts as a "Sensei" that adapts to your specific JLPT level and enforces a pedagogical **70/30 comprehensible input ratio**—ensuring you stay challenged without getting lost.

Built for learners who want to bridge the gap between "studying" and "speaking."

---

## ✨ Key Features

* **🎙️ Real-time Speech-to-Text:** Uses `faster-whisper` for high-accuracy Japanese speech recognition locally on your CPU.
* **🧠 Level-Adaptive AI:** Choose from **A0.1 (Absolute Beginner)** to **N1**. The AI restricts its vocabulary and grammar complexity based on your selection.
* **📈 The 70/30 Rule:** The system ensures a balance of 70% Japanese and 30% English (explanations/corrections) to maximize immersion.
* **🔊 Selective TTS:** Powered by Microsoft Edge’s neural voices. It intelligently filters out English and Markdown, speaking *only* the Japanese portions for pure listening practice.
* **📊 Live Volume Metering:** A custom GUI visualizer to ensure your microphone levels are perfect before you speak.
* **💾 Auto-Session Saving:** Conversations are saved locally so you can review your progress and vocabulary later.

---

## 🛠️ Tech Stack

- **Brain:** Llama-3.3-70b (via [Groq](https://groq.com/))
- **Ears:** Faster-Whisper (Local)
- **Voice:** Edge-TTS (Neural)
- **GUI:** CustomTkinter (Modern Dark Theme)

---

## 🚀 Quick Start

### 1. Prerequisites
Ensure you have Python 3.10 or higher installed.

### 2. Installation
Clone the repository and install the dependencies:
```bash
git clone [https://github.com/dariusconca170-prog/NihongoSpeak.git](https://github.com/dariusconca170-prog/NihongoSpeak.git)
cd NihongoSpeak
pip install -r requirements.txt
