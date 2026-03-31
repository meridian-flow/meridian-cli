"""Spawn operation input/output models and shared lightweight helpers."""

import shlex

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from meridian.lib.core.domain import SpawnStatus
from meridian.lib.core.util import FormatContext
from meridian.lib.ops.spawn.plan import SessionContinuation


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
    context_from: tuple[str, ...] = ()
    template_vars: tuple[str, ...] = ()
    agent: str | None = None
    skills: tuple[str, ...] = ()
    desc: str = ""
    work: str = ""
    dry_run: bool = False
    verbose: bool = False
    quiet: bool = False
    stream: bool = False
    background: bool = False
    repo_root: str | None = None
    timeout: float | None = None
    approval: str | None = None
    autocompact: int | None = None
    effort: str | None = None
    sandbox: str | None = None
    harness: str | None = None
    passthrough_args: tuple[str, ...] = ()
    session: SessionContinuation = SessionContinuation()


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
    agent_path: str | None = None
    agent_source: str | None = None
    skills: tuple[str, ...] = ()
    skill_paths: tuple[str, ...] = ()
    skill_sources: dict[str, str] = Field(default_factory=_empty_template_vars)
    bootstrap_required_items: tuple[str, ...] = ()
    bootstrap_missing_items: tuple[str, ...] = ()
    reference_files: tuple[str, ...] = ()
    template_vars: dict[str, str] = Field(default_factory=_empty_template_vars)
    context_from_resolved: tuple[str, ...] = ()
    report: str | None = None
    composed_prompt: str | None = None
    cli_command: tuple[str, ...] = ()
    exit_code: int | None = None
    duration_secs: float | None = None
    background: bool = False
    forked_from: str | None = None

    def to_wire(self) -> dict[str, object]:
        """Project minimal external JSON shape. Omit nulls and input echo."""
        wire: dict[str, object] = {"status": self.status}
        if self.spawn_id is not None:
            wire["spawn_id"] = self.spawn_id
        if self.forked_from is not None:
            wire["forked_from"] = self.forked_from
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
        if self.context_from_resolved:
            wire["context_from_resolved"] = list(self.context_from_resolved)
        if self.status == "dry-run":
            if self.model is not None:
                wire["model"] = self.model
            if self.harness_id is not None:
                wire["harness_id"] = self.harness_id
            if self.agent is not None:
                wire["agent"] = self.agent
            if self.agent_path is not None:
                wire["agent_path"] = self.agent_path
            if self.agent_source is not None:
                wire["agent_source"] = self.agent_source
            if self.skills:
                wire["skills"] = list(self.skills)
            if self.skill_paths:
                wire["skill_paths"] = list(self.skill_paths)
            if self.skill_sources:
                wire["skill_sources"] = dict(self.skill_sources)
            if self.bootstrap_required_items:
                wire["bootstrap_required_items"] = list(self.bootstrap_required_items)
            if self.bootstrap_missing_items:
                wire["bootstrap_missing_items"] = list(self.bootstrap_missing_items)
            if self.reference_files:
                wire["reference_files"] = list(self.reference_files)
            if self.template_vars:
                wire["template_vars"] = dict(self.template_vars)
            if self.composed_prompt is not None:
                wire["composed_prompt"] = self.composed_prompt
            if self.cli_command:
                wire["cli_command"] = list(self.cli_command)
        return wire

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        lines: list[str] = []
        if self.message:
            lines.append(self.message)
        else:
            lines.append(f"Spawn {self.status}.")
        if self.spawn_id:
            lines.append(f"Spawn id: {self.spawn_id}")
        if self.forked_from:
            lines.append(f"Forked from: {self.forked_from}")
        if self.model and self.harness_id:
            lines.append(f"Model: {self.model} ({self.harness_id})")
        elif self.model:
            lines.append(f"Model: {self.model}")
        if self.error:
            lines.append(f"Error: {self.error}")
        if self.warning:
            lines.append(f"Warning: {self.warning}")
        if self.cli_command:
            lines.append(shlex.join(self.cli_command))
        if self.exit_code is not None:
            lines.append(f"Exit code: {self.exit_code}")
        return "\n".join(lines)


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

    @model_serializer(mode="plain")
    def _serialize(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "spawns": [entry.model_dump() for entry in self.spawns],
            "truncated": self.truncated,
        }
        if self.total_count is not None:
            payload["total_count"] = self.total_count
        return payload

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Columnar list of spawns for text output mode."""
        if not self.spawns:
            return "(no spawns)"
        from meridian.cli.format_helpers import tabular

        rows = [["spawn", "status", "model", "duration", "cost"]]
        rows.extend(entry.as_row() for entry in self.spawns)
        result = tabular(rows)
        if self.truncated and self.total_count is not None:
            result += (
                f"\n({len(self.spawns)} of {self.total_count} shown — use --limit to see more)"
            )
        return result


class SpawnShowInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn_id: str
    include_report_body: bool = True
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
    report_body: str | None
    harness_session_id: str | None = None
    last_message: str | None = None
    log_path: str | None = None

    def _normalized_report_body(self) -> str | None:
        report_text = (self.report_body or "").strip()
        if not report_text:
            return None
        return report_text

    def _report_suffix(self) -> str:
        report_text = self._normalized_report_body()
        if report_text is None:
            return ""
        return f"\n\n{report_text}"

    def report_table_value(self) -> str:
        return self.report_path or "-"

    def report_section(self) -> str | None:
        report_text = self._normalized_report_body()
        if report_text is None:
            return None
        return f"Report for {self.spawn_id}\n{report_text}"

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Key-value detail view for text output mode. Omits None/empty fields."""
        from meridian.cli.format_helpers import kv_block

        status_str = self.status
        if self.exit_code is not None:
            status_str += f" (exit {self.exit_code})"

        duration_value: str | None = (
            None if self.duration_secs is None else f"{self.duration_secs:.1f}s"
        )

        cost_value: str | None = None if self.cost_usd is None else f"${self.cost_usd:.4f}"

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
        return kv_block(pairs) + self._report_suffix()


class SpawnWrittenFilesInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn_id: str
    repo_root: str | None = None


class SpawnWrittenFilesOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn_id: str
    written_files: tuple[str, ...]

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        if not self.written_files:
            return ""
        return "\n".join(self.written_files)


class SpawnContinueInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn_id: str
    prompt: str
    model: str = ""
    agent: str | None = None
    skills: tuple[str, ...] = ()
    fork: bool = False
    dry_run: bool = False
    timeout: float | None = None
    repo_root: str | None = None
    passthrough_args: tuple[str, ...] = ()
    approval: str | None = None


class SpawnWaitInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn_ids: tuple[str, ...] = ()
    # Compatibility alias for MCP clients that still send `spawn_id`.
    spawn_id: str | None = None
    timeout: float | None = None
    poll_interval_secs: float | None = None
    verbose: bool = False
    quiet: bool = False
    include_report_body: bool = False
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
        """Render waited spawns, expanding report content when available."""
        if len(self.spawns) == 1:
            return self.spawns[0].format_text(ctx)

        from meridian.cli.format_helpers import tabular

        rows = [["spawn_id", "status", "duration", "exit", "report"]]
        rows.extend(
            [
                run.spawn_id,
                run.status,
                f"{run.duration_secs:.1f}s" if run.duration_secs is not None else "-",
                str(run.exit_code) if run.exit_code is not None else "-",
                run.report_table_value(),
            ]
            for run in self.spawns
        )
        table = tabular(rows)

        report_sections: list[str] = []
        for run in self.spawns:
            section = run.report_section()
            if section is not None:
                report_sections.append(section)
        if not report_sections:
            return table
        return f"{table}\n\n" + "\n\n".join(report_sections)


__all__ = [
    "SpawnActionOutput",
    "SpawnCancelInput",
    "SpawnContinueInput",
    "SpawnCreateInput",
    "SpawnDetailOutput",
    "SpawnListEntry",
    "SpawnListInput",
    "SpawnListOutput",
    "SpawnShowInput",
    "SpawnStatsInput",
    "SpawnStatsOutput",
    "SpawnWaitInput",
    "SpawnWaitMultiOutput",
    "SpawnWrittenFilesInput",
    "SpawnWrittenFilesOutput",
]
