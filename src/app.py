"""
app.py — CustomTkinter dark-theme front-end for 日本語 Sensei.

Security: The API key is NEVER written to disk. It is sourced from
the GROQ_API_KEY env var or entered once via a secure modal dialog.
The key lives only in memory for the duration of the session.
"""

from __future__ import annotations

import json
import os
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import customtkinter as ctk

import config
from config import Colors
from audio_manager import AudioManager
from ai_engine import WhisperTranscriber, GroqChat
from tts_engine import TTSEngine
from vocab_tracker import VocabTracker
from session_memory import build_previous_session_summary
from pronunciation_scorer import score_pronunciation, format_score_badge

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ════════════════════════════════════════════════════════════════
#  VOLUME VISUALISER
# ════════════════════════════════════════════════════════════════

class VolumeVisualiser(ctk.CTkFrame):
    CANVAS_H: int = 68
    BAR_H: int = 6

    def __init__(
        self, master: ctk.CTkBaseClass, audio: AudioManager, **kw,
    ) -> None:
        super().__init__(
            master, fg_color=Colors.METER_BG, corner_radius=12,
            border_width=1, border_color=Colors.METER_BORDER, **kw)
        self._audio = audio
        self._active = False
        self._canvas_w: int = 600
        self._canvas = tk.Canvas(
            self, height=self.CANVAS_H, bg=Colors.METER_BG,
            highlightthickness=0, bd=0)
        self._canvas.pack(fill="x", padx=4, pady=4)
        self._canvas.bind("<Configure>", self._on_resize)
        self._draw_idle()

    def activate(self) -> None:
        self._active = True

    def deactivate(self) -> None:
        self._active = False
        self._draw_idle()

    def refresh(self) -> None:
        if self._active:
            self._draw_live()

    def _on_resize(self, event: tk.Event) -> None:
        self._canvas_w = max(event.width, 100)
        if not self._active:
            self._draw_idle()

    def _level_color(self, level: float) -> tuple[str, str]:
        if level < 0.35:
            return Colors.METER_LOW, Colors.METER_GLOW_LOW
        if level < 0.70:
            return Colors.METER_MID, Colors.METER_GLOW_MID
        return Colors.METER_HIGH, Colors.METER_GLOW_HIGH

    def _draw_idle(self) -> None:
        c = self._canvas
        c.delete("all")
        w = self._canvas_w
        mid_y = (self.CANVAS_H - self.BAR_H) / 2
        c.create_line(8, mid_y, w - 8, mid_y, fill=Colors.METER_IDLE, width=1)
        c.create_text(w // 2, mid_y, text="🎙  Audio Monitor",
                      fill=Colors.TEXT_SECONDARY, font=("Segoe UI", 10))
        bar_y = self.CANVAS_H - self.BAR_H - 2
        c.create_rectangle(4, bar_y, w - 4, bar_y + self.BAR_H,
                           fill="#0d0d1e", outline="")

    def _draw_live(self) -> None:
        c = self._canvas
        c.delete("all")
        w = self._canvas_w
        wave_h = self.CANVAS_H - self.BAR_H - 6
        mid_y = wave_h / 2
        level = self._audio.get_level()
        waveform = self._audio.get_waveform(config.WAVEFORM_DISPLAY_PTS)
        color, glow = self._level_color(level)
        n_pts = len(waveform)
        if n_pts < 2:
            return
        scale = mid_y * 4.5
        top_pts: list[tuple[float, float]] = []
        bot_pts: list[tuple[float, float]] = []
        for i in range(n_pts):
            x = 4 + i * (w - 8) / n_pts
            amp = min(abs(float(waveform[i])) * scale, mid_y * 0.93)
            top_pts.append((x, mid_y - amp))
            bot_pts.append((x, mid_y + amp))
        poly: list[float] = []
        for px, py in top_pts:
            poly.extend((px, py))
        for px, py in reversed(bot_pts):
            poly.extend((px, py))
        if len(poly) >= 6:
            c.create_polygon(poly, fill=glow, outline="", smooth=True)
        line: list[float] = []
        for i in range(n_pts):
            x = 4 + i * (w - 8) / n_pts
            y = max(3, min(wave_h - 3, mid_y - float(waveform[i]) * scale))
            line.extend((x, y))
        if len(line) >= 4:
            c.create_line(line, fill=color, width=1.5, smooth=True)
        c.create_line(4, mid_y, w - 4, mid_y, fill="#1a1a30", width=1)
        bar_y = wave_h + 4
        c.create_rectangle(4, bar_y, w - 4, bar_y + self.BAR_H,
                           fill="#0d0d1e", outline="")
        fill_w = max(0, (w - 8) * level)
        if fill_w > 1:
            c.create_rectangle(4, bar_y, 4 + fill_w, bar_y + self.BAR_H,
                               fill=color, outline="")
        peak = self._audio.get_peak()
        peak_x = 4 + (w - 8) * min(peak, 1.0)
        if peak > 0.02:
            c.create_line(peak_x, bar_y, peak_x, bar_y + self.BAR_H,
                          fill="#ffffff", width=2)
        db = self._audio.get_level_db()
        c.create_text(w - 10, 10, text=f"{db:+.0f} dB", anchor="e",
                      fill=Colors.TEXT_SECONDARY, font=("Consolas", 9))


# ════════════════════════════════════════════════════════════════
#  SESSION HISTORY MANAGER
# ════════════════════════════════════════════════════════════════

class HistoryManager:
    def __init__(self, base_dir: str = config.HISTORY_DIR) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self._session: dict = {}
        self._path: Optional[Path] = None
        self.new_session("A0.1")

    def new_session(self, level: str) -> None:
        ts = datetime.now()
        sid = ts.strftime("%Y%m%d_%H%M%S")
        self._session = {
            "id": sid, "level": level,
            "started": ts.isoformat(), "updated": ts.isoformat(),
            "messages": [],
        }
        self._path = self._base / f"session_{sid}.json"

    def set_level(self, level: str) -> None:
        self._session["level"] = level
        self._auto_save()

    def add_message(self, role: str, content: str) -> None:
        self._session["messages"].append({
            "role": role, "content": content,
            "time": datetime.now().isoformat(),
        })
        self._session["updated"] = datetime.now().isoformat()
        self._auto_save()

    def _auto_save(self) -> None:
        if self._path and self._session.get("messages"):
            try:
                self._path.write_text(
                    json.dumps(self._session, ensure_ascii=False, indent=2),
                    encoding="utf-8")
            except OSError:
                pass

    def list_sessions(self) -> list[dict]:
        results: list[dict] = []
        for fp in sorted(self._base.glob("session_*.json"), reverse=True):
            try:
                results.append(json.loads(fp.read_text(encoding="utf-8")))
            except Exception:
                continue
        return results

    def delete_session(self, session_id: str) -> None:
        (self._base / f"session_{session_id}.json").unlink(missing_ok=True)


# ════════════════════════════════════════════════════════════════
#  API KEY DIALOG  (secure — key stays in memory only)
# ════════════════════════════════════════════════════════════════

