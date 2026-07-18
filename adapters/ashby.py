"""Ashby: single GET, jobs under 'jobs'.

    https://api.ashbyhq.com/posting-api/job-board/{token}
"""

from __future__ import annotations

from adapters.http import get_json
from core.normalize import make_job

URL = "https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=false"


def fetch(source: dict) -> list[dict]:
    token = source.get("token") or source["company"]
    data = get_json(URL.format(token=token))
    jobs = []
    for j in data.get("jobs", []):
        jobs.append(
            make_job(
                id=j["id"],
                company=source["company"],
                title=j.get("title", ""),
                location=j.get("location", ""),
                url=j.get("jobUrl", "") or j.get("applyUrl", ""),
                dept=j.get("department", "") or j.get("team", ""),
                posted_at=j.get("publishedAt", ""),
            )
        )
    return jobs
