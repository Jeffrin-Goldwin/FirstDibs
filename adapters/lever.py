"""Lever: single GET, returns a top-level JSON array.

    https://api.lever.co/v0/postings/{company}?mode=json
"""

from __future__ import annotations

from adapters.http import get_json
from core.normalize import epoch_ms_to_iso, make_job

URL = "https://api.lever.co/v0/postings/{token}?mode=json"


def fetch(source: dict) -> list[dict]:
    token = source.get("token") or source["company"]
    data = get_json(URL.format(token=token))
    jobs = []
    for j in data:
        cats = j.get("categories") or {}
        jobs.append(
            make_job(
                id=j["id"],
                company=source["company"],
                title=j.get("text", ""),
                location=cats.get("location", ""),
                url=j.get("hostedUrl", "") or j.get("applyUrl", ""),
                dept=cats.get("team", "") or cats.get("department", ""),
                posted_at=epoch_ms_to_iso(j.get("createdAt")),
            )
        )
    return jobs
