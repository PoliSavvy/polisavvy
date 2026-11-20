"""Automatic checks that run on every AI-written item before it can publish.

These catch the common ways a summary drifts from neutral. They are a
safety net, not a replacement for the human review of sensitive items.
"""
from __future__ import annotations

import re

LOADED_WORDS = [
    "slam", "slams", "blast", "blasts", "radical", "extreme", "extremist", "controversial",
    "disastrous", "disaster", "landmark", "historic", "finally", "sneaky", "rammed",
    "so-called", "shocking", "outrageous", "reckless", "draconian", "woke", "failed government",
]
SENSITIVE_KEYWORDS = [
    "assisted dying", "medical assistance in dying", "maid", "abortion", "euthanasia",
    "immigration", "refugee", "asylum", "indigenous", "first nations", "métis", "metis", "inuit",
    "religio", "gender", "transgender", "firearm", "gun", "police", "rcmp", "criminal code",
    "terror", "national security", "foreign interference", "csis",
]
LIMITS = {"headline": 14, "short_title": 9}


def _words(s: str) -> int:
    return len(re.findall(r"\S+", s or ""))


def lint(item: dict) -> list[str]:
    """Return a list of style or neutrality problems (empty means clean)."""
    problems = []
    fields = {k: item.get(k) or "" for k in ("headline", "short_title", "what", "you", "sides_note")}
    for s in item.get("sides", []):
        fields[f"side:{s.get('who', '')}"] = s.get("text", "")
    if item.get("poll"):
        fields["poll"] = f"{item['poll'].get('q', '')} {item['poll'].get('reveal', '')}"
    for name, text in fields.items():
        low = text.lower()
        if "\u2014" in text:
            problems.append(f"{name}: contains an em dash")
        for w in LOADED_WORDS:
            if re.search(rf"\b{re.escape(w)}\b", low):
                problems.append(f"{name}: loaded word '{w}'")
        if re.search(r"\b(yesterday|today|tomorrow|this week|last week)\b", low) and name in ("what", "you"):
            problems.append(f"{name}: relative date, use the actual date")
    for k, n in LIMITS.items():
        if _words(item.get(k, "")) > n:
            problems.append(f"{k}: over {n} words")
    if item.get("headline", "").strip().endswith("?"):
        problems.append("headline: no question headlines")
    sides = item.get("sides", [])
    if len(sides) >= 2:
        lens = [_words(s.get("text", "")) for s in sides]
        if max(lens) > 2.5 * max(1, min(lens)):
            problems.append("sides: lengths are unbalanced, give each side similar space")
    poll = item.get("poll") or {}
    if poll and not str(poll.get("reveal", "")).startswith("**What actually happen"):
        problems.append("poll.reveal: must start with **What actually happened:** or **What actually happens:**")
    return problems


def is_sensitive(item: dict, raw: dict | None = None) -> bool:
    """Rule-based sensitivity check. True means a human must approve it."""
    if item.get("sensitive"):
        return True
    blob = " ".join([
        item.get("headline", ""), item.get("what", ""), item.get("you", ""),
        (raw or {}).get("official_title", ""), (raw or {}).get("text", ""),
    ]).lower()
    if any(k in blob for k in SENSITIVE_KEYWORDS):
        return True
    # party claims with numbers in them are easy to get wrong
    return any(re.search(r"\d", s.get("text", "")) for s in item.get("sides", []))
