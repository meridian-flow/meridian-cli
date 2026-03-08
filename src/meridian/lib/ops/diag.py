"""Doctor operation for file-authoritative state health and repair."""


import asyncio
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.config.settings import resolve_path_list
from meridian.lib.core.util import FormatContext
from meridian.lib.harness.materialize import cleanup_materialized
from meridian.lib.ops.runtime import build_runtime
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.state.session_store import cleanup_stale_sessions, list_active_sessions


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


def _state_root(repo_root: Path) -> Path:
    return resolve_state_paths(repo_root).root_dir


def _count_runs(repo_root: Path) -> int:
    return len(spawn_store.list_spawns(_state_root(repo_root)))


def _repair_stale_session_locks(repo_root: Path) -> int:
    cleanup = cleanup_stale_sessions(_state_root(repo_root))
    for harness_id, chat_id in cleanup.materialized_scopes:
        cleanup_materialized(harness_id, repo_root, chat_id)
    return len(cleanup.cleaned_ids)


def _repair_orphan_runs(repo_root: Path) -> int:
    state_root = _state_root(repo_root)

    def _background_pid(spawn_id: str) -> int | None:
        pid_path = state_root / "spawns" / spawn_id / "background.pid"
        if not pid_path.is_file():
            return None
        try:
            value = int(pid_path.read_text(encoding="utf-8").strip())
        except ValueError:
            return None
        return value if value > 0 else None

    def _pid_is_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    repaired = 0
    active_sessions = set(list_active_sessions(state_root))
    for run in spawn_store.list_spawns(state_root):
        if run.status != "running":
            continue
        pid = _background_pid(run.id)
        if pid is not None and _pid_is_alive(pid):
            continue
        if run.chat_id is not None and run.chat_id in active_sessions:
            continue

        spawn_store.finalize_spawn(
            state_root,
            run.id,
            status="failed",
            exit_code=1,
            error="orphan_run",
        )
        repaired += 1
    return repaired


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

    search_paths = runtime.config.search_paths
    agents_dirs = resolve_path_list(
        search_paths.agents,
        search_paths.global_agents,
        runtime.repo_root,
    )
    skills_dirs = resolve_path_list(
        search_paths.skills,
        search_paths.global_skills,
        runtime.repo_root,
    )

    warnings: list[str] = []
    if not skills_dirs:
        warnings.append("No configured skills directories were found.")
    if not agents_dirs:
        warnings.append("No configured agent profile directories were found.")

    running = [row.id for row in spawn_store.list_spawns(_state_root(runtime.repo_root)) if row.status == "running"]
    if running:
        warnings.append("Running spawns still present: " + ", ".join(running))

    agents_dir = agents_dirs[0] if agents_dirs else runtime.repo_root
    skills_dir = skills_dirs[0] if skills_dirs else runtime.repo_root

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
