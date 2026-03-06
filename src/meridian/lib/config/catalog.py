"""Alias-first model resolution backed by built-in + user alias files."""

from __future__ import annotations

import importlib.resources
import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from meridian.lib.config._paths import resolve_repo_root
from meridian.lib.config.routing import route_model
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.types import HarnessId, ModelId

if TYPE_CHECKING:
    from meridian.lib.formatting import FormatContext

logger = logging.getLogger(__name__)

_DEFAULT_ALIASES_RESOURCE = "default-aliases.toml"


@dataclass(frozen=True, slots=True)
class AliasEntry:
    """Alias entry for model lookup + operator-facing guidance."""

    model_id: ModelId
    alias: str
    role: str
    strengths: str
    cost_tier: str
    harness: HarnessId

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Key-value detail view for a single alias entry."""
        from meridian.cli.format_helpers import kv_block

        pairs: list[tuple[str, str | None]] = [
            ("Model", str(self.model_id)),
            ("Harness", str(self.harness)),
            ("Alias", self.alias or None),
            ("Role", self.role or None),
            ("Strengths", self.strengths or None),
            ("Cost", self.cost_tier or None),
        ]
        return kv_block(pairs)


# Backward-compatible export name.
CatalogModel = AliasEntry


def _catalog_path(repo_root: Path) -> Path:
    return resolve_state_paths(repo_root).models_path


def _coerce_alias_map(raw_aliases: object) -> dict[str, str]:
    if not isinstance(raw_aliases, dict):
        return {}

    aliases: dict[str, str] = {}
    for raw_alias, raw_model_id in cast("dict[object, object]", raw_aliases).items():
        alias = str(raw_alias).strip()
        if not alias:
            continue
        if not isinstance(raw_model_id, str):
            logger.warning("Ignoring non-string model id for alias '%s'.", alias)
            continue
        model_id = raw_model_id.strip()
        if not model_id:
            continue
        aliases[alias] = model_id
    return aliases


def _coerce_metadata_map(raw_metadata: object) -> dict[str, dict[str, str]]:
    if not isinstance(raw_metadata, dict):
        return {}

    metadata: dict[str, dict[str, str]] = {}
    for raw_alias, raw_row in cast("dict[object, object]", raw_metadata).items():
        alias = str(raw_alias).strip()
        if not alias or not isinstance(raw_row, dict):
            continue
        row = cast("dict[object, object]", raw_row)
        metadata[alias] = {
            "role": str(row.get("role", "")).strip(),
            "strengths": str(row.get("strengths", "")).strip(),
            "cost_tier": str(row.get("cost_tier", "")).strip(),
        }
    return metadata


def _entry(model_id: str, *, alias: str, role: str, strengths: str, cost_tier: str) -> AliasEntry:
    routing = route_model(model_id)
    return AliasEntry(
        model_id=ModelId(model_id),
        alias=alias,
        role=role,
        strengths=strengths,
        cost_tier=cost_tier,
        harness=routing.harness_id,
    )


def _load_alias_file(path: Path) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    payload_obj = tomllib.loads(path.read_text(encoding="utf-8"))
    payload = cast("dict[str, object]", payload_obj)
    return (
        _coerce_alias_map(payload.get("aliases")),
        _coerce_metadata_map(payload.get("metadata")),
    )


def load_builtin_aliases() -> list[AliasEntry]:
    """Load built-in aliases bundled with meridian."""

    resource_path = Path(
        str(importlib.resources.files("meridian.resources") / _DEFAULT_ALIASES_RESOURCE)
    )
    aliases, metadata = _load_alias_file(resource_path)
    return [
        _entry(
            model_id=model_id,
            alias=alias,
            role=metadata.get(alias, {}).get("role", ""),
            strengths=metadata.get(alias, {}).get("strengths", ""),
            cost_tier=metadata.get(alias, {}).get("cost_tier", ""),
        )
        for alias, model_id in sorted(aliases.items())
    ]


def load_user_aliases(repo_root: Path | None = None) -> list[AliasEntry]:
    """Load user-defined aliases from `.meridian/models.toml [aliases]`."""

    root = resolve_repo_root(repo_root)
    path = _catalog_path(root)
    if not path.is_file():
        return []

    aliases, _metadata = _load_alias_file(path)
    return [
        _entry(model_id=model_id, alias=alias, role="", strengths="", cost_tier="")
        for alias, model_id in sorted(aliases.items())
    ]


def load_merged_aliases(repo_root: Path | None = None) -> list[AliasEntry]:
    """Load built-in aliases merged with user aliases (user wins by alias key)."""

    merged: dict[str, AliasEntry] = {entry.alias: entry for entry in load_builtin_aliases()}
    for entry in load_user_aliases(repo_root=repo_root):
        merged[entry.alias] = entry
    return [merged[key] for key in sorted(merged)]


# Backward-compatible export name.
def load_model_catalog(repo_root: Path | None = None) -> list[AliasEntry]:
    return load_merged_aliases(repo_root=repo_root)


def resolve_model(name_or_alias: str, repo_root: Path | None = None) -> AliasEntry:
    """Resolve alias to model id, or pass through a direct model identifier."""

    normalized = name_or_alias.strip()
    if not normalized:
        raise ValueError("Model identifier must not be empty.")

    aliases = load_merged_aliases(repo_root=repo_root)
    by_alias = {entry.alias: entry for entry in aliases}
    resolved = by_alias.get(normalized)
    if resolved is not None:
        return resolved

    routing = route_model(normalized)
    return AliasEntry(
        model_id=ModelId(normalized),
        alias="",
        role="",
        strengths="",
        cost_tier="",
        harness=routing.harness_id,
    )
