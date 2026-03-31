"""CLI command handlers for managed agent source installs."""

from __future__ import annotations

import shutil
from collections import Counter
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Annotated, Any, Literal

from cyclopts import Parameter

from meridian.cli.utils import parse_csv_list
from meridian.lib.config.settings import resolve_repo_root
from meridian.lib.install.config import (
    SourceConfig,
    load_source_manifest,
    route_source_to_file,
    write_source_manifest,
)
from meridian.lib.install.engine import (
    InstallItemAction,
    InstallResult,
    install_status,
    reconcile_sources,
    remove_source,
)
from meridian.lib.install.hash import compute_item_hash
from meridian.lib.install.lock import read_lock, state_lock, write_lock
from meridian.lib.state.paths import ensure_gitignore, resolve_state_paths

Emitter = Callable[[Any], None]
SourceSelector = Literal["git", "path"]


def _install(
    emit: Emitter,
    source: Annotated[
        str,
        Parameter(help="Source to install (path, @owner/repo, or URL). Omit to sync from lock."),
    ] = "",
    name: Annotated[
        str | None,
        Parameter(name="--name", help="Optional name for the configured source."),
    ] = None,
    ref: Annotated[
        str | None,
        Parameter(name="--ref", help="Branch, tag, or commit for git sources."),
    ] = None,
    skills: Annotated[
        str | None,
        Parameter(name="--skills", help="Comma-separated skill include filter."),
    ] = None,
    agents: Annotated[
        str | None,
        Parameter(name="--agents", help="Comma-separated agent include filter."),
    ] = None,
    rename: Annotated[
        tuple[str, ...],
        Parameter(
            name="--rename",
            help="Rename mapping in OLD=NEW form. Repeatable.",
            negative_iterable=(),
        ),
    ] = (),
    local: Annotated[
        bool,
        Parameter(name="--local", help="Write source to agents.local.toml instead of agents.toml."),
    ] = False,
    force: Annotated[
        bool,
        Parameter(name="--force", help="Overwrite local modifications and unmanaged files."),
    ] = False,
    dry_run: Annotated[
        bool,
        Parameter(name="--dry-run", help="Preview install changes without writing."),
    ] = False,
) -> None:
    # No source arg → sync from lock (like old `update`)
    if not source.strip():
        ensure_gitignore(resolve_repo_root())
        _run_install_reconcile(emit, source=None, force=force, dry_run=dry_run, upgrade=False)
        return

    repo_root = resolve_repo_root()
    ensure_gitignore(repo_root)
    state_paths = resolve_state_paths(repo_root)
    source_config = _build_source_config(
        source=source,
        repo_root=repo_root,
        name=name,
        ref=ref,
        skills=skills,
        agents=agents,
        rename=rename,
    )

    manifest = load_source_manifest(
        state_paths.agents_manifest_path,
        state_paths.agents_local_manifest_path,
    )
    existing_source = manifest.find_source(source_config.name)

    if existing_source is not None:
        # Validate same locator
        if existing_source.url != source_config.url or existing_source.path != source_config.path:
            raise ValueError(
                f"Managed source '{source_config.name}' already exists with a different locator. "
                f"Use 'meridian sources update --ref <ref>' to change the ref, or "
                f"'meridian sources uninstall --source {source_config.name}' to remove it first."
            )
        # Validate compatible ref
        if (
            source_config.ref is not None
            and existing_source.ref is not None
            and source_config.ref != existing_source.ref
        ):
            raise ValueError(
                f"Managed source '{source_config.name}' already exists with ref "
                f"'{existing_source.ref}'. Use 'meridian sources update --ref <ref>' to change it."
            )
        # Merge agents/skills (union)
        merged_source = _merge_source_config(existing_source, source_config)
        target = manifest.file_for_source(source_config.name) or route_source_to_file(
            force_local=local
        )
        updated_manifest = manifest.with_source(merged_source, target=target)
    else:
        target = route_source_to_file(force_local=local)
        updated_manifest = manifest.with_source(source_config, target=target)

    with state_lock(state_paths.agents_lock_path):
        lock = read_lock(state_paths.agents_lock_path)
        result = reconcile_sources(
            repo_root=repo_root,
            sources=updated_manifest.all_sources,
            lock=lock,
            agents_cache_dir=state_paths.agents_cache_dir,
            force=force,
            dry_run=dry_run,
            source_filter=source_config.name,
        )
        _raise_on_install_errors(result)
        if not dry_run:
            write_source_manifest(
                state_paths.agents_manifest_path,
                state_paths.agents_local_manifest_path,
                updated_manifest,
            )
            write_lock(state_paths.agents_lock_path, lock)

    emit(_install_result_payload(result))


