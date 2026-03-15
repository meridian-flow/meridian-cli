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
# Known skill deps for bootstrap agents — auto-included when bootstrapping
_BOOTSTRAP_SKILL_NAMES = frozenset({"__meridian-orchestrate", "__meridian-spawn-agent"})


class BootstrapPlan(BaseModel):
    """Required runtime asset roots for one command."""

    model_config = ConfigDict(frozen=True)

    required_items: tuple[str, ...]
    missing_items: tuple[str, ...]


def planned_bootstrap_agent_names(
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

    updated_manifest = _ensure_bootstrap_source(
        manifest=manifest,
        item_ids=tuple(unresolved_bootstrap_items),
    )
    selected_sources.append(_BOOTSTRAP_SOURCE_NAME)
    return tuple(dict.fromkeys(selected_sources)), updated_manifest


def _locked_source_owning_item(item_id: str, lock: InstallLock) -> str | None:
    for source_name, source_record in lock.sources.items():
        if item_id in source_record.items:
            return source_name
    return None


def _is_bootstrap_item(item_id: str) -> bool:
    kind, name = parse_item_id(item_id)
    return kind == "agent" and name in _BOOTSTRAP_AGENT_NAMES


def _ensure_bootstrap_source(
    *,
    manifest: SourceManifest,
    item_ids: tuple[str, ...],
) -> SourceManifest:
    existing = manifest.find_source(_BOOTSTRAP_SOURCE_NAME)
    # Extract agent names from item_ids (all bootstrap items are agents)
    required_agent_names = tuple(parse_item_id(item_id)[1] for item_id in item_ids)

    if existing is None:
        bootstrap_source = SourceConfig(
            name=_BOOTSTRAP_SOURCE_NAME,
            kind="git",
            url=_BOOTSTRAP_URL,
            ref="main",
            agents=required_agent_names,
            skills=tuple(sorted(_BOOTSTRAP_SKILL_NAMES)),
        )
        # Bootstrap sources are always shared (git)
        return manifest.with_source(bootstrap_source, target="shared")

    if existing.agents is None and existing.skills is None:
        # No filter -- all items included, nothing to add
        return manifest

    existing_agent_names = set(existing.agents or ())
    merged_agents = list(existing.agents or ())
    for name in required_agent_names:
        if name not in existing_agent_names:
            merged_agents.append(name)

    # Also ensure skill deps are included
    existing_skill_names = set(existing.skills or ())
    merged_skills = list(existing.skills or ())
    for skill_name in sorted(_BOOTSTRAP_SKILL_NAMES):
        if skill_name not in existing_skill_names:
            merged_skills.append(skill_name)

    agents_changed = len(merged_agents) != len(existing.agents or ())
    skills_changed = len(merged_skills) != len(existing.skills or ())
    if not agents_changed and not skills_changed:
        return manifest

    updates: dict[str, object] = {}
    if agents_changed:
        updates["agents"] = tuple(merged_agents)
    if skills_changed:
        updates["skills"] = tuple(merged_skills)
    updated_source = existing.model_copy(update=updates)
    target = manifest.file_for_source(_BOOTSTRAP_SOURCE_NAME) or "shared"
    return manifest.with_source(updated_source, target=target)


def _agent_profile_path(repo_root: Path, item_id: str) -> Path:
    _, name = parse_item_id(item_id)
    return repo_root / ".agents" / "agents" / f"{name}.md"
