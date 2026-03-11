"""Spawn operation input/output models and shared lightweight helpers."""


from pydantic import BaseModel, ConfigDict, Field

from meridian.lib.core.domain import SpawnStatus
from meridian.lib.core.util import FormatContext


def _empty_template_vars() -> dict[str, str]:
    return {}


def _truncate_cell(value: str, *, max_chars: int) -> str:
    compact = " ".join(value.split()).strip()
    if len(compact) <= max_chars:
        return compact
    return f"{compact[: max_chars - 3].rstrip()}..."


class SpawnCreateInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    prompt: str = ""
    model: str = ""
    files: tuple[str, ...] = ()
    template_vars: tuple[str, ...] = ()
    agent: str | None = None
    desc: str = ""
    work: str = ""
    dry_run: bool = False
    verbose: bool = False
    quiet: bool = False
    stream: bool = False
    background: bool = False
    repo_root: str | None = None
    timeout: float | None = None
    permission_tier: str | None = None
    continue_harness_session_id: str | None = None
    continue_harness: str | None = None
    continue_fork: bool = False


class SpawnActionOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

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
    template_vars: dict[str, str] = Field(default_factory=_empty_template_vars)
    report: str | None = None
    composed_prompt: str | None = None
    cli_command: tuple[str, ...] = ()
    exit_code: int | None = None
    duration_secs: float | None = None
    background: bool = False

    def to_wire(self) -> dict[str, object]:
        """Project minimal external JSON shape. Omit nulls and input echo."""
        wire: dict[str, object] = {"status": self.status}
        if self.spawn_id is not None:
            wire["spawn_id"] = self.spawn_id
        if self.duration_secs is not None:
            wire["duration_secs"] = round(self.duration_secs, 2)
        if self.report is not None:
            wire["report"] = self.report
        if self.error is not None:
            wire["error"] = self.error
        if self.warning is not None:
            wire["warning"] = self.warning
        if self.exit_code is not None:
            wire["exit_code"] = self.exit_code
        if self.status == "dry-run":
            if self.composed_prompt is not None:
                wire["composed_prompt"] = self.composed_prompt
            if self.cli_command:
                wire["cli_command"] = list(self.cli_command)
        return wire


class SpawnListInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: SpawnStatus | None = None
    statuses: tuple[SpawnStatus, ...] | None = None
    model: str | None = None
    limit: int = 20
    failed: bool = False
    repo_root: str | None = None


class SpawnStatsInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    session: str | None = None
    repo_root: str | None = None


class SpawnStatsOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

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


class SpawnListEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn_id: str
    status: str
    model: str
    duration_secs: float | None
    cost_usd: float | None

    def as_row(self) -> list[str]:
        """Return columnar cells for tabular alignment."""
        return [
            self.spawn_id,
            self.status,
            _truncate_cell(self.model, max_chars=18),
            f"{self.duration_secs:.1f}s" if self.duration_secs is not None else "-",
            f"${self.cost_usd:.2f}" if self.cost_usd is not None else "-",
        ]


class SpawnListOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawns: tuple[SpawnListEntry, ...]
    total_count: int | None = None
    truncated: bool = False

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Columnar list of spawns for text output mode."""
        if not self.spawns:
            return "(no spawns)"
        from meridian.cli.format_helpers import tabular

        rows = [["spawn", "status", "model", "duration", "cost"]]
        rows.extend(entry.as_row() for entry in self.spawns)
        result = tabular(rows)
        if self.truncated and self.total_count is not None:
            result += f"\n({len(self.spawns)} of {self.total_count} shown — use --limit to see more)"
        return result


class SpawnShowInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn_id: str
    report: bool = False
    include_files: bool = False
    repo_root: str | None = None


class SpawnCancelInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn_id: str
    repo_root: str | None = None


class SpawnDetailOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn_id: str
    status: str
    model: str
    harness: str
    work_id: str | None = None
    desc: str | None = None
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
        else:
            duration_value = f"{self.duration_secs:.1f}s"

        cost_value: str | None
        if self.cost_usd is None:
            cost_value = None
        else:
            cost_value = f"${self.cost_usd:.4f}"

        failure_label: str | None = None
        if self.failure_reason is not None:
            failure_label = "Warning" if self.status == "succeeded" else "Failure"

        work_value = (self.work_id or "").strip() or None
        desc_value = (self.desc or "").strip() or None

        pairs: list[tuple[str, str | None]] = [
            ("Spawn", self.spawn_id),
            ("Status", status_str),
            ("Model", f"{self.model} ({self.harness})"),
            ("Duration", duration_value),
            ("Work", work_value),
            ("Desc", desc_value),
            (failure_label or "Failure", self.failure_reason),
            ("Cost", cost_value),
            ("Report", self.report_path),
            ("Last message", self.last_message),
            ("Log", self.log_path),
            ("Hint", f"tail -f {self.log_path}" if self.log_path else None),
        ]
        return kv_block(pairs)


class SpawnFilesInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn_id: str
    repo_root: str | None = None


class SpawnFilesOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn_id: str
    files: tuple[str, ...]

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        if not self.files:
            return ""
        return "\n".join(self.files)


class SpawnContinueInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn_id: str
    prompt: str
    model: str = ""
    agent: str | None = None
    fork: bool = False
    dry_run: bool = False
    timeout: float | None = None
    repo_root: str | None = None


class SpawnWaitInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn_ids: tuple[str, ...] = ()
    # Compatibility alias for MCP clients that still send `spawn_id`.
    spawn_id: str | None = None
    timeout: float | None = None
    poll_interval_secs: float | None = None
    verbose: bool = False
    quiet: bool = False
    report: bool = False
    include_files: bool = False
    repo_root: str | None = None


class SpawnWaitMultiOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

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


class SpawnListFilters(BaseModel):
    model_config = ConfigDict(frozen=True)

    """Type-safe run-list filters converted into parameterized SQL."""

    model: str | None = None
    status: SpawnStatus | None = None
    failed: bool = False
    limit: int = 20


__all__ = [
    "SpawnActionOutput",
    "SpawnCancelInput",
    "SpawnContinueInput",
    "SpawnCreateInput",
    "SpawnDetailOutput",
    "SpawnFilesInput",
    "SpawnFilesOutput",
    "SpawnListEntry",
    "SpawnListFilters",
    "SpawnListInput",
    "SpawnListOutput",
    "SpawnShowInput",
    "SpawnStatsInput",
    "SpawnStatsOutput",
    "SpawnWaitInput",
    "SpawnWaitMultiOutput",
]
