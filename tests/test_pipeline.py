import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline import neutrality, review, run as runmod, summarize
from pipeline.schema import validate_daily5, validate_edition

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def tmproot(tmp_path, monkeypatch):
    for d in ("data/editions", "data/daily5", "web", "docs"):
        shutil.copytree(ROOT / d, tmp_path / d)
    (tmp_path / "data/raw").mkdir()
    shutil.copy(FIX / "raw_sample.json", tmp_path / "data/raw/sample.json")
    for mod in (runmod, review):
        monkeypatch.setattr(mod, "ROOT", tmp_path)
    from pipeline.connectors import sources
    monkeypatch.setattr(sources, "ROOT", tmp_path)
    return tmp_path


def test_sample_data_is_valid():
    ed = json.loads((ROOT / "data/editions/2026-11-18.json").read_text())
    d5 = json.loads((ROOT / "data/daily5/2026-11-18.json").read_text())
    assert validate_edition(ed) == []
    assert validate_daily5(d5) == []


def test_build_renders_everything(tmp_path):
    from web.build import build
    html = build("2026-11-18", tmp_path).read_text()
    assert "gas tax break is extended into 2027" in html
    assert '<button class="term" data-term="confidence">confidence vote</button>' in html
    assert "{{" not in html and "{%" not in html
    assert "\u2014" not in html


def test_neutrality_lint_catches_loaded_words_and_em_dashes():
    item = {"headline": "Liberals slam bill", "short_title": "x", "what": "It does a thing \u2014 badly.",
            "you": "y", "sides": [], "poll": None}
    probs = neutrality.lint(item)
    assert any("slam" in p for p in probs) and any("em dash" in p for p in probs)


def test_sensitive_topics_are_held():
    assert neutrality.is_sensitive({"headline": "Changes to medical assistance in dying"})
    assert neutrality.is_sensitive({"headline": "x", "sides": [{"who": "A", "text": "Costs $5 billion"}]})
    assert not neutrality.is_sensitive({"headline": "Cell coverage maps bill passes", "sides": []})


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0
        self.messages = self

    def create(self, **kw):
        self.calls += 1
        return SimpleNamespace(content=[SimpleNamespace(text=json.dumps(self.replies.pop(0)))])


GOOD = {"id": "x", "kind": "vote", "status": "Passed a vote", "bill": "C-268", "category": "Phones and internet",
        "topics": ["tech"], "headline": "Cell coverage map bill passes its final House vote",
        "short_title": "Cell coverage bill passes the House", "what_label": "What it does",
        "what": "It requires checks on mobile coverage data that providers report.", "stage": {"done": 4, "current": True},
        "you_label": "What happens next", "you": "The Senate will study it next.",
        "sides": [{"who": "All parties", "text": "Every MP who voted supported it."}], "sides_note": None,
        "poll": {"q": "Your take: should it pass?", "reveal": "**What actually happened:** it passed 330 to 0."},
        "source": {"label": "See the vote", "url": "https://evil.example"}, "sensitive": False}


def test_summarizer_publishes_clean_facts_and_pins_source_url():
    raw = json.loads((FIX / "raw_sample.json").read_text())[0]
    item = summarize.Summarizer(client=FakeClient([GOOD])).summarize(raw)
    assert item["review"] == "auto"
    assert item["source"]["url"] == raw["url"]


def test_summarizer_retries_once_then_holds_bad_drafts():
    bad = dict(GOOD, headline="Parliament finally passes landmark radical coverage bill after shocking delay")
    client = FakeClient([bad, bad])
    raw = json.loads((FIX / "raw_sample.json").read_text())[0]
    item = summarize.Summarizer(client=client).summarize(raw)
    assert client.calls == 2 and item["review"] == "pending" and item["lint"]


def test_offline_run_without_ai_holds_new_facts(tmproot):
    rep = runmod.run("2026-11-19", offline=True, use_ai=False)
    assert set(rep["new"]) == {"vote-45-1-999", "c-35-first-reading"}
    assert set(rep["held"]) == set(rep["new"])
    ed = json.loads((tmproot / "data/editions/2026-11-19.json").read_text())
    assert ed["pm"] and ed["lobbying"]  # carried over from the previous day
    again = runmod.run("2026-11-19", offline=True, use_ai=False)
    assert again["new"] == []  # idempotent


