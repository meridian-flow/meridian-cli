"""CLI command handlers for managed agent source installs."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Annotated, Any, Literal

from cyclopts import Parameter

from meridian.lib.config.settings import resolve_repo_root
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.sync.install_config import ManagedSourceConfig, ManagedSourcesConfig
from meridian.lib.sync.install_config import load_install_config, write_install_config
from meridian.lib.sync.install_engine import InstallItemAction, InstallResult, install_status
from meridian.lib.sync.install_engine import reconcile_managed_sources, remove_managed_source
from meridian.lib.sync.install_lock import lock_file_guard, read_install_lock, write_install_lock
from meridian.lib.sync.install_types import ItemRef
from meridian.lib.sync.source_catalog import is_well_known_source, well_known_source_config

Emitter = Callable[[Any], None]
SourceSelector = Literal["git", "path", "alias"]

def _install(
    emit: Emitter,
    source: str,
    name: Annotated[
        str | None,
        Parameter(name="--name", help="Optional name for the configured managed source."),
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
    force: Annotated[
        bool,
        Parameter(name="--force", help="Overwrite local modifications and unmanaged files."),
    ] = False,
    dry_run: Annotated[
        bool,
        Parameter(name="--dry-run", help="Preview install changes without writing."),
    ] = False,
) -> None:
    repo_root = resolve_repo_root()
    state_paths = resolve_state_paths(repo_root)
    source_config = _build_managed_source_config(
        source=source,
        repo_root=repo_root,
        name=name,
        ref=ref,
        skills=skills,
        agents=agents,
        rename=rename,
    )

    existing = load_install_config(state_paths.agents_manifest_path)
    if any(configured.name == source_config.name for configured in existing.sources):
        raise ValueError(f"Managed source '{source_config.name}' already exists.")

    updated_config = ManagedSourcesConfig(sources=(*existing.sources, source_config))
    with lock_file_guard(state_paths.agents_lock_path):
        lock = read_install_lock(state_paths.agents_lock_path)
        result = reconcile_managed_sources(
            repo_root=repo_root,
            sources=updated_config.sources,
            lock=lock,
            agents_cache_dir=state_paths.agents_cache_dir,
            force=force,
            dry_run=dry_run,
            source_filter=source_config.name,
        )
        _raise_on_install_errors(result)
        if not dry_run:
            write_install_config(state_paths.agents_manifest_path, updated_config)
            write_install_lock(state_paths.agents_lock_path, lock)

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
    config = load_install_config(state_paths.agents_manifest_path)
    source = next((candidate for candidate in config.sources if candidate.name == name), None)
    if source is None:
        raise ValueError(f"Managed source '{name}' not found.")

    with lock_file_guard(state_paths.agents_lock_path):
        lock = read_install_lock(state_paths.agents_lock_path)
        if source.name in lock.sources:
            result = remove_managed_source(
                repo_root=repo_root,
                lock=lock,
                source_name=source.name,
                force=force,
                dry_run=dry_run,
            )
        else:
            result = InstallResult(actions=(), errors=())
        if not dry_run:
            updated_sources = tuple(
                candidate for candidate in config.sources if candidate.name != source.name
            )
            write_install_config(
                state_paths.agents_manifest_path,
                ManagedSourcesConfig(sources=updated_sources),
            )
            write_install_lock(state_paths.agents_lock_path, lock)

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
    _run_install_reconcile(emit, source=source, force=force, dry_run=dry_run, upgrade=False)


def _upgrade(
    emit: Emitter,
    source: Annotated[
        str | None,
        Parameter(name="--source", help="Upgrade only the named source."),
    ] = None,
    force: Annotated[
        bool,
        Parameter(name="--force", help="Overwrite local modifications and unmanaged files."),
    ] = False,
    dry_run: Annotated[
        bool,
        Parameter(name="--dry-run", help="Preview upgrade changes without writing."),
    ] = False,
) -> None:
    _run_install_reconcile(emit, source=source, force=force, dry_run=dry_run, upgrade=True)


def _status(emit: Emitter) -> None:
    repo_root = resolve_repo_root()
    state_paths = resolve_state_paths(repo_root)
    lock = read_install_lock(state_paths.agents_lock_path)
    emit(install_status(repo_root, lock))


def register_install_commands(app: Any, emit: Emitter) -> None:
    """Register top-level managed install commands."""

    app.command(partial(_install, emit), name="install", help="Add a source and install its items.")
    app.command(partial(_remove, emit), name="remove", help="Remove a source and its managed items.")
    app.command(partial(_update, emit), name="update", help="Install from the locked source state.")
    app.command(partial(_upgrade, emit), name="upgrade", help="Re-resolve floating refs and install.")
    app.command(partial(_status, emit), name="status", help="Compare managed install state vs local files.")


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
    config = load_install_config(state_paths.agents_manifest_path)

    with lock_file_guard(state_paths.agents_lock_path):
        lock = read_install_lock(state_paths.agents_lock_path)
        result = reconcile_managed_sources(
            repo_root=repo_root,
            sources=config.sources,
            lock=lock,
            agents_cache_dir=state_paths.agents_cache_dir,
            upgrade=upgrade,
            force=force,
            dry_run=dry_run,
            source_filter=source,
        )
        _raise_on_install_errors(result)
        if not dry_run:
            write_install_lock(state_paths.agents_lock_path, lock)

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


def _classify_source(source: str, *, repo_root: Path) -> SourceSelector:
    trimmed = source.strip()
    if is_well_known_source(trimmed):
        return "alias"
    candidate = Path(trimmed).expanduser()
    if candidate.is_absolute() or trimmed.startswith((".", "~")):
        return "path"
    if candidate.exists() or (repo_root / candidate).exists():
        return "path"
    return "git"


def _derive_source_name(source: str, selector: SourceSelector) -> str:
    if selector == "alias":
        return source.strip()
    if selector == "git":
        trimmed = source.strip().rstrip("/")
        if trimmed.endswith(".git"):
            trimmed = trimmed[:-4]
        repo_name = trimmed.rsplit("/", 1)[-1]
        derived = repo_name or "managed-source"
        return derived.replace(".", "-")

    normalized = Path(source.strip()).expanduser()
    derived = normalized.name or normalized.resolve().name or source.strip().rstrip("/").split("/")[-1]
    if not derived:
        raise ValueError("Could not derive a source name from the provided path.")
    return derived


def _parse_csv_list(raw: str | None, *, field_name: str) -> tuple[str, ...] | None:
    if raw is None:
        return None

    parts = [part.strip() for part in raw.split(",")]
    if any(not part for part in parts):
        raise ValueError(
            f"Invalid value for '{field_name}': expected comma-separated non-empty names."
        )
    return tuple(parts)


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


def _build_managed_source_config(
    *,
    source: str,
    repo_root: Path,
    name: str | None,
    ref: str | None,
    skills: str | None,
    agents: str | None,
    rename: tuple[str, ...],
) -> ManagedSourceConfig:
    selector = _classify_source(source, repo_root=repo_root)
    source_name = name.strip() if name is not None else _derive_source_name(source, selector)
    rename_map = _normalize_rename_map(_parse_rename_args(rename))
    items = _build_item_refs(agents=agents, skills=skills)

    if selector == "alias":
        configured = well_known_source_config(source.strip(), items=items)
        if ref is not None:
            configured = configured.model_copy(update={"ref": ref})
        return configured.model_copy(update={"name": source_name, "rename": rename_map})
    if selector == "path":
        return ManagedSourceConfig(
            name=source_name,
            kind="path",
            path=source,
            items=items,
            rename=rename_map,
        )

    url = (
        source
        if "://" in source or source.strip().endswith(".git")
        else f"https://github.com/{source.strip()}.git"
    )
    return ManagedSourceConfig(
        name=source_name,
        kind="git",
        url=url,
        ref=ref,
        items=items,
        rename=rename_map,
    )


def _build_item_refs(*, agents: str | None, skills: str | None) -> tuple[ItemRef, ...] | None:
    refs: list[ItemRef] = []
    for item_name in _parse_csv_list(agents, field_name="agents") or ():
        refs.append(ItemRef(kind="agent", name=item_name))
    for item_name in _parse_csv_list(skills, field_name="skills") or ():
        refs.append(ItemRef(kind="skill", name=item_name))
    if not refs:
        return None
    return tuple(refs)


def _normalize_rename_map(rename_map: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in rename_map.items():
        if ":" in key:
            normalized[key] = value
            continue
        normalized[f"agent:{key}"] = value
    return normalized
