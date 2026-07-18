"""Keyword / location filter applied to new jobs before notifying.

Phase 2: this logic moves into the Notifier Lambda, downstream of SQS.
Phase 4 swaps it for embedding-based relevance ranking.
"""

from __future__ import annotations


def _any_in(terms, haystack: str) -> bool:
    return any(t.lower() in haystack for t in terms)


def matches(job: dict, filters: dict) -> bool:
    """Match ANY title keyword AND ANY location, and NO exclude term.

    An empty or missing list means that axis is unconstrained.
    """
    title = job["title"].lower()
    location = job["location"].lower()

    excludes = filters.get("exclude") or []
    if _any_in(excludes, f"{title} {location}"):
        return False

    keywords = filters.get("title_keywords") or []
    if keywords and not _any_in(keywords, title):
        return False

    locations = filters.get("locations") or []
    if locations and not _any_in(locations, location):
        return False

    return True
