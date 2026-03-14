"""Well-known managed source definitions shared by CLI and runtime."""

from __future__ import annotations

from typing import cast

from meridian.lib.sync.install_config import ManagedSourceConfig
from meridian.lib.sync.install_types import ItemRef
from meridian.lib.sync.install_types import SourceKind

_WELL_KNOWN_SOURCES: dict[str, dict[str, str]] = {
    "meridian-agents": {
        "kind": "git",
        "url": "https://github.com/haowjy/meridian-agents.git",
        "ref": "main",
    }
}


def is_well_known_source(name: str) -> bool:
    """Return whether the given source name is a built-in alias."""

    return name.strip() in _WELL_KNOWN_SOURCES


def well_known_source_config(
    name: str,
    *,
    items: tuple[ItemRef, ...] | None = None,
) -> ManagedSourceConfig:
    """Build one well-known managed source declaration."""

    normalized = name.strip()
    payload = _WELL_KNOWN_SOURCES.get(normalized)
    if payload is None:
        raise ValueError(f"Unknown well-known managed source '{name}'.")

    return ManagedSourceConfig(
        name=normalized,
        kind=cast("SourceKind", payload["kind"]),
        url=payload.get("url"),
        path=payload.get("path"),
        ref=payload.get("ref"),
        items=items,
    )
