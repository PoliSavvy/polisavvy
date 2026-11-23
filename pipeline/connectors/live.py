"""Parsers for the live official sources.

Each parser takes the raw response text and returns raw records (see base.py).
Fetching is kept separate (sources.py) so every parser is tested against a
saved real response in tests/fixtures/live/.

Selection rules (applied the same way to every party and bill):
  * Bills: every completed reading and royal assent is a record, except
    first readings of non-government bills (dozens are introduced each week
    and most never get a vote). Pro forma bills (C-1, S-1) are skipped.
  * Votes: every recorded division, except votes on amendments and
    subamendments to a motion. Votes on a bill reading are folded into that
    bill's record so the same event is not shown twice.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

PARL = "45-1"

STAGE_FIELDS = [
    # field, stage key, plain stage hint
    ("PassedHouseFirstReadingDateTime", "house-1st-reading", "Introduced (first reading) in the House of Commons"),
    ("PassedHouseSecondReadingDateTime", "house-2nd-reading", "Passed second reading in the House of Commons and goes to committee"),
    ("PassedHouseThirdReadingDateTime", "house-3rd-reading", "Passed third reading (final vote) in the House of Commons"),
    ("PassedSenateFirstReadingDateTime", "senate-1st-reading", "First reading in the Senate"),
    ("PassedSenateSecondReadingDateTime", "senate-2nd-reading", "Passed second reading in the Senate"),
    ("PassedSenateThirdReadingDateTime", "senate-3rd-reading", "Passed third reading (final vote) in the Senate"),
    ("ReceivedRoyalAssentDateTime", "royal-assent", "Received royal assent and is now law"),
]


def strip_html(s: str | None) -> str:
    s = re.sub(r"<br\s*/?>|</p>|</li>", "\n", s or "")
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ")
    s = re.sub(r"(\d)\?%", r"\1%", s)  # LEGISinfo sometimes loses a thin space before %
    s = s.replace(" \u2014 ", ", ").replace("\u2014", "-")  # house style: no em dashes
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", s)).strip()


def bill_url(code: str) -> str:
    return f"https://www.parl.ca/legisinfo/en/bill/{PARL}/{code.lower()}"


def _is_gov(b: dict) -> bool:
    return "Government" in (b.get("BillDocumentTypeNameEn") or b.get("BillDocumentTypeName") or "")


def parse_bills(bills_json: str, since: str, details=None) -> list[dict]:
    """bills_json: LEGISinfo bill list. details(code) -> per-bill JSON text, or None to skip summaries."""
    out = []
    for b in json.loads(bills_json):
        code = b["NumberCode"]
        if b.get("IsProForma") or code in ("C-1", "S-1"):
            continue
        for field, key, hint in STAGE_FIELDS:
            when = (b.get(field) or "")[:10]
            if not when or when < since:
                continue
            if key.endswith("1st-reading") and not _is_gov(b):
                continue
            out.append({"_bill": b, "id": f"{code.lower()}-{key}", "date": when, "stage_hint": hint,
                        "kind_hint": "law" if key == "royal-assent" else ("debate" if "1st" in key else "vote")})
    # One record per bill per run: its latest stage in the window (e.g. "became law",
    # not also "passed the Senate" the same morning). Earlier stages already shown stay.
    order = {key: i for i, (_, key, _) in enumerate(STAGE_FIELDS)}
    latest: dict = {}
    for r in out:
        code = r["_bill"]["NumberCode"]
        k = (r["date"], order[r["id"].split("-", 2)[2]])
        if code not in latest or k > latest[code][0]:
            latest[code] = (k, r)
    out = [r for _, r in latest.values()]
    recs, cache = [], {}
    for r in out:
        b = r.pop("_bill")
        code = b["NumberCode"]
        summary = ""
        if details:
            if code not in cache:
                try:
                    d = json.loads(details(code))
                    d = d[0] if isinstance(d, list) else d
                    cache[code] = strip_html(d.get("ShortLegislativeSummaryEn") or d.get("ShortLegislativeSummary"))
                except Exception:
                    cache[code] = ""
            summary = cache[code]
        title = b.get("LongTitleEn") or b.get("LongTitle")
        short = b.get("ShortTitleEn") or b.get("ShortTitle")
        text = f"{r['stage_hint']} on {r['date']}. Status: {b.get('StatusNameEn') or b.get('StatusName')}."
        if summary:
            text += "\n\nLibrary of Parliament summary:\n" + summary[:2500]
        recs.append({
            "id": r["id"], "source": "legisinfo", "url": bill_url(code), "date": r["date"],
            "official_title": f"{title} ({short})" if short else title,
            "text": text, "kind_hint": r["kind_hint"], "bill": code, "stage_hint": r["stage_hint"],
            "bill_type": b.get("BillDocumentTypeNameEn") or b.get("BillDocumentTypeName"),
            **({"result": "Became law"} if r["kind_hint"] == "law" else {}),
        })
    return recs


def _t(el, tag):
    return (el.findtext(tag) or "").strip()


def vote_url(n: str | int) -> str:
    return f"https://www.ourcommons.ca/Members/en/votes/{PARL.replace('-', '/')}/{n}"


def party_breakdown(participants_xml: str) -> dict:
    """{party: {"Yea": n, "Nay": n, "Paired": n}} from the per-vote participant XML."""
    out: dict = defaultdict(Counter)
    for p in ET.fromstring(participants_xml).iter("VoteParticipant"):
        out[_t(p, "CaucusShortName") or "Other"][_t(p, "VoteValueName") or "Other"] += 1
    return {k: dict(v) for k, v in out.items()}


def parse_votes(votes_xml: str, since: str, participants=None) -> list[dict]:
    recs = []
    for v in ET.fromstring(votes_xml).iter("Vote"):
        when = _t(v, "DecisionEventDateTime")[:10]
        subject = _t(v, "DecisionDivisionSubject")
        if when < since or re.search(r"\((sub)?amendment\)", subject, re.I):
            continue
        n = _t(v, "DecisionDivisionNumber")
        yeas, nays = _t(v, "DecisionDivisionNumberOfYeas"), _t(v, "DecisionDivisionNumberOfNays")
        result = _t(v, "DecisionResultName")
        rec = {
            "id": f"vote-{PARL}-{n}", "source": "house_votes", "url": vote_url(n), "date": when,
            "official_title": subject, "kind_hint": "vote", "bill": _t(v, "BillNumberCode") or None,
            "result": "Passed a vote" if result == "Agreed To" else "Failed a vote",
            "tally": {"yeas": int(yeas or 0), "nays": int(nays or 0)},
            "text": f"House of Commons recorded vote no. {n}: {subject}. Result: {result}. Yeas {yeas}, Nays {nays}.",
            "motion_type": _t(v, "DecisionDivisionDocumentTypeName"),
        }
        if participants:
            try:
                rec["party_votes"] = party_breakdown(participants(n))
            except Exception:
                pass
        if not rec["bill"]:
            rec.pop("bill")
        recs.append(rec)
    return recs


def merge_bill_votes(records: list[dict]) -> list[dict]:
    """Fold a vote on a bill into that bill's same-day LEGISinfo record."""
    bills = {(r["bill"], r["date"]): r for r in records if r["source"] == "legisinfo"}
    out = []
    for r in records:
        target = bills.get((r.get("bill"), r["date"])) if r["source"] == "house_votes" else None
        if target and target["kind_hint"] == "vote":
            target["text"] += f"\n\nRecorded vote: {r['text']}"
            target["tally"], target["result"] = r["tally"], r["result"]
            if "party_votes" in r:
                target["party_votes"] = r["party_votes"]
            target["vote_url"] = r["url"]
            continue
        out.append(r)
    return out


