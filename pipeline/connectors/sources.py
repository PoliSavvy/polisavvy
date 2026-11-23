"""Connectors for official Canadian sources.

Live: LEGISinfo bills, House of Commons recorded votes, PM itinerary.
Pending: Lobbying (the registry site blocks automated downloads behind a
Cloudflare check) and Canada Gazette (reachable, but needs a plain-language
step before it is useful). Parsers live in live.py and are tested against
saved real responses, never guessed.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UA = "PoliSavvyBot/0.1 (+https://github.com/PoliSavvy/polisavvy)"


def get(url: str, timeout: int = 40) -> str:
    import requests
    last = None
    for _ in range(2):
        try:
            r = requests.get(url, timeout=timeout, headers={"User-Agent": UA})
            r.raise_for_status()
            r.encoding = r.encoding or "utf-8"
            return r.text
        except Exception as e:  # one retry, then give up for this run
            last = e
    raise last


class FixtureConnector:
    """Reads saved raw records from data/raw/*.json (for tests and offline runs)."""
    name = "fixture"

    def __init__(self, folder: Path | None = None):
        self.folder = folder or ROOT / "data/raw"

    def fetch(self, since: str) -> list[dict]:
        out = []
        for p in sorted(self.folder.glob("*.json")):
            for rec in json.loads(p.read_text()):
                if rec["date"] >= since:
                    out.append(rec)
        return out


class _Pending:
    name = "pending"
    endpoint = ""
    notes = ""

    def fetch(self, since: str) -> list[dict]:
        raise NotImplementedError(
            f"{self.name}: not built yet. Verify {self.endpoint} once the site is reachable. {self.notes}"
        )


class LegisInfo:
    name = "legisinfo"
    endpoint = "https://www.parl.ca/legisinfo/en/bills/json?parlsession=45-1"

    def fetch(self, since: str) -> list[dict]:
        from .live import PARL, parse_bills
        return parse_bills(get(self.endpoint), since,
                           details=lambda code: get(f"https://www.parl.ca/legisinfo/en/bill/{PARL}/{code.lower()}/json"))


class HouseVotes:
    name = "house_votes"
    endpoint = "https://www.ourcommons.ca/Members/en/votes/xml"

    def fetch(self, since: str) -> list[dict]:
        from .live import parse_votes, vote_url
        return parse_votes(get(self.endpoint), since, participants=lambda n: get(vote_url(n) + "/xml"))


class PMItinerary:
    """Feeds the PM tab (run.refresh_pm), not the item feed."""
    name = "pm_itinerary"
    endpoint = "https://www.pm.gc.ca/en/news.rss"

    def days(self) -> list[dict]:
        from .live import parse_itinerary
        return parse_itinerary(get(self.endpoint))


class Lobbying(_Pending):
    name = "lobbying"
    endpoint = "https://lobbycanada.gc.ca/media/mqbbmaqk/communications_ocl_cal.zip (monthly communication reports, CSV)"
    notes = "Blocked: the site answers automated requests with a Cloudflare challenge (HTTP 403). Aggregate by month, subject and institution for the Lobbying tab. Cadence: daily (data updates weekly)."


class CanadaGazette(_Pending):
    name = "gazette"
    endpoint = "https://gazette.gc.ca (Part I and Part II tables of contents)"
    notes = "Reachable via https://gazette.gc.ca/rss/p2-eng.xml. Needs a plain-language pass before regulation titles are readable. Cadence: every second Wednesday."


LIVE = [LegisInfo(), HouseVotes(), Lobbying(), CanadaGazette()]  # item feed sources
PM = PMItinerary()
