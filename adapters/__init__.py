"""Adapter registry: ats name -> fetch(source) -> list[normalized job]."""

from __future__ import annotations

from adapters import ashby, greenhouse, lever, workday

REGISTRY = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "ashby": ashby.fetch,
    "workday": workday.fetch,
}


def get(ats: str):
    try:
        return REGISTRY[ats]
    except KeyError:
        raise ValueError(f"unknown ats '{ats}'; known: {sorted(REGISTRY)}") from None