def _remove(
    emit: Emitter,
    name: str,
    force: Annotated[
        bool,
        Parameter(name="--force", help="Overwrite local modifications when removing."),
    ] = False,
    dry_run: Annotated[
        bool,
        Parameter(name="--dry-run", help="Preview removals without writing."),
    ] = False,
) -> None:
    repo_root = resolve_repo_root()
    state_paths = resolve_state_paths(repo_root)
    manifest = load_source_manifest(
        state_paths.agents_manifest_path,
        state_paths.agents_local_manifest_path,
    )
    source = manifest.find_source(name)
    if source is None:
        raise ValueError(f"Managed source '{name}' not found.")

    with state_lock(state_paths.agents_lock_path):
        lock = read_lock(state_paths.agents_lock_path)
        if source.name in lock.sources:
            result = remove_source(
                repo_root=repo_root,
                lock=lock,
                source_name=source.name,
                force=force,
                dry_run=dry_run,
            )
        else:
            result = InstallResult(actions=(), errors=())
        if not dry_run:
            updated_manifest = manifest.without_source(source.name)
            write_source_manifest(
                state_paths.agents_manifest_path,
                state_paths.agents_local_manifest_path,
                updated_manifest,
            )
            write_lock(state_paths.agents_lock_path, lock)

    emit(_install_result_payload(result))


def _update(
    emit: Emitter,
    source: Annotated[
        str | None,
        Parameter(name="--source", help="Update only the named source."),
    ] = None,
    force: Annotated[
        bool,
        Parameter(name="--force", help="Overwrite local modifications and unmanaged files."),
    ] = False,
    dry_run: Annotated[
        bool,
        Parameter(name="--dry-run", help="Preview update changes without writing."),
    ] = False,
) -> None:
    _run_install_reconcile(emit, source=source, force=force, dry_run=dry_run, upgrade=True)


def _uninstall(
    emit: Emitter,
    *names: Annotated[
        str,
        Parameter(help="Item names to uninstall (agents or skills)."),
    ],
    source: Annotated[
        str | None,
        Parameter(name="--source", help="Remove an entire source by name."),
    ] = None,
    force: Annotated[
        bool,
        Parameter(name="--force", help="Overwrite local modifications when removing."),
    ] = False,
    dry_run: Annotated[
        bool,
        Parameter(name="--dry-run", help="Preview removals without writing."),
    ] = False,
) -> None:
    if source is not None:
        # Remove entire source — delegate to existing remove logic
        _remove(emit, name=source, force=force, dry_run=dry_run)
        return

    if not names:
        raise ValueError(
            "Provide item names to uninstall, or use --source to remove an entire source."
        )

    repo_root = resolve_repo_root()
    state_paths = resolve_state_paths(repo_root)
    manifest = load_source_manifest(
        state_paths.agents_manifest_path,
        state_paths.agents_local_manifest_path,
    )

    with state_lock(state_paths.agents_lock_path):
        lock = read_lock(state_paths.agents_lock_path)
        actions: list[InstallItemAction] = []
        sources_to_update: dict[str, set[str]] = {}  # source_name → items to remove

        for item_name in names:
            # Try both agent: and skill: prefixes
            matched_key: str | None = None
            for prefix in ("agent:", "skill:"):
                candidate_key = f"{prefix}{item_name}"
                if candidate_key in lock.items:
                    matched_key = candidate_key
                    break

            if matched_key is None:
                raise ValueError(f"Item '{item_name}' is not installed.")

            entry = lock.items[matched_key]
            item_kind = "skill" if matched_key.startswith("skill:") else "agent"
            dest_path = repo_root / entry.destination_path

            action_name: str = "removed"
            reason = "Removed managed item."
            if dest_path.exists() or dest_path.is_symlink():
                local_hash = compute_item_hash(dest_path, item_kind)
                if local_hash != entry.content_hash and not force:
                    action_name = "kept"
                    reason = "Kept locally modified item."
                elif not dry_run:
                    if dest_path.is_dir() and not dest_path.is_symlink():
                        shutil.rmtree(dest_path)
                    else:
                        dest_path.unlink(missing_ok=True)

            actions.append(
                InstallItemAction(
                    item_key=matched_key,
                    item_kind=item_kind,
                    source_name=entry.source_name,
                    action=action_name,
                    reason=reason,
                    dest_path=entry.destination_path,
                )
            )

            if not dry_run and action_name == "removed":
                del lock.items[matched_key]
                sources_to_update.setdefault(entry.source_name, set()).add(item_name)

        # Update manifest: remove items from source's agents/skills lists
        if not dry_run and sources_to_update:
            updated_manifest = manifest
            for src_name, removed_names in sources_to_update.items():
                src = updated_manifest.find_source(src_name)
                if src is None:
                    continue
                new_agents = (
                    tuple(a for a in src.agents if a not in removed_names)
                    if src.agents is not None
                    else None
                )
                new_skills = (
                    tuple(s for s in src.skills if s not in removed_names)
                    if src.skills is not None
                    else None
                )
                has_remaining = (new_agents is None or len(new_agents) > 0) or (
                    new_skills is None or len(new_skills) > 0
                )
                if not has_remaining:
                    if src_name in lock.sources:
                        del lock.sources[src_name]
                    updated_manifest = updated_manifest.without_source(src_name)
                else:
                    target = updated_manifest.file_for_source(src_name) or "shared"
                    updated_src = src.model_copy(
                        update={
                            "agents": new_agents if new_agents else None,
                            "skills": new_skills if new_skills else None,
                        }
                    )
                    updated_manifest = updated_manifest.with_source(updated_src, target=target)
            write_source_manifest(
                state_paths.agents_manifest_path,
                state_paths.agents_local_manifest_path,
                updated_manifest,
            )
            write_lock(state_paths.agents_lock_path, lock)

    emit(_install_result_payload(InstallResult(actions=tuple(actions), errors=())))


