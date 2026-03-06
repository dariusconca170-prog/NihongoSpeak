"""
vocab_tracker.py — Spaced repetition vocabulary tracker.

Stores words the user struggles with and resurfaces them on a
simple interval schedule: day 1, day 3, day 7.

Data is written to ~/.nihongo_sensei/vocab.json.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import config

# Intervals in days for each SRS level (0=new, 1=seen once, 2=seen twice, …)
_SRS_INTERVALS: list[int] = [1, 3, 7, 14, 30]


class VocabTracker:
    """Persistent spaced-repetition store for difficult vocabulary."""

    def __init__(self, path: Optional[str] = None) -> None:
        base = Path(config.HISTORY_DIR).parent
        base.mkdir(parents=True, exist_ok=True)
        self._path = Path(path) if path else base / "vocab.json"
        self._data: dict[str, dict] = {}
        self._load()

    # ── Persistence ─────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if self._path.exists():
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data = raw
        except Exception:
            self._data = {}

    def _save(self) -> None:
        try:
            self._path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    # ── Public API ──────────────────────────────────────────────

    def mark_struggle(self, word: str, reading: str = "", meaning: str = "") -> None:
        """Record that the user struggled with *word*."""
        today = date.today().isoformat()
        if word not in self._data:
            self._data[word] = {
                "reading": reading,
                "meaning": meaning,
                "level": 0,
                "struggles": 0,
                "last_seen": today,
                "next_review": today,
                "added": today,
            }
        entry = self._data[word]
        entry["struggles"] = entry.get("struggles", 0) + 1
        entry["last_seen"] = today
        # Reset to level 0 on a struggle
        entry["level"] = 0
        interval = _SRS_INTERVALS[0]
        next_date = date.today() + timedelta(days=interval)
        entry["next_review"] = next_date.isoformat()
        if reading:
            entry["reading"] = reading
        if meaning:
            entry["meaning"] = meaning
        self._save()

    def mark_correct(self, word: str) -> None:
        """Advance the SRS level for *word* after a correct answer."""
        if word not in self._data:
            return
        entry = self._data[word]
        level = min(entry.get("level", 0) + 1, len(_SRS_INTERVALS) - 1)
        entry["level"] = level
        entry["last_seen"] = date.today().isoformat()
        interval = _SRS_INTERVALS[level]
        next_date = date.today() + timedelta(days=interval)
        entry["next_review"] = next_date.isoformat()
        self._save()

    def due_today(self) -> list[dict]:
        """Return vocab items due for review today or overdue."""
        today = date.today().isoformat()
        due = []
        for word, entry in self._data.items():
            if entry.get("next_review", today) <= today:
                due.append({"word": word, **entry})
        due.sort(key=lambda x: x.get("next_review", ""))
        return due

    def all_words(self) -> list[dict]:
        """Return all tracked words sorted by struggle count descending."""
        items = [{"word": w, **e} for w, e in self._data.items()]
        items.sort(key=lambda x: x.get("struggles", 0), reverse=True)
        return items

    def get_review_prompt(self) -> str:
        """Return an instruction string to inject into the system prompt
        listing words due for review today."""
        due = self.due_today()
        if not due:
            return ""
        words = ", ".join(
            f"{item['word']}"
            + (f" ({item['reading']})" if item.get("reading") else "")
            for item in due[:10]
        )
        return (
            f"\n\n## Spaced Repetition — Words to Review Today\n"
            f"The learner has struggled with these words recently. "
            f"Weave them naturally into your responses today: {words}"
        )

    def extract_and_log(self, ai_response: str, user_response: str) -> list[str]:
        """Best-effort: extract Japanese words flagged as corrections in
        the AI response and log them as struggles.

        Looks for patterns like 「X」→「Y」 or correction markers.
        Returns the list of words logged.
        """
        import re
        logged: list[str] = []

        # Pattern: 「wrong」→「correct」 or ✗word → ✓word
        correction_patterns = [
            r"「([^」]+)」\s*[→➜]\s*「([^」]+)」",
            r"✗\s*([\u3040-\u9FFF]+)\s*[→➜]\s*✓\s*([\u3040-\u9FFF]+)",
        ]
        for pat in correction_patterns:
            for m in re.finditer(pat, ai_response):
                wrong = m.group(1)
                if wrong and re.search(r"[\u3040-\u9FFF]", wrong):
                    self.mark_struggle(wrong)
                    logged.append(wrong)
        return logged
