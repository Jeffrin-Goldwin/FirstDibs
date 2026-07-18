"""Dedup store. SQLite now, DynamoDB in Phase 2 -- same interface.

The notify decision lives here and nowhere else: upsert() returns True exactly
once per job, ever. That is the whole dedup contract.

SQLite  : INSERT OR IGNORE, rowcount == 1 means new.
DynamoDB: put_item(ConditionExpression="attribute_not_exists(pk)"), no raise
          means new.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from core.normalize import now_iso

TTL_DAYS = 90

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    pk         TEXT PRIMARY KEY,
    company    TEXT NOT NULL,
    title      TEXT NOT NULL,
    url        TEXT,
    location   TEXT,
    dept       TEXT,
    posted_at  TEXT,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'open',
    ttl        INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_company_status ON jobs (company, status);
"""


def _ttl_from(ts: str) -> int:
    base = datetime.fromisoformat(ts)
    return int((base + timedelta(days=TTL_DAYS)).timestamp())


class Store:
    def __init__(self, path: str = "firstdips.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    @staticmethod
    def pk(source: str, job_id: str) -> str:
        return f"{source}#{job_id}"

    def upsert(self, job: dict) -> bool:
        """Insert if unseen. Returns True only the first time a job is seen.

        Idempotent: safe against retries, concurrent runs, duplicate deliveries.
        """
        key = self.pk(job["company"], job["id"])
        ts = now_iso()
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO jobs
                (pk, company, title, url, location, dept, posted_at,
                 first_seen, last_seen, status, ttl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
            """,
            (
                key,
                job["company"],
                job["title"],
                job["url"],
                job["location"],
                job["dept"],
                job["posted_at"],
                ts,
                ts,
                _ttl_from(ts),
            ),
        )
        is_new = cur.rowcount == 1

        if not is_new:
            # Known job: bump last_seen (and reopen if it had vanished and
            # come back). Never touch first_seen.
            self.conn.execute(
                "UPDATE jobs SET last_seen = ?, ttl = ?, status = 'open' WHERE pk = ?",
                (ts, _ttl_from(ts), key),
            )
        self.conn.commit()
        return is_new

    def close_missing(self, company: str, seen_ids: set[str]) -> int:
        """Flip jobs that vanished from this fetch to closed.

        'Filling up, apply now' signal. Only call after a *successful* fetch --
        a failed fetch looks identical to every job disappearing at once.
        """
        rows = self.conn.execute(
            "SELECT pk FROM jobs WHERE company = ? AND status = 'open'", (company,)
        ).fetchall()
        seen_pks = {self.pk(company, i) for i in seen_ids}
        gone = [r["pk"] for r in rows if r["pk"] not in seen_pks]
        if gone:
            self.conn.executemany(
                "UPDATE jobs SET status = 'closed' WHERE pk = ?",
                [(pk,) for pk in gone],
            )
            self.conn.commit()
        return len(gone)

    def prune_expired(self) -> int:
        """DynamoDB does this for free via the ttl attribute; SQLite needs a sweep."""
        now = int(datetime.now(timezone.utc).timestamp())
        cur = self.conn.execute("DELETE FROM jobs WHERE ttl < ?", (now,))
        self.conn.commit()
        return cur.rowcount

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"]

    def close(self) -> None:
        self.conn.close()
