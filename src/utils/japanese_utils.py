"""
japanese_utils.py — Utilities for Japanese text processing, cleaning, 
and number conversion. Extracted from ai_engine.py for maintainability.
"""

import re

_JP_NUMBER_MAP: list[tuple[str, str]] = [
    ("100000", "じゅうまん"),
    ("10000",  "いちまん"),
    ("1000",   "せん"),
    ("100",    "ひゃく"),
    ("20",     "にじゅう"),
    ("30",     "さんじゅう"),
    ("40",     "よんじゅう"),
    ("50",     "ごじゅう"),
    ("60",     "ろくじゅう"),
    ("70",     "ななじゅう"),
    ("80",     "はちじゅう"),
    ("90",     "きゅうじゅう"),
    ("11",     "じゅういち"),
    ("12",     "じゅうに"),
    ("13",     "じゅうさん"),
    ("14",     "じゅうよん"),
    ("15",     "じゅうご"),
    ("16",     "じゅうろく"),
    ("17",     "じゅうなな"),
    ("18",     "じゅうはち"),
    ("19",     "じゅうきゅう"),
    ("10",     "じゅう"),
    ("0",      "ゼロ"),
    ("1",      "いち"),
    ("2",      "に"),
    ("3",      "さん"),
    ("4",      "よん"),
    ("5",      "ご"),
    ("6",      "ろく"),
    ("7",      "なな"),
    ("8",      "はち"),
    ("9",      "きゅう"),
]

# Patterns for text processing
_STRICT_JP_CLEANER = re.compile(
    r"[^a-zA-Z\d\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\u3400-\u4DBF\u3000-\u303F！？、。：；「」\s]"
)
_STRIP_ALPHABET = re.compile(r"[a-zA-Z]")


def replace_digits_with_japanese(text: str) -> str:
    """Converts ASCII digits to Japanese number readings."""
    if not re.search(r"\d", text):
        return text

    def _num_to_jp(match: re.Match) -> str:
        result = ""
        remaining = match.group(0)
        while remaining:
            matched = False
            for arabic, japanese in _JP_NUMBER_MAP:
                if remaining.startswith(arabic):
                    result += japanese
                    remaining = remaining[len(arabic):]
                    matched = True
                    break
            if not matched:
                result += remaining[0]
                remaining = remaining[1:]
        return result

    return re.sub(r"\d+", _num_to_jp, text)


def post_process_japanese(text: str) -> str:
    """Cleans up raw Japanese text output from STT or LLM."""
    # 1. Clean up weird characters and force remove all alphabet (English) characters
    text = _STRIP_ALPHABET.sub("", text)
    text = _STRICT_JP_CLEANER.sub("", text)
    
    # 2. Process numbers
    text = replace_digits_with_japanese(text)
    
    # 3. Clean punctuation and spaces
    text = re.sub(r"([。、！？])\1+", r"\1", text)
    text = re.sub(
        r"([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF])"
        r"\s+"
        r"([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF])",
        r"\1\2",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text
