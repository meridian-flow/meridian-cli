"""Search operation across file-authoritative Meridian state."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from meridian.lib.config._paths import resolve_repo_root
from meridian.lib.ops.registry import OperationSpec, operation
from meridian.lib.state.paths import resolve_all_spaces_dir, resolve_space_dir

if TYPE_CHECKING:
    from meridian.lib.formatting import FormatContext

_FILE_TYPES = frozenset({"output", "logs", "runs", "sessions"})
_RUN_FILE_NAMES = {
    "output": "output.jsonl",
    "logs": "stderr.log",
}
_SPACE_FILE_NAMES = {
    "runs": "runs.jsonl",
    "sessions": "sessions.jsonl",
}


@dataclass(frozen=True, slots=True)
class GrepInput:
    pattern: str
    space_id: str | None = None
    run_id: str | None = None
    file_type: str | None = None
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class GrepMatch:
    space_id: str
    run_id: str | None
    file: str
    line: int
    text: str


@dataclass(frozen=True, slots=True)
class GrepOutput:
    results: tuple[GrepMatch, ...]
    total: int

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Return line-oriented grep matches."""
        lines: list[str] = []
        for match in self.results:
            prefix = (
                f"{match.space_id}/{match.run_id}/{match.file}"
                if match.run_id is not None
                else f"{match.space_id}/{match.file}"
            )
            lines.append(f"{prefix}:{match.line}: {match.text}")
        return "\n".join(lines)


def _parse_file_types(file_type: str | None) -> tuple[str, ...]:
    if file_type is None:
        return ("output", "logs", "runs", "sessions")
    normalized = file_type.strip().lower()
    if normalized not in _FILE_TYPES:
        allowed = ", ".join(sorted(_FILE_TYPES))
        raise ValueError(f"Unsupported file type '{file_type}'. Expected one of: {allowed}")
    return (normalized,)


def _repo_root(repo_root: str | None) -> Path:
    explicit = Path(repo_root).expanduser().resolve() if repo_root else None
    return resolve_repo_root(explicit)


def _iter_space_dirs(repo_root: Path, spaces_dir: Path, space_id: str | None) -> tuple[Path, ...]:
    if space_id is not None:
        return (resolve_space_dir(repo_root, space_id.strip()),)
    if not spaces_dir.is_dir():
        return ()
    return tuple(child for child in sorted(spaces_dir.iterdir()) if child.is_dir())


def _candidate_files(payload: GrepInput, repo_root: Path, spaces_dir: Path) -> tuple[Path, ...]:
    file_types = _parse_file_types(payload.file_type)
    normalized_space_id = (
        payload.space_id.strip() if payload.space_id is not None and payload.space_id.strip() else None
    )
    normalized_run_id = (
        payload.run_id.strip() if payload.run_id is not None and payload.run_id.strip() else None
    )

    if normalized_run_id and not normalized_space_id:
        raise ValueError("--run requires --space")

    files: list[Path] = []
    for space_dir in _iter_space_dirs(repo_root, spaces_dir, normalized_space_id):
        if normalized_run_id:
            run_dir = space_dir / "runs" / normalized_run_id
            for file_type in file_types:
                file_name = _RUN_FILE_NAMES.get(file_type)
                if file_name is None:
                    continue
                candidate = run_dir / file_name
                if candidate.is_file():
                    files.append(candidate)
            continue

        for file_type in file_types:
            run_file_name = _RUN_FILE_NAMES.get(file_type)
            if run_file_name is not None:
                files.extend(
                    path
                    for path in sorted((space_dir / "runs").glob(f"*/{run_file_name}"))
                    if path.is_file()
                )
                continue
            space_file_name = _SPACE_FILE_NAMES.get(file_type)
            if space_file_name is None:
                continue
            candidate = space_dir / space_file_name
            if candidate.is_file():
                files.append(candidate)

    return tuple(sorted(files))


def _extract_match_meta(file_path: Path, spaces_dir: Path) -> tuple[str, str | None, str]:
    relative = file_path.relative_to(spaces_dir)
    parts = relative.parts
    if len(parts) < 2:
        raise ValueError(f"Unexpected state file path '{file_path.as_posix()}'")

    space_id = parts[0]
    if len(parts) >= 4 and parts[1] == "runs":
        return space_id, parts[2], parts[3]
    return space_id, None, parts[-1]


def grep_sync(payload: GrepInput) -> GrepOutput:
    repo_root = _repo_root(payload.repo_root)
    spaces_dir = resolve_all_spaces_dir(repo_root)
    try:
        matcher = re.compile(payload.pattern)
    except re.error as exc:
        raise ValueError(f"Invalid regex pattern '{payload.pattern}': {exc}") from exc

    results: list[GrepMatch] = []
    for file_path in _candidate_files(payload, repo_root, spaces_dir):
        space_id, run_id, file_name = _extract_match_meta(file_path, spaces_dir)
        with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.rstrip("\n")
                if not matcher.search(line):
                    continue
                results.append(
                    GrepMatch(
                        space_id=space_id,
                        run_id=run_id,
                        file=file_name,
                        line=line_number,
                        text=line.strip(),
                    )
                )

    return GrepOutput(results=tuple(results), total=len(results))


async def grep(payload: GrepInput) -> GrepOutput:
    return await asyncio.to_thread(grep_sync, payload)


operation(
    OperationSpec[GrepInput, GrepOutput](
        name="grep",
        handler=grep,
        sync_handler=grep_sync,
        input_type=GrepInput,
        output_type=GrepOutput,
        cli_group=None,
        cli_name="grep",
        mcp_name="grep",
        description="Search across meridian state files.",
    )
)
