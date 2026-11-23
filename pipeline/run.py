"""One pipeline run: fetch, summarize, merge into today's edition, build.

    python -m pipeline.run                  # live connectors (once built)
    python -m pipeline.run --offline        # fixture records from data/raw
    python -m pipeline.run --offline --no-ai  # no API key needed, items held for review

Safe to run every 30 minutes: records already in the edition are skipped,
so each run only does work for genuinely new events.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path

from .connectors.base import check
from .connectors.live import merge_bill_votes, pm_section
from .connectors.sources import LIVE, PM, FixtureConnector

ROOT = Path(__file__).resolve().parent.parent
TZ_OFFSET = dt.timedelta(hours=-5)  # Ottawa standard time; good enough for picking the edition date


def today() -> str:
    return (dt.datetime.now(dt.timezone.utc) + TZ_OFFSET).date().isoformat()


def load_edition(date: str) -> dict:
    p = ROOT / "data/editions" / f"{date}.json"
    if p.exists():
        return json.loads(p.read_text())
    prev = sorted((ROOT / "data/editions").glob("*.json"))
    base = json.loads(prev[-1].read_text()) if prev else {}
    # A new day starts with yesterday's PM and lobbying sections until connectors refresh them.
    return {"date": date, "tldr": [], "items": [], "also_law": [],
            "pm": base.get("pm"), "lobbying": base.get("lobbying"), "extras_for_email": []}


def fact_only(raw: dict) -> dict:
    """Fallback when no AI is available: a bare, clearly-sourced fact, held for review."""
    return {
        "id": raw["id"], "kind": raw["kind_hint"], "status": raw.get("result", "Update"),
        "bill": raw.get("bill", raw["official_title"][:20]), "category": "Update", "topics": ["economy"],
        "headline": raw["official_title"], "short_title": raw["official_title"][:60],
        "what_label": "What happened", "what": raw["text"][:400],
        "stage": None, "you_label": "Why it matters", "you": "Plain-language summary coming soon.",
        "sides": [], "sides_note": None, "poll": None,
        "source": {"label": "See the official record", "url": raw["url"]},
        "sensitive": True, "review": "pending",
    }


def run(date: str, offline: bool, use_ai: bool, since_days: int = 2, force_quiz: bool = False) -> dict:
    ed = load_edition(date)
    have = {i["id"] for i in ed["items"]}
    since = (dt.date.fromisoformat(date) - dt.timedelta(days=since_days)).isoformat()
    connectors = [FixtureConnector()] if offline else LIVE
    summarizer = None
    if use_ai and os.environ.get("ANTHROPIC_API_KEY"):
        from .summarize import Summarizer
        summarizer = Summarizer()

    report = {"new": [], "held": [], "skipped": [], "errors": []}
    pm_changed = False if offline else refresh_pm(ed, date, report)
    if not offline and summarizer is None and use_ai:
        report["skipped"].append("bills and votes: no ANTHROPIC_API_KEY yet, so nothing is written up")
        connectors = []
    records = []
    for c in connectors:
        try:
            records += c.fetch(since)
        except NotImplementedError as e:
            report["skipped"].append(str(e))
        except Exception as e:  # one broken source must never stop the others
            report["errors"].append(f"{c.name}: {e}")
    for raw in merge_bill_votes(records):
        if raw["id"] in have:
            continue
        bad = check(raw)
        if bad:
            report["errors"].append(f"{raw.get('source')}/{raw.get('id')}: {bad}")
            continue
        try:
            item = summarizer.summarize(raw) if summarizer else fact_only(raw)
        except Exception as e:
            report["errors"].append(f"summarize {raw['id']}: {e}")
            item = fact_only(raw)
        ed["items"].append(item)
        have.add(item["id"])
        report["new"].append(item["id"])
        if item["review"] == "pending":
            report["held"].append(item["id"])

    ed_path = ROOT / "data/editions" / f"{date}.json"
    if not report["new"] and not ed_path.exists():
        # Nothing new in Parliament yet today: don't publish an empty edition.
        # A fresh PM schedule still goes onto the latest edition.
        prev = sorted((ROOT / "data/editions").glob("*.json"))
        if pm_changed and prev:
            last = json.loads(prev[-1].read_text())
            last["pm"] = ed["pm"]
            prev[-1].write_text(json.dumps(last, ensure_ascii=False, indent=1))
        return report
    published = [i for i in ed["items"] if i.get("review") in ("approved", "auto")]
    if report["new"] and len(ed.get("tldr") or []) < min(4, len(published)):
        ed["tldr"] = [i["short_title"].rstrip(".") + "." for i in published[:4]]
    ed_path.write_text(json.dumps(ed, ensure_ascii=False, indent=1))

    # Evening: draft tomorrow's Daily Savvy (held for one-tap approval).
    tomorrow = (dt.date.fromisoformat(date) + dt.timedelta(days=1)).isoformat()
    quiz_path = ROOT / "data/daily5" / f"{tomorrow}.json"
    local_hour = (dt.datetime.now(dt.timezone.utc) + TZ_OFFSET).hour
    if summarizer and not quiz_path.exists() and (local_hour >= 17 or force_quiz):
        from .daily5 import draft_daily5, save
        try:
            save(draft_daily5(summarizer.client, recent_items(date), tomorrow), ROOT)
            report["held"].append("quiz")
        except Exception as e:
            report["errors"].append(f"daily5: {e}")
    return report


def refresh_pm(ed: dict, date: str, report: dict) -> bool:
    """Rebuild the PM tab from the official itinerary. Returns True if it changed."""
    try:
        days = PM.days()
    except Exception as e:
        report["errors"].append(f"pm_itinerary: {e}")
        return False
    if not days:
        return False
    name = (ed.get("pm") or {}).get("name") or "Mark Carney"
    new = pm_section(days, date, name)
    if (ed.get("pm") or {}).get("timeline") == new["timeline"]:
        return False
    ed["pm"] = new
    report["new_pm"] = new["updated_from"]
    return True


def recent_items(date: str, days: int = 7) -> list[dict]:
    out = []
    for p in sorted((ROOT / "data/editions").glob("*.json"))[-days:]:
        out += [i for i in json.loads(p.read_text())["items"] if i.get("review") in ("approved", "auto")]
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--no-ai", action="store_true")
    ap.add_argument("--quiz", action="store_true", help="draft tomorrow's Daily Savvy now")
    a = ap.parse_args()
    rep = run(a.date or today(), a.offline, not a.no_ai, force_quiz=a.quiz)
    print(json.dumps(rep, indent=1))
