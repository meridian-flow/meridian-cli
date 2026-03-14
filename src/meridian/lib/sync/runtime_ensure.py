"""Runtime bootstrap/install reconciliation for required default agents."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.sync.install_config import ManagedSourcesConfig, load_install_config, write_install_config
from meridian.lib.sync.install_engine import reconcile_managed_sources
from meridian.lib.sync.install_lock import (
    ManagedInstallLock,
    lock_file_guard,
    read_install_lock,
    write_install_lock,
)
from meridian.lib.sync.install_types import ItemRef, format_item_id, parse_item_id
from meridian.lib.sync.source_catalog import well_known_source_config

_BOOTSTRAP_SOURCE_NAME = "meridian-agents"
_BOOTSTRAP_AGENT_NAMES = frozenset({"__meridian-orchestrator", "__meridian-subagent"})


class RuntimeAssetPlan(BaseModel):
    """Required runtime asset roots for one command."""

    model_config = ConfigDict(frozen=True)

    required_items: tuple[str, ...]
    missing_items: tuple[str, ...]


def planned_runtime_agent_names(
    *,
    configured_default: str,
    requested_agent: str | None,
) -> tuple[str, ...]:
    """Return bootstrap-eligible runtime agents that should be present locally."""

    requested = (requested_agent or "").strip()
    if not requested:
        configured = configured_default.strip()
        return (configured,) if configured else ()
    if requested in _BOOTSTRAP_AGENT_NAMES:
        return (requested,)
    return ()


def plan_required_runtime_assets(
    *,
    repo_root: Path,
    agent_names: tuple[str, ...],
) -> RuntimeAssetPlan:
    """Resolve required root agent items and detect which are missing locally."""

    required_items = tuple(
        item_id
        for item_id in dict.fromkeys(
            format_item_id("agent", name.strip())
            for name in agent_names
            if name.strip()
        )
    )
    missing_items = tuple(
        item_id for item_id in required_items if not _agent_profile_path(repo_root, item_id).is_file()
    )
    return RuntimeAssetPlan(required_items=required_items, missing_items=missing_items)


def ensure_runtime_assets(
    *,
    repo_root: Path,
    plan: RuntimeAssetPlan,
) -> None:
    """Ensure required default agents are installed from provenance or bootstrap source."""

    if not plan.missing_items:
        return

    state_paths = resolve_state_paths(repo_root)
    with lock_file_guard(state_paths.agents_lock_path):
        config = load_install_config(state_paths.agents_manifest_path)
        lock = read_install_lock(state_paths.agents_lock_path)
        selected_sources, updated_config = _select_runtime_sources(
            missing_items=plan.missing_items,
            config=config,
            lock=lock,
        )

        errors: list[str] = []
        for source_name in selected_sources:
            result = reconcile_managed_sources(
                repo_root=repo_root,
                sources=updated_config.sources,
                lock=lock,
                agents_cache_dir=state_paths.agents_cache_dir,
                source_filter=source_name,
            )
            errors.extend(result.errors)

        if errors:
            raise RuntimeError("; ".join(errors))
        if updated_config != config:
            write_install_config(state_paths.agents_manifest_path, updated_config)
        write_install_lock(state_paths.agents_lock_path, lock)

    remaining = tuple(
        item_id for item_id in plan.missing_items if not _agent_profile_path(repo_root, item_id).is_file()
    )
    if remaining:
        joined = ", ".join(sorted(remaining))
        raise FileNotFoundError(f"Required runtime agents are still missing after ensure: {joined}")


def _select_runtime_sources(
    *,
    missing_items: tuple[str, ...],
    config: ManagedSourcesConfig,
    lock: ManagedInstallLock,
) -> tuple[tuple[str, ...], ManagedSourcesConfig]:
    selected_sources: list[str] = []
    unresolved_bootstrap_items: list[str] = []

    for item_id in missing_items:
        locked_item = lock.items.get(item_id)
        if locked_item is not None:
            selected_sources.append(locked_item.source_name)
            continue

        source_name = _locked_source_owning_item(item_id, lock)
        if source_name is not None:
            selected_sources.append(source_name)
            continue

        unresolved_bootstrap_items.append(item_id)

    if not unresolved_bootstrap_items:
        return tuple(dict.fromkeys(selected_sources)), config

    unsupported = [
        item_id for item_id in unresolved_bootstrap_items if not _is_bootstrap_item(item_id)
    ]
    if unsupported:
        joined = ", ".join(sorted(unsupported))
        raise FileNotFoundError(
            "Required runtime agents are not installed and have no managed provenance: "
            f"{joined}. Install their source first or set a different configured default."
        )

    updated_config = _ensure_bootstrap_source(
        config=config,
        item_ids=tuple(unresolved_bootstrap_items),
    )
    selected_sources.append(_BOOTSTRAP_SOURCE_NAME)
    return tuple(dict.fromkeys(selected_sources)), updated_config


def _locked_source_owning_item(item_id: str, lock: ManagedInstallLock) -> str | None:
    for source_name, source_record in lock.sources.items():
        if item_id in source_record.items:
            return source_name
    return None


def _is_bootstrap_item(item_id: str) -> bool:
    kind, name = parse_item_id(item_id)
    return kind == "agent" and name in _BOOTSTRAP_AGENT_NAMES


def _ensure_bootstrap_source(
    *,
    config: ManagedSourcesConfig,
    item_ids: tuple[str, ...],
) -> ManagedSourcesConfig:
    existing = next((source for source in config.sources if source.name == _BOOTSTRAP_SOURCE_NAME), None)
    required_refs = tuple(ItemRef.from_item_id(item_id) for item_id in item_ids)

    if existing is None:
        bootstrap_source = well_known_source_config(_BOOTSTRAP_SOURCE_NAME, items=required_refs)
        return ManagedSourcesConfig(sources=(*config.sources, bootstrap_source))

    if existing.items is None:
        return config

    existing_item_ids = {item.item_id for item in existing.items}
    merged_items = list(existing.items)
    for item_ref in required_refs:
        if item_ref.item_id in existing_item_ids:
            continue
        merged_items.append(item_ref)

    if len(merged_items) == len(existing.items):
        return config

    updated_source = existing.model_copy(update={"items": tuple(merged_items)})
    return ManagedSourcesConfig(
        sources=tuple(
            updated_source if source.name == _BOOTSTRAP_SOURCE_NAME else source
            for source in config.sources
        )
    )


def _agent_profile_path(repo_root: Path, item_id: str) -> Path:
    _, name = parse_item_id(item_id)
    return repo_root / ".agents" / "agents" / f"{name}.md"
