"""Resolve and render prior spawn context references for spawn prompts."""

import re
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.ops.runtime import resolve_state_root
from meridian.lib.state import spawn_store

from .query import (
    read_report_text,
    read_spawn_row,
    read_written_files,
    resolve_spawn_reference,
)

_SESSION_REF_RE = re.compile(r"^c\d+$")


class SpawnContextRef(BaseModel):
    """Resolved context payload sourced from one prior spawn."""

    model_config = ConfigDict(frozen=True)

    spawn_id: str
    status: str
    agent: str
    desc: str
    model: str
    harness: str
    report_text: str | None = None
    written_files: tuple[str, ...] = ()
    harness_session_id: str | None = None
    chat_id: str | None = None


def _select_spawn_for_session(repo_root: Path, chat_id: str) -> spawn_store.SpawnRecord | None:
    from meridian.lib.state.reaper import reconcile_spawns

    state_root = resolve_state_root(repo_root)
    spawns = reconcile_spawns(
        state_root,
        spawn_store.list_spawns(state_root, filters={"chat_id": chat_id}),
    )
    if not spawns:
        return None

    for row in reversed(spawns):
        if row.status == "succeeded":
            return row
    return spawns[-1]


def _load_report_text(repo_root: Path, spawn_id: str) -> str | None:
    _, report_text = read_report_text(repo_root, spawn_id)
    return report_text


def _load_written_files(repo_root: Path, spawn_id: str) -> tuple[str, ...]:
    try:
        return read_written_files(repo_root, spawn_id)
    except (FileNotFoundError, OSError):
        return ()


def resolve_context_ref(repo_root: Path, ref: str) -> SpawnContextRef:
    """Resolve one --from value to a concrete prior spawn context payload."""

    normalized = ref.strip()
    if not normalized:
        raise ValueError("context reference is required")

    row = None
    if _SESSION_REF_RE.fullmatch(normalized):
        row = _select_spawn_for_session(repo_root, normalized)
        if row is None:
            raise ValueError(f"No spawns found for session '{normalized}'")
    else:
        spawn_id = resolve_spawn_reference(repo_root, normalized)
        row = read_spawn_row(repo_root, spawn_id)
        if row is None:
            raise ValueError(f"Spawn '{spawn_id}' not found")

    return SpawnContextRef(
        spawn_id=row.id,
        status=row.status,
        agent=row.agent or "",
        desc=row.desc or "",
        model=row.model or "",
        harness=row.harness or "",
        report_text=_load_report_text(repo_root, row.id),
        written_files=_load_written_files(repo_root, row.id),
        harness_session_id=row.harness_session_id,
        chat_id=row.chat_id,
    )


def _render_context_ref(ref: SpawnContextRef) -> str:
    status = ref.status or "unknown"
    agent = ref.agent or "n/a"
    desc = ref.desc or "n/a"

    lines = [
        f'<prior-spawn-context spawn="{ref.spawn_id}">',
        f"# Prior spawn: {ref.spawn_id}",
        f"**Status:** {status} | **Agent:** {agent} | **Desc:** {desc}",
        "",
        "## Report",
    ]
    if ref.report_text and ref.report_text.strip():
        lines.append(ref.report_text.strip())
    else:
        lines.append("No report available.")

    if ref.written_files:
        lines.append("")
        lines.append("## Files Modified")
        lines.extend(f"- {path}" for path in ref.written_files)

    lines.append("")
    lines.append("## Explore Further")
    lines.append(f"- Full details: `meridian spawn show {ref.spawn_id} --report`")
    lines.append(f"- Read modified files: `meridian spawn files {ref.spawn_id}`")
    if ref.chat_id and ref.chat_id.strip():
        lines.append(f"- Session transcript: `meridian session log {ref.chat_id}`")
    lines.append("</prior-spawn-context>")
    return "\n".join(lines)


def render_context_refs(refs: Sequence[SpawnContextRef]) -> str:
    """Render resolved --from references as prior-context prompt blocks."""

    if not refs:
        return ""
    return "\n\n".join(_render_context_ref(ref) for ref in refs)


__all__ = ["SpawnContextRef", "render_context_refs", "resolve_context_ref"]
