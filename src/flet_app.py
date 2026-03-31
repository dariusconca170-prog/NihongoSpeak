import flet as ft
import os
import threading
import time
import sys
import json
from config import Colors
import config
from utils import safe_print
from flet_components import Sidebar, ModernCard, ActionButton, ChatBubble
from audio_manager import AudioManager
from ai_engine import WhisperTranscriber, GroqChat
from tts_engine import TTSEngine
from vocab_tracker import VocabTracker


class NihongoSenseiApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "日本語 Sensei — Japanese Language Partner"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = Colors.BG_MAIN
        self.page.padding = 0
        self.page.window.min_width = 1100
        self.page.window.min_height = 850
        self.page.fonts = {
            "Inter": "https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bslnt%2Cwght%5D.ttf"
        }
        self.page.theme = ft.Theme(font_family="Inter")
        self.page.scroll = None  # Ensure the page itself doesn't scroll

        # Backends
        self.audio = AudioManager()
        self.whisper = WhisperTranscriber()
        self.chat = None
        self.tts = TTSEngine()
        self.vocab = VocabTracker()

        # State
        self.current_view = "chat"
        self.is_recording = False
        self.is_processing = False

        # UI References
        self.chat_input = None
        self.mic_btn_icon = None
        self.send_btn_icon = None
        self.status_text = None
        self.chat_messages = ft.ListView(
            expand=True,
            spacing=24,
            padding=ft.padding.symmetric(vertical=20),
            auto_scroll=True,
        )

        self.setup_ui()

        try:
            self.init_backends()
        except Exception as e:
            self.safe_log(f"FATAL: Failed to initialize backends: {e}")
            import traceback
            traceback.print_exc()
            # Optionally, exit the application gracefully here if initialization fails critically
            # self.page.window_close()

    def safe_log(self, message: str):
        """Helper to print messages safely on Windows consoles."""
        safe_print(message)

    def setup_ui(self):
        # Sidebar
        self.sidebar = Sidebar(on_change=self.handle_nav_change)

        # Content Area (Main Layout)
        self.content_container = ft.Container(
            expand=True,
            padding=ft.padding.only(left=60, right=60, top=40, bottom=40),
            bgcolor=Colors.BG_MAIN,
        )
        self.content_container.content = self.get_chat_view()

        # Main Layout with Sidebar + Content
        main_layout = ft.Row(
            [self.sidebar, self.content_container],
            expand=True,
            spacing=0,
        )
        self.page.add(main_layout)

    def handle_nav_change(self, view_id):
        self.current_view = view_id
        # Update sidebar visual state
        self.sidebar.set_selected(view_id)

        if view_id == "chat":
            self.content_container.content = self.get_chat_view()
        elif view_id == "review":
            self.content_container.content = self.get_review_view()
        elif view_id == "vocab":
            self.content_container.content = self.get_vocab_view()
        elif view_id == "dashboard":
            self.content_container.content = self.get_dashboard_view()
        elif view_id == "settings":
            self.content_container.content = self.get_settings_view()

        self.page.update()

    def get_chat_view(self):
        self.status_text = ft.Text("⏳ Initializing...", size=12, color=Colors.TEXT_SECONDARY)

        # Pill badge for ratio
        ratio_badge = ft.Container(
            content=ft.Text("70% JP / 30% EN", size=11, color=Colors.ACCENT_PRIMARY, weight="bold"),
            padding=ft.padding.symmetric(4, 10),
            border_radius=20,
            border=ft.border.all(1, Colors.ACCENT_PRIMARY),
            bgcolor="transparent",
        )

        # Mic button
        self.mic_btn_icon = ft.IconButton(
            icon=ft.Icons.MIC_ROUNDED,
            icon_color=Colors.TEXT_SECONDARY,  # Start muted/gray
            tooltip="Initializing AI model...",
            bgcolor="white05",
            disabled=True,  # Start disabled
        )
        self.mic_btn_icon.on_click = self.handle_mic_click

        # Send button
        self.send_btn_icon = ft.IconButton(
            icon=ft.Icons.SEND_ROUNDED,
            icon_color=Colors.ACCENT_PRIMARY,
            tooltip="Send Message"
        )
        self.send_btn_icon.on_click = lambda _: self.handle_send_text(self.chat_input.value)

        self.chat_input = ft.TextField(
            hint_text="Ask me anything in Japanese...",
            expand=True,
            border_radius=30,
            border_color=Colors.BORDER_DEFAULT,
            bgcolor=Colors.BG_INPUT,
            color=Colors.TEXT_PRIMARY,
            text_size=15,
            content_padding=ft.padding.symmetric(horizontal=24, vertical=16),
            cursor_color=Colors.ACCENT_PRIMARY,
            focused_border_color=Colors.ACCENT_PRIMARY,
            prefix=ft.Container(
                content=self.mic_btn_icon,
                padding=ft.padding.only(left=8, right=4)
            ),
            suffix=ft.Container(
                content=self.send_btn_icon,
                padding=ft.padding.only(right=8)
            )
        )
        self.chat_input.on_submit = lambda e: self.handle_send_text(e.control.value)

        chat_layout = ft.Column(
            [
                ft.Row([
                    ft.Column([
                        ft.Text("Japanese Sensei", size=24, weight="bold", color=Colors.TEXT_PRIMARY),
                        self.status_text,
                    ], spacing=2),
                    ft.Container(expand=True),
                    ratio_badge,
                ], alignment=ft.MainAxisAlignment.CENTER),
                ft.Container(
                    content=self.chat_messages,
                    expand=1,
                    padding=ft.padding.symmetric(vertical=20),
                ),
                ft.Container(
                    content=ft.Row(
                        [self.chat_input],
                        spacing=0,
                    ),
                    padding=ft.padding.only(bottom=10),
                )
            ],
            expand=True,
            scroll=None,
        )
        return chat_layout

    def get_review_view(self):
        return ft.Column([
            ft.Text("Session Review", size=24, weight="bold", color=Colors.TEXT_PRIMARY),
            ft.Text("Analyze your past conversations and improvements.", color=Colors.TEXT_SECONDARY),
            ft.Container(height=20),
            ModernCard(
                title="Historical Performance",
                content=ft.Text("Conversation data will appear here after your first session.", color=Colors.TEXT_SECONDARY)
            )
        ], spacing=10)

    def get_dashboard_view(self):
        # Calculate stats from vocab tracker
        all_words = self.vocab.all_words()
        due = self.vocab.due_today()

        return ft.Column([
            ft.Text("Progress Dashboard", size=24, weight="bold", color=Colors.TEXT_PRIMARY),
            ft.Container(height=20),
            ft.Row([
                ModernCard(title="Total Vocabulary", content=ft.Text(str(len(all_words)), size=32, weight="bold")),
                ModernCard(title="Due for Review", content=ft.Text(str(len(due)), size=32, weight="bold")),
            ], spacing=20),
            ft.Container(height=20),
            ModernCard(
                title="Recent Needs Improvement",
                content=ft.ListView(
                    [ft.Text(f"• {w['word']} ({w['reading']}) - {w['struggles']} struggles", color=Colors.TEXT_SECONDARY) for w in all_words[:5]],
                    height=200
                )
            )
        ])

    def get_vocab_view(self):
        # Get vocabulary data
        all_words = self.vocab.all_words()
        due_today = self.vocab.due_today()

        # Build the word list
        word_controls = []
        if not all_words:
            word_controls.append(
                ft.Text(
                    "No vocabulary tracked yet.\n"
                    "Words you struggle with will appear here.",
                    size=13,
                    color=Colors.TEXT_SECONDARY
                )
            )
        else:
            # Header row
            word_controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Text("Word", size=12, weight="bold", color=Colors.TEXT_SECONDARY, width=150),
                        ft.Text("Reading", size=12, weight="bold", color=Colors.TEXT_SECONDARY, width=150),
                        ft.Text("Struggles", size=12, weight="bold", color=Colors.TEXT_SECONDARY, width=80),
                        ft.Text("Next Review", size=12, weight="bold", color=Colors.TEXT_SECONDARY, width=120),
                    ]),
                    padding=10
                )
            )

            # Word rows
            for item in all_words:
                word = item.get("word", "")
                reading = item.get("reading", "")
                struggles = str(item.get("struggles", 0))
                next_review = item.get("next_review", "")
                is_due = word in {d.get("word", "") for d in due_today}

                word_controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Text(word, size=14, color=Colors.ACCENT_GOLD if is_due else Colors.TEXT_PRIMARY, width=150),
                            ft.Text(reading, size=13, color=Colors.TEXT_SECONDARY, width=150),
                            ft.Text(struggles, size=13, color=Colors.TEXT_SECONDARY, width=80),
                            ft.Text(next_review, size=13, color=Colors.TEXT_SECONDARY, width=120),
                        ]),
                        padding=10,
                        border=ft.border.only(bottom=1, color=Colors.BORDER_DEFAULT) if is_due else None
                    )
                )

        return ft.Column([
            ft.Text("Vocabulary Tracker", size=24, weight="bold", color=Colors.TEXT_PRIMARY),
            ft.Container(height=10),
            ft.Row([
                ModernCard(
                    title="Total Words",
                    content=ft.Text(str(len(all_words)), size=32, weight="bold")
                ),
                ModernCard(
                    title="Due Today",
                    content=ft.Text(str(len(due_today)), size=32, weight="bold", color=Colors.ACCENT_GOLD if due_today else Colors.TEXT_PRIMARY)
                ),
            ], spacing=20),
            ft.Container(height=20),
            ft.Text("Tracked Vocabulary", size=16, weight="bold", color=Colors.TEXT_PRIMARY),
            ft.Container(
                content=ft.ListView(
                    controls=word_controls,
                    height=400,
                ),
                border_radius=10,
                border=ft.border.all(1, Colors.BORDER_DEFAULT),
                bgcolor=Colors.BG_SECONDARY,
            ),
        ], spacing=10)

    def get_settings_view(self):
        self.api_key_input = ft.TextField(
            value=self.get_stored_api_key(),
            hint_text="gsk_...",
            password=True,
            can_reveal_password=True,
            border_radius=10,
            border_color=Colors.BORDER_DEFAULT,
            bgcolor=Colors.BG_INPUT,
            color=Colors.TEXT_PRIMARY,
            text_size=14,
            content_padding=ft.padding.all(14),
        )

        # Whisper Model Selection
        self.model_size_dropdown = ft.Dropdown(
            value=self.whisper._model_size,
            options=[ft.dropdown.Option(s) for s in config.WHISPER_MODEL_OPTIONS],
            border_radius=10,
            border_color=Colors.BORDER_DEFAULT,
            bgcolor=Colors.BG_INPUT,
            color=Colors.TEXT_PRIMARY,
            width=200,
        )
        self.model_size_dropdown.on_change = self.handle_model_change

        # Whisper Language Selection
        self.transcription_lang_dropdown = ft.Dropdown(
            value=self.whisper._language,
            options=[ft.dropdown.Option(key=o["value"], text=o["label"]) for o in config.WHISPER_LANGUAGE_OPTIONS],
            border_radius=10,
            border_color=Colors.BORDER_DEFAULT,
            bgcolor=Colors.BG_INPUT,
            color=Colors.TEXT_PRIMARY,
            width=200,
        )
        self.transcription_lang_dropdown.on_change = self.handle_transcription_lang_change

        settings_content = ft.Column([
            ft.Text("Groq API Key", size=14, weight="bold", color=Colors.TEXT_PRIMARY),
            self.api_key_input,
            ActionButton("Save Configuration", on_click=self.handle_save_api_key),
            ft.Divider(height=40, color=Colors.BORDER_DEFAULT),
            ft.Text("Engine Room", size=14, weight="bold", color=Colors.TEXT_PRIMARY),
            ft.Text("Configure your speech-to-text engine and hardware.", size=12, color=Colors.TEXT_SECONDARY),
            ft.Row([
                ft.Column([
                    ft.Text("Whisper Model Size:", size=13, color=Colors.TEXT_SECONDARY),
                    self.model_size_dropdown,
                ]),
                ft.VerticalDivider(width=20),
                ft.Column([
                    ft.Text("Transcription Language:", size=13, color=Colors.TEXT_SECONDARY),
                    self.transcription_lang_dropdown,
                ]),
            ], spacing=20),
            ft.Row([
                ft.Column([
                    ft.Text("Current Device:", size=13, color=Colors.TEXT_SECONDARY),
                    ft.Container(
                        content=ft.Column([
                            ft.Text(
                                self.whisper._device.upper() if self.whisper.ready else "Detecting...",
                                color=Colors.ACCENT_PRIMARY if self.whisper._device == "cuda" else Colors.WARNING,
                                weight="bold",
                                size=16
                            ),
                            ft.Text(
                                "Using GPU acceleration" if self.whisper._device == "cuda" else "Missing CUDA 12 (cublas64_12.dll)",
                                size=10,
                                color=Colors.TEXT_SECONDARY if self.whisper._device == "cuda" else Colors.ERROR,
                                italic=True
                            ) if self.whisper.ready else ft.Container(),
                            ActionButton(
                                "Install CUDA Libraries",
                                on_click=self.handle_fix_cuda,
                                primary=False
                            ) if self.whisper._device != "cuda" else ft.Container()
                        ], spacing=2),
                        padding=ft.padding.only(top=10)
                    )
                ])
            ], spacing=20),
            ft.Text("Pro tip: Larger models are more accurate but slower. 'CUDA' means your GPU is being used.", size=11, italic=True, color=Colors.TEXT_SECONDARY),
        ], spacing=15)

        return ft.Column([
            ft.Text("Settings", size=24, weight="bold", color=Colors.TEXT_PRIMARY),
            ft.Container(height=20),
            ModernCard(
                title="Application Settings",
                content=settings_content
            )
        ])

    def handle_model_change(self, e):
        new_size = self.model_size_dropdown.value
        self.safe_log(f"[SETTINGS] Changing Whisper model to: {new_size}")
        # Save to config file
        self.save_config_value("whisper_model_size", new_size)
        # Force a reload in the background
        self.status_text.value = f"⏳ Switching to {new_size}..."
        self.page.update()

        def do_reload():
            self.whisper.set_model_size(new_size)
            self.load_whisper_background()

        threading.Thread(target=do_reload, daemon=True).start()

    def handle_transcription_lang_change(self, e):
        new_lang = self.transcription_lang_dropdown.value
        self.safe_log(f"[SETTINGS] Changing transcription language to: {new_lang}")
        # Save to config file
        self.save_config_value("whisper_language", new_lang)
        self.whisper.set_language(new_lang)
        self.status_text.value = f"✅ Transcription set to: {new_lang}"
        self.page.update()

    def save_config_value(self, key, value):
        """Save a simple config key-value pair to disk."""
        try:
            config_path = os.path.join(config.HISTORY_DIR, ".app_config")
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            data = {}
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data[key] = value
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            self.safe_log(f"[CONFIG] Saved {key}={value}")
        except Exception as e:
            self.safe_log(f"[CONFIG] Error saving config: {e}")

    def load_config_value(self, key, default=None):
        """Load a simple config value from disk."""
        try:
            config_path = os.path.join(config.HISTORY_DIR, ".app_config")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get(key, default)
        except Exception as e:
            self.safe_log(f"[CONFIG] Error loading config: {e}")
        return default

    def load_whisper_background(self):
        self.safe_log("[INIT] Reloading Whisper model...")
        # Disable mic while reloading
        if self.mic_btn_icon:
            self.mic_btn_icon.disabled = True
            self.mic_btn_icon.icon_color = Colors.TEXT_SECONDARY
            self.mic_btn_icon.tooltip = f"Loading {self.whisper._model_size}..."
        self.page.update()

        try:
            self.whisper.load()
            self.safe_log(f"[INIT] Whisper ({self.whisper._model_size}) loaded on {self.whisper._device}.")
            # Re-enable mic
            if self.mic_btn_icon:
                self.mic_btn_icon.disabled = False
                self.mic_btn_icon.icon_color = Colors.ACCENT_PRIMARY
                self.mic_btn_icon.tooltip = "Voice Input (Push to Talk)"
            self.page.run_thread(lambda: setattr(self.status_text, 'value', f"✅ Ready ({self.whisper._model_size})"))
            # If we are in settings, update the view to show the new device
            if self.current_view == "settings":
                self.page.run_thread(lambda: self.handle_nav_change("settings"))
        except Exception as exc:
            err_msg = str(exc)
            self.safe_log(f"[INIT] ERROR loading Whisper: {err_msg}")
            self.page.run_thread(lambda: setattr(self.status_text, 'value', f"❌ Whisper Error"))
            self.page.update()

    def get_stored_api_key(self):
        key_path = os.path.join(config.HISTORY_DIR, ".groq_api_key")
        if os.path.exists(key_path):
            with open(key_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        return config.GROQ_API_KEY or ""

    def handle_save_api_key(self, e):
        self.safe_log("[SETTINGS] Attempting to save API Key...")
        key = self.api_key_input.value.strip()
        if not key:
            self.safe_log("[SETTINGS] ERROR: Key is empty")
            self.status_text.value = "❌ Please enter a valid API key."
            self.page.update()
            return

        try:
            key_path = os.path.join(config.HISTORY_DIR, ".groq_api_key")
            os.makedirs(os.path.dirname(key_path), exist_ok=True)
            with open(key_path, "w", encoding="utf-8") as f:
                f.write(key)
            self.safe_log(f"[SETTINGS] Key saved to: {key_path}")
            self.chat = GroqChat(api_key=key)
            self.safe_log("[SETTINGS] GroqChat re-initialized")
            self.status_text.value = "✅ Settings updated"
            self.add_message("assistant", "🤖 Settings updated successfully. Ready to continue.")
        except Exception as exc:
            err_msg = str(exc)
            self.safe_log(f"[SETTINGS] ERROR: {err_msg}")
            self.status_text.value = f"❌ Error: {err_msg}"
            self.page.update()

    def handle_fix_cuda(self, e):
        self.safe_log("[SETTINGS] Attempting to install CUDA libraries via pip...")
        self.status_text.value = "⏳ Installing CUDA libraries (pip)..."
        self.page.update()

        def run_install():
            try:
                import subprocess
                # Install cublas and cudnn for CUDA 12
                cmd = [sys.executable, "-m", "pip", "install", "nvidia-cublas-cu12", "nvidia-cudnn-cu12"]
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in process.stdout:
                    self.safe_log(f"[PIP] {line.strip()}")
                process.wait()
                if process.returncode == 0:
                    self.safe_log("[SETTINGS] CUDA libraries installed. Reloading model...")
                    self.page.run_thread(lambda: setattr(self.status_text, 'value', "✅ CUDA libraries installed. Reloading..."))
                    self.load_whisper_background()
                else:
                    self.safe_log(f"[SETTINGS] Pip install failed with code {process.returncode}")
                    self.page.run_thread(lambda: setattr(self.status_text, 'value', "❌ CUDA installation failed."))
            except Exception as exc:
                self.safe_log(f"[SETTINGS] Error during installation: {exc}")
                self.page.run_thread(lambda: setattr(self.status_text, 'value', "❌ Installation error."))

        threading.Thread(target=run_install, daemon=True).start()

    def add_message(self, role, text):
        is_assistant = role == "assistant"
        bubble = ChatBubble(role, text)

        # Wrap bubble in a constrained container to prevent overflow
        # Use explicit Alignment coordinates for compatibility
        try:
            page_width = self.page.window.width if self.page.window and self.page.window.width else 1100
        except:
            page_width = 1100

        bubble_container = ft.Container(
            content=bubble,
            width=min(700, page_width * 0.7),
            alignment=ft.Alignment(-1, 0) if is_assistant else ft.Alignment(1, 0),
        )
        row = ft.Row(
            [bubble_container],
            alignment=ft.MainAxisAlignment.START if is_assistant else ft.MainAxisAlignment.END,
        )
        self.chat_messages.controls.append(row)
        self.chat_messages.update()  # Explicitly update the list
        self.page.update()

    def handle_send_text(self, text):
        if not text or self.is_processing:
            return
        self.chat_input.value = ""
        self.add_message("user", text)
        self.process_chat(text)

    def handle_mic_click(self, e):
        if self.is_recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        if self.is_processing:
            return
        self.is_recording = True
        self.mic_btn_icon.icon_color = Colors.TEXT_INVERSE
        self.mic_btn_icon.bgcolor = Colors.ERROR
        self.status_text.value = "🔴 Listening..."
        self.audio.start_recording()
        self.page.update()

    def stop_recording(self):
        self.is_recording = False
        self.mic_btn_icon.icon_color = Colors.ACCENT_PRIMARY
        self.mic_btn_icon.bgcolor = "white05"
        self.status_text.value = "⏳ Processing speech..."
        self.page.update()
        audio_data = self.audio.stop_recording()
        threading.Thread(target=self.process_audio, args=(audio_data,), daemon=True).start()

    def process_audio(self, audio_data):
        if not audio_data:
            self.safe_log("[AUDIO] Recording too short or silent.")
            self.page.run_thread(lambda: setattr(self.status_text, 'value', "⚠️ Too quiet"))
            return

        if not self.whisper.ready:
            self.safe_log("[AUDIO] ERROR: Model not loaded — cannot transcribe yet.")
            self.page.run_thread(lambda: setattr(self.status_text, 'value', "⏳ AI model still loading..."))
            return

        self.safe_log(f"[AUDIO] Transcribing file: {audio_data}")
        try:
            text, lang = self.whisper.transcribe(audio_data=audio_data)
            if text:
                self.safe_log(f"[AUDIO] Transcribed: \"{text}\" ({lang})")
                self.page.run_thread(lambda: self.handle_send_text(text))
            else:
                self.safe_log("[AUDIO] No speech detected.")
                self.page.run_thread(lambda: setattr(self.status_text, 'value', "⚠️ Not detected"))
        except Exception as exc:
            err_msg = str(exc)
            self.safe_log(f"[AUDIO] ERROR: {err_msg}")
            self.page.run_thread(lambda: setattr(self.status_text, 'value', f"❌ Error: {err_msg}"))
            self.page.update()

    def process_chat(self, text):
        self.is_processing = True
        self.status_text.value = "🤖 Thinking..."
        self.page.update()
        self.safe_log(f"[CHAT] User: \"{text}\"")

        def run():
            try:
                response = self.chat.send(text)
                self.safe_log(f"[CHAT] AI: \"{response[:100]}...\"")
                self.page.run_thread(lambda: self.add_message("assistant", response))
                # Speak response
                threading.Thread(target=self.tts.speak, args=(response,), daemon=True).start()
                self.page.run_thread(lambda: setattr(self.status_text, 'value', "✅ Ready"))
            except Exception as exc:
                err_msg = str(exc)
                self.safe_log(f"[CHAT] ERROR: {err_msg}")
                self.page.run_thread(lambda: setattr(self.status_text, 'value', f"❌ AI Error: {err_msg}"))
            finally:
                self.is_processing = False
                self.page.update()

        threading.Thread(target=run, daemon=True).start()

    def init_backends(self):
        self.safe_log("[INIT] Starting backend initialization...")

        # 1. Load persisted settings
        saved_model_size = self.load_config_value("whisper_model_size", config.WHISPER_MODEL_SIZE)
        if saved_model_size != self.whisper._model_size:
            self.safe_log(f"[INIT] Applying persisted model size: {saved_model_size}")
            self.whisper.set_model_size(saved_model_size)

        saved_lang = self.load_config_value("whisper_language", config.WHISPER_LANGUAGE)
        if saved_lang != self.whisper._language:
            self.safe_log(f"[INIT] Applying persisted transcription language: {saved_lang}")
            self.whisper.set_language(saved_lang)

        # 2. Load API key
        api_key = self.get_stored_api_key()
        if not api_key:
            self.status_text.value = "🟡 API Key missing in Settings"
            self.page.update()
        else:
            try:
                from session_memory import build_previous_session_summary
                self.chat = GroqChat(api_key=api_key)
                # Inject context
                try:
                    summary = build_previous_session_summary()
                    vocab_prompt = self.vocab.get_review_prompt()
                    self.chat.set_session_context(
                        session_summary=summary,
                        vocab_review=vocab_prompt,
                    )
                except Exception as e:
                    self.safe_log(f"[INIT] Context injection warning: {e}")
                self.safe_log("[INIT] GroqChat initialized.")
                self.status_text.value = "✅ Connected"
            except Exception as exc:
                self.safe_log(f"[INIT] ERROR initializing GroqChat: {exc}")
                self.status_text.value = f"❌ Init Error: {exc}"

        self.tts.initialize()

    def load_whisper(self):
        self.safe_log("[INIT] Loading Whisper model...")
        try:
            self.whisper.load()
            self.safe_log(f"[INIT] Whisper model loaded ({self.whisper._model_size}).")
            # Enable mic
            if self.mic_btn_icon:
                self.mic_btn_icon.disabled = False
                self.mic_btn_icon.icon_color = Colors.ACCENT_PRIMARY
                self.mic_btn_icon.tooltip = "Voice Input (Push to Talk)"
            self.page.run_thread(lambda: setattr(self.status_text, 'value', f"✅ Ready ({self.whisper._model_size})"))
            self.add_message("assistant", "やっほー！🌸 日本語の練習しようね！")
        except Exception as exc:
            err_msg = str(exc)
            self.safe_log(f"[INIT] ERROR loading Whisper: {err_msg}")
            self.page.run_thread(lambda: setattr(self.status_text, 'value', f"❌ Whisper Error"))
            self.page.update()

        threading.Thread(target=load_whisper, daemon=True).start()


def main(page: ft.Page):
    NihongoSenseiApp(page)


if __name__ == "__main__":
    ft.app(target=main)
