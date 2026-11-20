"""Build the static site from data files.

    python -m web.build                 # latest edition -> dist/index.html
    python -m web.build --date 2026-11-18

Only items with review == "approved" or "auto" are published. Anything
"pending" waits for a human to approve it (see docs/REVIEW.md).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.schema import GLOSSARY, STAGES, TOPICS, TERM_RE, validate_daily5, validate_edition  # noqa: E402

LAUNCH_DATE = "2026-11-01"  # Daily Savvy game #1
PUBLISHABLE = {"approved", "auto"}


def rich(text: str | None) -> Markup:
    """Escape text, then allow **bold** and [[term|label]] glossary buttons."""
    if not text:
        return Markup("")
    out = str(escape(text))
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = TERM_RE.sub(lambda m: f'<button class="term" data-term="{m.group(1)}">{m.group(2)}</button>', out)
    return Markup(out)


def latest(folder: Path) -> Path:
    files = sorted(folder.glob("*.json"))
    if not files:
        raise SystemExit(f"No data files in {folder}")
    return files[-1]


def load(date: str | None) -> tuple[dict, dict]:
    ed_path = ROOT / "data/editions" / f"{date}.json" if date else latest(ROOT / "data/editions")
    ed = json.loads(ed_path.read_text())
    d5_path = ROOT / "data/daily5" / f"{ed['date']}.json"
    if not d5_path.exists():  # fall back to the most recent approved quiz
        d5_path = latest(ROOT / "data/daily5")
    d5 = json.loads(d5_path.read_text())
    return ed, d5


def build(date: str | None = None, out: Path | None = None) -> Path:
    ed, d5 = load(date)
    problems = validate_edition(ed) + validate_daily5(d5)
    if problems:
        raise SystemExit("Data problems:\n  " + "\n  ".join(problems))

    ed = dict(ed)
    held = [i["id"] for i in ed["items"] if i.get("review") not in PUBLISHABLE]
    ed["items"] = [i for i in ed["items"] if i.get("review") in PUBLISHABLE]
    quiz_ok = d5.get("review") in PUBLISHABLE

    day = dt.date.fromisoformat(ed["date"])
    env = Environment(loader=FileSystemLoader(ROOT / "web/templates"), autoescape=select_autoescape(["html", "j2"]))
    env.filters["rich"] = rich
    payload = {
        "glossary": GLOSSARY,
        "topics": TOPICS,
        "daily5": d5["questions"] if quiz_ok else [],
        "quiz_date": d5["date"],
        "launch": LAUNCH_DATE,
        "lobbying": ed.get("lobbying"),
        "extras": ed.get("extras_for_email", []),
    }
    html = env.get_template("index.html.j2").render(
        ed=ed,
        stages=STAGES,
        payload=payload,
        edition_label=f"Edition · {day.strftime('%b')} {day.day}, {day.year}",
        long_date=f"{day.strftime('%B')} {day.day}, {day.year}",
    )
    out = out or ROOT / "dist"
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html)
    (out / "edition.json").write_text(json.dumps(ed, ensure_ascii=False, indent=1))
    print(f"Built {out / 'index.html'} for {ed['date']}: {len(ed['items'])} items published"
          + (f", {len(held)} held for review ({', '.join(held)})" if held else "")
          + ("" if quiz_ok else ", Daily Savvy held for review"))
    return out / "index.html"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    build(a.date, a.out)
