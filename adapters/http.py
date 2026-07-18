"""Shared HTTP with a real User-Agent and 429-aware backoff.

Every adapter fetches through here so 'be a good citizen' lives in one place.
"""

from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)

USER_AGENT = "FirstDips/0.1 (+personal job radar; contact jeffcrjj@gmail.com)"

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})


def request(method: str, url: str, *, max_retries: int = 3, **kwargs) -> requests.Response:
    """GET/POST with exponential backoff on 429 and 5xx. Raises on final failure."""
    kwargs.setdefault("timeout", 20)
    delay = 2.0
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = _session.request(method, url, **kwargs)
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = float(resp.headers.get("Retry-After", delay))
                log.warning("%s %s -> %s, backing off %.1fs", method, url, resp.status_code, wait)
                time.sleep(wait)
                delay *= 2
                continue
            # Other 4xx (404 wrong token, 403, ...) are permanent -- don't retry.
            resp.raise_for_status()
            return resp
        except requests.HTTPError:
            raise
        except requests.RequestException as exc:
            last_exc = exc
            log.warning("%s %s failed (attempt %d): %s", method, url, attempt + 1, exc)
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"exhausted retries for {method} {url}") from last_exc


def get_json(url: str, **kwargs):
    return request("GET", url, **kwargs).json()


def post_json(url: str, json_body: dict, **kwargs):
    return request("POST", url, json=json_body, **kwargs).json()
