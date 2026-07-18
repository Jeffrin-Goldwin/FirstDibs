# FirstDips

> Hover over the job boards. Strike the moment a role appears.

A personal job-radar. It polls the ATS boards companies post through (Greenhouse,
Lever, Ashby, Workday), detects brand-new postings, and pushes them to Telegram —
so you apply within minutes of a role going live instead of a week later via an
aggregator. This is **Phase 1**: a local MVP proving freshness end-to-end. See
[context.md](context.md) for the full design and the AWS Phase 2 target.

## How it works

`load sources → run the right ATS adapter per source → normalize → conditional
insert (dedup) → filter → notify`. A job is notified **exactly once, ever** — the
dedup store returns "new" only the first time a job's stable ATS id is seen, which
makes the notify decision idempotent against retries and re-runs.

## Setup

```bash
python -m pip install -r requirements.txt      # add -dev for tests
cp .env.example .env                            # then fill in Telegram creds
```

`.env` is optional — without it, jobs print to the console instead of Telegram.
To get Telegram creds: message @BotFather to make a bot (gives `TELEGRAM_BOT_TOKEN`),
then message @userinfobot to get your `TELEGRAM_CHAT_ID`.

## Run

```bash
python main.py --dry-run          # one pass, print to console, notify nothing
python main.py                    # one pass, notify via Telegram (or console)
python main.py --loop             # every hour, forever
python main.py --only stripe      # restrict to one company (repeatable)
```

Schedule it with cron (`0 * * * *  cd /path/to/FirstDips && python main.py`) or
just leave `--loop` running.

## Output

The terminal UI is rendered with [rich](https://github.com/Textualize/rich).
Each pass prints a colored per-source summary table — **New / Notified** in
green, **Closed** in amber, error rows in red, unchanged counts dimmed — and
every newly-seen job (console mode) shows as a panel with its title, location,
department, posted date, and apply link. Color auto-disables when output is
piped or redirected, so `--loop` logs stay plain text. The posted date shown is
whatever the ATS exposes (an edit or publish timestamp); it is display-only and
distinct from `first_seen` (see Notes).

## Configure sources

Edit [sources.yaml](sources.yaml). Each source names its `ats` and a board
`token` (the per-company id in the ATS URL). Workday needs `tenant`, `dc`, `site`
instead. The `filters` block decides what actually pushes: a job notifies if it
matches ANY `title_keywords` **and** ANY `locations`, and NO `exclude` term
(empty list = that axis is unconstrained).

```yaml
sources:
  - company: stripe
    ats: greenhouse
    token: stripe
    priority: high
  - company: spotify
    ats: lever
    token: spotify
```

Growing this file is the highest-leverage work — coverage beats pipeline.

## Layout

```
sources.yaml         source registry + filters
adapters/            one fetch(source) -> list[job] per ATS
  greenhouse.py lever.py ashby.py workday.py
  http.py            shared UA + 429/5xx backoff
core/
  normalize.py       the normalized job schema
  store.py           SQLite dedup; same interface as DynamoDB (Phase 2)
  filters.py         keyword/location match
  notify.py          Telegram (+ console fallback)
  ui.py              rich terminal output (tables, job cards, logging)
  config.py          .env + sources.yaml loaders
main.py              orchestration loop
tests/               dedup contract + filter logic
```

## Test

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Notes

- `first_seen` is computed by FirstDips, **not** taken from the ATS timestamp —
  some boards backfill or re-timestamp, so their "posted" date can't be trusted
  for "new".
- Jobs that vanish from a fetch flip to `status=closed` (an "apply now, it's
  filling" signal). Rows self-prune 90 days after `last_seen`.
- `firstdips.db` and `raw/` are local artifacts (gitignored). `raw/` mirrors the
  Phase 2 S3 archive so matching can be re-run historically without re-fetching.
