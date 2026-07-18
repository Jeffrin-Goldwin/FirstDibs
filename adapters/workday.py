"""Workday: paginated POST with a JSON body. The painful adapter.

    POST https://{tenant}.wd{n}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
    body: {"limit": 20, "offset": 0, "searchText": ""}

Per-source config needs tenant, dc (e.g. "wd3"), and site (e.g. "External").
The job URL is built from externalPath, which is relative to the *careers*
host, not the cxs API host.
"""

from __future__ import annotations

from adapters.http import post_json
from core.normalize import make_job

API = "https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
CAREERS = "https://{tenant}.{dc}.myworkdayjobs.com/{site}"

PAGE = 20
MAX_PAGES = 50  # safety cap: 1000 postings per company


def fetch(source: dict) -> list[dict]:
    tenant = source["tenant"]
    dc = source["dc"]
    site = source["site"]
    api = API.format(tenant=tenant, dc=dc, site=site)
    careers = CAREERS.format(tenant=tenant, dc=dc, site=site)

    jobs = []
    offset = 0
    for _ in range(MAX_PAGES):
        data = post_json(api, {"limit": PAGE, "offset": offset, "searchText": ""})
        postings = data.get("jobPostings", [])
        if not postings:
            break
        for j in postings:
            path = j.get("externalPath", "")
            url = f"{careers}{path}" if path else ""
            jobs.append(
                make_job(
                    # bulletId is the stable posting id; externalPath is a fallback.
                    id=j.get("bulletFields", [None])[0] or path,
                    company=source["company"],
                    title=j.get("title", ""),
                    location=j.get("locationsText", ""),
                    url=url,
                    dept="",
                    posted_at=j.get("postedOn", ""),
                )
            )
        total = data.get("total", 0)
        offset += PAGE
        if offset >= total:
            break
    return jobs
