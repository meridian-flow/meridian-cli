"""Doctor operation for file-authoritative state health and repair."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from meridian.lib.config._paths import resolve_path_list
from meridian.lib.ops._runtime import build_runtime
from meridian.lib.ops.registry import OperationSpec, operation
from meridian.lib.space import space_file
from meridian.lib.space.session_store import cleanup_stale_sessions, list_active_sessions
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_all_spaces_dir

if TYPE_CHECKING:
    from meridian.lib.formatting import FormatContext


@dataclass(frozen=True, slots=True)
class DoctorInput:
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class DoctorOutput:
    ok: bool
    repo_root: str
    spaces_checked: int
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
            ("spaces_checked", str(self.spaces_checked)),
            ("runs_checked", str(self.runs_checked)),
            ("agents_dir", self.agents_dir),
            ("skills_dir", self.skills_dir),
            ("repaired", ", ".join(self.repaired) if self.repaired else "none"),
        ]
        result = kv_block(pairs)
        for warning in self.warnings:
            result += f"\nwarning: {warning}"
        return result


def _space_dirs(repo_root: Path) -> list[Path]:
    spaces_dir = resolve_all_spaces_dir(repo_root)
    if not spaces_dir.is_dir():
        return []
    return [child for child in sorted(spaces_dir.iterdir()) if child.is_dir()]


def _detect_missing_or_corrupt_spaces(repo_root: Path) -> list[str]:
    bad: list[str] = []
    for space_dir in _space_dirs(repo_root):
        if space_file.get_space(repo_root, space_dir.name) is None:
            bad.append(space_dir.name)
    return bad


def _count_runs(repo_root: Path) -> int:
    total = 0
    for space_dir in _space_dirs(repo_root):
        if space_file.get_space(repo_root, space_dir.name) is None:
            continue
        total += len(spawn_store.list_spawns(space_dir))
    return total


def _repair_stale_session_locks(repo_root: Path) -> int:
    repaired = 0
    for space_dir in _space_dirs(repo_root):
        if space_file.get_space(repo_root, space_dir.name) is None:
            continue
        repaired += len(cleanup_stale_sessions(space_dir, repo_root=repo_root))
    return repaired


def _repair_orphan_runs(repo_root: Path) -> int:
    def _background_pid(space_dir: Path, run_id: str) -> int | None:
        pid_path = space_dir / "spawns" / run_id / "background.pid"
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
    for space_dir in _space_dirs(repo_root):
        record = space_file.get_space(repo_root, space_dir.name)
        if record is None:
            continue

        active_sessions = set(list_active_sessions(space_dir))
        for run in spawn_store.list_spawns(space_dir):
            if run.status != "running":
                continue
            pid = _background_pid(space_dir, run.id)
            if pid is not None and _pid_is_alive(pid):
                continue
            if run.chat_id is not None and run.chat_id in active_sessions:
                continue

            spawn_store.finalize_spawn(
                space_dir,
                run.id,
                status="failed",
                exit_code=1,
                error="orphan_run",
            )
            repaired += 1
    return repaired


def _repair_stale_space_status(repo_root: Path) -> int:
    repaired = 0
    for space_dir in _space_dirs(repo_root):
        record = space_file.get_space(repo_root, space_dir.name)
        if record is None:
            continue

        active_sessions = list_active_sessions(space_dir)
        desired = "active" if active_sessions else "closed"
        if record.status != desired:
            space_file.update_space_status(repo_root, record.id, desired)
            repaired += 1
    return repaired


def doctor_sync(payload: DoctorInput) -> DoctorOutput:
    runtime = build_runtime(payload.repo_root)

    repaired: list[str] = []
    stale_locks = _repair_stale_session_locks(runtime.repo_root)
    if stale_locks > 0:
        repaired.append("stale_session_locks")

    # Skip destructive repairs when running as a subagent (MERIDIAN_SPACE_ID set).
    # Subagents should never mark their parent's concurrent spawns as failed
    # or close the parent space.
    if not os.environ.get("MERIDIAN_SPACE_ID"):
        orphan_runs = _repair_orphan_runs(runtime.repo_root)
        if orphan_runs > 0:
            repaired.append("orphan_runs")

        stale_status = _repair_stale_space_status(runtime.repo_root)
        if stale_status > 0:
            repaired.append("stale_space_status")

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

    bad_spaces = _detect_missing_or_corrupt_spaces(runtime.repo_root)
    if bad_spaces:
        warnings.append(
            "Missing/corrupt space.json detected for spaces: " + ", ".join(sorted(bad_spaces))
        )
        repaired.append("missing_or_corrupt_space_json")

    for space_dir in _space_dirs(runtime.repo_root):
        record = space_file.get_space(runtime.repo_root, space_dir.name)
        if record is None:
            continue
        active_sessions = list_active_sessions(space_dir)
        if record.status == "active" and not active_sessions:
            warnings.append(f"Space '{record.id}' is marked active with no live sessions.")

        running = [row.id for row in spawn_store.list_spawns(space_dir) if row.status == "running"]
        if running:
            warnings.append(f"Space '{record.id}' has orphan candidate running spawns: {', '.join(running)}")

    agents_dir = agents_dirs[0] if agents_dirs else runtime.repo_root
    skills_dir = skills_dirs[0] if skills_dirs else runtime.repo_root

    return DoctorOutput(
        ok=not warnings,
        repo_root=runtime.repo_root.as_posix(),
        spaces_checked=len(_space_dirs(runtime.repo_root)),
        runs_checked=_count_runs(runtime.repo_root),
        agents_dir=agents_dir.as_posix(),
        skills_dir=skills_dir.as_posix(),
        warnings=tuple(warnings),
        repaired=tuple(sorted(set(repaired))),
    )


async def doctor(payload: DoctorInput) -> DoctorOutput:
    return await asyncio.to_thread(doctor_sync, payload)


operation(
    OperationSpec[DoctorInput, DoctorOutput](
        name="doctor",
        handler=doctor,
        sync_handler=doctor_sync,
        input_type=DoctorInput,
        output_type=DoctorOutput,
        cli_group="doctor",
        cli_name="doctor",
        mcp_name="doctor",
        description="Spawn diagnostics checks.",
    )
)
