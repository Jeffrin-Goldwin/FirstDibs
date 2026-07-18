"""Terminal presentation layer (rich).

Kept separate from logging/business logic so the CLI look can change without
touching the pipeline. Everything here is display-only and no-ops gracefully
when output is piped (rich auto-disables color for non-TTY streams).
"""

from __future__ import annotations

import logging
import sys

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.normalize import fmt_posted

# Windows consoles default to a legacy code page (cp1252) that can't encode the
# emoji we use; force UTF-8 on the streams BEFORE constructing the Console so it
# picks the modern (non-legacy) renderer and emoji encode cleanly. Must precede
# Console() — rich locks in legacy-vs-modern at construction time.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass  # already utf-8, or a stream that can't be reconfigured

# Single shared console so the log handler, tables, and spinners all coordinate
# their cursor position and never scribble over each other.
console = Console()


def install_logging(level: int = logging.INFO) -> None:
    """Route logging through rich so levels are colored and aligned.

    RichHandler renders its own timestamp/level column, so the format string
    carries only the message.
    """
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%H:%M:%S]",
        handlers=[
            RichHandler(
                console=console,
                show_path=False,
                rich_tracebacks=True,
                markup=False,
                omit_repeated_times=False,
            )
        ],
    )


def fetching(company: str):
    """Spinner context manager shown while a single source is fetched."""
    return console.status(f"[cyan]fetching[/] {company}…", spinner="dots")


def _cell(value: int, positive_style: str) -> Text:
    """Right-aligned count; highlighted when non-zero, dim when zero."""
    style = positive_style if value else "dim"
    return Text(str(value), style=style, justify="right")


def pass_header(source_count: int, store_count: int, stamp: str) -> None:
    console.rule(
        f"[bold]FirstDips[/] · pass {stamp} · "
        f"{source_count} source(s) · {store_count} jobs in store",
        style="cyan",
    )


def summary_table(rows: list[dict], totals: dict) -> None:
    """Render the per-source pass summary.

    Each row dict: company, error(str|None), fetched, new, notified, closed.
    """
    table = Table(box=None, pad_edge=False, expand=False, header_style="bold")
    table.add_column("Company", no_wrap=True)
    table.add_column("Status")
    table.add_column("Fetched", justify="right")
    table.add_column("New", justify="right")
    table.add_column("Notified", justify="right")
    table.add_column("Closed", justify="right")

    for r in rows:
        errored = bool(r["error"])
        company = Text(r["company"], style="red" if errored else "white")
        status = (
            Text("ERROR", style="bold red")
            if errored
            else Text("ok", style="green")
        )
        table.add_row(
            company,
            status,
            Text(str(r["fetched"]), style="dim" if errored else "white", justify="right"),
            _cell(r["new"], "bold green"),
            _cell(r["notified"], "bold green"),
            _cell(r["closed"], "yellow"),
        )

    table.add_section()
    table.add_row(
        Text("TOTAL", style="bold"),
        Text(""),
        Text(str(totals["fetched"]), style="bold", justify="right"),
        _cell(totals["new"], "bold green"),
        _cell(totals["notified"], "bold green"),
        _cell(totals["closed"], "yellow"),
    )
    console.print(table)


def job_card(job: dict) -> None:
    """Colored panel for a single newly-seen job (console notifier)."""
    body = Text()
    body.append(job["title"], style="bold white")
    if job["location"]:
        body.append(f"\n📍 {job['location']}", style="cyan")
    if job["dept"]:
        body.append(f"\n🏷 {job['dept']}", style="magenta")
    posted = fmt_posted(job["posted_at"])
    if posted:
        body.append(f"\n🗓 Posted {posted}", style="dim")
    if job["url"]:
        body.append(f"\n🔗 {job['url']}", style="blue underline")

    console.print(
        Panel(
            body,
            title=f"[bold green]NEW[/] · {job['company']}",
            title_align="left",
            border_style="green",
            expand=False,
            padding=(0, 1),
        )
    )
