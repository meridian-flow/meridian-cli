"""Space summary and export artifact helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from meridian.lib.space import space_file
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import SpacePaths, resolve_space_dir
from meridian.lib.types import SpaceId


def space_summary_path(repo_root: Path, space_id: SpaceId) -> Path:
    """Return canonical `space-summary.md` path for one space."""

    space_dir = resolve_space_dir(repo_root, space_id)
    return SpacePaths.from_space_dir(space_dir).fs_dir / "space-summary.md"


def _render_summary_markdown(
    record: space_file.SpaceRecord,
    *,
    spawns: list[spawn_store.SpawnRecord],
) -> str:
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = [
        f"# Space Summary: {record.id}",
        "",
        f"- Generated: {timestamp}",
        f"- Name: {record.name or '(unnamed)'}",
        f"- Total spawns: {len(spawns)}",
        "",
        "## Recent Runs",
    ]

    if spawns:
        for row in reversed(spawns[-20:]):
            lines.append(
                "- "
                f"{row.id} | {row.status} | {row.model or '-'} | "
                f"started {row.started_at or '-'} | "
                f"finished {row.finished_at or '-'}"
            )
    else:
        lines.append("- No spawns yet")

    lines.append("")
    return "\n".join(lines)


def generate_space_summary(
    *,
    repo_root: Path,
    space_id: SpaceId,
) -> Path:
    """Generate a simple markdown summary into the space `fs/` directory."""

    record = space_file.get_space(repo_root, space_id)
    if record is None:
        raise ValueError(f"Space '{space_id}' not found")

    space_dir = resolve_space_dir(repo_root, space_id)
    summary_path = space_summary_path(repo_root, space_id)
    markdown = _render_summary_markdown(record, spawns=spawn_store.list_spawns(space_dir))

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(markdown, encoding="utf-8")
    return summary_path


def collect_space_markdown_artifacts(
    *,
    repo_root: Path,
    space_id: SpaceId,
) -> tuple[Path, ...]:
    """Collect committable markdown artifact paths for one space."""

    space_dir = resolve_space_dir(repo_root, space_id)
    found: dict[str, Path] = {}

    summary = generate_space_summary(repo_root=repo_root, space_id=space_id)
    found[summary.as_posix()] = summary

    for run in spawn_store.list_spawns(space_dir):
        report_path = SpacePaths.from_space_dir(space_dir).spawns_dir / run.id / "report.md"
        if not report_path.is_file():
            continue
        found[report_path.as_posix()] = report_path

    return tuple(found[key] for key in sorted(found))
