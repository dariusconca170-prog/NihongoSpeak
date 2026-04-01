"""
config.py — Central configuration for 日本語 Sensei.

SECURITY: No API keys are stored in this file or written to disk.
The key is sourced from the GROQ_API_KEY environment variable or
entered at runtime via a modal dialog. GitHub-safe by default.
"""

import os

# ── API & Model Defaults ────────────────────────────────────────
# NEVER hardcode a key here.  Set via environment variable or
# enter at runtime through the in-app dialog.
GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL: str = "llama-3.3-70b-versatile"
CHAT_MODEL: str = GROQ_MODEL

WHISPER_MODEL_SIZE: str = "large-v3"
WHISPER_DEVICE: str = "auto"
WHISPER_COMPUTE_TYPE: str = "default"
WHISPER_LANGUAGE: str = "ja"

WHISPER_MODEL_OPTIONS: list[str] = [
    "tiny",
    "base",
    "small",
    "medium",
    "large-v3",
]

WHISPER_LANGUAGE_OPTIONS: list[dict[str, str]] = [
    {"label": "Auto Detect", "value": "auto"},
    {"label": "Japanese", "value": "ja"},
    {"label": "English", "value": "en"},
]

# ── Audio Defaults ──────────────────────────────────────────────
SAMPLE_RATE: int = 16000
CHANNELS: int = 1
MIN_RECORD_SECONDS: float = 0.4
SILENCE_RMS_FLOOR: float = 0.001

# ── JLPT & Sub-500 Levels ──────────────────────────────────────
JLPT_LEVELS: list[str] = [
    "A0.1",              # 0-100 words    — single-word responses
    "A0.2",              # 100-250 words  — binary choices
    "A0.3",              # 250-500 words  — simple SVO patterns
    "Beginner",          # day-one guided — mostly English
    "Elementary",        # kana literate  — bridge to N5
    "N5", "N4", "N3", "N2", "N1",
    "Any Level",
]

# ── Speech Input Language ───────────────────────────────────────
INPUT_LANGUAGES: dict[str, str | None] = {
    "🇯🇵  Japanese":  "ja",
    "🇬🇧  English":   "en",
    "🌐  Auto":       None,
}
DEFAULT_INPUT_LANG: str = "🇯🇵  Japanese"

# ── Auto-Save ──────────────────────────────────────────────────
HISTORY_DIR: str = os.path.join(
    os.path.expanduser("~"), ".nihongo_sensei", "sessions",
)

# ── Translation ────────────────────────────────────────────────
TRANSLATE_SYSTEM_PROMPT: str = (
    "You are a precise Japanese-to-English translator. "
    "Translate the following text into clear, natural English. "
    "Output ONLY the English translation — no labels, no original text, "
    "no commentary. Preserve meaning, tone, and nuance. "
    "If there are cultural references, add a very brief note in parentheses."
)

# ── Volume Meter ───────────────────────────────────────────────
WAVEFORM_BUF_LEN: int = 3200
WAVEFORM_DOWNSAMPLE: int = 4
WAVEFORM_DISPLAY_PTS: int = 280

# ── TTS (edge-tts + pygame) ───────────────────────────────────
TTS_DEFAULT_VOICE: str = "ja-JP-NanamiNeural"
TTS_DEFAULT_RATE: str = "+0%"

TTS_VOICES: dict[str, str] = {
    "Nanami 👩 (Female)":  "ja-JP-NanamiNeural",
    "Keita  👨 (Male)":    "ja-JP-KeitaNeural",
}

TTS_RATES: dict[str, str] = {
    "Very Slow":  "-50%",
    "Slow":       "-25%",
    "Normal":     "+0%",
    "Fast":       "+20%",
    "Very Fast":  "+50%",
}


# ── UI Colour Palette ──────────────────────────────────────────

