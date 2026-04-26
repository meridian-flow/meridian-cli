"""Doctor operation for file-authoritative state health and repair."""

import asyncio
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.config.project_root import resolve_project_root
from meridian.lib.core.depth import is_root_side_effect_process
from meridian.lib.core.spawn_lifecycle import is_active_spawn_status
from meridian.lib.core.util import FormatContext
from meridian.lib.harness.ids import HarnessId
from meridian.lib.ops.config import ensure_runtime_state_bootstrap_sync
from meridian.lib.ops.config_surface import build_config_surface
from meridian.lib.ops.mars import check_upgrade_availability, format_upgrade_availability
from meridian.lib.ops.pruning import (
    OrphanProjectDir,
    StaleSpawnArtifact,
    prune_orphan_project_dirs,
    prune_stale_spawn_artifacts,
    scan_orphan_project_dirs,
    scan_stale_spawn_artifacts,
)
from meridian.lib.ops.runtime import resolve_runtime_root
from meridian.lib.state import spawn_store
from meridian.lib.state.session_store import cleanup_stale_sessions
from meridian.lib.state.user_paths import get_user_home


class DoctorInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_root: str | None = None
    prune: bool = False
    global_: bool = False


class DoctorOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    ok: bool
    project_root: str
    runs_checked: int
    agents_dir: str
    skills_dir: str
    orphan_project_dirs: tuple[OrphanProjectDir, ...] = ()
    stale_spawn_artifacts: tuple[StaleSpawnArtifact, ...] = ()
    pruned_orphan_dirs: int = 0
    pruned_spawn_artifacts: int = 0
    warnings: tuple["DoctorWarning", ...] = ()
    repaired: tuple[str, ...] = ()

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Key-value health check output for text output mode."""
        from meridian.lib.core.formatting import kv_block

        status = "ok" if self.ok else "WARNINGS"
        pairs: list[tuple[str, str | None]] = [
            ("ok", status),
            ("project_root", self.project_root),
            ("runs_checked", str(self.runs_checked)),
            ("agents_dir", self.agents_dir),
            ("skills_dir", self.skills_dir),
            ("orphan_project_dirs", str(len(self.orphan_project_dirs))),
            ("stale_spawn_artifacts", str(len(self.stale_spawn_artifacts))),
            ("pruned_orphan_dirs", str(self.pruned_orphan_dirs)),
            ("pruned_spawn_artifacts", str(self.pruned_spawn_artifacts)),
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


def _repair_stale_session_locks(project_root: Path) -> int:
    cleanup = cleanup_stale_sessions(resolve_runtime_root(project_root))
    return len(cleanup.cleaned_ids)


def _repair_orphan_runs(project_root: Path) -> int:
    from meridian.lib.state.reaper import reconcile_spawns

    runtime_root = resolve_runtime_root(project_root)
    spawns = spawn_store.list_spawns(runtime_root)
    running_before = sum(1 for s in spawns if is_active_spawn_status(s.status))
    reconciled = reconcile_spawns(runtime_root, spawns)
    running_after = sum(1 for s in reconciled if is_active_spawn_status(s.status))
    return running_before - running_after


def doctor_sync(payload: DoctorInput) -> DoctorOutput:
    explicit_root = (
        Path(payload.project_root).expanduser().resolve() if payload.project_root else None
    )
    surface = build_config_surface(resolve_project_root(explicit_root))
    project_root = surface.project_root
    ensure_runtime_state_bootstrap_sync(project_root)
    runtime_root = resolve_runtime_root(project_root)
    spawns = spawn_store.list_spawns(runtime_root)
    active_spawn_ids = {
        spawn.id for spawn in spawns if is_active_spawn_status(spawn.status)
    }
    retention_days = surface.resolved_config.state.retention_days
    now = time.time()
    orphan_project_dirs = (
        scan_orphan_project_dirs(get_user_home(), retention_days, now)
        if payload.global_
        else []
    )
    stale_spawn_artifacts = scan_stale_spawn_artifacts(
        runtime_root,
        retention_days,
        active_spawn_ids,
        now,
    )

    pruned_orphan_dirs = 0
    pruned_spawn_artifacts = 0
    repaired: list[str] = []
    if payload.prune:
        pruned_orphan_dirs = prune_orphan_project_dirs(orphan_project_dirs)
        pruned_spawn_artifacts = prune_stale_spawn_artifacts(stale_spawn_artifacts)
        if pruned_orphan_dirs > 0:
            repaired.append("orphan_project_dirs")
        if pruned_spawn_artifacts > 0:
            repaired.append("spawn_artifacts")

    stale_locks = _repair_stale_session_locks(project_root)
    if stale_locks > 0:
        repaired.append("stale_session_locks")

    if is_root_side_effect_process():
        orphan_runs = _repair_orphan_runs(project_root)
        if orphan_runs > 0:
            repaired.append("orphan_runs")

    agents_dir = project_root / ".agents" / "agents"
    skills_dir = project_root / ".agents" / "skills"
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
    if not payload.prune and orphan_project_dirs:
        warnings.append(
            DoctorWarning(
                code="stale_orphan_project_dirs",
                message=(
                    f"{len(orphan_project_dirs)} stale project dir(s) would be pruned "
                    "with --prune --global."
                ),
                payload={
                    "project_uuids": [item.uuid for item in orphan_project_dirs],
                    "paths": [item.path for item in orphan_project_dirs],
                },
            )
        )
    if not payload.prune and stale_spawn_artifacts:
        warnings.append(
            DoctorWarning(
                code="stale_spawn_artifacts",
                message=(
                    f"{len(stale_spawn_artifacts)} stale spawn artifact dir(s) would be "
                    "pruned with --prune."
                ),
                payload={
                    "spawn_ids": [item.spawn_id for item in stale_spawn_artifacts],
                    "paths": [item.path for item in stale_spawn_artifacts],
                },
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

    availability = check_upgrade_availability(project_root)
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

    running = [row.id for row in spawns if is_active_spawn_status(row.status)]
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
        project_root=project_root.as_posix(),
        runs_checked=len(spawns),
        agents_dir=agents_dir.as_posix(),
        skills_dir=skills_dir.as_posix(),
        orphan_project_dirs=tuple(orphan_project_dirs),
        stale_spawn_artifacts=tuple(stale_spawn_artifacts),
        pruned_orphan_dirs=pruned_orphan_dirs,
        pruned_spawn_artifacts=pruned_spawn_artifacts,
        warnings=tuple(warnings),
        repaired=tuple(sorted(set(repaired))),
    )


async def doctor(payload: DoctorInput) -> DoctorOutput:
    return await asyncio.to_thread(doctor_sync, payload)