def _list_sources(emit: Emitter) -> None:
    repo_root = resolve_repo_root()
    state_paths = resolve_state_paths(repo_root)
    manifest = load_source_manifest(
        state_paths.agents_manifest_path,
        state_paths.agents_local_manifest_path,
    )
    lock = read_lock(state_paths.agents_lock_path)

    sources_payload: list[dict[str, object]] = []
    for source in manifest.all_sources:
        locked_source = lock.sources.get(source.name)
        source_agents: list[str] = []
        source_skills: list[str] = []
        if locked_source is not None:
            for item_key in sorted(locked_source.realized_closure):
                if item_key.startswith("agent:"):
                    source_agents.append(item_key[6:])
                elif item_key.startswith("skill:"):
                    source_skills.append(item_key[6:])
        entry: dict[str, object] = {
            "name": source.name,
            "kind": source.kind,
            "url": source.url,
            "path": source.path,
            "ref": source.ref,
            "local": manifest.file_for_source(source.name) == "local",
            "agents": source_agents,
            "skills": source_skills,
        }
        if manifest.is_overridden(source.name):
            entry["overridden"] = True
        sources_payload.append(entry)
    emit({"sources": sources_payload})


def _status(emit: Emitter) -> None:
    repo_root = resolve_repo_root()
    state_paths = resolve_state_paths(repo_root)
    lock = read_lock(state_paths.agents_lock_path)
    emit(install_status(repo_root, lock))


def register_sources_commands(app: Any, emit: Emitter) -> None:
    """Register sources subcommand group."""

    app.default(partial(_list_sources, emit))
    app.command(
        partial(_list_sources, emit), name="list", help="Show installed sources and their items."
    )
    app.command(partial(_install, emit), name="install", help="Install sources and items.")
    app.command(partial(_uninstall, emit), name="uninstall", help="Remove items or sources.")
    app.command(partial(_update, emit), name="update", help="Re-resolve refs and install latest.")
    app.command(partial(_status, emit), name="status", help="Compare lock vs local files.")


def _run_install_reconcile(
    emit: Emitter,
    *,
    source: str | None,
    force: bool,
    dry_run: bool,
    upgrade: bool,
) -> None:
    repo_root = resolve_repo_root()
    state_paths = resolve_state_paths(repo_root)
    manifest = load_source_manifest(
        state_paths.agents_manifest_path,
        state_paths.agents_local_manifest_path,
    )

    with state_lock(state_paths.agents_lock_path):
        lock = read_lock(state_paths.agents_lock_path)
        result = reconcile_sources(
            repo_root=repo_root,
            sources=manifest.all_sources,
            lock=lock,
            agents_cache_dir=state_paths.agents_cache_dir,
            upgrade=upgrade,
            force=force,
            dry_run=dry_run,
            source_filter=source,
        )
        _raise_on_install_errors(result)
        if not dry_run:
            write_lock(state_paths.agents_lock_path, lock)

    emit(_install_result_payload(result))


def _raise_on_install_errors(result: InstallResult) -> None:
    if not result.errors:
        return
    raise ValueError("; ".join(result.errors))


def _install_result_payload(result: InstallResult) -> dict[str, object]:
    counts = Counter(action.action for action in result.actions)
    return {
        "installed": counts["installed"],
        "updated": counts["updated"] + counts["reinstalled"],
        "reinstalled": counts["reinstalled"],
        "skipped": counts["skipped"],
        "conflicts": counts["conflict"],
        "removed": counts["removed"],
        "kept": counts["kept"],
        "errors": list(result.errors),
        "items": [_action_payload(action) for action in result.actions],
    }


