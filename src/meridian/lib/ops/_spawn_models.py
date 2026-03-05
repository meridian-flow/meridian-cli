"""Spawn operation input/output dataclasses and shared lightweight model helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from meridian.lib.domain import SpawnStatus

if TYPE_CHECKING:
    from meridian.lib.formatting import FormatContext


def _empty_template_vars() -> dict[str, str]:
    return {}


@dataclass(frozen=True, slots=True)
class SpawnCreateInput:
    prompt: str = ""
    model: str = ""
    files: tuple[str, ...] = ()
    template_vars: tuple[str, ...] = ()
    agent: str | None = None
    report_path: str = "report.md"
    dry_run: bool = False
    verbose: bool = False
    quiet: bool = False
    stream: bool = False
    background: bool = False
    space: str | None = None
    repo_root: str | None = None
    timeout: float | None = None
    permission_tier: str | None = None
    continue_harness_session_id: str | None = None
    continue_harness: str | None = None
    continue_fork: bool = False


@dataclass(frozen=True, slots=True)
class SpawnActionOutput:
    command: str
    status: str
    spawn_id: str | None = None
    message: str | None = None
    error: str | None = None
    current_depth: int | None = None
    max_depth: int | None = None
    model: str | None = None
    harness_id: str | None = None
    warning: str | None = None
    agent: str | None = None
    reference_files: tuple[str, ...] = ()
    template_vars: dict[str, str] = field(default_factory=_empty_template_vars)
    report_path: str | None = None
    composed_prompt: str | None = None
    cli_command: tuple[str, ...] = ()
    exit_code: int | None = None
    duration_secs: float | None = None
    background: bool = False

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Compact single-line summary for text output mode."""
        # Intentionally omit composed_prompt/cli_command from text output.
        # Background submissions print only the run ID so callers can capture
        # it via R1=$(meridian spawn spawn --background ...).
        if self.background and self.spawn_id is not None and self.status == "running":
            return self.spawn_id
        parts: list[str] = [self.command, self.status]
        if self.spawn_id is not None:
            parts.append(self.spawn_id)
        if self.model is not None:
            parts.append(f"model={self.model}")
        if self.harness_id is not None:
            parts.append(f"harness={self.harness_id}")
        if self.duration_secs is not None:
            parts.append(f"{self.duration_secs:.1f}s")
        if self.exit_code is not None:
            parts.append(f"exit={self.exit_code}")
        if self.message is not None:
            parts.append(self.message)
        if self.error is not None:
            parts.append(f"error={self.error}")
        if self.warning is not None:
            parts.append(f"warning={self.warning}")
        summary = "  ".join(parts)
        # For dry-run, append the full command so it can be copy-pasted.
        if self.status == "dry-run" and self.cli_command:
            import shlex
            summary = f"{summary}\n{shlex.join(self.cli_command)}"
        return summary


@dataclass(frozen=True, slots=True)
class SpawnListInput:
    space: str | None = None
    status: SpawnStatus | None = None
    model: str | None = None
    limit: int = 20
    no_space: bool = False
    failed: bool = False
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class SpawnStatsInput:
    session: str | None = None
    space: str | None = None
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class SpawnStatsOutput:
    total_runs: int
    succeeded: int
    failed: int
    cancelled: int
    running: int
    total_duration_secs: float
    total_cost_usd: float
    models: dict[str, int]

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        lines = [
            f"total_runs: {self.total_runs}",
            f"succeeded: {self.succeeded}",
            f"failed: {self.failed}",
            f"cancelled: {self.cancelled}",
            f"running: {self.running}",
            f"total_duration: {self.total_duration_secs:.1f}s",
            f"total_cost: ${self.total_cost_usd:.4f}",
        ]
        if self.models:
            lines.append("models:")
            for model, count in self.models.items():
                lines.append(f"{model}: {count}")
        else:
            lines.append("models: (none)")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class SpawnListEntry:
    spawn_id: str
    status: str
    model: str
    space_id: str | None
    duration_secs: float | None
    cost_usd: float | None

    def as_row(self) -> list[str]:
        """Return columnar cells for tabular alignment."""
        return [
            self.spawn_id,
            self.status,
            self.model,
            self.space_id if self.space_id is not None else "-",
            f"{self.duration_secs:.1f}s" if self.duration_secs is not None else "-",
            f"${self.cost_usd:.2f}" if self.cost_usd is not None else "-",
        ]


