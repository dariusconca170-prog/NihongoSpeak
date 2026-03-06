"""
pronunciation_scorer.py — Phoneme/mora-level pronunciation scoring.

Compares the Whisper transcription against expected Japanese text
using mora segmentation and edit-distance similarity.  No external
API required — runs entirely offline.

Returns a ``PronunciationResult`` with:
  - overall_score   float 0.0-1.0
  - mora_scores     list of (mora, status) where status is
                    "correct", "unclear", or "missing"
  - feedback        human-readable summary string
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


# ── Katakana → Hiragana normalisation ───────────────────────────

def _to_hiragana(text: str) -> str:
    """Convert katakana to hiragana for comparison."""
    result = []
    for ch in text:
        cp = ord(ch)
        # Full-width katakana → hiragana offset
        if 0x30A1 <= cp <= 0x30F6:
            result.append(chr(cp - 0x60))
        else:
            result.append(ch)
    return "".join(result)


def _normalize(text: str) -> str:
    """Lowercase, strip spaces, convert kata→hira, strip non-Japanese ASCII."""
    text = unicodedata.normalize("NFKC", text)
    text = _to_hiragana(text)
    # Remove all non-Japanese characters except digits
    text = re.sub(r"[^\u3040-\u309F\u4E00-\u9FFF\d]", "", text)
    return text


# ── Mora segmentation ────────────────────────────────────────────

# Two-character morae: きゃ きゅ きょ etc.
_DIGRAPHS = re.compile(
    r"[きぎしじちぢにひびぴみりゐゑ][ゃゅょ]|[つ][ぁぃぇぉ]|っ[^]"
)

def _segment_mora(text: str) -> list[str]:
    """Split hiragana text into mora units."""
    mora: list[str] = []
    i = 0
    while i < len(text):
        # Check for two-char mora (small ya/yu/yo combo)
        if i + 1 < len(text) and text[i + 1] in "ゃゅょぁぃぅぇぉ":
            mora.append(text[i: i + 2])
            i += 2
        else:
            mora.append(text[i])
            i += 1
    return mora


# ── Levenshtein distance ─────────────────────────────────────────

def _levenshtein(a: list[str], b: list[str]) -> int:
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[:]
        dp[0] = i
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev[j - 1] + cost)
    return dp[n]


# ── Result dataclass ─────────────────────────────────────────────

@dataclass
class PronunciationResult:
    overall_score: float                       # 0.0 – 1.0
    mora_scores: list[tuple[str, str]] = field(default_factory=list)
    # each tuple: (mora_text, "correct" | "unclear" | "missing")
    feedback: str = ""
    expected_text: str = ""
    heard_text: str = ""


# ── Main scorer ──────────────────────────────────────────────────

def score_pronunciation(
    expected: str,
    heard: str,
    *,
    min_length: int = 2,
) -> PronunciationResult:
    """Compare *heard* (Whisper transcript) against *expected* Japanese text.

    Parameters
    ----------
    expected : str
        The Japanese text the learner was supposed to say.
    heard : str
        What Whisper transcribed from the learner's speech.
    min_length : int
        Minimum mora count below which scoring is skipped (returns None score).

    Returns
    -------
    PronunciationResult
        Populated with score and per-mora feedback.
    """
    exp_norm = _normalize(expected)
    heard_norm = _normalize(heard)

    exp_mora = _segment_mora(exp_norm)
    heard_mora = _segment_mora(heard_norm)

    if len(exp_mora) < min_length:
        # Too short to score meaningfully
        return PronunciationResult(
            overall_score=1.0,
            mora_scores=[(m, "correct") for m in exp_mora],
            feedback="",
            expected_text=expected,
            heard_text=heard,
        )

    # Edit distance gives us a global similarity
    dist = _levenshtein(exp_mora, heard_mora)
    max_len = max(len(exp_mora), len(heard_mora), 1)
    score = max(0.0, 1.0 - dist / max_len)

    # Build per-mora alignment using simple LCS-based approach
    mora_scores: list[tuple[str, str]] = []
    i = j = 0
    # Greedy alignment
    while i < len(exp_mora):
        em = exp_mora[i]
        if j < len(heard_mora) and heard_mora[j] == em:
            mora_scores.append((em, "correct"))
            i += 1
            j += 1
        elif j < len(heard_mora) and j + 1 < len(heard_mora) and heard_mora[j + 1] == em:
            # skip one extra heard mora (insertion)
            mora_scores.append((em, "correct"))
            i += 1
            j += 2
        else:
            # Check if mora appears nearby in heard (substitution / unclear)
            nearby = heard_mora[j: j + 3] if j < len(heard_mora) else []
            if em in nearby:
                mora_scores.append((em, "unclear"))
            else:
                mora_scores.append((em, "missing"))
            i += 1
            j += 1

    # Feedback string
    n_correct = sum(1 for _, s in mora_scores if s == "correct")
    n_unclear = sum(1 for _, s in mora_scores if s == "unclear")
    n_missing = sum(1 for _, s in mora_scores if s == "missing")

    if score >= 0.9:
        summary = "Excellent pronunciation!"
    elif score >= 0.75:
        summary = "Good — a few mora to polish."
    elif score >= 0.5:
        summary = "Needs practice — focus on the highlighted mora."
    else:
        summary = "Keep practising — try saying it slowly."

    parts = [f"{summary}  ({score * 100:.0f}%)"]
    if n_unclear:
        unclear_list = [m for m, s in mora_scores if s == "unclear"]
        parts.append(f"Unclear: {' · '.join(unclear_list)}")
    if n_missing:
        missing_list = [m for m, s in mora_scores if s == "missing"]
        parts.append(f"Missing: {' · '.join(missing_list)}")

    return PronunciationResult(
        overall_score=score,
        mora_scores=mora_scores,
        feedback="  |  ".join(parts),
        expected_text=expected,
        heard_text=heard,
    )


def format_score_badge(result: PronunciationResult) -> str:
    """Return a compact one-line badge string for display in the GUI."""
    pct = int(result.overall_score * 100)
    if pct >= 90:
        icon = "🟢"
    elif pct >= 70:
        icon = "🟡"
    else:
        icon = "🔴"
    return f"{icon} Pronunciation: {pct}%  —  {result.feedback}"
