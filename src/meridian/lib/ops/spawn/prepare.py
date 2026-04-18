"""Spawn create-input validation and payload preparation helpers."""

from difflib import get_close_matches
from pathlib import Path

import structlog
from pydantic import BaseModel, ConfigDict

from meridian.lib.catalog.models import load_discovered_models, load_merged_aliases, resolve_model
from meridian.lib.config.settings import MeridianConfig
from meridian.lib.core.context import RuntimeContext
from meridian.lib.harness.registry import HarnessRegistry, get_default_harness_registry
from meridian.lib.launch.context import build_launch_context
from meridian.lib.launch.reference import load_reference_files, parse_template_assignments
from meridian.lib.launch.request import (
    ExecutionBudget,
    LaunchArgvIntent,
    LaunchCompositionSurface,
    LaunchRuntime,
    RetryPolicy,
    SessionRequest,
    SpawnRequest,
)
from meridian.lib.utils.time import minutes_to_seconds

from ..runtime import (
    OperationRuntime,
    build_runtime,
    resolve_runtime_root_and_config,
    resolve_state_root,
)
from .models import SpawnCreateInput

logger = structlog.get_logger(__name__)
_DISCOVERED_MODEL_CONTEXT_LIMIT = 12
_DRY_RUN_REPORT_PATH = "<spawn-report-path>"


class _CreateRuntimeView(BaseModel):
    model_config = ConfigDict(frozen=True)

    """Subset of runtime dependencies needed for payload composition."""

    repo_root: Path
    config: MeridianConfig
    harness_registry: HarnessRegistry


def _model_validation_context(
    requested_model: str,
    *,
    repo_root: Path | None,
) -> str:
    aliases = load_merged_aliases(repo_root=repo_root)
    discovered_models = load_discovered_models()
    if not aliases and not discovered_models:
        return ""

    available_aliases = ", ".join(
        f"{entry.alias} -> {entry.model_id} [{entry.harness}]" for entry in aliases
    )

    discovered_model_ids = sorted({model.id for model in discovered_models})
    if len(discovered_model_ids) > _DISCOVERED_MODEL_CONTEXT_LIMIT:
        preview = ", ".join(discovered_model_ids[:_DISCOVERED_MODEL_CONTEXT_LIMIT])
        remaining = len(discovered_model_ids) - _DISCOVERED_MODEL_CONTEXT_LIMIT
        available_discovered_models = f"{preview}, ... (+{remaining} more)"
    else:
        available_discovered_models = ", ".join(discovered_model_ids)

    candidates: list[str] = discovered_model_ids.copy()
    for entry in aliases:
        candidates.append(entry.alias)
        candidates.append(str(entry.model_id))

    suggestion: str | None = None
    close = get_close_matches(requested_model, candidates, n=1, cutoff=0.5)
    if close:
        suggestion = close[0]
    else:
        for candidate in candidates:
            lowered_candidate = candidate.lower()
            lowered_requested = requested_model.lower()
            if lowered_candidate.startswith(lowered_requested) or lowered_requested.startswith(
                lowered_candidate
            ):
                suggestion = candidate
                break

    context_lines: list[str] = []
    if available_aliases:
        context_lines.append(f"Available aliases: {available_aliases}")
    if available_discovered_models:
        context_lines.append(f"Discovered models: {available_discovered_models}")
    if suggestion is not None:
        context_lines.append(f"Did you mean: {suggestion}?")
    return "\n".join(context_lines)


def _validate_requested_model(
    requested_model: str,
    *,
    repo_root: str | None,
) -> tuple[str, str | None]:
    normalized = requested_model.strip()
    if not normalized:
        return "", None

    explicit_root = Path(repo_root).expanduser().resolve() if repo_root else None
    try:
        resolved = resolve_model(normalized, repo_root=explicit_root)
    except ValueError:
        validation_context = _model_validation_context(normalized, repo_root=explicit_root)
        message = (
            f"Unknown model '{normalized}'. Spawn `meridian models list` "
            "to inspect supported models."
        )
        if validation_context:
            message = f"{message}\n{validation_context}"
        raise ValueError(message) from None

    if resolved.alias:
        return str(resolved.model_id), None
    return normalized, None