@dataclass(frozen=True, slots=True)
class SpawnListOutput:
    spawns: tuple[SpawnListEntry, ...]

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Columnar list of spawns for text output mode."""
        if not self.spawns:
            return "(no spawns)"
        from meridian.cli.format_helpers import tabular

        return tabular([entry.as_row() for entry in self.spawns])


@dataclass(frozen=True, slots=True)
class SpawnShowInput:
    spawn_id: str
    report: bool = False
    include_files: bool = False
    space: str | None = None
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class SpawnCancelInput:
    spawn_id: str
    space: str | None = None
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class SpawnDetailOutput:
    spawn_id: str
    status: str
    model: str
    harness: str
    space_id: str | None
    started_at: str
    finished_at: str | None
    duration_secs: float | None
    exit_code: int | None
    failure_reason: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    report_path: str | None
    report_summary: str | None
    report: str | None
    files_touched: tuple[str, ...] | None
    last_message: str | None = None
    log_path: str | None = None

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Key-value detail view for text output mode. Omits None/empty fields."""
        from meridian.cli.format_helpers import kv_block

        status_str = self.status
        if self.exit_code is not None:
            status_str += f" (exit {self.exit_code})"

        duration_value: str | None
        if self.duration_secs is None:
            duration_value = None
        elif isinstance(self.duration_secs, int | float):
            duration_value = f"{self.duration_secs:.1f}s"
        else:
            duration_value = str(self.duration_secs)

        cost_value: str | None
        if self.cost_usd is None:
            cost_value = None
        elif isinstance(self.cost_usd, int | float):
            cost_value = f"${self.cost_usd:.4f}"
        else:
            cost_value = str(self.cost_usd)

        pairs: list[tuple[str, str | None]] = [
            ("Spawn", self.spawn_id),
            ("Status", status_str),
            ("Model", f"{self.model} ({self.harness})"),
            ("Duration", duration_value),
            ("Space", self.space_id),
            ("Failure", self.failure_reason),
            ("Cost", cost_value),
            ("Report", self.report_path),
            ("Last message", self.last_message),
            ("Log", self.log_path),
            ("Hint", f"tail -f {self.log_path}" if self.log_path else None),
        ]
        return kv_block(pairs)


@dataclass(frozen=True, slots=True)
class SpawnContinueInput:
    spawn_id: str
    prompt: str
    model: str = ""
    fork: bool = False
    dry_run: bool = False
    timeout: float | None = None
    space: str | None = None
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class SpawnWaitInput:
    spawn_ids: tuple[str, ...] = ()
    # Compatibility alias for MCP clients that still send `spawn_id`.
    spawn_id: str | None = None
    timeout: float | None = None
    poll_interval_secs: float | None = None
    verbose: bool = False
    quiet: bool = False
    report: bool = False
    include_files: bool = False
    space: str | None = None
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class SpawnWaitMultiOutput:
    spawns: tuple[SpawnDetailOutput, ...]
    total_runs: int
    succeeded_runs: int
    failed_runs: int
    cancelled_runs: int
    any_failed: bool
    # Compatibility fields for single-run callers.
    spawn_id: str | None = None
    status: str | None = None
    exit_code: int | None = None

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Summarize waited spawns as a fixed-column table."""
        from meridian.cli.format_helpers import tabular

        rows = [["spawn_id", "status", "duration", "exit"]]
        rows.extend(
            [
                run.spawn_id,
                run.status,
                f"{run.duration_secs:.1f}s" if run.duration_secs is not None else "-",
                str(run.exit_code) if run.exit_code is not None else "-",
            ]
            for run in self.spawns
        )
        return tabular(rows)


@dataclass(frozen=True, slots=True)
class SpawnListFilters:
    """Type-safe run-list filters converted into parameterized SQL."""

    model: str | None = None
    space: str | None = None
    no_space: bool = False
    status: SpawnStatus | None = None
    failed: bool = False
    limit: int = 20