class _APIKeyDialog(ctk.CTkToplevel):
    """Modal dialog to securely collect the Groq API key at runtime.

    The key is:
    • Masked with bullets while typing
    • Stored only in ``self.api_key`` (in-memory)
    • NEVER written to disk, config files, or environment
    • Discarded when the dialog is garbage-collected
    """

    def __init__(self, parent: ctk.CTk) -> None:
        super().__init__(parent)
        self.title("🔑  Groq API Key")
        self.geometry("560x310")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.api_key: Optional[str] = None

        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width()  - 560) // 2
        py = parent.winfo_y() + (parent.winfo_height() - 310) // 2
        self.geometry(f"+{max(px, 0)}+{max(py, 0)}")

        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=32, pady=24)

        ctk.CTkLabel(
            wrap, text="🔑  Groq API Key Required",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(pady=(0, 6))

        ctk.CTkLabel(
            wrap,
            text="Your key is used for this session only.\n"
                 "It is NEVER saved to disk or transmitted anywhere\n"
                 "except directly to the Groq API.",
            font=ctk.CTkFont(size=12),
            text_color=Colors.TEXT_SECONDARY,
            justify="center",
        ).pack(pady=(0, 14))

        ctk.CTkLabel(
            wrap,
            text="Get a free key → console.groq.com/keys",
            font=ctk.CTkFont(size=11),
            text_color=Colors.ACCENT_GREEN,
        ).pack(pady=(0, 12))

        self._entry = ctk.CTkEntry(
            wrap, placeholder_text="gsk_…", width=460, height=44,
            font=ctk.CTkFont(size=14), show="•",
            border_color="#28284a",
        )
        self._entry.pack(pady=(0, 16))
        self._entry.bind("<Return>", lambda _: self._submit())
        self._entry.focus()

        btn_row = ctk.CTkFrame(wrap, fg_color="transparent")
        btn_row.pack()

        ctk.CTkButton(
            btn_row, text="Continue  →", height=42, width=180,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=Colors.SEND_BTN, hover_color=Colors.SEND_BTN_HOVER,
            command=self._submit,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_row, text="Cancel", height=42, width=100,
            font=ctk.CTkFont(size=13),
            fg_color=Colors.CLEAR_BTN, hover_color=Colors.CLEAR_BTN_HOVER,
            command=self.destroy,
        ).pack(side="left")

    def _submit(self) -> None:
        key = self._entry.get().strip()
        if key:
            self.api_key = key
            # clear the entry widget immediately for safety
            self._entry.delete(0, "end")
            self.destroy()


# ════════════════════════════════════════════════════════════════
#  HISTORY BROWSER DIALOG
# ════════════════════════════════════════════════════════════════

class _HistoryDialog(ctk.CTkToplevel):
    def __init__(self, parent: ctk.CTk, history: HistoryManager,
                 on_load: callable) -> None:
        super().__init__(parent)
        self.title("📚  Session History")
        self.geometry("660x520")
        self.minsize(500, 350)
        self.transient(parent)
        self.grab_set()
        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width()  - 660) // 2
        py = parent.winfo_y() + (parent.winfo_height() - 520) // 2
        self.geometry(f"+{max(px, 0)}+{max(py, 0)}")
        self._history = history
        self._on_load = on_load

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=20, pady=(16, 4))
        ctk.CTkLabel(hdr, text="📚  Past Sessions",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(hdr, text=f"Saved in: {config.HISTORY_DIR}",
                     font=ctk.CTkFont(size=10),
                     text_color=Colors.TEXT_SECONDARY).pack(side="right")

        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color=Colors.BG_SECONDARY, corner_radius=12)
        self._scroll.pack(fill="both", expand=True, padx=20, pady=12)
        self._scroll.grid_columnconfigure(0, weight=1)
        self._populate()

    def _populate(self) -> None:
        for w in self._scroll.winfo_children():
            w.destroy()
        sessions = self._history.list_sessions()
        if not sessions:
            ctk.CTkLabel(self._scroll, text="No saved sessions yet.",
                         font=ctk.CTkFont(size=14),
                         text_color=Colors.TEXT_SECONDARY).pack(pady=40)
            return
        for sess in sessions[:80]:
            self._card(sess)

    def _card(self, sess: dict) -> None:
        card = ctk.CTkFrame(self._scroll, fg_color=Colors.ASSISTANT_BUBBLE,
                            corner_radius=10, border_width=1,
                            border_color=Colors.ASSISTANT_BORDER)
        card.pack(fill="x", pady=4, padx=4)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 2))
        started = sess.get("started", "?")[:16].replace("T", "  ")
        ctk.CTkLabel(top, text=f"🗓  {started}",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        ctk.CTkLabel(top, text=f"📚 {sess.get('level', '?')}",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=Colors.ACCENT_GOLD).pack(side="left", padx=(12, 0))
        ctk.CTkLabel(top, text=f"💬 {len(sess.get('messages', []))} msgs",
                     font=ctk.CTkFont(size=11),
                     text_color=Colors.TEXT_SECONDARY).pack(side="left", padx=(12, 0))
        preview = ""
        for m in sess.get("messages", []):
            if m.get("role") == "user":
                preview = m.get("content", "")[:90]
                break
        if preview:
            ctk.CTkLabel(card,
                         text=f"  \"{preview}{'…' if len(preview) >= 90 else ''}\"",
                         font=ctk.CTkFont(size=11),
                         text_color=Colors.TEXT_SECONDARY,
                         anchor="w").pack(fill="x", padx=12, pady=(0, 2))
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(2, 10))
        sid = sess.get("id", "")
        ctk.CTkButton(btn_row, text="▶  Load", width=80, height=28,
                      font=ctk.CTkFont(size=11, weight="bold"),
                      fg_color=Colors.SEND_BTN, hover_color=Colors.SEND_BTN_HOVER,
                      corner_radius=8,
                      command=lambda s=sess: self._load(s)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="🗑  Delete", width=80, height=28,
                      font=ctk.CTkFont(size=11),
                      fg_color=Colors.CLEAR_BTN, hover_color=Colors.CLEAR_BTN_HOVER,
                      corner_radius=8,
                      command=lambda s=sid: self._delete(s)).pack(side="left")

    def _load(self, sess: dict) -> None:
        self._on_load(sess)
        self.destroy()

    def _delete(self, session_id: str) -> None:
        self._history.delete_session(session_id)
        self._populate()


# ════════════════════════════════════════════════════════════════
#  MAIN APPLICATION WINDOW
# ════════════════════════════════════════════════════════════════

