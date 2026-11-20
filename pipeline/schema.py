"""Data format for PoliSavvy.

An *edition* is one day of the site (data/editions/YYYY-MM-DD.json).
A *daily5* file is that day's quiz (data/daily5/YYYY-MM-DD.json).

Validation here is deliberately plain Python so the pipeline has no
heavy dependencies. Every function returns a list of problems; an empty
list means the data is good.
"""
from __future__ import annotations

import re

KINDS = {"law", "vote", "debate"}
STAGES = ["Introduced", "First vote", "Committee", "Final vote", "Senate", "Law"]
TOPICS = {
    "cost": "Cost of living", "housing": "Housing", "health": "Health",
    "climate": "Climate and energy", "economy": "Jobs and economy",
    "tech": "Tech and internet", "world": "Trade and world",
    "transparency": "Lobbying and transparency", "justice": "Justice and safety",
    "indigenous": "Indigenous affairs", "education": "Education",
}
REVIEW_STATES = {"approved", "pending", "auto"}
TERM_RE = re.compile(r"\[\[([a-z0-9-]+)\|([^\]]+)\]\]")

# Glossary used by [[key|label]] markup in text fields.
GLOSSARY = {
    "confidence": ["Confidence vote", "A vote on whether the House still supports the government. Budgets are automatically confidence votes. If the government loses one, it usually leads to an election."],
    "time-allocation": ["Time allocation", "A rule the government can use to set a limit on how long MPs can debate a bill before it goes to a vote."],
    "pmb": ["Private member's bill", "A bill put forward by an individual MP who is not a cabinet minister. These can come from any party and pass less often than government bills."],
    "minority": ["Minority government", "When the governing party has fewer than half the seats in the House, it needs votes from at least one other party to pass budgets and laws."],
    "royal-assent": ["Royal Assent", "The final step that turns a bill into law. The Governor General signs it on behalf of the King."],
    "lobbying": ["Lobbying", "Trying to influence government decisions on behalf of a company, union or group. Paid lobbyists must register and report arranged meetings with senior officials."],
    "riding": ["Riding", "The area an MP represents. Canada has 343 of them, and each one elects one MP."],
    "committee": ["Committee", "A small group of MPs from different parties that studies bills in detail, hears from experts and can propose changes."],
}


def _req(obj: dict, keys: list[str], where: str) -> list[str]:
    return [f"{where}: missing '{k}'" for k in keys if obj.get(k) in (None, "", [])]


def check_terms(text: str | None, where: str) -> list[str]:
    if not text:
        return []
    return [f"{where}: unknown glossary term '{k}'" for k, _ in TERM_RE.findall(text) if k not in GLOSSARY]


def validate_item(it: dict) -> list[str]:
    w = f"item {it.get('id', '?')}"
    p = _req(it, ["id", "kind", "status", "bill", "headline", "short_title", "what", "you", "source", "topics"], w)
    if it.get("kind") not in KINDS:
        p.append(f"{w}: kind must be one of {sorted(KINDS)}")
    for t in it.get("topics", []):
        if t not in TOPICS:
            p.append(f"{w}: unknown topic '{t}'")
    st = it.get("stage")
    if st is not None and not (isinstance(st.get("done"), int) and 0 <= st["done"] <= len(STAGES)):
        p.append(f"{w}: stage.done must be 0..{len(STAGES)}")
    src = it.get("source") or {}
    if not str(src.get("url", "")).startswith("https://"):
        p.append(f"{w}: source.url must be an https link to the official record")
    if it.get("review", "pending") not in REVIEW_STATES:
        p.append(f"{w}: review must be one of {sorted(REVIEW_STATES)}")
    for s in it.get("sides", []):
        p += _req(s, ["who", "text"], f"{w} side")
    for f in ("what", "you", "sides_note"):
        p += check_terms(it.get(f), f"{w}.{f}")
    return p


def validate_edition(ed: dict) -> list[str]:
    p = _req(ed, ["date", "items"], "edition")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(ed.get("date", ""))):
        p.append("edition: date must be YYYY-MM-DD")
    ids = [i.get("id") for i in ed.get("items", [])]
    if len(ids) != len(set(ids)):
        p.append("edition: duplicate item ids")
    for it in ed.get("items", []):
        p += validate_item(it)
    return p


def validate_daily5(d5: dict) -> list[str]:
    p = _req(d5, ["date", "questions"], "daily5")
    qs = d5.get("questions", [])
    if len(qs) != 5:
        p.append(f"daily5: needs exactly 5 questions, has {len(qs)}")
    for n, q in enumerate(qs, 1):
        w = f"daily5 q{n}"
        p += _req(q, ["type", "q", "why", "link"], w)
        if "order" in q:
            if len(q["order"]) < 3:
                p.append(f"{w}: order questions need 3+ steps")
        else:
            opts = q.get("opts") or []
            if len(opts) < 2:
                p.append(f"{w}: needs 2+ options")
            if not isinstance(q.get("a"), int) or not 0 <= q["a"] < len(opts):
                p.append(f"{w}: answer index out of range")
    return p
