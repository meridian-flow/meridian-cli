"""Spawn create-input validation and payload preparation helpers."""

from difflib import get_close_matches
from pathlib import Path

import structlog
from pydantic import BaseModel, ConfigDict

from meridian.lib.catalog.models import load_discovered_models, load_merged_aliases, resolve_model
from meridian.lib.config.settings import MeridianConfig
from meridian.lib.core.context import RuntimeContext
from meridian.lib.core.overrides import RuntimeOverrides, resolve
from meridian.lib.core.types import ModelId
from meridian.lib.harness.registry import HarnessRegistry, get_default_harness_registry
from meridian.lib.install.provenance import resolve_runtime_asset_provenance
from meridian.lib.launch.prompt import (
    compose_run_prompt_text,
    compose_skill_injections,
    dedupe_skill_names,
)
from meridian.lib.launch.reference import load_reference_files, parse_template_assignments
from meridian.lib.launch.resolve import (
    ensure_bootstrap_ready,
    resolve_policies,
    resolve_profile_path,
    resolve_skill_paths,
    resolve_skills_from_profile,
)
from meridian.lib.safety.permissions import (
    resolve_permission_pipeline,
)
from meridian.lib.utils.time import minutes_to_seconds

from ..runtime import OperationRuntime, build_runtime, resolve_runtime_root_and_config
from .context_ref import render_context_refs, resolve_context_ref
from .models import SpawnCreateInput
from .plan import ExecutionPolicy, PreparedSpawnPlan, SessionContinuation

logger = structlog.get_logger(__name__)
_DISCOVERED_MODEL_CONTEXT_LIMIT = 12


