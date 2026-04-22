"""Filesystem path helpers for file-authoritative Meridian state."""

import os
import tomllib
import warnings
from pathlib import Path
from typing import Self, cast

from pydantic import BaseModel, ConfigDict, ValidationError

from meridian.lib.config.context_config import ContextConfig
from meridian.lib.core.types import SpawnId
from meridian.lib.state.atomic import atomic_write_text
from meridian.lib.state.user_paths import (
    get_or_create_project_uuid,
    get_project_data_root,
    get_project_uuid,
)

_MERIDIAN_DIR = ".meridian"
_GITIGNORE_CONTENT = (
    "# Ignore everything by default\n"
    "*\n"
    "\n"
    "# Track .gitignore itself\n"
    "!.gitignore\n"
    "\n"
    "# Track project identity\n"
    "!id\n"
    "\n"
    "# Track shared project state\n"
    "!kb/\n"
    "!kb/**\n"
    "!work/\n"
    "!work/**\n"
    "!archive/\n"
    "!archive/**\n"
)
_REQUIRED_GITIGNORE_LINES = (
    "!.gitignore",
    "!id",
    "!kb/",
    "!kb/**",
    "!work/",
    "!work/**",
    "!archive/",
    "!archive/**",
)
_DEPRECATED_GITIGNORE_LINES = (
    "id",
    "# Ignore the project UUID",
    "!fs/",
    "!fs/**",
    "!work-archive/",
    "!work-archive/**",
    "!work-items/",
    "!work-items/**",
    "!agents.toml",
    "!agents.lock",
    "!config.toml",
)


def _is_project_local_root(root_dir: Path) -> bool:
    """Return True when a `.meridian` root belongs to one project root."""

    return root_dir.name == _MERIDIAN_DIR and (root_dir.parent / ".git").exists()


class RuntimePaths(BaseModel):
    """Resolved runtime paths for one Meridian state root.

    This object models runtime state roots (spawn/session indexes and per-spawn
    artifacts). Legacy work-item path fields are still present for transitional
    callers and will be removed when all work-store callers move to project paths.
    """

    model_config = ConfigDict(frozen=True)

    root_dir: Path
    spawns_jsonl: Path
    spawns_flock: Path
    sessions_jsonl: Path
    sessions_flock: Path
    hook_state_json: Path
    session_id_counter: Path
    session_id_counter_flock: Path
    sessions_dir: Path
    kb_dir: Path
    work_dir: Path
    work_archive_dir: Path
    work_items_dir: Path
    work_items_flock: Path
    work_items_rename_intent: Path
    spawns_dir: Path

    @classmethod
    def from_root_dir(cls, root_dir: Path) -> Self:
        """Build state-root-relative paths from an absolute state directory."""

        project_paths: ProjectPaths | None = None
        if _is_project_local_root(root_dir):
            project_paths = resolve_project_paths(root_dir.parent)

        return cls(
            root_dir=root_dir,
            spawns_jsonl=root_dir / "spawns.jsonl",
            spawns_flock=root_dir / "spawns.jsonl.flock",
            sessions_jsonl=root_dir / "sessions.jsonl",
            sessions_flock=root_dir / "sessions.jsonl.flock",
            hook_state_json=root_dir / "hook-state.json",
            session_id_counter=root_dir / "session-id-counter",
            session_id_counter_flock=root_dir / "session-id-counter.flock",
            sessions_dir=root_dir / "sessions",
            kb_dir=(
                project_paths.kb_dir
                if project_paths is not None
                else root_dir / "kb"
            ),
            work_dir=(
                project_paths.work_dir
                if project_paths is not None
                else root_dir / "work"
            ),
            work_archive_dir=(
                project_paths.work_archive_dir
                if project_paths is not None
                else root_dir / "archive" / "work"
            ),
            work_items_dir=root_dir / "work-items",
            work_items_flock=root_dir / "work-items.flock",
            work_items_rename_intent=root_dir / "work-items.rename.intent.json",
            spawns_dir=root_dir / "spawns",
        )


class ProjectPaths(BaseModel):
    """Resolved on-disk Meridian project data paths."""

    model_config = ConfigDict(frozen=True)

    root_dir: Path
    id_file: Path
    kb_dir: Path
    work_dir: Path
    work_archive_dir: Path

    @classmethod
    def from_root_dir(cls, root_dir: Path) -> Self:
        """Build project-data-relative paths from one state directory."""

        return cls(
            root_dir=root_dir,
            id_file=root_dir / "id",
            kb_dir=root_dir / "kb",
            work_dir=root_dir / "work",
            work_archive_dir=root_dir / "archive" / "work",
        )


def _runtime_root_override_value() -> str:
    override = os.getenv("MERIDIAN_PROJECT_ROOT", "").strip()
    if override:
        return override
    # Transitional fallback while callers migrate env var naming.
    return os.getenv("MERIDIAN_STATE_ROOT", "").strip()


