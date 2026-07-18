"""Greenhouse: single GET, jobs under 'jobs'.

    https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
"""

from __future__ import annotations

from adapters.http import get_json
from core.normalize import make_job

URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"


def fetch(source: dict) -> list[dict]:
    token = source.get("token") or source["company"]
    data = get_json(URL.format(token=token))
    jobs = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        dept = ""
        depts = j.get("departments") or []
        if depts:
            dept = depts[0].get("name", "")
        jobs.append(
            make_job(
                id=j["id"],
                company=source["company"],
                title=j.get("title", ""),
                location=loc,
                url=j.get("absolute_url", ""),
                dept=dept,
                posted_at=j.get("updated_at", "") or j.get("first_published", ""),
            )
        )
    return jobs
