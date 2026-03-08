"""CLI command handlers for standalone sync operations."""

from __future__ import annotations

import shutil
from collections import Counter
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Annotated, Any, Literal

from cyclopts import Parameter

from meridian.lib.config.settings import resolve_repo_root
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.sync.config import (
    SyncSourceConfig,
    add_sync_source,
    load_sync_config,
    remove_sync_source,
)
from meridian.lib.sync.engine import SyncItemAction, SyncResult, sync_items
from meridian.lib.sync.hash import compute_item_hash
from meridian.lib.sync.lock import lock_file_guard, read_lock_file, write_lock_file

Emitter = Callable[[Any], None]
ItemKind = Literal["skill", "agent"]


def _sync_install(
    emit: Emitter,
    source: str,
    name: Annotated[
        str | None,
        Parameter(name="--name", help="Optional name for the configured sync source."),
    ] = None,
    ref: Annotated[
        str | None,
        Parameter(name="--ref", help="Branch or tag for repo sources."),
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
        Parameter(name="--dry-run", help="Preview sync changes without writing."),
    ] = False,
) -> None:
    repo_root = resolve_repo_root()
    state_paths = resolve_state_paths(repo_root)
    selector = _classify_source(source, repo_root=repo_root)
    source_name = name.strip() if name is not None else _derive_source_name(source, selector)
    source_config = SyncSourceConfig(
        name=source_name,
        repo=source if selector == "repo" else None,
        path=source if selector == "path" else None,
        ref=ref,
        skills=_parse_csv_list(skills, field_name="skills"),
        agents=_parse_csv_list(agents, field_name="agents"),
        rename=_parse_rename_args(rename),
    )

    existing = load_sync_config(state_paths.config_path)
    if any(configured.name == source_config.name for configured in existing.sources):
        raise ValueError(f"Sync source '{source_config.name}' already exists.")

    if not dry_run:
        add_sync_source(state_paths.config_path, source_config)

    with lock_file_guard(state_paths.sync_lock_path):
        result = sync_items(
            repo_root=repo_root,
            sources=(source_config,),
            sync_cache_dir=state_paths.sync_cache_dir,
            sync_lock_path=state_paths.sync_lock_path,
            force=force,
            dry_run=dry_run,
        )

    emit(_sync_result_payload(result))


def _sync_remove(emit: Emitter, name: str) -> None:
    repo_root = resolve_repo_root()
    state_paths = resolve_state_paths(repo_root)
    config = load_sync_config(state_paths.config_path)
    source = next((candidate for candidate in config.sources if candidate.name == name), None)
    if source is None:
        raise ValueError(f"Sync source '{name}' not found.")

    with lock_file_guard(state_paths.sync_lock_path):
        lock = read_lock_file(state_paths.sync_lock_path)
        source_entries = sorted(
            (
                (item_key, entry)
                for item_key, entry in lock.items.items()
                if entry.source_name == source.name
            ),
            key=lambda pair: pair[0],
        )

        emitted_items: list[dict[str, object]] = []
        removed_count = 0
        warned_count = 0

        for item_key, entry in source_entries:
            dest_path = repo_root / entry.dest_path
            local_name = _local_name_for_entry(entry.item_kind, dest_path)
            claude_path = _claude_path_for_item(repo_root, entry.item_kind, local_name)

            local_hash = (
                compute_item_hash(dest_path, entry.item_kind) if _path_exists(dest_path) else None
            )
            matches_lock = local_hash == entry.tree_hash if local_hash is not None else True

            action = "removed"
            reason = "Removed managed item."
            if matches_lock:
                if _path_exists(dest_path):
                    _remove_path(dest_path)
                if claude_path.is_symlink():
                    claude_path.unlink()
                elif _path_exists(claude_path):
                    reason = (
                        "Removed managed item; left an unmanaged Claude path in place."
                    )
                    warned_count += 1
                removed_count += 1
            else:
                action = "kept"
                reason = "Kept locally modified item."
                warned_count += 1
                if claude_path.is_symlink():
                    claude_path.unlink()

            emitted_items.append(
                {
                    "key": item_key,
                    "action": action,
                    "reason": reason,
                    "dest_path": entry.dest_path,
                }
            )
            del lock.items[item_key]

        remove_sync_source(state_paths.config_path, source.name)
        write_lock_file(state_paths.sync_lock_path, lock)

    emit(
        {
            "removed": removed_count,
            "warned": warned_count,
            "errors": [],
            "items": emitted_items,
        }
    )


def _sync_update(
    emit: Emitter,
    source: Annotated[
        str | None,
        Parameter(name="--source", help="Sync only the named source."),
    ] = None,
    force: Annotated[
        bool,
        Parameter(name="--force", help="Overwrite local modifications and unmanaged files."),
    ] = False,
    dry_run: Annotated[
        bool,
        Parameter(name="--dry-run", help="Preview sync changes without writing."),
    ] = False,
    prune: Annotated[
        bool,
        Parameter(name="--prune", help="Remove orphaned managed content."),
    ] = False,
) -> None:
    _run_sync(emit, source=source, force=force, dry_run=dry_run, prune=prune, upgrade=False)