def _resolve_project_runtime_root(project_root: Path) -> Path:
    """Resolve runtime root from env override or default `.meridian` location."""

    override = _runtime_root_override_value()
    if not override:
        return project_root / _MERIDIAN_DIR

    candidate = Path(override).expanduser()
    if candidate.is_absolute():
        return candidate
    return project_root / candidate


def _resolve_runtime_state_override(project_root: Path) -> Path | None:
    override = _runtime_root_override_value()
    if not override:
        return None
    candidate = Path(override).expanduser()
    return candidate if candidate.is_absolute() else project_root / candidate


def _context_config_paths(
    project_root: Path,
    *,
    user_config: Path | None = None,
    project_config: Path | None = None,
    local_config: Path | None = None,
) -> tuple[Path | None, Path, Path]:
    from meridian.lib.config.settings import resolve_user_config_path

    return (
        resolve_user_config_path(user_config),
        project_config or (project_root / "meridian.toml"),
        local_config or (project_root / "meridian.local.toml"),
    )


def _load_context_table(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        payload_obj = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid TOML in Meridian config '{path.as_posix()}': {exc}") from exc

    payload = cast("dict[str, object]", payload_obj)
    context = payload.get("context")
    if context is None:
        return None
    if not isinstance(context, dict):
        raise ValueError(
            f"Invalid value for 'context' in '{path.as_posix()}': expected table."
        )
    return cast("dict[str, object]", context)


def _merge_nested_dicts(base: dict[str, object], overrides: dict[str, object]) -> dict[str, object]:
    merged = dict(base)
    for key, value in overrides.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge_nested_dicts(
                cast("dict[str, object]", current),
                cast("dict[str, object]", value),
            )
            continue
        merged[key] = value
    return merged


def resolve_project_paths(project_root: Path) -> ProjectPaths:
    """Resolve project-owned `.meridian/` paths only (ignores runtime overrides)."""

    return resolve_project_paths_from_context(project_root)


def resolve_project_paths_for_write(project_root: Path) -> ProjectPaths:
    """Resolve project-owned paths for write flows.

    If context paths contain ``{project}``, this ensures `.meridian/id` exists
    before path substitution so write callers never materialize literal
    placeholder directories.
    """

    return resolve_project_paths_from_context(project_root, create_project_uuid=True)


def _try_load_context_config(
    project_root: Path,
    *,
    user_config: Path | None = None,
    project_config: Path | None = None,
    local_config: Path | None = None,
) -> ContextConfig | None:
    """Try loading merged context config from user/project/local Meridian config files."""

    merged_context: dict[str, object] = {}
    found_context = False
    for config_path in _context_config_paths(
        project_root,
        user_config=user_config,
        project_config=project_config,
        local_config=local_config,
    ):
        if config_path is None:
            continue
        context_table = _load_context_table(config_path)
        if context_table is None:
            continue
        found_context = True
        merged_context = _merge_nested_dicts(merged_context, context_table)

    if not found_context:
        return None

    try:
        return ContextConfig.model_validate(merged_context)
    except ValidationError as exc:
        raise ValueError(f"Invalid Meridian [context] configuration: {exc}") from exc


def load_context_config(
    project_root: Path,
    *,
    user_config: Path | None = None,
    project_config: Path | None = None,
    local_config: Path | None = None,
) -> ContextConfig | None:
    """Load merged context config for one project, or ``None`` when no [context] exists."""

    return _try_load_context_config(
        project_root,
        user_config=user_config,
        project_config=project_config,
        local_config=local_config,
    )


def resolve_project_paths_from_context(
    project_root: Path,
    context_config: ContextConfig | None = None,
    *,
    create_project_uuid: bool = False,
) -> ProjectPaths:
    """Resolve project paths with optional context config, falling back to defaults."""

    if context_config is None:
        context_config = _try_load_context_config(project_root)

    if context_config is None:
        return ProjectPaths.from_root_dir(project_root / _MERIDIAN_DIR)

    from meridian.lib.context.resolver import (
        context_uses_project_placeholder,
        resolve_context_paths,
    )

    project_state_dir = project_root / _MERIDIAN_DIR
    project_uuid: str | None = None
    if context_uses_project_placeholder(context_config):
        if create_project_uuid:
            project_uuid = get_or_create_project_uuid(project_state_dir)
        else:
            project_uuid = get_project_uuid(project_state_dir)
        if project_uuid is None:
            return ProjectPaths.from_root_dir(project_state_dir)

    resolved = resolve_context_paths(
        project_root,
        context_config,
        project_uuid=project_uuid,
    )
    return ProjectPaths(
        root_dir=project_state_dir,
        id_file=project_state_dir / "id",
        kb_dir=resolved.kb_root,
        work_dir=resolved.work_root,
        work_archive_dir=resolved.work_archive,
    )


def resolve_state_paths(project_root: Path) -> ProjectPaths:
    """Resolve all state paths rooted under `.meridian/`."""

    root_dir = _resolve_project_runtime_root(project_root)
    return ProjectPaths.from_root_dir(root_dir)


def resolve_project_runtime_root(project_root: Path) -> Path:
    """Resolve runtime state root for read paths.

    This helper is read-only: it never creates `.meridian/id`.
    If no runtime UUID exists yet, it falls back to project `.meridian/`.
    """

    runtime_root = resolve_project_runtime_root_or_none(project_root)
    if runtime_root is not None:
        return runtime_root
    return resolve_project_paths(project_root).root_dir


def resolve_project_runtime_root_or_none(project_root: Path) -> Path | None:
    """Resolve runtime state root without mutation.

    Returns None when no project UUID has been initialized yet.
    """

    override = _resolve_runtime_state_override(project_root)
    if override is not None:
        return override

    project_uuid = get_project_uuid(resolve_project_paths(project_root).root_dir)
    if project_uuid is None:
        return None
    return get_project_data_root(project_uuid)


def resolve_project_runtime_root_for_write(project_root: Path) -> Path:
    """Resolve runtime state root for write paths, creating project UUID if needed."""

    override = _resolve_runtime_state_override(project_root)
    if override is not None:
        return override

    project_uuid = get_or_create_project_uuid(resolve_project_paths(project_root).root_dir)
    return get_project_data_root(project_uuid)


def resolve_cache_dir(project_root: Path) -> Path:
    """Return runtime cache directory for a project root."""

    return resolve_project_runtime_root(project_root) / "cache"


def resolve_kb_dir(project_root: Path) -> Path:
    """Return `.meridian/kb/` for a project root."""

    return resolve_project_paths(project_root).kb_dir


def resolve_fs_dir(project_root: Path) -> Path:
    """Deprecated alias for :func:`resolve_kb_dir`."""

    warnings.warn(
        "resolve_fs_dir() is deprecated; use resolve_kb_dir() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return resolve_kb_dir(project_root)


def resolve_work_scratch_dir(runtime_root: Path, work_id: str) -> Path:
    """Return the work-scoped scratch directory for a work item."""

    return RuntimePaths.from_root_dir(runtime_root).work_dir / work_id


def spawn_log_subpath(spawn_id: SpawnId | str) -> Path:
    """Return spawn log path relative to the Meridian state root."""

    return Path("spawns") / str(spawn_id)


def resolve_spawn_log_dir(project_root: Path, spawn_id: SpawnId | str) -> Path:
    """Resolve absolute spawn log directory for a spawn ID."""

    return resolve_project_runtime_root(project_root) / spawn_log_subpath(spawn_id)


def heartbeat_path(runtime_root: Path, spawn_id: SpawnId | str) -> Path:
    """Return heartbeat sentinel path for a spawn under a state root."""

    return RuntimePaths.from_root_dir(runtime_root).spawns_dir / str(spawn_id) / "heartbeat"


def ensure_gitignore(project_root: Path) -> Path:
    """Seed `.meridian/.gitignore` and non-destructively add required tracked entries."""

    meridian_dir = resolve_project_paths(project_root).root_dir
    meridian_dir.mkdir(parents=True, exist_ok=True)
    gitignore_path = meridian_dir / ".gitignore"

    if gitignore_path.exists():
        existing_text = gitignore_path.read_text(encoding="utf-8")
        updated_text = _merge_required_gitignore_lines(existing_text)
        if updated_text != existing_text:
            atomic_write_text(gitignore_path, updated_text)
        return gitignore_path

    atomic_write_text(gitignore_path, _GITIGNORE_CONTENT)
    return gitignore_path


def _merge_required_gitignore_lines(existing_text: str) -> str:
    filtered_lines = [
        line
        for line in existing_text.splitlines()
        if line.strip() not in _DEPRECATED_GITIGNORE_LINES
    ]
    normalized_existing = "\n".join(filtered_lines)
    if existing_text.endswith("\n"):
        normalized_existing += "\n"

    present_lines = {line.strip() for line in filtered_lines}
    missing_lines = [line for line in _REQUIRED_GITIGNORE_LINES if line not in present_lines]
    if not missing_lines:
        return normalized_existing

    suffix = "\n".join(
        [
            "",
            "# Added by Meridian to keep required project state tracked",
            *missing_lines,
            "",
        ]
    )
    if not normalized_existing.endswith("\n"):
        return normalized_existing + suffix
    return normalized_existing + suffix.lstrip("\n")


# Transitional aliases for callers still on pre-rename symbols.
_is_repo_owned_state_root = _is_project_local_root
StatePaths = ProjectPaths
StateRootPaths = RuntimePaths
RepoStatePaths = ProjectPaths
resolve_repo_paths = resolve_project_paths
resolve_repo_state_paths = resolve_project_paths
resolve_repo_paths_from_context = resolve_project_paths_from_context
resolve_repo_state_paths_for_write = resolve_project_paths_for_write
resolve_repo_state_paths_from_context = resolve_project_paths_from_context
resolve_runtime_state_root = resolve_project_runtime_root
resolve_runtime_state_root_or_none = resolve_project_runtime_root_or_none
resolve_runtime_state_root_for_write = resolve_project_runtime_root_for_write
