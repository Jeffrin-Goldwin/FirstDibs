"""Config loading. sources.yaml now, SSM Parameter Store in Phase 2."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path | None = None) -> None:
    """Minimal .env reader so we don't take a dependency for five lines.

    Real environment variables always win.
    """
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def load_sources(path: Path | None = None) -> dict:
    path = path or ROOT / "sources.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data.setdefault("sources", [])
    data.setdefault("filters", {})
    data.setdefault("defaults", {})
    return data
