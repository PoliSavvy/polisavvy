"""Turn a raw record from a connector into a plain-language site item.

The style guide (docs/STYLE_GUIDE.md) is sent as the model's instructions,
so the writing rules live in one human-readable place.

Every result goes through three gates:
  1. schema validation (pipeline/schema.py)
  2. neutrality lint (pipeline/neutrality.py), with one automatic rewrite try
  3. sensitivity check: sensitive items are saved as review="pending"
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .neutrality import is_sensitive, lint
from .schema import validate_item

ROOT = Path(__file__).resolve().parent.parent
STYLE_GUIDE = (ROOT / "docs/STYLE_GUIDE.md").read_text()
MODEL = os.environ.get("PP_MODEL", "claude-sonnet-5-5")

ITEM_SHAPE = {
    "id": "same as input id",
    "kind": "law | vote | debate",
    "status": "Became law | Passed a vote | Failed a vote | Being debated | Introduced",
    "bill": "e.g. C-41, or a short name like 'Budget 2026'",
    "category": "1 to 3 word section label, e.g. Health",
    "topics": ["1 to 3 topic keys"],
    "headline": "max 14 words",
    "short_title": "max 9 words",
    "what_label": "What it does | What happened",
    "what": "1 to 2 sentences",
    "stage": {"done": "number of completed steps 0-6 of Introduced, First vote, Committee, Final vote, Senate, Law", "current": "true if the next step is under way"},
    "you_label": "What it means for you | Why it matters | What happens next",
    "you": "1 to 2 sentences",
    "sides": [{"who": "party or 'Supporters (government)'", "text": "one sentence"}],
    "sides_note": "optional one sentence or null",
    "poll": {"q": "Your take: ...", "reveal": "**What actually happened:** ..."},
    "source": {"label": "Read the bill on LEGISinfo", "url": "official https link from input"},
    "sensitive": "true if it touches anything on the sensitive list",
}


def _prompt(raw: dict, feedback: list[str] | None = None) -> str:
    msg = (
        "Write one PoliSavvy item from this official record. Use only facts in the record.\n\n"
        f"RECORD:\n{json.dumps(raw, ensure_ascii=False, indent=1)}\n\n"
        f"Return only a JSON object with exactly these fields:\n{json.dumps(ITEM_SHAPE, indent=1)}\n"
        "Use stage null if this is not a bill. Use poll null if a yes/no question makes no sense."
    )
    if feedback:
        msg += "\n\nYour previous draft broke these rules. Fix them:\n- " + "\n- ".join(feedback)
    return msg


def _parse(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("model did not return JSON")
    return json.loads(m.group(0))


class Summarizer:
    def __init__(self, client=None, model: str = MODEL):
        if client is None:
            import anthropic  # imported lazily so tests run without a key
            client = anthropic.Anthropic()
        self.client = client
        self.model = model

    def _ask(self, prompt: str) -> dict:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=1500,
            system=STYLE_GUIDE,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse(resp.content[0].text)

    def summarize(self, raw: dict) -> dict:
        item = self._ask(_prompt(raw))
        problems = lint(item) + validate_item(item)
        if problems:  # one rewrite attempt with the exact problems listed
            item = self._ask(_prompt(raw, problems))
            problems = lint(item) + validate_item(item)
        item["id"] = raw["id"]
        item["source"] = item.get("source") or {}
        item["source"]["url"] = raw["url"]  # never trust a model-written link
        item["source"].setdefault("label", "See the official record")
        item["lint"] = problems
        item["review"] = "pending" if (problems or is_sensitive(item, raw)) else "auto"
        return item