def _action_payload(action: InstallItemAction) -> dict[str, object]:
    return {
        "key": action.item_key,
        "item_kind": action.item_kind,
        "source_name": action.source_name,
        "action": action.action,
        "reason": action.reason,
        "dest_path": action.dest_path,
    }


def _merge_source_config(existing: SourceConfig, incoming: SourceConfig) -> SourceConfig:
    """Merge incoming agents/skills into an existing source config (union)."""

    # None means "all" — union with anything stays None
    if (existing.agents is None and existing.skills is None) or (
        incoming.agents is None and incoming.skills is None
    ):
        merged_agents = None
        merged_skills = None
    else:
        existing_agents = set(existing.agents or ())
        incoming_agents = set(incoming.agents or ())
        merged_agents_set = existing_agents | incoming_agents
        merged_agents = tuple(sorted(merged_agents_set)) if merged_agents_set else None

        existing_skills = set(existing.skills or ())
        incoming_skills = set(incoming.skills or ())
        merged_skills_set = existing_skills | incoming_skills
        merged_skills = tuple(sorted(merged_skills_set)) if merged_skills_set else None

    # Merge rename maps (incoming overrides)
    merged_rename = {**existing.rename, **incoming.rename}

    return existing.model_copy(
        update={
            "agents": merged_agents,
            "skills": merged_skills,
            "rename": merged_rename,
        }
    )


def _classify_source(source: str, *, repo_root: Path) -> SourceSelector:
    trimmed = source.strip()
    if trimmed.startswith("@"):
        return "git"
    candidate = Path(trimmed).expanduser()
    if candidate.is_absolute() or trimmed.startswith((".", "~")):
        return "path"
    if candidate.exists() or (repo_root / candidate).exists():
        return "path"
    return "git"


def _derive_source_name(source: str, selector: SourceSelector) -> str:
    if selector == "git":
        trimmed = source.strip()
        if trimmed.startswith("@"):
            # @owner/repo → repo
            trimmed = trimmed.lstrip("@")
        trimmed = trimmed.rstrip("/")
        if trimmed.endswith(".git"):
            trimmed = trimmed[:-4]
        repo_name = trimmed.rsplit("/", 1)[-1]
        derived = repo_name or "managed-source"
        return derived.replace(".", "-")

    normalized = Path(source.strip()).expanduser()
    derived = (
        normalized.name or normalized.resolve().name or source.strip().rstrip("/").split("/")[-1]
    )
    if not derived:
        raise ValueError("Could not derive a source name from the provided path.")
    return derived


def _parse_rename_args(rename_args: tuple[str, ...]) -> dict[str, str]:
    rename_map: dict[str, str] = {}
    for raw in rename_args:
        old, separator, new = raw.partition("=")
        old_name = old.strip()
        new_name = new.strip()
        if separator != "=" or not old_name or not new_name:
            raise ValueError("Invalid --rename value: expected OLD=NEW.")
        rename_map[old_name] = new_name
    return rename_map


def _build_source_config(
    *,
    source: str,
    repo_root: Path,
    name: str | None,
    ref: str | None,
    skills: str | None,
    agents: str | None,
    rename: tuple[str, ...],
) -> SourceConfig:
    selector = _classify_source(source, repo_root=repo_root)
    source_name = name.strip() if name is not None else _derive_source_name(source, selector)
    rename_map = _normalize_rename_map(_parse_rename_args(rename))
    agent_names = parse_csv_list(agents, field_name="agents", none_for_empty=True)
    skill_names = parse_csv_list(skills, field_name="skills", none_for_empty=True)

    if selector == "path":
        return SourceConfig(
            name=source_name,
            kind="path",
            path=source,
            agents=agent_names,
            skills=skill_names,
            rename=rename_map,
        )

    trimmed = source.strip()
    if trimmed.startswith("@"):
        # @owner/repo → https://github.com/owner/repo.git
        url = f"https://github.com/{trimmed.lstrip('@')}.git"
    elif "://" in trimmed or trimmed.endswith(".git"):
        url = trimmed
    else:
        url = f"https://github.com/{trimmed}.git"
    return SourceConfig(
        name=source_name,
        kind="git",
        url=url,
        ref=ref,
        agents=agent_names,
        skills=skill_names,
        rename=rename_map,
    )


def _normalize_rename_map(rename_map: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in rename_map.items():
        if ":" in key:
            normalized[key] = value
            continue
        normalized[f"agent:{key}"] = value
    return normalized