# ---------------- PM itinerary (feeds the PM tab, not the item feed) ----------------

DATE_IN_TITLE = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December) (\d{1,2}), (\d{4})")
TIME_RE = re.compile(r"^\d{1,2}:\d{2}\s*[ap]\.m\.$")


def _itinerary_events(desc: str) -> list[dict]:
    events, where = [], ""
    for m in re.finditer(r"<h2[^>]*>(.*?)</h2>|<p(?![^>]*Indent)[^>]*>\s*<strong>(.*?)</strong>(.*?)</p>", desc, re.S):
        if m.group(1) is not None:
            where = strip_html(m.group(1))
            continue
        time, what = strip_html(m.group(2)), strip_html(m.group(3))
        if TIME_RE.match(time) and what:
            events.append({"time": time, "where": where, "what": what})
    if not events:
        text = strip_html(desc).replace("Note: All times local and subject to change", "").replace("Note: All times local", "").strip()
        if text:
            events.append({"time": "", "where": where, "what": text.split("\n")[-1][:300]})
    return events


def parse_itinerary(rss: str) -> list[dict]:
    """Daily itineraries from the PM news RSS: [{date, title, url, events}] (newest wins per date)."""
    days: dict = {}
    for it in ET.fromstring(rss).iter("item"):
        link, title = _t(it, "link"), _t(it, "title")
        if "/media-advisories/" not in link:
            continue
        m = DATE_IN_TITLE.search(title)
        if not m:
            continue
        date = dt.datetime.strptime(" ".join(m.groups()), "%B %d %Y").date().isoformat()
        pub = _t(it, "pubDate")
        prev = days.get(date)
        if prev and prev["_pub"] >= dt.datetime.strptime(pub[:25], "%a, %d %b %Y %H:%M:%S").isoformat():
            continue
        days[date] = {"date": date, "title": title, "url": link, "events": _itinerary_events(_t(it, "description")),
                      "_pub": dt.datetime.strptime(pub[:25], "%a, %d %b %Y %H:%M:%S").isoformat()}
    return [{k: v for k, v in d.items() if k != "_pub"} for d in sorted(days.values(), key=lambda d: d["date"])]


def pm_section(days: list[dict], today: str, name: str, keep: int = 4) -> dict:
    """Factual PM tab built only from the official itineraries. No AI, no paraphrase."""
    timeline = []
    for d in days[-keep:]:
        label = dt.date.fromisoformat(d["date"]).strftime("%b %-d")
        state = "now" if d["date"] == today else ("next" if d["date"] > today else "done")
        for e in d["events"]:
            timeline.append({"when": f"{label} · {e['time']}" if e["time"] else label,
                             "where": e["where"], "what": e["what"], "state": state})
    return {
        "name": name,
        "headline": "The PM's public schedule, from his official itinerary",
        "intro": "This is copied from the itinerary the Prime Minister's Office posts each day. Times are local to where he is.",
        "timeline": timeline,
        "good_to_know": None,
        "source": {"label": "See the PM's official daily itinerary", "url": days[-1]["url"] if days else "https://www.pm.gc.ca/en/news/media-advisories"},
        "updated_from": [d["date"] for d in days[-keep:]],
    }