def _sync_upgrade(
    emit: Emitter,
    source: Annotated[
        str | None,
        Parameter(name="--source", help="Sync only the named source."),
    ] = None,
    force: Annotated[
        bool,
        Parameter(name="--force", help="Overwrite local modifications and unmanaged files."),
    ] = False,
    dry_run: Annotated[
        bool,
        Parameter(name="--dry-run", help="Preview sync changes without writing."),
    ] = False,
    prune: Annotated[
        bool,
        Parameter(name="--prune", help="Remove orphaned managed content."),
    ] = False,
) -> None:
    _run_sync(emit, source=source, force=force, dry_run=dry_run, prune=prune, upgrade=True)


def _sync_status(emit: Emitter) -> None:
    repo_root = resolve_repo_root()
    state_paths = resolve_state_paths(repo_root)
    config = load_sync_config(state_paths.config_path)
    configured_sources = {source.name for source in config.sources}
    lock = read_lock_file(state_paths.sync_lock_path)

    payload: list[dict[str, object]] = []
    for item_key, entry in sorted(lock.items.items()):
        dest_path = repo_root / entry.dest_path
        if entry.source_name not in configured_sources:
            status = "orphaned"
            reason = "Source is no longer configured."
        elif not _path_exists(dest_path):
            status = "missing"
            reason = "Managed item is missing locally."
        else:
            local_hash = compute_item_hash(dest_path, entry.item_kind)
            if local_hash == entry.tree_hash:
                status = "in-sync"
                reason = "Local content matches the lock file."
            else:
                status = "locally-modified"
                reason = "Local content differs from the lock file."

        payload.append(
            {
                "key": item_key,
                "status": status,
                "reason": reason,
                "source_name": entry.source_name,
                "item_kind": entry.item_kind,
                "dest_path": entry.dest_path,
            }
        )

    emit(payload)


def register_sync_commands(app: Any, emit: Emitter) -> None:
    """Register sync subcommands onto the given app."""

    app.command(
        partial(_sync_install, emit),
        name="install",
        help="Add a source and install its items.",
    )
    app.command(
        partial(_sync_remove, emit),
        name="remove",
        help="Remove a source and its managed items.",
    )
    app.command(
        partial(_sync_update, emit),
        name="update",
        help="Sync from lock file (reproducible).",
    )
    app.command(
        partial(_sync_upgrade, emit),
        name="upgrade",
        help="Re-resolve refs to latest upstream.",
    )
    app.command(
        partial(_sync_status, emit),
        name="status",
        help="Compare lock vs local files.",
    )


def _run_sync(
    emit: Emitter,
    *,
    source: str | None,
    force: bool,
    dry_run: bool,
    prune: bool,
    upgrade: bool,
) -> None:
    repo_root = resolve_repo_root()
    state_paths = resolve_state_paths(repo_root)
    config = load_sync_config(state_paths.config_path)

    with lock_file_guard(state_paths.sync_lock_path):
        lock = read_lock_file(state_paths.sync_lock_path)
        locked_commits = {
            entry.source_name: entry.locked_commit
            for entry in lock.items.values()
        }
        result = sync_items(
            repo_root=repo_root,
            sources=config.sources,
            sync_cache_dir=state_paths.sync_cache_dir,
            sync_lock_path=state_paths.sync_lock_path,
            locked_commits=locked_commits,
            upgrade=upgrade,
            force=force,
            dry_run=dry_run,
            prune=prune,
            source_filter=source,
        )

    emit(_sync_result_payload(result))


def _sync_result_payload(result: SyncResult) -> dict[str, object]:
    counts = Counter(action.action for action in result.actions)
    return {
        "installed": counts["installed"],
        "updated": counts["updated"] + counts["reinstalled"],
        "reinstalled": counts["reinstalled"],
        "skipped": counts["skipped"],
        "conflicts": counts["conflict"],
        "removed": counts["removed"],
        "orphaned": counts["orphan_warned"],
        "errors": list(result.errors),
        "items": [_action_payload(action) for action in result.actions],
    }


def _action_payload(action: SyncItemAction) -> dict[str, object]:
    return {
        "key": action.item_key,
        "item_kind": action.item_kind,
        "source_name": action.source_name,
        "action": action.action,
        "reason": action.reason,
        "dest_path": action.dest_path,
    }


def _classify_source(source: str, *, repo_root: Path) -> Literal["repo", "path"]:
    trimmed = source.strip()
    candidate = Path(trimmed).expanduser()
    if candidate.is_absolute() or trimmed.startswith((".", "~")):
        return "path"
    if candidate.exists() or (repo_root / candidate).exists():
        return "path"
    if trimmed.count("/") == 1:
        return "repo"
    return "path"


def _derive_source_name(source: str, selector: Literal["repo", "path"]) -> str:
    if selector == "repo":
        owner, _, repo = source.strip().partition("/")
        return f"{owner}-{repo}"

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


def _local_name_for_entry(item_kind: ItemKind, dest_path: Path) -> str:
    if item_kind == "skill":
        return dest_path.name
    return dest_path.stem


def _claude_path_for_item(repo_root: Path, item_kind: ItemKind, local_name: str) -> Path:
    if item_kind == "skill":
        return repo_root / ".claude" / "skills" / local_name
    return repo_root / ".claude" / "agents" / f"{local_name}.md"


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
        return
    path.unlink(missing_ok=True)
