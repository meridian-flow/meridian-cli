"""Doctor operation for file-authoritative state health and repair."""

import asyncio
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.config.settings import resolve_project_root
from meridian.lib.core.spawn_lifecycle import is_active_spawn_status
from meridian.lib.core.util import FormatContext
from meridian.lib.harness.ids import HarnessId
from meridian.lib.ops.config import ensure_runtime_state_bootstrap_sync
from meridian.lib.ops.config_surface import build_config_surface
from meridian.lib.ops.mars import check_upgrade_availability, format_upgrade_availability
from meridian.lib.ops.runtime import resolve_state_root
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
    warnings: tuple["DoctorWarning", ...] = ()
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
            result += f"\nwarning: {warning.code}: {warning.message}"
        return result


class DoctorWarning(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    payload: dict[str, object] | None = None


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
    explicit_root = Path(payload.repo_root).expanduser().resolve() if payload.repo_root else None
    surface = build_config_surface(resolve_project_root(explicit_root))
    repo_root = surface.repo_root
    ensure_runtime_state_bootstrap_sync(repo_root)

    repaired: list[str] = []
    stale_locks = _repair_stale_session_locks(repo_root)
    if stale_locks > 0:
        repaired.append("stale_session_locks")

    if int(os.getenv("MERIDIAN_DEPTH", "0")) <= 0:
        orphan_runs = _repair_orphan_runs(repo_root)
        if orphan_runs > 0:
            repaired.append("orphan_runs")

    agents_dir = repo_root / ".agents" / "agents"
    skills_dir = repo_root / ".agents" / "skills"
    agents_dirs = [agents_dir] if agents_dir.is_dir() else []
    skills_dirs = [skills_dir] if skills_dir.is_dir() else []

    warnings: list[DoctorWarning] = []
    if surface.warning is not None:
        warnings.append(
            DoctorWarning(
                code="missing_project_root",
                message=surface.warning,
            )
        )
    for finding in surface.workspace_findings:
        warnings.append(
            DoctorWarning(
                code=finding.code,
                message=finding.message,
                payload=finding.payload,
            )
        )
    codex_workspace_applicability = surface.workspace.applicability.get(HarnessId.CODEX.value)
    if codex_workspace_applicability == "unsupported:requires_config_generation":
        warnings.append(
            DoctorWarning(
                code="workspace_unsupported_harness",
                message=(
                    "Workspace roots cannot be projected to codex yet; "
                    "this harness requires config generation."
                ),
                payload={
                    "harness": HarnessId.CODEX.value,
                    "applicability": codex_workspace_applicability,
                },
            )
        )
    if not skills_dirs:
        warnings.append(
            DoctorWarning(
                code="missing_skills_directories",
                message="No configured skills directories were found.",
            )
        )
    if not agents_dirs:
        warnings.append(
            DoctorWarning(
                code="missing_agent_profile_directories",
                message="No configured agent profile directories were found.",
            )
        )

    availability = check_upgrade_availability(repo_root)
    if availability is None:
        warnings.append(
            DoctorWarning(
                code="updates_check_failed",
                message="Could not check for dependency updates (`mars outdated --json` failed).",
            )
        )
    elif availability.count > 0:
        warning_lines = format_upgrade_availability(availability, style="warning")
        warnings.append(
            DoctorWarning(
                code="outdated_dependencies",
                message="\n".join(warning_lines),
                payload={
                    "within_constraint": list(availability.within_constraint),
                    "beyond_constraint": list(availability.beyond_constraint),
                },
            )
        )

    running = [
        row.id
        for row in spawn_store.list_spawns(resolve_state_root(repo_root))
        if is_active_spawn_status(row.status)
    ]
    if running:
        warnings.append(
            DoctorWarning(
                code="active_spawns_present",
                message="Active spawns still present: " + ", ".join(running),
                payload={"spawn_ids": running},
            )
        )

    return DoctorOutput(
        ok=not warnings,
        repo_root=repo_root.as_posix(),
        runs_checked=_count_runs(repo_root),
        agents_dir=agents_dir.as_posix(),
        skills_dir=skills_dir.as_posix(),
        warnings=tuple(warnings),
        repaired=tuple(sorted(set(repaired))),
    )


async def doctor(payload: DoctorInput) -> DoctorOutput:
    return await asyncio.to_thread(doctor_sync, payload)
