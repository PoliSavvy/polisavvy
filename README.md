# PoliSavvy

What Canada's federal government did, explained like a normal person would.
Every item links to the official record.

## How it works

```
 official sources ──> connectors ──> AI summarizer ──> neutrality checks
 (LEGISinfo, votes,                  (docs/STYLE_GUIDE.md      │
  PM itinerary,                       is its rulebook)         ▼
  lobbying, Gazette)                               clean fact?   sensitive or flagged?
                                                      │                │
                                                 publish now     "Review needed" issue
                                                      │          (/approve from your phone)
                                                      ▼                │
                                         data/editions/DATE.json <─────┘
                                                      │
                                          web/build.py ──> static site (GitHub Pages)
```

- **Runs itself:** `.github/workflows/update.yml` runs every 30 minutes on
  weekdays during the day and every 2 hours on weekends. Each run only does
  work for new events.
- **You approve from your phone:** sensitive items and each day's Daily Savvy wait
  in a GitHub issue. Reply `/approve all` and the site updates in about a minute.
- **Costs almost nothing to host:** the site is static and hosted free on
  GitHub Pages. The only running cost is the AI API.

## Folders

| Path | What's in it |
| --- | --- |
| `data/editions/` | One JSON file per day: the items, PM timeline, lobbying stats |
| `data/daily5/` | One quiz per day |
| `pipeline/` | Connectors, summarizer, neutrality checks, review, the run script |
| `web/` | The site template and the build script |
| `docs/STYLE_GUIDE.md` | Writing and neutrality rules. The AI reads this as its instructions |
| `docs/SETUP.md` | One-time setup steps |
| `tests/` | `python -m pytest` |

## Run it locally

```
pip install -r requirements.txt
python -m pytest -q
python -m web.build                         # builds dist/index.html
python -m pipeline.run --offline --no-ai    # try the pipeline without an API key
python -m pipeline.review list              # see what's waiting for review
```

## Status

| Piece | Status |
| --- | --- |
| Site template (Today, PM, Lobbying, Daily Savvy, For you) | Done, renders from data |
| Data format and validation | Done |
| AI summarizer, neutrality checks, sensitivity rules | Done, tested with a fake model |
| Review by issue comment | Done |
| Scheduled updates and deploy | Done, needs setup (docs/SETUP.md) |
| Live connectors | Next: need live access to the government sites to build against real responses |
| Accounts, emails, quiz stats server | Phase 2 |
| Riding map, MP report cards, French | Phase 3 |