def validate_create_input(payload: SpawnCreateInput) -> tuple[SpawnCreateInput, str | None]:
    if not payload.prompt.strip() and not payload.files:
        raise ValueError("prompt required: use --prompt/-p or attach at least one --file/-f.")

    resolved_model, model_warning = _validate_requested_model(
        payload.model,
        repo_root=payload.repo_root,
    )
    if resolved_model and resolved_model != payload.model:
        return payload.model_copy(update={"model": resolved_model}), model_warning
    return payload, model_warning


def build_create_payload(
    payload: SpawnCreateInput,
    *,
    runtime: OperationRuntime | None = None,
    preflight_warning: str | None = None,
    ctx: RuntimeContext | None = None,
) -> SpawnRequest:
    _ = ctx
    runtime_view: _CreateRuntimeView
    if runtime is not None:
        runtime_view = _CreateRuntimeView(
            repo_root=runtime.repo_root,
            config=runtime.config,
            harness_registry=runtime.harness_registry,
        )
    elif payload.dry_run:
        repo_root, config = resolve_runtime_root_and_config(payload.repo_root)
        runtime_view = _CreateRuntimeView(
            repo_root=repo_root,
            config=config,
            harness_registry=get_default_harness_registry(),
        )
    else:
        runtime_bundle = build_runtime(payload.repo_root)
        runtime_view = _CreateRuntimeView(
            repo_root=runtime_bundle.repo_root,
            config=runtime_bundle.config,
            harness_registry=runtime_bundle.harness_registry,
        )
    loaded_references = load_reference_files(
        payload.files,
        base_dir=runtime_view.repo_root,
        include_content=False,
    )
    parsed_template_vars = parse_template_assignments(payload.template_vars)
    timeout_secs = minutes_to_seconds(payload.timeout)
    kill_grace_secs = minutes_to_seconds(runtime_view.config.kill_grace_minutes) or 0.0

    raw_request = SpawnRequest(
        prompt=payload.prompt,
        prompt_is_composed=False,
        model=payload.model or None,
        harness=payload.harness,
        agent=payload.agent,
        skills=payload.skills,
        extra_args=payload.passthrough_args,
        sandbox=payload.sandbox,
        approval=payload.approval,
        autocompact=payload.autocompact,
        effort=payload.effort,
        retry=RetryPolicy(
            max_attempts=max(1, runtime_view.config.max_retries + 1),
            backoff_secs=runtime_view.config.retry_backoff_seconds,
        ),
        budget=ExecutionBudget(
            timeout_secs=int(timeout_secs) if timeout_secs is not None else None,
            kill_grace_secs=int(kill_grace_secs),
        ),
        session=SessionRequest(
            continue_chat_id=payload.session.continue_chat_id,
            requested_harness_session_id=(
                (payload.session.requested_harness_session_id or "").strip() or None
            ),
            continue_fork=payload.session.continue_fork,
            source_execution_cwd=payload.session.source_execution_cwd,
            forked_from_chat_id=payload.session.forked_from_chat_id,
            continue_harness=payload.session.continue_harness,
            continue_source_tracked=payload.session.continue_source_tracked,
            continue_source_ref=payload.session.continue_source_ref,
        ),
        context_from=payload.context_from,
        reference_files=tuple(str(reference.path) for reference in loaded_references),
        template_vars=parsed_template_vars,
        work_id_hint=payload.work.strip() or None,
        warning=preflight_warning,
    )

    preview_context = build_launch_context(
        spawn_id="dry-run",
        request=raw_request,
        runtime=LaunchRuntime(
            argv_intent=LaunchArgvIntent.REQUIRED,
            composition_surface=LaunchCompositionSurface.SPAWN_PREPARE,
            config_snapshot=runtime_view.config.model_dump(mode="json", exclude_none=True),
            report_output_path=_DRY_RUN_REPORT_PATH,
            state_root=resolve_state_root(runtime_view.repo_root).as_posix(),
            project_paths_repo_root=runtime_view.repo_root.as_posix(),
            project_paths_execution_cwd=runtime_view.repo_root.as_posix(),
        ),
        harness_registry=runtime_view.harness_registry,
        dry_run=True,
    )
    return preview_context.resolved_request.model_copy(
        update={"cli_command": preview_context.argv}
    )


__all__ = ["build_create_payload", "validate_create_input"]