def test_review_comment_flow(tmproot):
    runmod.run("2026-11-19", offline=True, use_ai=False)
    assert "c-35-first-reading" in review.issue_body("2026-11-19")
    assert review.parse_comment("/approve c-35-first-reading") == ("approve", ["c-35-first-reading"])
    assert review.parse_comment("thanks!") is None
    review.apply("2026-11-19", "reject", ["vote-45-1-999"])
    review.apply("2026-11-19", "approve", ["all"])
    ed = json.loads((tmproot / "data/editions/2026-11-19.json").read_text())
    assert [i["id"] for i in ed["items"]] == ["c-35-first-reading"]
    assert ed["items"][0]["review"] == "approved"
    assert review.issue_body("2026-11-19") == ""


def test_held_quiz_and_items_stay_off_the_site(tmp_path, monkeypatch):
    import web.build as wb
    root = tmp_path / "r"
    for d in ("data/editions", "data/daily5", "web"):
        shutil.copytree(ROOT / d, root / d)
    ed_p = root / "data/editions/2026-11-18.json"
    ed = json.loads(ed_p.read_text()); ed["items"][1]["review"] = "pending"; ed_p.write_text(json.dumps(ed))
    d5_p = root / "data/daily5/2026-11-18.json"
    d5 = json.loads(d5_p.read_text()); d5["review"] = "pending"; d5_p.write_text(json.dumps(d5))
    monkeypatch.setattr(wb, "ROOT", root)
    html = wb.build("2026-11-18", tmp_path / "out").read_text()
    assert "medically assisted dying rules" not in html
    assert '"daily5": []' in html


def test_quiet_day_publishes_nothing(tmproot):
    (tmproot / "data/raw/sample.json").unlink()
    rep = runmod.run("2026-11-21", offline=True, use_ai=False)
    assert rep["new"] == [] and not (tmproot / "data/editions/2026-11-21.json").exists()


# ---------------- live parsers, tested against saved real responses ----------------
LIVE_FIX = FIX / "live"


def test_legisinfo_parser_keeps_latest_stage_and_skips_noise():
    from pipeline.connectors.live import parse_bills
    recs = parse_bills((LIVE_FIX / "bills.json").read_text(), "2026-11-17",
                       details=lambda code: (LIVE_FIX / "bill_c-42.json").read_text() if code == "C-42" else "[]")
    ids = {r["id"] for r in recs}
    assert "c-10-royal-assent" in ids and "c-10-senate-3rd-reading" not in ids  # latest stage only
    assert "c-296-house-1st-reading" not in ids  # non-government first reading skipped
    assert not any(r["bill"] == "S-1" for r in recs)  # pro forma skipped
    c42 = next(r for r in recs if r["bill"] == "C-42")
    assert c42["id"] == "c-42-house-2nd-reading" and "Groceries and Essentials Benefit" in c42["text"]
    assert "50%" in c42["text"] and "—" not in c42["text"]
    from pipeline.connectors.base import check
    assert all(check(r) == [] for r in recs)


def test_votes_parser_skips_amendments_and_folds_into_bill():
    from pipeline.connectors.live import merge_bill_votes, parse_bills, parse_votes
    votes = parse_votes((LIVE_FIX / "votes.xml").read_text(), "2026-11-17",
                        participants=lambda n: (LIVE_FIX / "vote_196.xml").read_text())
    subjects = [v["official_title"] for v in votes]
    assert not any("amendment)" in s for s in subjects)
    v196 = next(v for v in votes if v["id"] == "vote-45-1-196")
    assert v196["tally"] == {"yeas": 162, "nays": 151} and v196["result"] == "Passed a vote"
    assert v196["party_votes"]["Liberal"]["Yea"] > 0 and v196["url"].endswith("/votes/45/1/196")
    bills = parse_bills((LIVE_FIX / "bills.json").read_text(), "2026-11-17")
    merged = merge_bill_votes(bills + votes)
    c41 = next(r for r in merged if r.get("bill") == "C-41")
    assert c41["source"] == "legisinfo" and "tally" in c41
    assert not any(r["source"] == "house_votes" and r.get("bill") == "C-41" for r in merged)


def test_pm_itinerary_is_copied_not_rewritten():
    from pipeline.connectors.live import parse_itinerary, pm_section
    days = parse_itinerary((LIVE_FIX / "pm_news.rss").read_text())
    assert [d["date"] for d in days] == ["2026-11-18", "2026-11-19", "2026-11-21"]
    pm = pm_section(days, "2026-11-21", "Mark Carney")
    nov19 = [t for t in pm["timeline"] if t["when"].startswith("Nov 19")]
    assert nov19[0]["when"] == "Nov 19 · 8:55 a.m." and "APEC" in nov19[0]["what"]
    assert nov19[-1]["where"].startswith("National Capital Region")
    assert pm["timeline"][-1]["state"] == "now"
    assert all("Note for media" not in t["what"] for t in pm["timeline"])
