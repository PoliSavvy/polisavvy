"""Connectors for official Canadian sources.

STATUS: the fixture connector works today. The live connectors are stubs
until the build environment can reach the government sites (see
docs/SETUP.md, step 2). Each stub lists the endpoint to verify. Parsers are
written against real responses only, never guessed, so a wrong guess can
never put a wrong fact on the site.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


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


class LegisInfo(_Pending):
    name = "legisinfo"
    endpoint = "https://www.parl.ca/legisinfo/en/bills/json?parlsession=45-1 (bill list with latest stage)"
    notes = "Emit a record when a bill's latest completed stage changes. Cadence: every 30 min on sitting days."


class HouseVotes(_Pending):
    name = "house_votes"
    endpoint = "https://www.ourcommons.ca/Members/en/votes/xml (recorded divisions with yea/nay totals)"
    notes = "Emit one record per new division number, with result and tally. Cadence: every 30 min on sitting days."


class PMItinerary(_Pending):
    name = "pm_itinerary"
    endpoint = "https://www.pm.gc.ca/en/news/itineraries (daily itinerary pages)"
    notes = "Feeds the PM tab timeline, not the bill feed. Cadence: hourly."


class Lobbying(_Pending):
    name = "lobbying"
    endpoint = "https://lobbycanada.gc.ca/media/mqbbmaqk/communications_ocl_cal.zip (monthly communication reports, CSV)"
    notes = "Aggregate by month, subject and institution for the Lobbying tab. Cadence: daily (data updates weekly)."


class CanadaGazette(_Pending):
    name = "gazette"
    endpoint = "https://gazette.gc.ca (Part I and Part II tables of contents)"
    notes = "Regulations and royal assent notices. Cadence: daily."


LIVE = [LegisInfo(), HouseVotes(), PMItinerary(), Lobbying(), CanadaGazette()]
