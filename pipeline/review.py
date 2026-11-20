"""Human review of held items, built to be used from a phone.

When the pipeline holds items, the GitHub workflow opens an issue listing
them. Reply to the issue with one of these comments:

    /approve all          publish every held item and the Daily Savvy
    /approve c-41 quiz    publish specific items (quiz = the Daily Savvy)
    /reject c-41          drop an item

Locally the same thing works from the command line:

    python -m pipeline.review list
    python -m pipeline.review approve all
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _latest_date() -> str:
    return sorted((ROOT / "data/editions").glob("*.json"))[-1].stem


def _paths(date: str) -> tuple[Path, Path]:
    return ROOT / "data/editions" / f"{date}.json", ROOT / "data/daily5" / f"{date}.json"


def pending(date: str) -> tuple[list[dict], dict | None]:
    ed_p, d5_p = _paths(date)
    ed = json.loads(ed_p.read_text())
    items = [i for i in ed["items"] if i.get("review") == "pending"]
    d5 = json.loads(d5_p.read_text()) if d5_p.exists() else None
    return items, (d5 if d5 and d5.get("review") == "pending" else None)


def apply(date: str, action: str, ids: list[str]) -> list[str]:
    ed_p, d5_p = _paths(date)
    ed = json.loads(ed_p.read_text())
    everything = "all" in ids
    done = []
    keep = []
    for it in ed["items"]:
        hit = it.get("review") == "pending" and (everything or it["id"] in ids)
        if hit and action == "reject":
            done.append(f"rejected {it['id']}")
            continue
        if hit and action == "approve":
            it["review"] = "approved"
            it.pop("lint", None)
            done.append(f"approved {it['id']}")
        keep.append(it)
    ed["items"] = keep
    ed_p.write_text(json.dumps(ed, ensure_ascii=False, indent=1))
    if d5_p.exists() and (everything or "quiz" in ids):
        d5 = json.loads(d5_p.read_text())
        if d5.get("review") == "pending":
            if action == "approve":
                d5["review"] = "approved"
                d5_p.write_text(json.dumps(d5, ensure_ascii=False, indent=1))
                done.append("approved quiz")
            else:
                d5_p.unlink()
                done.append("rejected quiz (yesterday's stays up until a new one is approved)")
    return done


def issue_body(date: str) -> str:
    items, d5 = pending(date)
    if not items and not d5:
        return ""
    out = [f"## {len(items)} item(s) waiting for review, edition {date}", "",
           "Reply `/approve all`, `/approve <id> ...`, `/reject <id>`, or `quiz` for the Daily Savvy.", ""]
    for i in items:
        out += [f"### `{i['id']}` {i.get('headline', '')}",
                f"**{i.get('what_label', 'What')}:** {i.get('what', '')}",
                f"**{i.get('you_label', 'Why')}:** {i.get('you', '')}"]
        for s in i.get("sides", []):
            out.append(f"- *{s['who']}:* {s['text']}")
        if i.get("lint"):
            out.append("> Automatic checks flagged: " + "; ".join(i["lint"]))
        out += [f"[Official source]({i['source']['url']})", ""]
    if d5:
        out += ["### `quiz` Daily Savvy"]
        for n, q in enumerate(d5["questions"], 1):
            ans = " → ".join(q["order"]) if "order" in q else q["opts"][q["a"]]
            out.append(f"{n}. {q['q']} **Answer:** {ans}")
    return "\n".join(out)


def parse_comment(body: str) -> tuple[str, list[str]] | None:
    words = body.strip().split()
    if not words or words[0] not in ("/approve", "/reject"):
        return None
    return words[0][1:], [w.lower() for w in words[1:]] or ["all"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "approve", "reject", "issue", "comment"])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--date", default=None)
    a = ap.parse_args()
    date = a.date or _latest_date()
    if a.cmd == "list":
        print(issue_body(date) or "Nothing waiting for review.")
    elif a.cmd == "issue":
        print(issue_body(date))
    elif a.cmd == "comment":  # used by the GitHub workflow
        parsed = parse_comment(" ".join(a.ids))
        if not parsed:
            sys.exit(0)
        print("\n".join(apply(date, *parsed)) or "Nothing matched.")
    else:
        print("\n".join(apply(date, a.cmd, a.ids or ["all"])) or "Nothing matched.")
