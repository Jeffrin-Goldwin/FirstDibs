"""SmartRecruiters: paginated GET, postings under 'content'.

    https://api.smartrecruiters.com/v1/companies/{token}/postings?limit=100&offset=N

The list endpoint caps `limit` at 100 and reports the full count in
`totalFound`, so we page by `offset` until we've seen them all. The public
apply URL is derived from the company token + posting id.
"""

from __future__ import annotations

from adapters.http import get_json
from core.normalize import make_job

URL = "https://api.smartrecruiters.com/v1/companies/{token}/postings?limit={limit}&offset={offset}"
APPLY = "https://jobs.smartrecruiters.com/{token}/{jid}"
PAGE = 100


def fetch(source: dict) -> list[dict]:
    token = source.get("token") or source["company"]
    jobs: list[dict] = []
    offset = 0
    while True:
        data = get_json(URL.format(token=token, limit=PAGE, offset=offset))
        content = data.get("content", [])
        for j in content:
            loc = j.get("location") or {}
            location = loc.get("fullLocation") or ", ".join(
                p for p in (loc.get("city", ""), loc.get("country", "").upper()) if p
            )
            jid = j["id"]
            jobs.append(
                make_job(
                    id=jid,
                    company=source["company"],
                    title=j.get("name", ""),
                    location=location,
                    url=APPLY.format(token=token, jid=jid),
                    dept=(j.get("department") or {}).get("label", ""),
                    posted_at=j.get("releasedDate", ""),
                )
            )
        offset += PAGE
        # Stop when we've paged past the reported total, or a short/empty page.
        if offset >= data.get("totalFound", 0) or not content:
            break
    return jobs
