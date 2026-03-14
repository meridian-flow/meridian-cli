"""Shared types for the managed install model."""

from __future__ import annotations

import re
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, field_validator

ItemKind = Literal["agent", "skill"]
SourceKind = Literal["git", "path"]

_SOURCE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def normalize_required_string(raw: str, *, source: str) -> str:
    """Normalize one required string field."""

    normalized = raw.strip()
    if not normalized:
        raise ValueError(f"Invalid value for '{source}': expected non-empty string.")
    return normalized


class ItemRef(BaseModel):
    """One canonical item reference in the install model."""

    model_config = ConfigDict(frozen=True)

    kind: ItemKind
    name: str

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return normalize_required_string(value, source="name")

    @property
    def item_id(self) -> str:
        """Return the canonical `kind:name` identity."""

        return format_item_id(self.kind, self.name)

    @classmethod
    def from_item_id(cls, item_id: str) -> "ItemRef":
        """Parse one canonical item id."""

        kind, name = parse_item_id(item_id)
        return cls(kind=kind, name=name)


def validate_source_name(name: str) -> str:
    """Validate one configured source name."""

    normalized = normalize_required_string(name, source="name")
    if _SOURCE_NAME_PATTERN.fullmatch(normalized) is None:
        raise ValueError(
            "Invalid value for 'name': expected alphanumeric characters, hyphens, "
            "or underscores."
        )
    return normalized


def format_item_id(kind: ItemKind, name: str) -> str:
    """Format one canonical item id."""

    return f"{kind}:{normalize_required_string(name, source='name')}"


def parse_item_id(item_id: str) -> tuple[ItemKind, str]:
    """Parse one canonical item id into kind and name."""

    normalized = normalize_required_string(item_id, source="item_id")
    kind_text, separator, name = normalized.partition(":")
    if separator != ":" or not name:
        raise ValueError(
            "Invalid value for 'item_id': expected canonical 'agent:name' or 'skill:name'."
        )

    if kind_text not in {"agent", "skill"}:
        raise ValueError(
            "Invalid value for 'item_id': expected canonical 'agent:name' or 'skill:name'."
        )

    return cast("ItemKind", kind_text), normalize_required_string(name, source="item_id")
