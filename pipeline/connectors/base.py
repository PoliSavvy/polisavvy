"""Connector interface.

A connector fetches new official records from one source and returns them
as plain dicts ("raw records") that the summarizer turns into site items.

Every raw record needs:
    id              stable, unique id, e.g. "c-41-second-reading" or "vote-45-1-193"
    source          connector name
    url             https link to the official record (shown as the source link)
    date            YYYY-MM-DD the event happened
    official_title  the official name of the bill, vote or event
    text            the official wording or summary, trimmed to what matters
    kind_hint       "law" | "vote" | "debate"

Optional: bill, stage_hint, result, tally, positions (party -> stated position,
only when the official record contains it).
"""
from __future__ import annotations

from typing import Protocol


class Connector(Protocol):
    name: str

    def fetch(self, since: str) -> list[dict]:
        """Return raw records for events on or after `since` (YYYY-MM-DD)."""
        ...


REQUIRED = ("id", "source", "url", "date", "official_title", "text", "kind_hint")


def check(record: dict) -> list[str]:
    missing = [k for k in REQUIRED if not record.get(k)]
    bad_url = [] if str(record.get("url", "")).startswith("https://") else ["url must be https"]
    return missing + bad_url
