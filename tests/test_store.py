"""The dedup contract: upsert() returns True exactly once per job, ever."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.normalize import make_job  # noqa: E402
from core.store import Store  # noqa: E402


def _job(jid="1", company="acme", title="Engineer", location="Remote"):
    return make_job(id=jid, company=company, title=title, location=location, url="u")


def test_new_job_returns_true_once():
    s = Store(":memory:")
    assert s.upsert(_job()) is True
    assert s.upsert(_job()) is False  # same job again -> known
    assert s.count() == 1
    s.close()


def test_upsert_is_idempotent_under_repeats():
    s = Store(":memory:")
    firsts = [s.upsert(_job()) for _ in range(5)]
    assert firsts == [True, False, False, False, False]
    s.close()


def test_first_seen_never_changes():
    s = Store(":memory:")
    s.upsert(_job())
    fs1 = s.conn.execute("SELECT first_seen FROM jobs").fetchone()["first_seen"]
    s.upsert(_job())  # bump last_seen
    fs2 = s.conn.execute("SELECT first_seen FROM jobs").fetchone()["first_seen"]
    assert fs1 == fs2
    s.close()


def test_close_missing_flips_status():
    s = Store(":memory:")
    s.upsert(_job("1"))
    s.upsert(_job("2"))
    # Only job 1 seen this fetch -> job 2 closes.
    closed = s.close_missing("acme", {"1"})
    assert closed == 1
    row = s.conn.execute("SELECT status FROM jobs WHERE pk='acme#2'").fetchone()
    assert row["status"] == "closed"
    s.close()


def test_vanished_job_reopens_on_return():
    s = Store(":memory:")
    s.upsert(_job("1"))
    s.close_missing("acme", set())  # job 1 vanishes -> closed
    s.upsert(_job("1"))  # comes back
    row = s.conn.execute("SELECT status FROM jobs WHERE pk='acme#1'").fetchone()
    assert row["status"] == "open"
    s.close()
