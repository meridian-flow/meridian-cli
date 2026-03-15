"""Doctor operation for file-authoritative state health and repair."""

import asyncio
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.spawn_lifecycle import is_active_spawn_status
from meridian.lib.core.util import FormatContext
from meridian.lib.ops.runtime import build_runtime, resolve_state_root
from meridian.lib.state import spawn_store
from meridian.lib.state.session_store import cleanup_stale_sessions


class DoctorInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_root: str | None = None


class DoctorOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    ok: bool
    repo_root: str
    runs_checked: int
    agents_dir: str
    skills_dir: str
    warnings: tuple[str, ...] = ()
    repaired: tuple[str, ...] = ()

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Key-value health check output for text output mode."""
        from meridian.cli.format_helpers import kv_block

        status = "ok" if self.ok else "WARNINGS"
        pairs: list[tuple[str, str | None]] = [
            ("ok", status),
            ("repo_root", self.repo_root),
            ("runs_checked", str(self.runs_checked)),
            ("agents_dir", self.agents_dir),
            ("skills_dir", self.skills_dir),
            ("repaired", ", ".join(self.repaired) if self.repaired else "none"),
        ]
        result = kv_block(pairs)
        for warning in self.warnings:
            result += f"\nwarning: {warning}"
        return result


def _count_runs(repo_root: Path) -> int:
    return len(spawn_store.list_spawns(resolve_state_root(repo_root)))


def _repair_stale_session_locks(repo_root: Path) -> int:
    cleanup = cleanup_stale_sessions(resolve_state_root(repo_root))
    return len(cleanup.cleaned_ids)


def _repair_orphan_runs(repo_root: Path) -> int:
    from meridian.lib.state.reaper import reconcile_spawns

    state_root = resolve_state_root(repo_root)
    spawns = spawn_store.list_spawns(state_root)
    running_before = sum(1 for s in spawns if is_active_spawn_status(s.status))
    reconciled = reconcile_spawns(state_root, spawns)
    running_after = sum(1 for s in reconciled if is_active_spawn_status(s.status))
    return running_before - running_after


def doctor_sync(payload: DoctorInput) -> DoctorOutput:
    runtime = build_runtime(payload.repo_root)

    repaired: list[str] = []
    stale_locks = _repair_stale_session_locks(runtime.repo_root)
    if stale_locks > 0:
        repaired.append("stale_session_locks")

    if int(os.getenv("MERIDIAN_DEPTH", "0")) <= 0:
        orphan_runs = _repair_orphan_runs(runtime.repo_root)
        if orphan_runs > 0:
            repaired.append("orphan_runs")

    agents_dir = runtime.repo_root / ".agents" / "agents"
    skills_dir = runtime.repo_root / ".agents" / "skills"
    agents_dirs = [agents_dir] if agents_dir.is_dir() else []
    skills_dirs = [skills_dir] if skills_dir.is_dir() else []

    warnings: list[str] = []
    if not skills_dirs:
        warnings.append("No configured skills directories were found.")
    if not agents_dirs:
        warnings.append("No configured agent profile directories were found.")

    running = [
        row.id
        for row in spawn_store.list_spawns(resolve_state_root(runtime.repo_root))
        if is_active_spawn_status(row.status)
    ]
    if running:
        warnings.append("Active spawns still present: " + ", ".join(running))

    return DoctorOutput(
        ok=not warnings,
        repo_root=runtime.repo_root.as_posix(),
        runs_checked=_count_runs(runtime.repo_root),
        agents_dir=agents_dir.as_posix(),
        skills_dir=skills_dir.as_posix(),
        warnings=tuple(warnings),
        repaired=tuple(sorted(set(repaired))),
    )


async def doctor(payload: DoctorInput) -> DoctorOutput:
    return await asyncio.to_thread(doctor_sync, payload)