class Colors:
    # high-end 2026 SaaS aesthetic (Linear/ChatGPT/Notion style)
    BG_SIDEBAR     = "#0D0D0E" # Dark sidebar
    BG_MAIN        = "#161618" # Slightly lighter main workspace
    BG_INPUT       = "#1E1E20" # TextField background
    
    BORDER_DEFAULT = "white10" # Crisp, modern dividers
    BORDER_FOCUS   = "white24"
    
    ACCENT_PRIMARY = "#6366F1" # Vibrant Indigo (Linear style)
    ACCENT_SECONDARY= "#4F46E5" # Deeper Indigo
    
    TEXT_PRIMARY   = "#F8F9FA" # Near white
    TEXT_SECONDARY = "#94A3B8" # Muted slate
    TEXT_INVERSE   = "#FFFFFF"
    
    # Message Bubbles
    USER_BUBBLE    = "#2D2D2E" # Subtle dark gray
    AI_BUBBLE      = "#1E1E2E" # Very slight purple/blue tint
    
    # Functional Colors
    SUCCESS        = "#10B981" # Emerald
    ERROR          = "#EF4444" # Rose
    WARNING        = "#F59E0B" # Amber
    
    # Legacy compatibility (keeping mapping for now)
    BG_DARK        = BG_MAIN
    BG_PRIMARY     = BG_MAIN
    BG_SECONDARY   = BG_SIDEBAR
    BG_TERTIARY    = BG_INPUT
    BORDER_SUBTLE  = BORDER_DEFAULT
    ACCENT_GREEN   = SUCCESS
    ACCENT_RED     = ERROR
    ACCENT_GOLD    = WARNING
    PTT_READY_BORDER  = "#81C784" # Even lighter for the border
    PTT_REC           = "#f44336" # Red for recording
    PTT_REC_HOVER     = "#ef5350" # Lighter red on hover
    PTT_REC_BORDER    = "#e57373" # Even lighter for the border
    PTT_PROC          = "#FFC107" # Amber for processing
    PTT_PROC_HOVER    = "#FFD54F" # Lighter amber on hover
    PTT_PROC_BORDER   = "#FFE082" # Even lighter for the border

    SEND_BTN          = "#2196F3" # Blue for send
    SEND_BTN_HOVER    = "#64B5F6" # Lighter blue on hover
    CLEAR_BTN         = "#f44336" # Red for clear
    CLEAR_BTN_HOVER   = "#ef5350" # Lighter red on hover
    HISTORY_BTN       = "#607D8B" # Blue-grey for history
    HISTORY_BTN_HOVER = "#78909C" # Lighter blue-grey on hover

    # Accents & Text
    ACCENT_GREEN      = "#81C784" # Light green for success/accent
    ACCENT_GOLD       = "#FFD54F" # Light amber for highlights
    ACCENT_RED        = "#e57373" # Light red for errors/warnings

    TEXT_PRIMARY      = "#FFFFFF" # White for primary text
    TEXT_SECONDARY    = "#B0BEC5" # Light grey for secondary text
    STATUS_BAR        = "#1a1a1a" # Same as dark background

    # Volume Meter
    METER_BG          = "#2c2c2c" # Dark grey background
    METER_BORDER      = "#4a4a4a" # Muted border
    METER_IDLE        = "#607D8B" # Blue-grey for idle
    METER_LOW         = "#4CAF50" # Green for low volume
    METER_MID         = "#FFC107" # Amber for medium volume
    METER_HIGH        = "#f44336" # Red for high volume
    METER_GLOW_LOW    = "#388E3C" # Darker green for glow
    METER_GLOW_MID    = "#FFA000" # Darker amber for glow
    METER_GLOW_HIGH   = "#D32F2F" # Darker red for glow

    # Other UI Elements
    TRANSLATE_BTN     = "#607D8B" # Blue-grey for translate
    TRANSLATE_HOVER   = "#78909C" # Lighter blue-grey on hover
    TRANSLATE_TEXT    = "#B0BEC5" # Light grey for translated text

    TTS_ON            = "#4CAF50" # Green for TTS on
    TTS_ON_HOVER      = "#66BB6A" # Lighter green on hover
    TTS_OFF           = "#607D8B" # Blue-grey for TTS off
    TTS_OFF_HOVER     = "#78909C" # Lighter blue-grey on hover
    TTS_SPEAKING      = "#2196F3" # Blue for speaking
    TTS_SPEAKING_HOVER= "#64B5F6" # Lighter blue on hover
    TTS_PLAY          = "#607D8B" # Blue-grey for play
    TTS_PLAY_HOVER    = "#78909C" # Lighter blue-grey on hover

    LANG_JP           = "#f44336" # Red for Japanese
    LANG_JP_HOVER     = "#ef5350" # Lighter red on hover
    LANG_EN           = "#2196F3" # Blue for English
    LANG_EN_HOVER     = "#64B5F6" # Lighter blue on hover
    LANG_AUTO         = "#607D8B" # Blue-grey for auto
    LANG_AUTO_HOVER   = "#78909C" # Lighter blue-grey on hover


