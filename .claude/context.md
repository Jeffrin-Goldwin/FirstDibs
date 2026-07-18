# FirstDips — context.md

> Hover over the job boards. Strike the moment a role appears.

FirstDips is a personal job-radar. It polls the ATS (applicant tracking system) boards that companies post through, detects brand-new postings within the hour, and pushes them to me instantly. The goal is to apply within minutes of a role going live instead of finding it a week later through an aggregator.

---

## Problem

Job postings reach me ~a week late. The cause is structural: LinkedIn / Indeed / job-alert emails are *downstream* of the source. They scrape company sites, re-index, and batch into alerts — I see a copy of a copy. By the time an alert lands, the posting is days old and has hundreds of applicants.

## Core insight (this drives the whole design)

The fresh signal lives at the **source**: the ATS each company posts through. Modern companies use Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Workable, etc. — and almost all expose **structured JSON endpoints** that update the instant a recruiter hits publish. No HTML parsing, no headless browser, no anti-bot fights.

So FirstDips is **not a web scraper**. It's an **hourly poller over a registry of ATS endpoints, with a diff**. HTML scraping (Playwright on Fargate) is a *fallback* for the handful of companies on a bespoke careers page with no known ATS — not the backbone.

### Known ATS endpoints

| ATS | Endpoint | Method |
|---|---|---|
| Greenhouse | `https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | GET |
| Lever | `https://api.lever.co/v0/postings/{company}?mode=json` | GET |
| Ashby | `https://api.ashbyhq.com/posting-api/job-board/{token}` | GET |
| SmartRecruiters | `https://api.smartrecruiters.com/v1/companies/{company}/postings` | GET |
| Workday | `https://{tenant}.wd{n}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` | POST (JSON body, paginated) |

## Non-goals

- Not building a general-purpose scraper or a crawl-the-whole-internet system.
- Not competing with aggregators on breadth. FirstDips wins on **freshness and precision** for a curated list of target companies.
- Not scraping HTML unless a company has no ATS and I specifically want them.

---

## Architecture

Two phases. Phase 1 runs on my machine; Phase 2 is the AWS target. Interfaces are designed so the swap is nearly mechanical.

```
EventBridge Scheduler (hourly)
        │
        ▼
Fetcher Lambda  ──reads──► SSM Params (source registry)
   │   │        ──invokes─► Fargate + Playwright (HTML fallback)
   │   │
   │   ▼
   │  DynamoDB (dedup, conditional put) ──raw──► S3 (archive)
   │   │
   │   ▼
   │  SQS (new jobs only)
   │   │
   │   ▼
   │  Notifier Lambda (keyword / location filter)
   │   │
   │   ▼
   │  Telegram / SES
```

- **EventBridge Scheduler** — `rate(1 hour)` baseline; a priority group of dream companies on `rate(15 minutes)`.
- **Fetcher Lambda** — container image (so Playwright deps are available); reads the registry, runs the right ATS adapter per source, normalizes, and writes to DynamoDB.
- **DynamoDB** — the dedup store and source of truth for "have I seen this job."
- **S3** — raw response archive; lets me re-run matching logic historically without re-fetching.
- **SQS** — carries *new* jobs only; decouples fetching from delivery, gives retries + DLQ for free.
- **Notifier Lambda** — applies my keyword/location/seniority filter, then pushes.
- **Telegram / SES** — Telegram for instant push (primary), SES for email (secondary).

---

## Data model

### Normalized job schema

Every adapter returns a list of these, regardless of source ATS:

```json
{
  "id":        "ats-provided-stable-id",
  "company":   "stripe",
  "title":     "Senior Platform Engineer",
  "location":  "Remote — India",
  "url":       "https://.../apply",
  "dept":      "Infrastructure",
  "posted_at": "2026-07-17T09:00:00Z"
}
```

### DynamoDB item

```
PK        = "{source}#{job_id}"
title, url, company, location, dept
first_seen   (computed by FirstDips — NOT the ATS timestamp)
last_seen
status       "open" | "closed"
ttl          last_seen + 90 days   (auto-prune)
```

---

## Dedup contract (the crux)

This is what decides *notify on new, don't spam, don't miss*. Model each job by its **ATS-provided stable ID** and use a **conditional put**:

```python
try:
    table.put_item(
        Item={"pk": f"{source}#{jid}", "title": t, "url": u,
              "first_seen": now, "last_seen": now, "status": "open"},
        ConditionExpression="attribute_not_exists(pk)")
    is_new = True          # put succeeded => never seen => notify
except ConditionalCheckFailedException:
    is_new = False         # already known => bump last_seen only
```

Rules:

1. The notify decision is **idempotent** — safe against Lambda retries, concurrent invocations, and duplicate SQS deliveries.
2. **Do not trust the ATS `posted_at`/`created_at`** for "new." Compute `first_seen` in FirstDips, because some boards backfill or re-timestamp.
3. Jobs that were in the store but vanish from the current fetch → flip `status` to `closed`. Useful "apply now, it's filling" signal.
4. TTL self-prunes the table ~90 days after `last_seen`.

Local equivalent: SQLite `INSERT OR IGNORE` + check `rowcount` (1 = new).

---

## Source registry

Config-driven. Local: `sources.yaml`. AWS: SSM Parameter Store (or S3 JSON) so sources change without a redeploy.

```yaml
sources:
  - company: stripe
    ats: greenhouse
    token: stripe
    priority: high          # -> 15-min group
  - company: vercel
    ats: lever
    token: vercel
  - company: someco
    ats: workday
    tenant: someco
    dc: wd3
    site: External
```

**Source coverage is the highest-leverage variable**, not the pipeline. Time-to-notify averages ~30 min at hourly polling; the week-long lag disappears the moment I poll the ATS directly. Ongoing work = curating this file.

Seeding fast: Greenhouse/Lever have search/enumerate APIs; and I can identify a company's ATS from its careers-page URL.

---

## Repo structure (Phase 1)

```
FirstDips/
  sources.yaml
  adapters/            # one fetch() -> list[dict] per ATS type
    greenhouse.py
    lever.py
    ashby.py
    workday.py
  core/
    normalize.py       # -> normalized job schema
    store.py           # SQLite now; same interface as DynamoDB later
    notify.py          # Telegram bot (instant, free)
  main.py              # load -> fetch all -> normalize -> diff -> filter -> notify
```

`main.py` loop: load sources → per source call the right adapter → normalize → conditional-insert → filter on keywords/locations → notify.

Run: `cron` (`0 * * * *`) or `while True: sleep(3600)`.

---

## Local → AWS mapping

| Local (Phase 1) | AWS (Phase 2) |
|---|---|
| `cron` / sleep loop | EventBridge Scheduler |
| `main.py` | Fetcher Lambda (container image) |
| `store.py` on SQLite | DynamoDB (swap two methods, keep interface) |
| `sources.yaml` | SSM Parameter Store / S3 JSON |
| in-process new-job list | SQS → Notifier Lambda |
| local raw files | S3 raw archive |
| Telegram bot | Telegram bot + SES |

The swap is mechanical *because* the interfaces were designed for it — `store.py` and the adapters don't change shape between phases.

---

## Tech stack

- **Language:** Python 3.12
- **Local store:** SQLite → **DynamoDB** (on-demand)
- **Compute:** Lambda (container image); **Fargate + Playwright** only for HTML fallback
- **Schedule:** EventBridge Scheduler
- **Queue:** SQS (+ DLQ)
- **Config/secrets:** SSM Parameter Store
- **Notify:** Telegram Bot API (primary), SES (secondary)
- **IaC:** Terraform
- **CI/CD:** (TBD — likely GitHub Actions or Azure DevOps)

Cost: at a few hundred companies, everything sits inside free tier. Lambda, DynamoDB on-demand, and SQS are effectively free at this volume; SES is fractions of a cent.

---

## Roadmap

- **Phase 1 — local MVP.** Four ATS adapters + `main.py` + SQLite + Telegram, on cron. Prove freshness end-to-end.
- **Phase 2 — AWS.** Lift to Lambda + DynamoDB + EventBridge + SQS + SES/Telegram via Terraform.
- **Phase 3 — coverage + fallback.** Grow `sources.yaml`; add Fargate/Playwright for a few no-ATS target companies.
- **Phase 4 — smarter matching.** Move from keyword filter to relevance ranking (embeddings) for title/JD fit.

---

## Gotchas (front-loaded)

- **Workday is the painful adapter.** `POST` with a JSON body (`{"limit":20,"offset":0,"searchText":""}`), paginated, and you need the tenant + site path per company. Budget an afternoon; the other three are single GETs.
- **Be a good citizen.** Set a real `User-Agent`; honor `429` with exponential backoff. ATS JSON endpoints almost never block, but don't get IP-throttled.
- **HTML fallback is a last resort.** Each bespoke careers page is custom parsing + ongoing maintenance — exactly the cost the ATS approach avoids. Only add one for a company I specifically want.
- **`first_seen` is mine, not the ATS's.** See dedup contract.

---

## Glossary

- **ATS** — applicant tracking system (Greenhouse, Lever, Ashby, Workday…). The source of truth for job postings.
- **Board token** — the per-company identifier in an ATS URL (e.g. `stripe` in the Greenhouse endpoint).
- **first_seen** — the timestamp FirstDips first observed a job. The basis for "new," independent of ATS timestamps.