def merge_warnings(*warnings: str | None) -> str | None:
    """Join non-empty warning strings with consistent separators."""

    parts = [item.strip() for item in warnings if item and item.strip()]
    if not parts:
        return None
    return "; ".join(parts)


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
) -> PreparedSpawnPlan:
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
    bootstrap_plan = ensure_bootstrap_ready(
        repo_root=runtime_view.repo_root,
        configured_default_agent=runtime_view.config.default_agent,
        requested_agent=payload.agent,
        dry_run=payload.dry_run,
        builtin_default_agent="__meridian-subagent",
    )
    cli_overrides = RuntimeOverrides.from_spawn_input(payload)
    env_overrides = RuntimeOverrides.from_env()
    config_overrides = RuntimeOverrides.from_config(runtime_view.config)
    pre_resolved = resolve(cli_overrides, env_overrides, config_overrides)

    policies = resolve_policies(
        repo_root=runtime_view.repo_root,
        overrides=pre_resolved,
        requested_agent=payload.agent,
        config=runtime_view.config,
        harness_registry=runtime_view.harness_registry,
        configured_default_agent=runtime_view.config.default_agent,
        builtin_default_agent="__meridian-subagent",
        configured_default_harness=runtime_view.config.default_harness,
        skills_readonly=payload.dry_run,
    )
    profile = policies.profile
    profile_overrides = RuntimeOverrides.from_agent_profile(profile)
    resolved = resolve(cli_overrides, env_overrides, profile_overrides, config_overrides)

    # Merge profile skills with ad-hoc CLI --skills entries, deduplicating.
    merged_skill_names = dedupe_skill_names(
        (*policies.resolved_skills.skill_names, *payload.skills)
    )
    if payload.skills:
        resolved_skills = resolve_skills_from_profile(
            profile_skills=merged_skill_names,
            repo_root=runtime_view.repo_root,
            readonly=payload.dry_run,
        )
    else:
        resolved_skills = policies.resolved_skills
    harness = policies.adapter
    route_warning = None
    reference_mode = harness.capabilities.reference_input_mode
    prompt_policy = harness.run_prompt_policy()
    use_reference_paths = reference_mode == "paths"
    loaded_references = load_reference_files(
        payload.files,
        base_dir=runtime_view.repo_root,
        include_content=not use_reference_paths,
    )
    parsed_template_vars = parse_template_assignments(payload.template_vars)
    adhoc_agent_payload = (
        harness.build_adhoc_agent_payload(
            name=profile.name,
            description=profile.description,
            prompt=profile.body,
        )
        if profile is not None and harness.capabilities.supports_native_agents
        else ""
    )
    agent_for_params = profile.name if profile is not None else None

    context_from_resolved: tuple[str, ...] = ()
    prior_output: str | None = None
    if payload.context_from:
        resolved_context_refs = tuple(
            resolve_context_ref(runtime_view.repo_root, ref) for ref in payload.context_from
        )
        context_from_resolved = tuple(ref.spawn_id for ref in resolved_context_refs)
        prior_output = render_context_refs(resolved_context_refs)

    composed_prompt = compose_run_prompt_text(
        skills=resolved_skills.loaded_skills if prompt_policy.include_skills else (),
        references=loaded_references,
        user_prompt=payload.prompt,
        agent_body=(profile.body.strip() if profile is not None else "")
        if prompt_policy.include_agent_body
        else "",
        template_variables=parsed_template_vars,
        prior_output=prior_output,
        reference_mode=reference_mode,
    )
    requested_harness_session_id = (payload.continue_harness_session_id or "").strip()
    requested_harness = (payload.continue_harness or "").strip()
    resolved_continue_harness_session_id: str | None = None
    resolved_continue_fork = False
    continuation_warning: str | None = None
    if requested_harness_session_id:
        if requested_harness and requested_harness != str(harness.id):
            continuation_warning = (
                "Continuation session ignored because target harness differs from source run."
            )
        elif not harness.capabilities.supports_session_resume:
            continuation_warning = (
                f"Harness '{harness.id}' does not support session resume; starting fresh."
            )
        else:
            resolved_continue_harness_session_id = requested_harness_session_id
            if payload.continue_fork:
                if harness.capabilities.supports_session_fork:
                    resolved_continue_fork = True
                else:
                    continuation_warning = (
                        f"Harness '{harness.id}' does not support session fork; resuming in-place."
                    )

    missing_skills_warning = (
        f"Skipped unavailable skills: {', '.join(resolved_skills.missing_skills)}."
        if resolved_skills.missing_skills
        else None
    )
    warning = merge_warnings(policies.warning, route_warning, missing_skills_warning)
    warning = merge_warnings(warning, continuation_warning)
    warning = merge_warnings(preflight_warning, warning)
    from meridian.lib.harness.adapter import SpawnParams

    permission_config, resolver = resolve_permission_pipeline(
        sandbox=resolved.sandbox,
        allowed_tools=profile.tools if profile is not None else (),
        approval=resolved.approval or "default",
    )

    appended_system_prompt = None
    if prompt_policy.skill_injection_mode == "append-system-prompt":
        appended_system_prompt = compose_skill_injections(resolved_skills.loaded_skills) or None

    preview_command = tuple(
        harness.build_command(
            SpawnParams(
                prompt=composed_prompt,
                model=ModelId(policies.model) if policies.model else None,
                thinking=resolved.thinking,
                skills=resolved_skills.skill_names,
                agent=agent_for_params,
                adhoc_agent_payload=adhoc_agent_payload,
                repo_root=runtime_view.repo_root.as_posix(),
                mcp_tools=profile.mcp_tools if profile is not None else (),
                continue_harness_session_id=resolved_continue_harness_session_id,
                continue_fork=resolved_continue_fork,
                appended_system_prompt=appended_system_prompt,
                extra_args=payload.passthrough_args,
            ),
            resolver,
        )
    )
    session_agent_path = resolve_profile_path(profile)
    session_skill_paths = resolve_skill_paths(resolved_skills.loaded_skills)
    runtime_provenance = resolve_runtime_asset_provenance(
        repo_root=runtime_view.repo_root,
        agent_path=session_agent_path,
        skill_paths=session_skill_paths,
    )

    return PreparedSpawnPlan(
        model=policies.model,
        harness_id=str(harness.id),
        warning=warning,
        prompt=composed_prompt,
        skills=resolved_skills.skill_names,
        agent_path=session_agent_path,
        agent_source=runtime_provenance.agent_source,
        skill_sources=runtime_provenance.skill_sources,
        bootstrap_required_items=bootstrap_plan.required_items,
        bootstrap_missing_items=bootstrap_plan.missing_items,
        reference_files=tuple(str(reference.path) for reference in loaded_references),
        template_vars=parsed_template_vars,
        context_from_resolved=context_from_resolved,
        mcp_tools=profile.mcp_tools if profile is not None else (),
        agent_name=agent_for_params,
        session_agent=profile.name if profile is not None else "",
        session_agent_path=session_agent_path,
        skill_paths=session_skill_paths,
        adhoc_agent_payload=adhoc_agent_payload,
        cli_command=preview_command,
        passthrough_args=payload.passthrough_args,
        appended_system_prompt=appended_system_prompt,
        autocompact=resolved.autocompact,
        session=SessionContinuation(
            harness_session_id=resolved_continue_harness_session_id,
            continue_fork=resolved_continue_fork,
        ),
        execution=ExecutionPolicy(
            timeout_secs=minutes_to_seconds(payload.timeout),
            kill_grace_secs=minutes_to_seconds(runtime_view.config.kill_grace_minutes) or 0.0,
            max_retries=runtime_view.config.max_retries,
            retry_backoff_secs=runtime_view.config.retry_backoff_seconds,
            permission_config=permission_config,
            permission_resolver=resolver,
            allowed_tools=profile.tools if profile is not None else (),
        ),
    )


__all__ = ["build_create_payload", "validate_create_input"]