# ═══════════════════════════════════════════════════════════════
#  70/30 RATIO INSTRUCTIONS
# ═══════════════════════════════════════════════════════════════

RATIO_INSTRUCTION: str = (
    "## Your Persona: The 70/30 Language Partner\n"
    "You are not a robot; you are a language learning partner. Your goal is to make learning feel like a natural conversation. Follow this simple, effective structure for every single message:\n\n"
    "**1. The Immersion (about 70% of your message):**\n"
    "   Start with a short story, a fun scenario, or a simple description in Japanese. This is the comprehensible input. It should be engaging and just a little bit challenging (i+1), using context to make it understandable without needing a direct translation.\n\n"
    "**2. The Turn (about 30% of your message):**\n"
    "   This is where you hand the conversation back to the learner. End EVERY message with a clear, simple task that prompts them to respond in Japanese. It could be a direct question, a fill-in-the-blank, or a choice. The key is to always give them a reason to reply.\n\n"
    "Think of it as a friendly rally in a game of tennis. You serve the ball with a story, and they return it by answering your question. Keep the conversation flowing!"
)

RATIO_REMINDER: str = (
    "Quick check-in: Remember our 70/30 flow! Start with a bit of a story or context in Japanese, then end with a simple question or task to keep the conversation going. Your turn!"
)


def build_ratio_instruction(japanese_pct: int) -> str:
    """Return a ratio instruction string for the given Japanese percentage.

    *japanese_pct* is an integer 50–100 representing how much of the
    response should be Japanese.  The remainder is English explanation /
    output task.
    """
    english_pct = 100 - japanese_pct
    return (
        f"## CRITICAL — {japanese_pct}/{english_pct} Language Ratio Rule\n"
        f"Every single response you write MUST follow this structure:\n\n"
        f"**{japanese_pct}% — Comprehensible Input (Japanese):**\n"
        f"  A short story, scenario, description, or contextual passage "
        f"written in Japanese at the learner's level. Engaging, natural, "
        f"and slightly above their current ability (i+1 comprehensible input).\n\n"
        f"**{english_pct}% — Output Task / English Support:**\n"
        f"  End EVERY message with a specific, actionable task that forces "
        f"the learner to produce language — a direct question, fill-in-the-blank, "
        f"or choice that requires a Japanese response. "
        f"{'Use more English explanation to support the learner.' if japanese_pct <= 60 else 'Keep English minimal.'}\n\n"
        f"Format: input first, then the task. The task must flow from the input."
    )


def build_ratio_reminder(japanese_pct: int) -> str:
    english_pct = 100 - japanese_pct
    return (
        f"REMINDER: Your response MUST be approximately {japanese_pct}% Japanese "
        f"comprehensible input and {english_pct}% output task / English support. "
        f"Always end with a concrete task for the learner."
    )


# ═══════════════════════════════════════════════════════════════
#  A0 LEVEL CONSTRAINTS
# ═══════════════════════════════════════════════════════════════

