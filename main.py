"""FirstDips Phase 1 entrypoint.

Flow: load sources -> per source run the right adapter -> normalize ->
conditional-insert (dedup) -> filter -> notify. New jobs only, ever.

    python main.py                 one pass, notify via Telegram if configured
    python main.py --dry-run       one pass, print to console, do not notify
    python main.py --loop          run every hour forever
    python main.py --only stripe   restrict to one company (repeatable)
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import adapters
from core import filters, ui
from core.config import ROOT, load_env, load_sources
from core.normalize import make_job  # noqa: F401  (kept for schema reference)
from core.notify import ConsoleNotifier, TelegramNotifier
from core.store import Store

log = logging.getLogger("firstdips")

RAW_DIR = ROOT / "raw"
HOUR = 3600


def archive_raw(company: str, jobs: list[dict]) -> None:
    """Mirror of the S3 raw archive: lets matching logic be re-run historically."""
    RAW_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RAW_DIR / f"{company}_{stamp}.json"
    path.write_text(json.dumps(jobs, indent=2), encoding="utf-8")


def process_source(source: dict, store: Store, notifier, cfg: dict, delay: float) -> dict:
    company = source["company"]
    ats = source["ats"]
    stats = {"fetched": 0, "new": 0, "notified": 0, "closed": 0, "error": None}
    try:
        fetch = adapters.get(ats)
        with ui.fetching(company):
            jobs = fetch(source)
        stats["fetched"] = len(jobs)
        archive_raw(company, jobs)

        for job in jobs:
            if store.upsert(job):  # True only the first time ever
                stats["new"] += 1
                if filters.matches(job, cfg.get("filters", {})):
                    if notifier.send(job):
                        stats["notified"] += 1

        # Only safe after a successful fetch -- see close_missing docstring.
        seen_ids = {j["id"] for j in jobs}
        stats["closed"] = store.close_missing(company, seen_ids)
    except Exception as exc:  # one bad source must not sink the whole run
        log.exception("source %s (%s) failed", company, ats)
        stats["error"] = str(exc)
    finally:
        time.sleep(delay)
    return stats


def run_once(store: Store, notifier, cfg: dict, only: set[str] | None) -> None:
    delay = float(cfg.get("defaults", {}).get("request_delay", 1.0))
    sources = cfg["sources"]
    if only:
        sources = [s for s in sources if s["company"] in only]

    stamp = datetime.now().strftime("%H:%M:%S")
    ui.pass_header(len(sources), store.count(), stamp)

    totals = {"fetched": 0, "new": 0, "notified": 0, "closed": 0}
    rows = []
    for source in sources:
        s = process_source(source, store, notifier, cfg, delay)
        rows.append({"company": source["company"], **s})
        for k in totals:
            totals[k] += s[k]

    store.prune_expired()
    ui.summary_table(rows, totals)


def main() -> None:
    p = argparse.ArgumentParser(description="FirstDips job radar (Phase 1)")
    p.add_argument("--loop", action="store_true", help="run every hour forever")
    p.add_argument("--dry-run", action="store_true", help="print instead of notifying")
    p.add_argument("--only", action="append", default=[], help="restrict to company (repeatable)")
    p.add_argument("--db", default=str(ROOT / "firstdips.db"))
    args = p.parse_args()

    ui.install_logging(logging.INFO)
    load_env()
    cfg = load_sources()

    if args.dry_run:
        notifier = ConsoleNotifier()
    else:
        notifier = TelegramNotifier()
        if not notifier.configured:
            log.warning("Telegram not configured (.env), falling back to console output")
            notifier = ConsoleNotifier()

    store = Store(args.db)
    only = set(args.only) or None
    try:
        run_once(store, notifier, cfg, only)
        while args.loop:
            log.info("sleeping %ds", HOUR)
            time.sleep(HOUR)
            run_once(store, notifier, cfg, only)
    except KeyboardInterrupt:
        # Ctrl+C is the intended way to stop --loop; exit quietly, no traceback.
        log.info("⚠️ Key board interrupt detected, shutting down")
    finally:
        store.close()


if __name__ == "__main__":
    main()
