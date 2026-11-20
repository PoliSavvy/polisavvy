"""Draft tomorrow's Daily Savvy from the last week of published items.

The quiz is always saved as review="pending": it only goes live after a
human approves it (one tap, see docs/REVIEW.md).
"""
from __future__ import annotations

import json
from pathlib import Path

from .schema import validate_daily5
from .summarize import MODEL, STYLE_GUIDE, _parse

SHAPE = {
    "questions": [
        {"type": "Passed or failed? | Higher or lower | Which bill is this? | Where in the world? | Guess the number",
         "q": "question", "opts": ["2 to 4 options"], "a": "index of the right option", "hl": "true for 2-option questions",
         "why": "one sentence explaining the answer", "link": "#today | #pm | #lobbying | #daily"},
        {"type": "Put it in order", "q": "instruction", "order": ["steps in the correct order"], "why": "...", "link": "..."},
    ]
}


def draft_daily5(client, items: list[dict], date: str, model: str = MODEL) -> dict:
    facts = [{k: i.get(k) for k in ("id", "bill", "status", "headline", "what", "you")} for i in items]
    prompt = (
        "Write the Daily Savvy quiz from these published items. Exactly 5 questions, mixed types, "
        "at most one 'Put it in order'. Facts only.\n\n"
        f"ITEMS:\n{json.dumps(facts, ensure_ascii=False, indent=1)}\n\n"
        f"Return only JSON shaped like:\n{json.dumps(SHAPE, indent=1)}"
    )
    resp = client.messages.create(model=model, max_tokens=2000, system=STYLE_GUIDE,
                                  messages=[{"role": "user", "content": prompt}])
    quiz = {"date": date, "review": "pending", **_parse(resp.content[0].text)}
    problems = validate_daily5(quiz)
    if problems:
        raise ValueError("Daily Savvy draft failed checks: " + "; ".join(problems))
    return quiz


def save(quiz: dict, root: Path) -> Path:
    p = root / "data/daily5" / f"{quiz['date']}.json"
    p.write_text(json.dumps(quiz, ensure_ascii=False, indent=1))
    return p