_A0_CONSTRAINTS: dict[str, str] = {
    "A0.1": (
        "## A0.1 Constraints (0-100 words)\n"
        "The learner knows FEWER than 100 Japanese words. This is their "
        "very first exposure.\n\n"
        "STRICT RULES:\n"
        "• Use ONLY these categories of words: greetings (こんにちは, "
        "おはよう, こんばんは), yes/no (はい, いいえ), numbers いち-じゅう, "
        "basic nouns (ねこ, いぬ, みず, ごはん, ほん), colours (あか, あお, しろ), "
        "and 5-10 common verbs in ます form.\n"
        "• Write EVERYTHING in hiragana. ZERO kanji.\n"
        "• ALWAYS show romaji in parentheses: e.g. ねこ (neko).\n"
        "• The 70% input section must be 2-3 very short sentences "
        "using heavy repetition of the SAME words.\n"
        "• The 30% output task must require only a ONE-WORD response.\n"
        "• Example tasks: 'What is this? → ねこ', 'Say yes → はい', "
        "'What colour? → あか'.\n"
        "• NEVER ask for a full sentence — only single words.\n"
        "• Repeat new words at least 3 times across input and task.\n"
        "• Celebrate every attempt with enthusiasm."
    ),
    "A0.2": (
        "## A0.2 Constraints (100-250 words)\n"
        "The learner knows approximately 100-250 words. They can read "
        "hiragana and katakana and know basic greetings.\n\n"
        "STRICT RULES:\n"
        "• Use only hiragana and katakana. NO kanji.\n"
        "• Add romaji for any word introduced in the last few messages.\n"
        "• The 70% input section should be a simple 3-4 sentence "
        "mini-story using familiar vocabulary with 1-2 new words.\n"
        "• The 30% output task MUST be a BINARY CHOICE question.\n"
        "• Example task formats:\n"
        "  — 'Aですか、Bですか？' (Is it A or B?)\n"
        "  — 'はいですか、いいえですか？' (Yes or no?)\n"
        "  — 'Which one: ねこ or いぬ?'\n"
        "• NEVER ask open-ended questions — always give exactly 2 options.\n"
        "• Build vocabulary around: food, animals, family, daily objects, "
        "weather, and basic adjectives (おおきい, ちいさい, いい, わるい).\n"
        "• Use です/ます exclusively."
    ),
    "A0.3": (
        "## A0.3 Constraints (250-500 words)\n"
        "The learner knows approximately 250-500 words. They can form "
        "very basic sentences and understand simple questions.\n\n"
        "STRICT RULES:\n"
        "• Use hiragana and katakana primarily. Introduce only the "
        "simplest kanji (一, 二, 三, 人, 大, 小) WITH furigana.\n"
        "• The 70% input section should be a 4-6 sentence scenario "
        "or mini-story about daily life.\n"
        "• The 30% output task MUST require a simple "
        "Subject-Verb-Object (SVO) sentence pattern.\n"
        "• Example task formats:\n"
        "  — 'What do you eat? → わたしは ___を たべます'\n"
        "  — 'Where do you go? → わたしは ___に いきます'\n"
        "  — 'Use this pattern: [person]は [thing]が すきです'\n"
        "• Always provide the sentence PATTERN/TEMPLATE the learner "
        "should use, with a blank for them to fill.\n"
        "• Limit to these grammar patterns: XはYです, XをVます, "
        "XにいきますXがすきです, Xがあります/います.\n"
        "• Vocabulary domains: daily routines, school/work, hobbies, "
        "shopping, transport, basic time expressions."
    ),
}


# ═══════════════════════════════════════════════════════════════
#  LEVEL GUIDANCE (all levels)
# ═══════════════════════════════════════════════════════════════

_LEVEL_GUIDANCE: dict[str, str] = {
    **_A0_CONSTRAINTS,
    "Beginner": (
        "The learner knows virtually NO Japanese — this is day one. "
        "Communicate PRIMARILY in English. Introduce only 1-2 new "
        "Japanese words or short phrases per message. Write ALL "
        "Japanese exclusively in hiragana and ALWAYS provide romaji "
        "in parentheses right after — e.g. こんにちは (konnichiwa). "
        "Do NOT use any kanji at all. Focus on:\n"
        "  • Greetings: こんにちは、おはよう、こんばんは\n"
        "  • Self-introduction: わたしは…です\n"
        "  • Yes/No: はい / いいえ\n"
        "  • Polite phrases: ありがとう、すみません、おねがいします\n"
        "  • Numbers 1-10: いち、に、さん…\n"
        "  • Basic objects the learner can see around them\n"
        "Keep sentences extremely short (2-4 words). Celebrate every "
        "small success enthusiastically. If the learner attempts any "
        "Japanese at all, praise them warmly before gently correcting.\n\n"
        "For the 70% input: use mostly English with embedded Japanese "
        "words highlighted. For the 30% task: ask the learner to "
        "repeat a single word or very short phrase."
    ),
    "Elementary": (
        "The learner has finished the 'absolute beginner' stage. They "
        "can read hiragana and katakana, know basic greetings, numbers "
        "1-20, and a handful of everyday words (~50-100 vocabulary). "
        "They are NOT yet at N5.\n\n"
        "Guidelines:\n"
        "  • Write Japanese in hiragana/katakana only — NO kanji yet.\n"
        "  • Always add romaji in parentheses for new or tricky words.\n"
        "  • Use です/ます forms exclusively.\n"
        "  • Build simple sentences: [subject]は [object]が すきです。\n"
        "  • Introduce one new grammar point per 2-3 messages.\n"
        "  • Use about 50% Japanese / 50% English in each reply.\n"
        "  • Teach: colours, animals, food, family words, days of the week, "
        "    basic verbs (たべます、のみます、いきます、みます).\n"
        "  • When the learner speaks broken Japanese, gently restate the "
        "    correct version and explain in English."
    ),
    "N5": (
        "Use only the most basic vocabulary and です/ます sentence patterns. "
        "Write primarily in hiragana, introducing only the simplest kanji "
        "(一 二 三 人 日 大 etc.) and always place furigana in parentheses. "
        "Keep every sentence short and clear."
    ),
    "N4": (
        "Use elementary vocabulary and grammar: て-form, ない-form, potential "
        "form, basic compound sentences. Use N5+N4 level kanji; add furigana "
        "in parentheses for any kanji above N4."
    ),
    "N3": (
        "Use intermediate vocabulary, passive form, causative form, various "
        "conditional forms, and complex sentence connectors. Write common "
        "kanji freely; only add furigana for uncommon readings."
    ),
    "N2": (
        "Use upper-intermediate vocabulary, nuanced grammar (ものの, にもかかわらず, "
        "etc.), and register switching between formal and informal. Use kanji "
        "freely without furigana unless the reading is unusual."
    ),
    "N1": (
        "Use advanced vocabulary, four-character idioms (四字熟語), literary "
        "grammar, and keigo (敬語). Speak as naturally as with a native "
        "speaker, including cultural nuance."
    ),
    "Any Level": (
        "Start at a moderate level and dynamically adapt your vocabulary and "
        "grammar complexity to match the user's demonstrated proficiency."
    ),
}


