"""Claude-only preflight helpers owned by the Claude adapter."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import cast

import structlog

from meridian.lib.launch.text_utils import dedupe_nonempty

logger = structlog.get_logger(__name__)

# Internal sentinel consumed by Claude projection; never forwarded to the CLI.
CLAUDE_PARENT_ALLOWED_TOOLS_FLAG = "--meridian-parent-allowed-tools"


def project_slug(repo_root: Path) -> str:
    """Map a repo path to Claude's on-disk project slug format."""

    return re.sub(r"[^a-zA-Z0-9]", "-", str(repo_root.resolve()))


def ensure_claude_session_accessible(
    source_session_id: str,
    source_cwd: Path | None,
    child_cwd: Path,
) -> None:
    """Symlink one source Claude session file into the child's project dir."""

    if source_cwd is None:
        return
    if source_cwd.resolve() == child_cwd.resolve():
        return

    # Validate session ID to prevent path traversal.
    safe_session_id = Path(source_session_id).name
    if (
        safe_session_id != source_session_id
        or "/" in source_session_id
        or ".." in source_session_id
    ):
        return

    claude_projects = Path.home() / ".claude" / "projects"
    source_slug = project_slug(source_cwd)
    child_slug = project_slug(child_cwd)

    source_file = claude_projects / source_slug / f"{safe_session_id}.jsonl"
    if not source_file.exists():
        return

    child_project = claude_projects / child_slug
    child_project.mkdir(parents=True, exist_ok=True)
    target_file = child_project / f"{safe_session_id}.jsonl"
    try:
        os.symlink(source_file, target_file)
    except FileExistsError:
        try:
            if target_file.resolve() != source_file.resolve():
                target_file.unlink()
                os.symlink(source_file, target_file)
        except OSError:
            pass


def read_parent_claude_permissions(execution_cwd: Path) -> tuple[list[str], list[str]]:
    """Read parent Claude settings and return add-dir + allowed-tools payloads."""

    additional_directories: list[str] = []
    allowed_tools: list[str] = []

    settings_dir = execution_cwd / ".claude"
    settings_files = (
        settings_dir / "settings.json",
        settings_dir / "settings.local.json",
    )

    for settings_path in settings_files:
        if not settings_path.exists():
            continue

        try:
            raw_payload = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning(
                "Failed to parse parent Claude settings while forwarding child permissions",
                path=str(settings_path),
            )
            continue

        if not isinstance(raw_payload, dict):
            continue
        payload = cast("dict[str, object]", raw_payload)
        raw_permissions = payload.get("permissions")
        if not isinstance(raw_permissions, dict):
            continue
        permissions = cast("dict[str, object]", raw_permissions)

        raw_additional_directories = permissions.get("additionalDirectories")
        if isinstance(raw_additional_directories, list):
            for directory in cast("list[object]", raw_additional_directories):
                if isinstance(directory, str):
                    additional_directories.append(directory)

        raw_allowed_tools = permissions.get("allow")
        if isinstance(raw_allowed_tools, list):
            for tool in cast("list[object]", raw_allowed_tools):
                if isinstance(tool, str):
                    allowed_tools.append(tool)

    return dedupe_nonempty(additional_directories), dedupe_nonempty(allowed_tools)


def expand_claude_passthrough_args(
    *,
    execution_cwd: Path,
    child_cwd: Path,
    passthrough_args: tuple[str, ...],
) -> tuple[str, ...]:
    """Apply Claude-specific passthrough expansion for child execution."""

    if child_cwd.resolve() == execution_cwd.resolve():
        return passthrough_args

    expanded_args: list[str] = [*passthrough_args, "--add-dir", str(execution_cwd)]
    parent_additional_directories, parent_allowed_tools = read_parent_claude_permissions(
        execution_cwd
    )

    for additional_directory in parent_additional_directories:
        expanded_args.extend(("--add-dir", additional_directory))

    if parent_allowed_tools:
        expanded_args.extend(
            (
                CLAUDE_PARENT_ALLOWED_TOOLS_FLAG,
                ",".join(parent_allowed_tools),
            )
        )

    return tuple(expanded_args)


__all__ = [
    "CLAUDE_PARENT_ALLOWED_TOOLS_FLAG",
    "ensure_claude_session_accessible",
    "expand_claude_passthrough_args",
    "project_slug",
    "read_parent_claude_permissions",
]
