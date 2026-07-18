"""Telegram push. Phase 2 adds SES as a secondary channel."""

from __future__ import annotations

import html
import logging
import os

import requests

from core.normalize import fmt_posted

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def format(self, job: dict) -> str:
        e = html.escape
        parts = [f"<b>{e(job['title'])}</b>", f"{e(job['company'])}"]
        if job["location"]:
            parts.append(f"📍 {e(job['location'])}")
        if job["dept"]:
            parts.append(f"🏷 {e(job['dept'])}")
        posted = fmt_posted(job["posted_at"])
        if posted:
            parts.append(f"🗓 Posted {e(posted)}")
        if job["url"]:
            parts.append(f'<a href="{e(job["url"])}">Apply</a>')
        return "\n".join(parts)

    def send(self, job: dict) -> bool:
        if not self.configured:
            log.warning("telegram not configured; would send: %s", job["title"])
            return False
        try:
            r = requests.post(
                API.format(token=self.token),
                json={
                    "chat_id": self.chat_id,
                    "text": self.format(job),
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                },
                timeout=15,
            )
            r.raise_for_status()
            return True
        except requests.RequestException as exc:
            # Never let a delivery failure kill the run -- the job is already
            # marked seen, so a raise here would mean a silently missed job.
            log.error("telegram send failed for %s: %s", job["url"], exc)
            return False


class ConsoleNotifier:
    """Used with --dry-run, and whenever Telegram isn't configured yet."""

    configured = True

    def send(self, job: dict) -> bool:
        from core.ui import job_card  # local import: keeps notify import-light

        job_card(job)
        return True
