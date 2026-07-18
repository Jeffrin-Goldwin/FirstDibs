"""Normalized job schema shared by every adapter."""

from __future__ import annotations

from datetime import datetime, timezone

FIELDS = ("id", "company", "title", "location", "url", "dept", "posted_at")


def make_job(
    *,
    id: str,
    company: str,
    title: str,
    location: str = "",
    url: str = "",
    dept: str = "",
    posted_at: str = "",
) -> dict:
    """Build a normalized job. Adapters must return these and nothing else.

    posted_at is carried for display only. It is never the basis for "new" --
    see first_seen in store.py.
    """
    return {
        "id": str(id),
        "company": company,
        "title": (title or "").strip(),
        "location": (location or "").strip(),
        "url": url or "",
        "dept": (dept or "").strip(),
        "posted_at": posted_at or "",
    }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fmt_posted(posted_at: str) -> str:
    """Human-friendly posted date for display.

    ISO datetimes -> 'YYYY-MM-DD'. Workday-style human strings ('Posted Today')
    pass through unchanged. Empty -> ''.
    """
    if not posted_at:
        return ""
    try:
        return datetime.fromisoformat(posted_at.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return posted_at


def epoch_ms_to_iso(ms) -> str:
    if not ms:
        return ""
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat(
            timespec="seconds"
        )
    except (TypeError, ValueError, OverflowError, OSError):
        return ""