# ═══════════════════════════════════════════════════════════════
#  SYSTEM PROMPT BUILDER
# ═══════════════════════════════════════════════════════════════

def get_system_prompt(
    level: str,
    japanese_pct: int = 70,
    session_summary: str = "",
    vocab_review: str = "",
) -> str:
    """Return a detailed system prompt tuned to *level*.

    Parameters
    ----------
    level : str
        JLPT / custom level string.
    japanese_pct : int
        Percentage of the response that should be Japanese (50-100).
    session_summary : str
        Optional summary of the previous session to inject.
    vocab_review : str
        Optional spaced-repetition words to review today.
    """
    guidance = _LEVEL_GUIDANCE.get(level, _LEVEL_GUIDANCE["Any Level"])

    if level in ("N5", "N4", "N3", "N2", "N1"):
        level_label = f"JLPT {level}"
    elif level == "Beginner":
        level_label = "Absolute Beginner (pre-JLPT, day one)"
    elif level == "Elementary":
        level_label = "Elementary (between Beginner and JLPT N5)"
    elif level.startswith("A0"):
        word_ranges = {
            "A0.1": "0-100 words",
            "A0.2": "100-250 words",
            "A0.3": "250-500 words",
        }
        rng = word_ranges.get(level, "sub-500 words")
        level_label = f"{level} — Sub-beginner ({rng})"
    else:
        level_label = level

    ratio_block = build_ratio_instruction(japanese_pct)
    english_pct = 100 - japanese_pct

    parts = [
        f"You are **Sensei (先生)**, a warm, friendly, and encouraging "
        f"Japanese-language tutor.\n"
        f"The learner is studying at the **{level_label}** level.\n",
        f"## Language guidelines\n{guidance}\n",
        ratio_block,
        f"\n## General conversation rules\n"
        f"1. ALWAYS follow the {japanese_pct}/{english_pct} language ratio above.\n"
        f"2. When the learner makes a mistake, gently correct it and give a "
        f"   one-line explanation. Use 「wrong」→「correct」 format for corrections.\n"
        f"3. Encourage the learner to use more Japanese each turn.\n"
        f"4. Weave in useful vocabulary or grammar organically.\n"
        f"5. Use emoji sparingly to keep the tone friendly.\n"
        f"6. If the learner writes entirely in English, reply partly in "
        f"   Japanese at their level to coax them into practising.\n"
        f"7. NEVER end a message without a concrete task or question "
        f"   for the learner to respond to.",
    ]

    if session_summary:
        parts.append(f"\n{session_summary}")
    if vocab_review:
        parts.append(f"\n{vocab_review}")

    return "\n\n".join(parts)
