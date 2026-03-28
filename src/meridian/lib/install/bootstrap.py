"""Runtime bootstrap/install reconciliation for required default agents."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.install.config import (
    SourceConfig,
    SourceManifest,
    load_source_manifest,
    write_source_manifest,
)
from meridian.lib.install.engine import reconcile_sources
from meridian.lib.install.lock import (
    InstallLock,
    read_lock,
    state_lock,
    write_lock,
)
from meridian.lib.install.types import format_item_id, parse_item_id
from meridian.lib.state.paths import resolve_state_paths

_BOOTSTRAP_SOURCE_NAME = "meridian-base"
_BOOTSTRAP_URL = "https://github.com/haowjy/meridian-base.git"
_BOOTSTRAP_AGENT_NAMES = frozenset({"__meridian-orchestrator", "__meridian-subagent"})


class BootstrapPlan(BaseModel):
    """Required runtime asset roots for one command."""

    model_config = ConfigDict(frozen=True)

    required_items: tuple[str, ...]
    missing_items: tuple[str, ...]


def bootstrap_source_config() -> SourceConfig:
    """Return the canonical managed source record for bundled Meridian assets.

    Uses ``agents=None, skills=None`` (unfiltered) so that every agent and
    skill published by the bootstrap repo is installed.  This avoids a
    dependency on a local ``meridian-base/`` tree which does not exist in
    pip/uv-installed packages.
    """

    return SourceConfig(
        name=_BOOTSTRAP_SOURCE_NAME,
        kind="git",
        url=_BOOTSTRAP_URL,
        ref="main",
        agents=None,
        skills=None,
    )


def planned_bootstrap_agent_names(
    *,
    configured_default: str,
    requested_agent: str | None,
    builtin_default: str,
) -> tuple[str, ...]:
    """Return bootstrap-eligible runtime agents that should be present locally."""

    requested = (requested_agent or "").strip()
    if not requested:
        configured = configured_default.strip()
        if configured in _BOOTSTRAP_AGENT_NAMES:
            return (configured,)
        builtin = builtin_default.strip()
        return (builtin,) if builtin in _BOOTSTRAP_AGENT_NAMES else ()
    if requested in _BOOTSTRAP_AGENT_NAMES:
        return (requested,)
    return ()


def plan_bootstrap_assets(
    *,
    repo_root: Path,
    agent_names: tuple[str, ...],
) -> BootstrapPlan:
    """Resolve required root agent items and detect which are missing locally."""

    required_items = tuple(
        item_id
        for item_id in dict.fromkeys(
            format_item_id("agent", name.strip()) for name in agent_names if name.strip()
        )
    )
    missing_items = tuple(
        item_id
        for item_id in required_items
        if not _agent_profile_path(repo_root, item_id).is_file()
    )
    return BootstrapPlan(required_items=required_items, missing_items=missing_items)


def ensure_bootstrap_assets(
    *,
    repo_root: Path,
    plan: BootstrapPlan,
) -> None:
    """Ensure required default agents are installed from provenance or bootstrap source."""

    if not plan.missing_items:
        return

    state_paths = resolve_state_paths(repo_root)
    with state_lock(state_paths.agents_lock_path):
        manifest = load_source_manifest(
            state_paths.agents_manifest_path,
            state_paths.agents_local_manifest_path,
        )
        lock = read_lock(state_paths.agents_lock_path)
        selected_sources, updated_manifest = _select_runtime_sources(
            missing_items=plan.missing_items,
            manifest=manifest,
            lock=lock,
        )

        errors: list[str] = []
        for source_name in selected_sources:
            result = reconcile_sources(
                repo_root=repo_root,
                sources=updated_manifest.all_sources,
                lock=lock,
                agents_cache_dir=state_paths.agents_cache_dir,
                source_filter=source_name,
            )
            errors.extend(result.errors)

        if errors:
            raise RuntimeError("; ".join(errors))
        if updated_manifest != manifest:
            write_source_manifest(
                state_paths.agents_manifest_path,
                state_paths.agents_local_manifest_path,
                updated_manifest,
            )
        write_lock(state_paths.agents_lock_path, lock)

    remaining = tuple(
        item_id
        for item_id in plan.missing_items
        if not _agent_profile_path(repo_root, item_id).is_file()
    )
    if remaining:
        joined = ", ".join(sorted(remaining))
        raise FileNotFoundError(f"Required runtime agents are still missing after ensure: {joined}")


def _select_runtime_sources(
    *,
    missing_items: tuple[str, ...],
    manifest: SourceManifest,
    lock: InstallLock,
) -> tuple[tuple[str, ...], SourceManifest]:
    """Select declared sources for missing runtime items.

    Precedence is always manifest first, lock second:
    - if a lock entry points to a source that is still declared in the manifest, reuse it
    - if a lock entry points to a source that is no longer declared, treat it as stale
    - builtin bootstrap items without declared provenance are rehydrated via meridian-base
    """

    selected_sources: list[str] = []
    unresolved_bootstrap_items: list[str] = []

    for item_id in missing_items:
        source_name = _declared_source_name_for_item(
            item_id,
            manifest=manifest,
            lock=lock,
        )
        if source_name is not None:
            selected_sources.append(source_name)
            continue

        unresolved_bootstrap_items.append(item_id)

    if not unresolved_bootstrap_items:
        return tuple(dict.fromkeys(selected_sources)), manifest

    unsupported = [
        item_id for item_id in unresolved_bootstrap_items if not _is_bootstrap_item(item_id)
    ]
    if unsupported:
        joined = ", ".join(sorted(unsupported))
        raise FileNotFoundError(
            "Required runtime agents are not installed and have no managed provenance: "
            f"{joined}. Install their source first or set a different configured default."
        )

    updated_manifest = ensure_bootstrap_source_manifest(
        manifest=manifest,
        item_ids=tuple(unresolved_bootstrap_items),
    )
    selected_sources.append(_BOOTSTRAP_SOURCE_NAME)
    return tuple(dict.fromkeys(selected_sources)), updated_manifest


def _declared_source_name_for_item(
    item_id: str,
    *,
    manifest: SourceManifest,
    lock: InstallLock,
) -> str | None:
    """Return manifest-declared provenance for an installed item, if any."""

    source_name = _declared_source_from_locked_item(
        item_id,
        manifest=manifest,
        lock=lock,
    )
    if source_name is not None:
        return source_name
    return _declared_source_from_locked_source_record(
        item_id,
        manifest=manifest,
        lock=lock,
    )


def _declared_source_from_locked_item(
    item_id: str,
    *,
    manifest: SourceManifest,
    lock: InstallLock,
) -> str | None:
    locked_item = lock.items.get(item_id)
    if locked_item is None:
        return None
    return _manifest_declared_source_name(
        locked_item.source_name,
        manifest=manifest,
    )


def _declared_source_from_locked_source_record(
    item_id: str,
    *,
    manifest: SourceManifest,
    lock: InstallLock,
) -> str | None:
    for source_name, source_record in lock.sources.items():
        if item_id in source_record.items:
            declared_source_name = _manifest_declared_source_name(
                source_name,
                manifest=manifest,
            )
            if declared_source_name is not None:
                return declared_source_name
    return None


def _manifest_declared_source_name(
    source_name: str,
    *,
    manifest: SourceManifest,
) -> str | None:
    if manifest.find_source(source_name) is None:
        return None
    return source_name


def _is_bootstrap_item(item_id: str) -> bool:
    kind, name = parse_item_id(item_id)
    return kind == "agent" and name in _BOOTSTRAP_AGENT_NAMES


def ensure_bootstrap_source_manifest(
    *,
    manifest: SourceManifest,
    item_ids: tuple[str, ...],
) -> SourceManifest:
    existing = manifest.find_source(_BOOTSTRAP_SOURCE_NAME)
    bootstrap_source = bootstrap_source_config()
    # Validate item ids even though the source we record is the complete bootstrap set.
    _ = tuple(parse_item_id(item_id)[1] for item_id in item_ids)

    if existing is None:
        # Bootstrap sources are always shared (git)
        return manifest.with_source(bootstrap_source, target="shared")

    if existing.agents is None and existing.skills is None:
        # No filter -- all items included, nothing to add
        return manifest

    agents_changed = tuple(existing.agents or ()) != tuple(bootstrap_source.agents or ())
    skills_changed = tuple(existing.skills or ()) != tuple(bootstrap_source.skills or ())
    if not agents_changed and not skills_changed:
        return manifest

    updates: dict[str, object] = {}
    if agents_changed:
        updates["agents"] = bootstrap_source.agents
    if skills_changed:
        updates["skills"] = bootstrap_source.skills
    updated_source = existing.model_copy(update=updates)
    target = manifest.file_for_source(_BOOTSTRAP_SOURCE_NAME) or "shared"
    return manifest.with_source(updated_source, target=target)


def _agent_profile_path(repo_root: Path, item_id: str) -> Path:
    _, name = parse_item_id(item_id)
    return repo_root / ".agents" / "agents" / f"{name}.md"