class JapaneseTutorApp(ctk.CTk):

    def __init__(self) -> None:
        super().__init__()

        self.title("日本語 Sensei — Japanese Language Tutor")
        self.geometry("1020x850")
        self.minsize(820, 680)
        self.configure(fg_color=Colors.BG_DARK)

        self._is_recording: bool = False
        self._timer_id: Optional[str] = None
        self._last_expected_japanese: str = ""
        self._is_processing: bool = False
        self._timer_id: Optional[str] = None

        # backends
        self.audio = AudioManager()
        self.whisper = WhisperTranscriber()
        self.chat: Optional[GroqChat] = None
        self.history = HistoryManager()
        self.tts = TTSEngine()
        self.vocab = VocabTracker()

        # user-adjustable Japanese ratio (50-100%)
        self._japanese_pct: int = 70

        # speech input language (Whisper)
        self._whisper_lang: Optional[str] = (
            config.INPUT_LANGUAGES[config.DEFAULT_INPUT_LANG]
        )

        # last AI output — used for pronunciation scoring
        self._last_expected_japanese: str = ""

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()
        self.after(250, self._init_backends)

    # ────────────────────────────────────────────────────────────
    #  SHUTDOWN
    # ────────────────────────────────────────────────────────────

    def _on_close(self) -> None:
        try:
            self.tts.shutdown()
        except Exception:
            pass
        self.destroy()

    # ────────────────────────────────────────────────────────────
    #  BACKEND INIT  (secure API key flow)
    # ────────────────────────────────────────────────────────────

    def _init_backends(self) -> None:
        """Initialize all backends.

        API key acquisition priority:
        1. ``GROQ_API_KEY`` environment variable  (CI / power users)
        2. Secure in-app modal dialog             (everyone else)

        The key is passed directly to ``GroqChat.__init__`` and
        held only in the Groq client's memory.  It is **never**
        written to any file, config, or environment variable.
        """
        api_key = config.GROQ_API_KEY          # from env var

        if not api_key:
            dlg = _APIKeyDialog(self)
            self.wait_window(dlg)
            api_key = dlg.api_key              # from dialog (or None)
            if not api_key:
                self._status("❌  No API key provided — exiting …")
                self.after(3000, self.destroy)
                return

        try:
            self.chat = GroqChat(api_key=api_key)
        except Exception as exc:
            self._status(f"❌  Groq init failed: {exc}")
            return

        # Discard local reference — only GroqChat holds the key now
        del api_key

        # Inject previous-session context + SRS vocab
        try:
            summary = build_previous_session_summary()
            vocab_prompt = self.vocab.get_review_prompt()
            self.chat.set_session_context(
                session_summary=summary,
                vocab_review=vocab_prompt,
            )
            self.chat.set_ratio(self._japanese_pct)
        except Exception:
            pass

        tts_ok = self.tts.initialize()
        if tts_ok:
            self._status("🔊  TTS ready  •  ⏳  Loading Whisper model …")
        else:
            self._status("⚠  TTS unavailable  •  ⏳  Loading Whisper …")
            self.tts_toggle_btn.configure(
                text="🔇  No TTS", state="disabled",
                fg_color=Colors.TTS_OFF)

        def _load() -> None:
            try:
                self.whisper.load()
                self.after(0, self._on_whisper_ready)
            except Exception as exc:
                err_msg = str(exc)
                self.after(0, lambda: self._status(f"❌  Whisper: {err_msg}"))

        threading.Thread(target=_load, daemon=True).start()

    def _on_whisper_ready(self) -> None:
        self._status("✅  All systems ready — speak or type!")
        self.ptt_btn.configure(state="normal")
        self.send_btn.configure(state="normal")
        self.txt_entry.configure(state="normal")

    # ────────────────────────────────────────────────────────────
    #  UI BUILD
    # ────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self._build_tabview()
        self._build_input_area()
        self._build_status_bar()

    def _build_tabview(self) -> None:
        """Build the main tabview containing chat and session review tabs."""
        self._tabview = ctk.CTkTabview(
            self,
            fg_color=Colors.BG_SECONDARY,
            segmented_button_fg_color=Colors.BG_DARK,
            segmented_button_selected_color=Colors.SEND_BTN,
            segmented_button_selected_hover_color=Colors.SEND_BTN_HOVER,
            segmented_button_unselected_color=Colors.BG_SECONDARY,
            corner_radius=14,
            border_width=1,
            border_color=Colors.CHAT_BORDER,
        )
        self._tabview.grid(row=1, column=0, sticky="nsew", padx=20, pady=8)
        self._tabview.add("💬  Chat")
        self._tabview.add("📖  Session Review")
        self._tabview.add("📊  Vocabulary")
        self._tabview.tab("💬  Chat").grid_columnconfigure(0, weight=1)
        self._tabview.tab("💬  Chat").grid_rowconfigure(0, weight=1)
        self._tabview.tab("📖  Session Review").grid_columnconfigure(0, weight=1)
        self._tabview.tab("📖  Session Review").grid_rowconfigure(0, weight=1)
        self._tabview.tab("📊  Vocabulary").grid_columnconfigure(0, weight=1)
        self._tabview.tab("📊  Vocabulary").grid_rowconfigure(0, weight=1)

        self._build_chat_area()
        self._build_session_review_tab()
        self._build_vocab_tab()

    # ── header ──────────────────────────────────────────────────

    def _build_header(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color=Colors.HEADER_BG, corner_radius=0)
        hdr.grid(row=0, column=0, sticky="ew")
        pad = ctk.CTkFrame(hdr, fg_color="transparent")
        pad.pack(fill="x", padx=22, pady=(14, 12))
        pad.grid_columnconfigure(3, weight=1)

        # row 0: title
        tbox = ctk.CTkFrame(pad, fg_color="transparent")
        tbox.grid(row=0, column=0, columnspan=9, sticky="w", pady=(0, 12))
        ctk.CTkLabel(tbox, text="日本語",
                     font=ctk.CTkFont(size=32, weight="bold"),
                     text_color=Colors.ACCENT_RED).pack(side="left")
        ctk.CTkLabel(tbox, text=" Sensei",
                     font=ctk.CTkFont(size=32, weight="bold"),
                     text_color=Colors.TEXT_PRIMARY).pack(side="left")
        ctk.CTkLabel(tbox, text="    🎌  Immersive Japanese Tutor",
                     font=ctk.CTkFont(size=13),
                     text_color=Colors.TEXT_SECONDARY
                     ).pack(side="left", padx=(8, 0))

        # row 1: mic + language + level + buttons
        col = 0

        ctk.CTkLabel(pad, text="🎙  Mic:",
                     font=ctk.CTkFont(size=13, weight="bold")
                     ).grid(row=1, column=col, sticky="w", padx=(0, 6))
        col += 1

        devs = AudioManager.list_input_devices()
        names = [d[1] for d in devs] or ["No input devices"]
        self._dev_map: dict[str, int] = {d[1]: d[0] for d in devs}
        self.mic_cb = ctk.CTkComboBox(
            pad, values=names, width=260, command=self._on_mic_changed,
            font=ctk.CTkFont(size=12), dropdown_font=ctk.CTkFont(size=11),
            state="readonly")
        self.mic_cb.grid(row=1, column=col, sticky="w", padx=(0, 12))
        if devs:
            self.mic_cb.set(names[0])
            self.audio.set_device(devs[0][0])
        col += 1

        ctk.CTkLabel(pad, text="🗣  Speak:",
                     font=ctk.CTkFont(size=13, weight="bold")
                     ).grid(row=1, column=col, sticky="w", padx=(0, 6))
        col += 1

        lang_names = list(config.INPUT_LANGUAGES.keys())
        self.lang_cb = ctk.CTkComboBox(
            pad, values=lang_names, width=145,
            command=self._on_input_lang_changed,
            font=ctk.CTkFont(size=12), state="readonly")
        self.lang_cb.set(config.DEFAULT_INPUT_LANG)
        self.lang_cb.grid(row=1, column=col, sticky="w", padx=(0, 12))
        col += 1

        ctk.CTkFrame(pad, fg_color="transparent").grid(
            row=1, column=col, sticky="ew")
        col += 1

        ctk.CTkLabel(pad, text="📚  Level:",
                     font=ctk.CTkFont(size=13, weight="bold")
                     ).grid(row=1, column=col, sticky="e", padx=(0, 6))
        col += 1

        self.lvl_cb = ctk.CTkComboBox(
            pad, values=config.JLPT_LEVELS, width=120,
            command=self._on_level_changed,
            font=ctk.CTkFont(size=12), state="readonly")
        self.lvl_cb.set("A0.1")
        self.lvl_cb.grid(row=1, column=col, sticky="e", padx=(0, 10))
        col += 1

        ctk.CTkButton(pad, text="📂", width=36, height=30,
                      font=ctk.CTkFont(size=14),
                      fg_color=Colors.HISTORY_BTN,
                      hover_color=Colors.HISTORY_BTN_HOVER,
                      command=self._open_history
                      ).grid(row=1, column=col, sticky="e", padx=(0, 4))
        col += 1

        ctk.CTkButton(pad, text="🗑", width=36, height=30,
                      font=ctk.CTkFont(size=14),
                      fg_color=Colors.CLEAR_BTN,
                      hover_color=Colors.CLEAR_BTN_HOVER,
                      command=self._clear_chat
                      ).grid(row=1, column=col, sticky="e")

        # row 2: separator
        ctk.CTkFrame(pad, height=1, fg_color="#1c1c3a").grid(
            row=2, column=0, columnspan=col + 1, sticky="ew", pady=(10, 8))

        # row 3: TTS controls
        tc = 0
        ctk.CTkLabel(pad, text="🔊  Voice:",
                     font=ctk.CTkFont(size=13, weight="bold")
                     ).grid(row=3, column=tc, sticky="w", padx=(0, 6))
        tc += 1

        self.tts_toggle_btn = ctk.CTkButton(
            pad, text="🔊  Voice ON", width=120, height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=Colors.TTS_ON, hover_color=Colors.TTS_ON_HOVER,
            corner_radius=8, command=self._toggle_tts)
        self.tts_toggle_btn.grid(row=3, column=tc, sticky="w", padx=(0, 14))
        tc += 1

        ctk.CTkLabel(pad, text="🗣:",
                     font=ctk.CTkFont(size=13, weight="bold")
                     ).grid(row=3, column=tc + 2, sticky="e", padx=(0, 4))

        voice_names = list(config.TTS_VOICES.keys())
        self.voice_cb = ctk.CTkComboBox(
            pad, values=voice_names, width=170,
            command=self._on_voice_changed,
            font=ctk.CTkFont(size=11), state="readonly")
        self.voice_cb.set(voice_names[0])
        self.voice_cb.grid(row=3, column=tc + 3, sticky="e", padx=(0, 10))

        ctk.CTkLabel(pad, text="⏩:",
                     font=ctk.CTkFont(size=13, weight="bold")
                     ).grid(row=3, column=tc + 4, sticky="e", padx=(0, 4))

        rate_names = list(config.TTS_RATES.keys())
        self.rate_cb = ctk.CTkComboBox(
            pad, values=rate_names, width=105,
            command=self._on_rate_changed,
            font=ctk.CTkFont(size=11), state="readonly")
        self.rate_cb.set("Normal")
        self.rate_cb.grid(row=3, column=tc + 5, sticky="e")

        # row 4: separator
        ctk.CTkFrame(pad, height=1, fg_color="#1c1c3a").grid(
            row=4, column=0, columnspan=col + 1, sticky="ew", pady=(10, 8))

        # row 5: Japanese ratio slider
        ratio_row = ctk.CTkFrame(pad, fg_color="transparent")
        ratio_row.grid(row=5, column=0, columnspan=col + 1, sticky="ew", pady=(0, 4))

        ctk.CTkLabel(ratio_row, text="🇯🇵  Japanese ratio:",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")

        self._ratio_label = ctk.CTkLabel(
            ratio_row, text="70% JP / 30% EN",
            font=ctk.CTkFont(size=12),
            text_color=Colors.ACCENT_GOLD, width=130)
        self._ratio_label.pack(side="left", padx=(8, 6))

        self._ratio_slider = ctk.CTkSlider(
            ratio_row, from_=50, to=100, number_of_steps=10,
            width=200, command=self._on_ratio_changed)
        self._ratio_slider.set(70)
        self._ratio_slider.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(ratio_row,
                     text="50/50",
                     font=ctk.CTkFont(size=10),
                     text_color=Colors.TEXT_SECONDARY).pack(side="left")
        self._ratio_hint = ctk.CTkLabel(
            ratio_row, text="← adjust →",
            font=ctk.CTkFont(size=10),
            text_color=Colors.TEXT_SECONDARY)
        self._ratio_hint.pack(side="left", padx=4)
        ctk.CTkLabel(ratio_row,
                     text="100% JP",
                     font=ctk.CTkFont(size=10),
                     text_color=Colors.TEXT_SECONDARY).pack(side="left")

    # ── chat area ───────────────────────────────────────────────

    def _build_chat_area(self) -> None:
        parent = self._tabview.tab("💬  Chat")
        self.chat_scroll = ctk.CTkScrollableFrame(
            parent, fg_color="transparent", corner_radius=0,
            scrollbar_button_color="#252548",
            scrollbar_button_hover_color="#38386a")
        self.chat_scroll.grid(row=0, column=0, sticky="nsew")
        self.chat_scroll.grid_columnconfigure(0, weight=1)

        self._bubble(
            "assistant",
            "こんにちは！👋  Welcome to 日本語 Sensei!\n\n"
            "I'm your personal Japanese tutor using the 70/30 method:\n"
            "  📖  70% — I'll give you Japanese stories & context\n"
            "  ✍️  30% — Then a task for YOU to respond to!\n\n"
            "Getting started:\n"
            "  •  Pick your mic and level above\n"
            "  •  Set 🗣 Speak to 🇯🇵 Japanese for speech input\n"
            "  •  Hold 🎤 to speak, or type below\n"
            "  •  Beginners → try A0.1 (just single words!)\n\n"
            "一緒に日本語を勉強しましょう！ 🌸",
        )

    # ── session review tab ──────────────────────────────────────

    def _build_session_review_tab(self) -> None:
        parent = self._tabview.tab("📖  Session Review")
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.grid(row=0, column=0, sticky="nsew")
        top.grid_columnconfigure(0, weight=1)
        top.grid_rowconfigure(1, weight=1)

        # Controls row
        ctrl = ctk.CTkFrame(top, fg_color="transparent")
        ctrl.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        ctk.CTkLabel(ctrl, text="📖  Session Review",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")

        ctk.CTkButton(
            ctrl, text="🔄  Refresh", width=100, height=30,
            font=ctk.CTkFont(size=12),
            fg_color=Colors.HISTORY_BTN, hover_color=Colors.HISTORY_BTN_HOVER,
            corner_radius=8, command=self._refresh_session_review,
        ).pack(side="right", padx=(0, 4))

        # Session selector
        self._review_session_cb = ctk.CTkComboBox(
            ctrl, values=["— pick a session —"], width=280,
            font=ctk.CTkFont(size=11), state="readonly",
            command=self._on_review_session_selected)
        self._review_session_cb.pack(side="right", padx=(0, 8))

        # Content scroll
        self._review_scroll = ctk.CTkScrollableFrame(
            top, fg_color=Colors.BG_DARK, corner_radius=10,
            scrollbar_button_color="#252548")
        self._review_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._review_scroll.grid_columnconfigure(0, weight=1)

        self._refresh_session_review()

    def _refresh_session_review(self) -> None:
        sessions = self.history.list_sessions()
        if not sessions:
            self._review_session_cb.configure(values=["— no sessions saved —"])
            return
        labels = []
        self._review_sessions_map: dict[str, dict] = {}
        for s in sessions[:50]:
            started = s.get("started", "")[:16].replace("T", " ")
            label = f"{started}  [{s.get('level', '?')}]  {len(s.get('messages', []))} msgs"
            labels.append(label)
            self._review_sessions_map[label] = s
        self._review_session_cb.configure(values=labels)
        if labels:
            self._review_session_cb.set(labels[0])
            self._on_review_session_selected(labels[0])

    def _on_review_session_selected(self, label: str) -> None:
        for w in self._review_scroll.winfo_children():
            w.destroy()
        sess = getattr(self, "_review_sessions_map", {}).get(label)
        if not sess:
            return
        messages = sess.get("messages", [])
        vocab_seen: list[str] = []

        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            is_assistant = role == "assistant"
            fg = Colors.ASSISTANT_BUBBLE if is_assistant else Colors.USER_BUBBLE
            bc = Colors.ASSISTANT_BORDER if is_assistant else Colors.USER_BORDER
            tag = "Sensei 🎓" if is_assistant else "You 🗣"
            tag_clr = Colors.ACCENT_GOLD if is_assistant else Colors.ACCENT_GREEN

            card = ctk.CTkFrame(self._review_scroll, fg_color=fg,
                                corner_radius=12, border_width=1, border_color=bc)
            card.pack(fill="x", padx=4, pady=3)
            ctk.CTkLabel(card, text=tag, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=tag_clr).pack(anchor="w", padx=10, pady=(6, 0))

            # Highlight corrections in assistant messages
            display_text = content
            if is_assistant and ("→" in content or "✗" in content):
                import re as _re
                corrections = _re.findall(r"「([^」]+)」\s*→\s*「([^」]+)」", content)
                for wrong, correct in corrections:
                    vocab_seen.append(wrong)
                    display_text = display_text.replace(
                        f"「{wrong}」→「{correct}」",
                        f"⚠ 「{wrong}」→「{correct}」 ✓"
                    )

            ctk.CTkLabel(card, text=display_text,
                         font=ctk.CTkFont(size=12),
                         text_color=Colors.TEXT_PRIMARY,
                         wraplength=550, justify="left", anchor="w"
                         ).pack(anchor="w", padx=10, pady=(2, 8))

        if vocab_seen:
            vcard = ctk.CTkFrame(self._review_scroll,
                                 fg_color="#1a1a10", corner_radius=10,
                                 border_width=1, border_color=Colors.ACCENT_GOLD)
            vcard.pack(fill="x", padx=4, pady=(8, 4))
            ctk.CTkLabel(vcard, text="📚  Vocabulary corrected this session:",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=Colors.ACCENT_GOLD).pack(anchor="w", padx=10, pady=(8, 2))
            ctk.CTkLabel(vcard, text="  •  " + "\n  •  ".join(set(vocab_seen)),
                         font=ctk.CTkFont(size=12),
                         text_color=Colors.TEXT_PRIMARY,
                         justify="left", anchor="w").pack(anchor="w", padx=10, pady=(0, 8))

    # ── vocab tab ───────────────────────────────────────────────

    def _build_vocab_tab(self) -> None:
        parent = self._tabview.tab("📊  Vocabulary")
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.grid(row=0, column=0, sticky="nsew")
        top.grid_columnconfigure(0, weight=1)
        top.grid_rowconfigure(1, weight=1)

        ctrl = ctk.CTkFrame(top, fg_color="transparent")
        ctrl.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        ctk.CTkLabel(ctrl, text="📊  Tracked Vocabulary  (Spaced Repetition)",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        ctk.CTkButton(
            ctrl, text="🔄  Refresh", width=90, height=28,
            font=ctk.CTkFont(size=11),
            fg_color=Colors.HISTORY_BTN, hover_color=Colors.HISTORY_BTN_HOVER,
            corner_radius=8, command=self._refresh_vocab_tab,
        ).pack(side="right")

        self._vocab_scroll = ctk.CTkScrollableFrame(
            top, fg_color=Colors.BG_DARK, corner_radius=10,
            scrollbar_button_color="#252548")
        self._vocab_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._vocab_scroll.grid_columnconfigure(0, weight=1)
        self._vocab_scroll.grid_columnconfigure(1, weight=1)
        self._vocab_scroll.grid_columnconfigure(2, weight=0)
        self._vocab_scroll.grid_columnconfigure(3, weight=0)
        self._refresh_vocab_tab()

    def _refresh_vocab_tab(self) -> None:
        for w in self._vocab_scroll.winfo_children():
            w.destroy()

        words = self.vocab.all_words()
        due = {item["word"] for item in self.vocab.due_today()}

        if not words:
            ctk.CTkLabel(self._vocab_scroll,
                         text="No vocabulary tracked yet.\n"
                              "Words you struggle with will appear here.",
                         font=ctk.CTkFont(size=13),
                         text_color=Colors.TEXT_SECONDARY).pack(pady=40)
            return

        # Header
        headers = ["Word", "Reading", "Struggles", "Next Review", "Level"]
        for col, h in enumerate(headers):
            ctk.CTkLabel(self._vocab_scroll, text=h,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=Colors.TEXT_SECONDARY
                         ).grid(row=0, column=col, sticky="w", padx=(6, 10), pady=(4, 2))

        for row, item in enumerate(words, start=1):
            word = item["word"]
            is_due = word in due
            clr = Colors.ACCENT_GOLD if is_due else Colors.TEXT_PRIMARY
            cells = [
                word,
                item.get("reading", ""),
                str(item.get("struggles", 0)),
                item.get("next_review", ""),
                str(item.get("level", 0)),
            ]
            for col, val in enumerate(cells):
                ctk.CTkLabel(self._vocab_scroll, text=val,
                             font=ctk.CTkFont(size=12),
                             text_color=clr
                             ).grid(row=row, column=col, sticky="w", padx=(6, 10), pady=1)

    # ── input area ──────────────────────────────────────────────

    def _build_input_area(self) -> None:
        box = ctk.CTkFrame(self, fg_color="transparent")
        box.grid(row=2, column=0, sticky="ew", padx=20, pady=(4, 10))
        box.grid_columnconfigure(0, weight=1)

        txt_row = ctk.CTkFrame(box, fg_color="transparent")
        txt_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        txt_row.grid_columnconfigure(0, weight=1)

        self.txt_entry = ctk.CTkEntry(
            txt_row, placeholder_text="✍  Type in Japanese or English …",
            height=44, font=ctk.CTkFont(size=14),
            corner_radius=10, border_color="#28284a", state="disabled")
        self.txt_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.txt_entry.bind("<Return>", self._on_send_text)

        self.send_btn = ctk.CTkButton(
            txt_row, text="Send ➤", width=90, height=44,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=Colors.SEND_BTN, hover_color=Colors.SEND_BTN_HOVER,
            corner_radius=10, command=self._on_send_text, state="disabled")
        self.send_btn.grid(row=0, column=1)

        self.vol_viz = VolumeVisualiser(box, self.audio)
        self.vol_viz.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        ptt_frame = ctk.CTkFrame(box, fg_color="transparent")
        ptt_frame.grid(row=2, column=0, sticky="ew")
        ptt_frame.grid_columnconfigure(0, weight=1)

        self.ptt_btn = ctk.CTkButton(
            ptt_frame, text="🎤   Hold to Speak", height=60,
            font=ctk.CTkFont(size=20, weight="bold"),
            fg_color=Colors.PTT_READY, hover_color=Colors.PTT_READY_HOVER,
            border_width=2, border_color=Colors.PTT_READY_BORDER,
            corner_radius=14, state="disabled")
        self.ptt_btn.grid(row=0, column=0, sticky="ew")
        self.ptt_btn.bind("<ButtonPress-1>", self._ptt_press)
        self.ptt_btn.bind("<ButtonRelease-1>", self._ptt_release)

        self.lang_badge = ctk.CTkLabel(
            ptt_frame, text=self._lang_badge_text(),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=Colors.TEXT_PRIMARY,
            fg_color=Colors.LANG_JP,
            corner_radius=16, width=100, height=32)
        self.lang_badge.grid(row=0, column=1, padx=(12, 0))

        info_row = ctk.CTkFrame(box, fg_color="transparent")
        info_row.grid(row=3, column=0, sticky="ew", pady=(2, 0))
        info_row.grid_columnconfigure(0, weight=1)
        self.save_lbl = ctk.CTkLabel(
            info_row, text="💾  Auto-save active",
            font=ctk.CTkFont(size=10), text_color="#445544")
        self.save_lbl.grid(row=0, column=0, sticky="w")
        self.dur_label = ctk.CTkLabel(
            info_row, text="", font=ctk.CTkFont(size=11),
            text_color=Colors.TEXT_SECONDARY)
        self.dur_label.grid(row=0, column=1, sticky="e")

    # ── status bar ──────────────────────────────────────────────

    def _build_status_bar(self) -> None:
        bar = ctk.CTkFrame(self, height=28, fg_color=Colors.STATUS_BAR,
                           corner_radius=0)
        bar.grid(row=3, column=0, sticky="ew")
        bar.grid_propagate(False)
        self.status_lbl = ctk.CTkLabel(
            bar, text="⏳  Initializing …",
            font=ctk.CTkFont(size=11), text_color=Colors.TEXT_SECONDARY)
        self.status_lbl.pack(side="left", padx=16, pady=2)
        ctk.CTkLabel(
            bar,
            text=f"Whisper {config.WHISPER_MODEL_SIZE}  •  "
                 f"LLM {config.GROQ_MODEL}  •  "
                 f"TTS edge-tts  •  70/30 ratio",
            font=ctk.CTkFont(size=10), text_color="#444466"
        ).pack(side="right", padx=16, pady=2)

    # ────────────────────────────────────────────────────────────
    #  LANGUAGE BADGE
    # ────────────────────────────────────────────────────────────

    def _lang_badge_text(self) -> str:
        if self._whisper_lang == "ja":
            return "🇯🇵  JA"
        if self._whisper_lang == "en":
            return "🇬🇧  EN"
        return "🌐  AUTO"

    def _lang_badge_color(self) -> str:
        if self._whisper_lang == "ja":
            return Colors.LANG_JP
        if self._whisper_lang == "en":
            return Colors.LANG_EN
        return Colors.LANG_AUTO

    def _update_lang_badge(self) -> None:
        self.lang_badge.configure(
            text=self._lang_badge_text(),
            fg_color=self._lang_badge_color())

    # ────────────────────────────────────────────────────────────
    #  CHAT BUBBLES
    # ────────────────────────────────────────────────────────────

    def _bubble(
        self, role: str, text: str, *,
        translatable: bool = False, speakable: bool = False,
    ) -> None:
        is_user = role == "user"
        container = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        container.pack(fill="x", padx=4, pady=5)

        fg = Colors.USER_BUBBLE if is_user else Colors.ASSISTANT_BUBBLE
        bc = Colors.USER_BORDER if is_user else Colors.ASSISTANT_BORDER
        bubble = ctk.CTkFrame(container, fg_color=fg, corner_radius=16,
                              border_width=1, border_color=bc)
        side = "right" if is_user else "left"
        final_px = (90, 4) if is_user else (4, 90)
        if is_user:
            start_px = (final_px[0], final_px[1] + 48)
        else:
            start_px = (final_px[0] + 48, final_px[1])
        bubble.pack(side=side, padx=start_px)

        tag = "You  🗣" if is_user else "Sensei  🎓"
        tag_clr = Colors.ACCENT_GREEN if is_user else Colors.ACCENT_GOLD
        ctk.CTkLabel(bubble, text=tag,
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=tag_clr).pack(anchor="w", padx=14, pady=(10, 0))

        ctk.CTkLabel(bubble, text=text,
                     font=ctk.CTkFont(size=14),
                     text_color=Colors.TEXT_PRIMARY,
                     wraplength=460, justify="left", anchor="w"
                     ).pack(anchor="w", padx=14, pady=(4, 6))

        if not is_user and (speakable or translatable):
            self._attach_action_buttons(bubble, text, speakable, translatable)

        def _anim_pad(step: int = 0, steps: int = 8) -> None:
            if not bubble.winfo_exists():
                return
            t = min(1.0, step / steps)
            cur_left = int(start_px[0] + (final_px[0] - start_px[0]) * t)
            cur_right = int(start_px[1] + (final_px[1] - start_px[1]) * t)
            bubble.pack_configure(padx=(cur_left, cur_right))
            if step < steps:
                self.after(18, lambda: _anim_pad(step + 1, steps))
            else:
                bubble.pack_configure(padx=final_px)
        _anim_pad()
        self._smooth_scroll_bottom()

    def _attach_action_buttons(
        self, bubble: ctk.CTkFrame, original_text: str,
        speakable: bool, translatable: bool,
    ) -> None:
        action_frame = ctk.CTkFrame(bubble, fg_color="transparent")
        action_frame.pack(fill="x", padx=14, pady=(0, 10))
        btn_row = ctk.CTkFrame(action_frame, fg_color="transparent")
        btn_row.pack(anchor="w")

        if speakable:
            play_btn = ctk.CTkButton(
                btn_row, text="🔊  Play", width=90, height=26,
                font=ctk.CTkFont(size=11),
                fg_color=Colors.TTS_PLAY, hover_color=Colors.TTS_PLAY_HOVER,
                corner_radius=8)
            play_btn.pack(side="left", padx=(0, 6))

            def _play_click(btn: ctk.CTkButton = play_btn) -> None:
                if self.tts.is_playing:
                    self.tts.stop()
                    btn.configure(text="🔊  Play")
                    self._status("⏹  Stopped")
                    return
                if not self.tts.available:
                    self._status("⚠  TTS not available")
                    return
                was_enabled = self.tts.enabled
                if not was_enabled:
                    self.tts._enabled = True
                btn.configure(text="⏹  Stop")
                self._status("🔊  Sensei is speaking …")

                def _done() -> None:
                    if not was_enabled:
                        self.tts._enabled = False
                    def _ui() -> None:
                        btn.configure(text="🔊  Play")
                        if not self._is_processing:
                            self._status("✅  Ready")
                    self.after(0, _ui)
                self.tts.speak(original_text, on_done=_done)

            play_btn.configure(command=_play_click)

        if translatable:
            trans_state: dict = {
                "fetched": False, "visible": False,
                "translation": "", "label": None, "busy": False,
            }

            def _toggle_translate() -> None:
                if trans_state["busy"]:
                    return
                if trans_state["fetched"]:
                    if trans_state["visible"]:
                        if trans_state["label"]:
                            trans_state["label"].pack_forget()
                        tr_btn.configure(text="🔄  Translate")
                        trans_state["visible"] = False
                    else:
                        if trans_state["label"]:
                            trans_state["label"].pack(
                                fill="x", padx=0, pady=(6, 0))
                        tr_btn.configure(text="👁  Hide")
                        trans_state["visible"] = True
                    self.after(40, self._scroll_bottom)
                    return

                trans_state["busy"] = True
                tr_btn.configure(text="⏳ …", state="disabled")

                def _work() -> None:
                    try:
                        result = self.chat.translate(original_text)
                        def _done() -> None:
                            trans_state.update(
                                translation=result, fetched=True,
                                visible=True, busy=False)
                            lbl = ctk.CTkLabel(
                                action_frame, text=f"📝  {result}",
                                font=ctk.CTkFont(size=12),
                                text_color=Colors.TRANSLATE_TEXT,
                                wraplength=420, justify="left", anchor="w")
                            lbl.pack(fill="x", padx=0, pady=(6, 0))
                            trans_state["label"] = lbl
                            tr_btn.configure(text="👁  Hide", state="normal")
                            self.after(40, self._scroll_bottom)
                        self.after(0, _done)
                    except Exception:
                        def _err() -> None:
                            trans_state["busy"] = False
                            tr_btn.configure(text="❌  Retry", state="normal")
                        self.after(0, _err)

                threading.Thread(target=_work, daemon=True).start()

            tr_btn = ctk.CTkButton(
                btn_row, text="🔄  Translate", width=110, height=26,
                font=ctk.CTkFont(size=11),
                fg_color=Colors.TRANSLATE_BTN,
                hover_color=Colors.TRANSLATE_HOVER,
                corner_radius=8, command=_toggle_translate)
            tr_btn.pack(side="left")

    def _typing_indicator(self) -> ctk.CTkFrame:
        ctr = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        ctr.pack(fill="x", padx=4, pady=5)
        bub = ctk.CTkFrame(ctr, fg_color=Colors.ASSISTANT_BUBBLE,
                           corner_radius=16, border_width=1,
                           border_color=Colors.ASSISTANT_BORDER)
        bub.pack(side="left", padx=(4, 90))
        ctk.CTkLabel(bub, text="Sensei  🎓",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=Colors.ACCENT_GOLD
                     ).pack(anchor="w", padx=14, pady=(10, 0))
        lbl = ctk.CTkLabel(bub, text="💭  Thinking",
                           font=ctk.CTkFont(size=14),
                           text_color=Colors.TEXT_SECONDARY)
        lbl.pack(anchor="w", padx=14, pady=(4, 12))

        def _animate_dots(i: int = 0) -> None:
            if not lbl.winfo_exists():
                return
            dots = "." * ((i % 3) + 1)
            lbl.configure(text=f"💭  Thinking{dots}")
            self.after(320, lambda: _animate_dots(i + 1))
        _animate_dots()
        self.after(60, self._scroll_bottom)
        return ctr

    def _scroll_bottom(self) -> None:
        try:
            self.chat_scroll._parent_canvas.update_idletasks()
            self.chat_scroll._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    # ────────────────────────────────────────────────────────────
    #  TTS CONTROLS
    # ────────────────────────────────────────────────────────────

    def _toggle_tts(self) -> None:
        if not self.tts.available:
            return
        if self.tts.enabled:
            self.tts.enabled = False
            self._animate_button_colors(
                self.tts_toggle_btn,
                text="🔇  Voice OFF",
                fg_color=Colors.TTS_OFF,
                hover_color=Colors.TTS_OFF_HOVER,
            )
            self._status("🔇  Voice output disabled")
        else:
            self.tts.enabled = True
            self._animate_button_colors(
                self.tts_toggle_btn,
                text="🔊  Voice ON",
                fg_color=Colors.TTS_ON,
                hover_color=Colors.TTS_ON_HOVER,
            )
            self._status("🔊  Voice output enabled")

    def _on_voice_changed(self, name: str) -> None:
        self.tts.set_voice(name)
        self._status(f"🗣  Voice → {name}")

    def _on_rate_changed(self, name: str) -> None:
        self.tts.set_rate(name)
        self._status(f"⏩  Speed → {name}")

    def _auto_speak(self, text: str) -> None:
        if not self.tts.enabled:
            return
        self._status("🔊  Sensei is speaking …")
        self._animate_button_colors(
            self.tts_toggle_btn,
            text="🔊  Speaking …",
            fg_color=Colors.TTS_SPEAKING,
            hover_color=Colors.TTS_SPEAKING_HOVER,
        )

        def _on_done() -> None:
            def _ui() -> None:
                if self.tts.enabled:
                    self._animate_button_colors(
                        self.tts_toggle_btn,
                        text="🔊  Voice ON",
                        fg_color=Colors.TTS_ON,
                        hover_color=Colors.TTS_ON_HOVER,
                    )
                if not self._is_processing and not self._is_recording:
                    self._status("✅  Ready")
            self.after(0, _ui)
        self.tts.speak(text, on_done=_on_done)

    # ────────────────────────────────────────────────────────────
    #  CONTROL CALLBACKS
    # ────────────────────────────────────────────────────────────

    def _on_ratio_changed(self, value: float) -> None:
        pct = int(round(value / 10) * 10)  # snap to 10% increments
        self._japanese_pct = pct
        eng = 100 - pct
        self._ratio_label.configure(text=f"{pct}% JP / {eng}% EN")
        if self.chat:
            self.chat.set_ratio(pct)

    def _on_mic_changed(self, name: str) -> None:
        idx = self._dev_map.get(name)
        if idx is not None:
            self.audio.set_device(idx)
            self._status(f"🎙  Mic → {name[:45]}")

    def _on_input_lang_changed(self, name: str) -> None:
        self._whisper_lang = config.INPUT_LANGUAGES.get(name)
        self._update_lang_badge()
        if self._whisper_lang == "ja":
            hint = "Whisper will transcribe as Japanese (はい not \"hi\")"
        elif self._whisper_lang == "en":
            hint = "Whisper will transcribe as English"
        else:
            hint = "Whisper will auto-detect language"
        self._status(f"🗣  {hint}")

    def _on_level_changed(self, level: str) -> None:
        if self.chat:
            self.chat.set_level(level)
        self.history.set_level(level)

        level_hints = {
            "A0.1": "Single-word responses only (0-100 words)",
            "A0.2": "Binary choices: A or B? (100-250 words)",
            "A0.3": "Simple sentences: Subject-Verb-Object (250-500 words)",
            "Beginner": "Day-one learner, mostly English",
            "Elementary": "Knows kana, bridging to N5",
        }
        hint = level_hints.get(level, f"JLPT {level}")

        msg = (f"📚  Level → **{level}**\n"
               f"📋  {hint}\n"
               f"I'll adapt my teaching to this level.  続けましょう！")
        self._bubble("assistant", msg)

    def _clear_chat(self) -> None:
        self.tts.stop()
        for w in self.chat_scroll.winfo_children():
            w.destroy()
        if self.chat:
            self.chat.clear_history()
        self.history.new_session(self.lvl_cb.get())
        self._bubble(
            "assistant",
            "🌸  Chat cleared!  Let's start fresh.\n"
            "新しい会話を始めましょう！ What shall we talk about?")
        self._flash_save("💾  New session started")

    def _open_history(self) -> None:
        _HistoryDialog(self, self.history, self._load_session)

    def _load_session(self, sess: dict) -> None:
        self.tts.stop()
        for w in self.chat_scroll.winfo_children():
            w.destroy()
        level = sess.get("level", "A0.1")
        messages = sess.get("messages", [])
        if self.chat:
            self.chat.load_history(messages, level)
        self.lvl_cb.set(level)
        self.history.set_level(level)
        self._bubble(
            "assistant",
            f"📂  Restored session from "
            f"{sess.get('started', '?')[:16].replace('T', '  ')}\n"
            f"Level: {level}  •  {len(messages)} messages loaded")
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            self._bubble(role, content,
                         translatable=(role == "assistant"),
                         speakable=(role == "assistant"))
        self.history._session = sess
        self.history._path = (
            Path(config.HISTORY_DIR) / f"session_{sess['id']}.json")
        self._status(f"📂  Session restored  ({len(messages)} msgs)")

    # ────────────────────────────────────────────────────────────
    #  PUSH-TO-TALK
    # ────────────────────────────────────────────────────────────

    def _ptt_press(self, _evt: object = None) -> None:
        if (str(self.ptt_btn.cget("state")) == "disabled"
                or self._is_processing or self._is_recording
                or not self.whisper.ready):
            return

        self.tts.stop()
        self._is_recording = True
        self._animate_button_colors(
            self.ptt_btn,
            text="🔴   Recording …",
            fg_color=Colors.PTT_REC,
            hover_color=Colors.PTT_REC_HOVER,
            border_color=Colors.PTT_REC_BORDER,
        )

        lang_hint = self._lang_badge_text()
        self._status(f"🔴  Recording [{lang_hint}] — release to stop")

        try:
            self.audio.start_recording()
        except Exception as exc:
            self._is_recording = False
            self._reset_ptt()
            self._status(f"❌  Mic error: {exc}")
            return

        self.vol_viz.activate()
        self._tick_timer()

    def _tick_timer(self) -> None:
        if self._is_recording:
            self.dur_label.configure(text=f"⏱  {self.audio.elapsed():.1f} s")
            self.vol_viz.refresh()
            self._timer_id = self.after(65, self._tick_timer)

    def _ptt_release(self, _evt: object = None) -> None:
        if not self._is_recording:
            return
        self._is_recording = False
        if self._timer_id:
            self.after_cancel(self._timer_id)
            self._timer_id = None
        self.vol_viz.deactivate()
        self._animate_button_colors(
            self.ptt_btn,
            text="⏳   Processing …",
            fg_color=Colors.PTT_PROC,
            hover_color=Colors.PTT_PROC_HOVER,
            border_color=Colors.PTT_PROC_BORDER,
        )
        self._status("⏳  Processing audio …")
        threading.Thread(target=self._handle_voice, daemon=True).start()

    def _handle_voice(self) -> None:
        self._is_processing = True
        try:
            self.after(0, lambda: self._status("💾  Closing audio stream …"))
            try:
                wav = self.audio.stop_recording()
            except Exception as exc:
                self.after(0, lambda e=exc: self._status(f"❌  Audio error: {e}"))
                return

            if wav is None:
                self.after(0, lambda: self._status(
                    "⚠  Too short or silent — try again!"))
                return

            lang = self._whisper_lang
            self.after(0, lambda: self._status("🔄  Transcribing speech …"))
            
            try:
                text, _detected_lang = self.whisper.transcribe(wav, language=lang)
            except Exception as exc:
                self.after(0, lambda e=exc: self._status(
                    f"❌  Transcription failed: {str(e)[:80]}"))
                # If we're on CPU now but we were on CUDA, it means the fallback worked but the retry failed
                if self.whisper._device == "cpu":
                    self.after(0, lambda: self._status("❌  CUDA failed — even CPU fallback failed!"))
                self.after(0, lambda: self._show_retry_hint("transcription"))
                return
            finally:
                try:
                    if wav and os.path.exists(wav):
                        os.unlink(wav)
                except OSError:
                    pass

            # Update status if we're now on CPU due to a runtime fallback
            if self.whisper._device == "cpu" and lang == "ja":
                self.after(0, lambda: self._status("⚠  Switched to CPU for stability"))

            if not text.strip():
                self.after(0, lambda: self._status(
                    "⚠  Couldn't recognise speech — try again!"))
                return

            def _show_user(t: str = text) -> None:
                self._bubble("user", t)
                self.history.add_message("user", t)

                # Pronunciation scoring against last AI prompt
                if self._last_expected_japanese and lang == "ja":
                    try:
                        result = score_pronunciation(
                            self._last_expected_japanese, t)
                        badge = format_score_badge(result)
                        self._bubble_info(badge)
                        # Log struggles
                        if result.overall_score < 0.7:
                            for mora, status in result.mora_scores:
                                if status == "missing" and len(mora) > 1:
                                    self.vocab.mark_struggle(mora)
                    except Exception:
                        pass
            self.after(0, _show_user)

            self.after(0, lambda: self._status("💭  Sensei is thinking …"))
            
            # Show typing indicator without blocking the thread
            ind_holder: list[Optional[ctk.CTkFrame]] = [None]
            def _show_ind() -> None:
                ind_holder[0] = self._typing_indicator()
            self.after(0, _show_ind)

            try:
                # Add a bit of breathing room for the UI to update
                import time as _time
                _time.sleep(0.1) 
                
                reply = self.chat.send(text)
            except Exception as exc:
                self.after(0, lambda: ind_holder[0] and ind_holder[0].destroy())
                self.after(0, lambda e=exc: self._status(
                    f"❌  Groq API error: {str(e)[:80]}"))
                self.after(0, lambda: self._show_retry_hint("AI response"))
                return

            # Extract Japanese portion for next pronunciation check
            try:
                import re as _re
                jp_chars = _re.findall(r"[\u3040-\u9FFF]+", reply)
                self._last_expected_japanese = " ".join(jp_chars[:3]) if jp_chars else ""
            except Exception:
                self._last_expected_japanese = ""

            # Log corrections into vocab tracker
            try:
                self.vocab.extract_and_log(reply, text)
            except Exception:
                pass

            def _show_reply(r: str = reply) -> None:
                if ind_holder[0]:
                    ind_holder[0].destroy()
                self._bubble("assistant", r,
                             translatable=True, speakable=True)
                self.history.add_message("assistant", r)
                self._flash_save()
                if self.tts.enabled:
                    self._auto_speak(r)
                else:
                    self._status("✅  Ready")
            self.after(0, _show_reply)

        except Exception as exc:
            self.after(0, lambda e=exc: self._status(f"❌  Unexpected error: {str(e)[:90]}"))
        finally:
            self._is_processing = False
            self.after(0, self._reset_ptt)
            self.after(0, lambda: self.dur_label.configure(text=""))

    # ────────────────────────────────────────────────────────────
    #  TEXT INPUT
    # ────────────────────────────────────────────────────────────

    def _on_send_text(self, _evt: object = None) -> None:
        if str(self.send_btn.cget("state")) == "disabled":
            return
        text = self.txt_entry.get().strip()
        if not text or self._is_processing or self.chat is None:
            return

        self.tts.stop()
        self.txt_entry.delete(0, "end")
        self._bubble("user", text)
        self.history.add_message("user", text)
        self._is_processing = True
        self.send_btn.configure(state="disabled")
        indicator = self._typing_indicator()
        self._status("💭  Sensei is thinking …")

        def _work() -> None:
            try:
                reply = self.chat.send(text)

                # Log any corrections into vocab tracker
                try:
                    self.vocab.extract_and_log(reply, text)
                except Exception:
                    pass

                # Capture expected Japanese for next pronunciation check
                try:
                    import re as _re
                    jp_chars = _re.findall(r"[\u3040-\u9FFF]+", reply)
                    self._last_expected_japanese = " ".join(jp_chars[:3]) if jp_chars else ""
                except Exception:
                    pass

                def _done(r: str = reply) -> None:
                    indicator.destroy()
                    self._bubble("assistant", r,
                                 translatable=True, speakable=True)
                    self.history.add_message("assistant", r)
                    self._flash_save()
                    self.send_btn.configure(state="normal")
                    if self.tts.enabled:
                        self._auto_speak(r)
                    else:
                        self._status("✅  Ready")
                self.after(0, _done)
            except Exception as exc:
                def _err(e: Exception = exc) -> None:
                    indicator.destroy()
                    self._status(f"❌  Groq error: {str(e)[:80]}")
                    self.send_btn.configure(state="normal")
                    self._show_retry_hint("AI response")
                self.after(0, _err)
            finally:
                self._is_processing = False

        threading.Thread(target=_work, daemon=True).start()

    # ────────────────────────────────────────────────────────────
    #  HELPERS
    # ────────────────────────────────────────────────────────────

    def _status(self, msg: str) -> None:
        self.status_lbl.configure(text=msg)

    def _bubble_info(self, text: str) -> None:
        """Display a small informational pill below the last bubble."""
        ctr = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        ctr.pack(fill="x", padx=4, pady=(0, 4))
        ctk.CTkLabel(
            ctr, text=text,
            font=ctk.CTkFont(size=11),
            text_color=Colors.TEXT_SECONDARY,
            fg_color="#141428",
            corner_radius=6,
        ).pack(side="left", padx=(8, 0), ipadx=8, ipady=3)
        self.after(60, self._scroll_bottom)

    def _show_retry_hint(self, context: str = "") -> None:
        """Show a retry hint in the chat when an error occurs."""
        msg = f"⚠  {context.capitalize()} failed — you can try again."
        ctr = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        ctr.pack(fill="x", padx=4, pady=3)

        retry_frame = ctk.CTkFrame(ctr, fg_color="#2a0a0a", corner_radius=10,
                                   border_width=1, border_color="#5a1a1a")
        retry_frame.pack(side="left", padx=(4, 90))
        ctk.CTkLabel(retry_frame, text=msg,
                     font=ctk.CTkFont(size=12),
                     text_color=Colors.ACCENT_RED
                     ).pack(padx=12, pady=(8, 4))

        def _retry() -> None:
            retry_frame.destroy()
            ctr.destroy()
            self._status("🔄  Ready to try again — speak or type.")
        ctk.CTkButton(retry_frame, text="🔄  Dismiss", width=90, height=26,
                      font=ctk.CTkFont(size=11),
                      fg_color=Colors.CLEAR_BTN,
                      hover_color=Colors.CLEAR_BTN_HOVER,
                      corner_radius=6, command=_retry
                      ).pack(padx=12, pady=(0, 8))
        self._smooth_scroll_bottom()

    def _reset_ptt(self) -> None:
        self._animate_button_colors(
            self.ptt_btn,
            text="🎤   Hold to Speak",
            fg_color=Colors.PTT_READY,
            hover_color=Colors.PTT_READY_HOVER,
            border_color=Colors.PTT_READY_BORDER,
            duration_ms=500) # Longer duration for a smoother feel

    def _flash_save(self, text: str = "💾  Auto-saved") -> None:
        self.save_lbl.configure(text=text, text_color=Colors.ACCENT_GREEN)
        self.after(2500, lambda: self.save_lbl.configure(
            text="💾  Auto-save active", text_color="#445544"))

    def _hex_to_rgb(self, hx: str) -> tuple[int, int, int]:
        s = hx.strip()
        if isinstance(s, tuple):
            s = s[-1]
        if s.startswith("#"):
            s = s[1:]
        if len(s) == 3:
            s = "".join(ch * 2 for ch in s)
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        return r, g, b

    def _rgb_to_hex(self, rgb: tuple[int, int, int]) -> str:
        r, g, b = rgb
        return f"#{r:02x}{g:02x}{b:02x}"

    def _lerp_color(self, a: str, b: str, t: float) -> str:
        ar, ag, ab = self._hex_to_rgb(a)
        br, bg, bb = self._hex_to_rgb(b)
        cr = int(ar + (br - ar) * t)
        cg = int(ag + (bg - ag) * t)
        cb = int(ab + (bb - ab) * t)
        return self._rgb_to_hex((cr, cg, cb))

    def _normalize_color(self, val) -> str:
        if isinstance(val, tuple):
            try:
                return val[-1]
            except Exception:
                return str(val[0])
        return str(val)

    def _animate_button_colors(
        self,
        btn: ctk.CTkButton,
        *,
        text: Optional[str] = None,
        fg_color: Optional[str] = None,
        hover_color: Optional[str] = None,
        border_color: Optional[str] = None,
        duration_ms: int = 220,
        steps: int = 10,
    ) -> None:
        try:
            start_fg = self._normalize_color(btn.cget("fg_color"))
            start_hover = self._normalize_color(btn.cget("hover_color"))
            start_border = self._normalize_color(btn.cget("border_color"))
        except Exception:
            start_fg = start_hover = start_border = None

        end_fg = fg_color or start_fg
        end_hover = hover_color or start_hover
        end_border = border_color or start_border

        if text is not None:
            btn.configure(text=text)

        if not (start_fg and end_fg):
            if fg_color or hover_color or border_color:
                btn.configure(
                    fg_color=fg_color or start_fg,
                    hover_color=hover_color or start_hover,
                    border_color=border_color or start_border,
                )
            return

        def _step(i: int = 0) -> None:
            t = min(1.0, i / steps)
            try:
                btn.configure(
                    fg_color=self._lerp_color(start_fg, end_fg, t),
                    hover_color=self._lerp_color(start_hover, end_hover, t) if start_hover and end_hover else end_hover,
                    border_color=self._lerp_color(start_border, end_border, t) if start_border and end_border else end_border,
                )
            except Exception:
                return
            if i < steps:
                self.after(max(1, duration_ms // steps), lambda: _step(i + 1))
        _step()

    def _smooth_scroll_bottom(self, duration_ms: int = 240, steps: int = 8) -> None:
        try:
            canvas = self.chat_scroll._parent_canvas
            canvas.update_idletasks()
            _, cur_end = canvas.yview()
        except Exception:
            self.after(60, self._scroll_bottom)
            return
        start = cur_end
        end = 1.0
        if start >= 0.995:
            self.after(60, self._scroll_bottom)
            return

        def _s(i: int = 0) -> None:
            t = min(1.0, i / steps)
            val = start + (end - start) * t
            try:
                canvas.yview_moveto(val)
            except Exception:
                return
            if i < steps:
                self.after(max(1, duration_ms // steps), lambda: _s(i + 1))
        _s()
