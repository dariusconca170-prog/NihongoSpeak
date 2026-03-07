"""
session_memory.py — Loads the most recent session and produces a
brief summary string to inject into the system prompt on startup.

The summary is built locally from the session JSON without any
additional API calls.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import config


def _jp_ratio(text: str) -> float:
    """Rough Japanese character ratio in *text*."""
    if not text:
        return 0.0
    jp = len(re.findall(r"[\u3040-\u9FFF]", text))
    return jp / max(len(text), 1)


def build_previous_session_summary(history_dir: Optional[str] = None) -> str:
    """Return a short summary of the most recently saved session,
    or an empty string if no prior session exists."""
    base = Path(history_dir or config.HISTORY_DIR)
    if not base.exists():
        return ""

    files = sorted(base.glob("session_*.json"), reverse=True)
    if not files:
        return ""

    try:
        session = json.loads(files[0].read_text(encoding="utf-8"))
    except Exception:
        return ""

    messages = session.get("messages", [])
    if not messages:
        return ""

    level = session.get("level", "unknown")
    started = session.get("started", "")[:16].replace("T", " ")
    msg_count = len(messages)

    # Collect the last few user messages as topic indicators
    user_msgs = [
        m["content"][:80]
        for m in messages
        if m.get("role") == "user"
    ][-5:]

    # Collect any assistant corrections (lines with → or 正しくは)
    corrections: list[str] = []
    for m in messages:
        if m.get("role") == "assistant":
            for line in m["content"].splitlines():
                if "→" in line or "正しくは" in line or "✗" in line:
                    corrections.append(line.strip()[:120])
            if len(corrections) >= 5:
                break

    lines = [
        "## Previous Session Summary",
        f"Date: {started}  |  Level: {level}  |  Messages: {msg_count}",
    ]
    if user_msgs:
        lines.append("Recent topics from the learner:")
        for u in user_msgs:
            lines.append(f"  - {u}")
    if corrections:
        lines.append("Corrections made last session (reinforce these):")
        for c in corrections[:5]:
            lines.append(f"  - {c}")
    lines.append(
        "Continue naturally from this context. "
        "If the learner returns to a topic from last session, acknowledge it briefly."
    )
    return "\n".join(lines)
