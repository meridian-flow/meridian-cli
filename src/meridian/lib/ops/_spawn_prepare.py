"""Spawn create-input validation and payload preparation helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from difflib import get_close_matches
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from meridian.lib.config.aliases import load_merged_aliases, resolve_model
from meridian.lib.config.discovery import load_discovered_models
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.launch_resolve import (
    load_agent_profile_with_fallback,
    resolve_permission_tier_from_profile,
    resolve_skills_from_profile,
)
from meridian.lib.ops._runtime import OperationRuntime, build_runtime, resolve_runtime_root_and_config
from meridian.lib.prompt import (
    compose_run_prompt_text,
    load_reference_files,
    parse_template_assignments,
    resolve_run_defaults,
)
from meridian.lib.harness.adapter import PermissionResolver
from meridian.lib.safety.permissions import (
    PermissionConfig,
    warn_profile_tier_escalation,
    build_permission_config,
    build_permission_resolver,
    validate_permission_config_for_harness,
)
from meridian.lib.types import ModelId

from ._utils import merge_warnings
from ._spawn_models import SpawnCreateInput

if TYPE_CHECKING:
    from meridian.lib.config.settings import MeridianConfig
    from meridian.lib.harness.registry import HarnessRegistry

logger = structlog.get_logger(__name__)
_DISCOVERED_MODEL_CONTEXT_LIMIT = 12


@dataclass(frozen=True, slots=True)
class _PreparedCreate:
    model: str
    harness_id: str
    warning: str | None
    composed_prompt: str
    skills: tuple[str, ...]
    reference_files: tuple[str, ...]
    template_vars: dict[str, str]
    mcp_tools: tuple[str, ...]
    agent_name: str | None
    session_agent: str
    session_agent_path: str
    skill_paths: tuple[str, ...]
    cli_command: tuple[str, ...]
    permission_config: PermissionConfig
    permission_resolver: PermissionResolver
    allowed_tools: tuple[str, ...]
    continue_harness_session_id: str | None
    continue_fork: bool


@dataclass(frozen=True, slots=True)
class _CreateRuntimeView:
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
        f"{entry.alias} -> {entry.model_id} [{entry.harness}]"
        for entry in aliases
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
            f"Unknown model '{normalized}'. Spawn `meridian models list` to inspect supported models."
        )
        if validation_context:
            message = f"{message}\n{validation_context}"
        raise ValueError(message) from None

    if resolved.alias:
        return str(resolved.model_id), None
    return normalized, None


def _validate_create_input(payload: SpawnCreateInput) -> tuple[SpawnCreateInput, str | None]:
    if not payload.prompt.strip() and not payload.files:
        raise ValueError("prompt required: use --prompt/-p or attach at least one --file/-f.")

    resolved_model, model_warning = _validate_requested_model(
        payload.model,
        repo_root=payload.repo_root,
    )
    if resolved_model and resolved_model != payload.model:
        return replace(payload, model=resolved_model), model_warning
    return payload, model_warning


def _build_create_payload(
    payload: SpawnCreateInput,
    *,
    runtime: OperationRuntime | None = None,
    preflight_warning: str | None = None,
) -> _PreparedCreate:
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

    # Track whether the agent was explicitly requested via --agent flag.
    # Used to suppress noisy permission-escalation warnings for the implicit
    # default agent profile (which normally has sandbox > config default).
    agent_explicitly_requested = bool(payload.agent)

    profile = load_agent_profile_with_fallback(
        repo_root=runtime_view.repo_root,
        search_paths=runtime_view.config.search_paths,
        requested_agent=payload.agent,
        configured_default=runtime_view.config.default_agent,
        fallback_name="agent",
    )

    defaults = resolve_run_defaults(
        payload.model,
        profile=profile,
        default_model=runtime_view.config.default_model,
    )

    resolved_skills = resolve_skills_from_profile(
        profile_skills=defaults.skills,
        repo_root=runtime_view.repo_root,
        search_paths=runtime_view.config.search_paths,
        readonly=payload.dry_run,
    )
    harness, route_warning = runtime_view.harness_registry.route(
        defaults.model,
        repo_root=runtime_view.repo_root,
    )
    reference_mode = harness.capabilities.reference_input_mode
    use_reference_paths = reference_mode == "paths"
    loaded_references = load_reference_files(
        payload.files,
        base_dir=runtime_view.repo_root,
        include_content=not use_reference_paths,
        space_id=payload.space,
    )
    parsed_template_vars = parse_template_assignments(payload.template_vars)
    # --- Native agent passthrough for Claude ---
    # When the harness supports native agents, skip injecting agent body and
    # skill content into the composed prompt. Instead, pass agent name and
    # skill names via SpawnParams so the harness loads them natively.
    # This keeps skills persistent across context compaction.
    native_agents = harness.capabilities.supports_native_agents

    # With --skills removed, skills come exclusively from the agent profile.
    # Native-agent harnesses either use the profile name directly or no agent.
    adhoc_agent_json = ""
    agent_for_params = defaults.agent_name

    composed_prompt = compose_run_prompt_text(
        skills=() if native_agents else resolved_skills.loaded_skills,
        references=loaded_references,
        user_prompt=payload.prompt,
        agent_body="" if native_agents else defaults.agent_body,
        template_variables=parsed_template_vars,
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
        f"Skipped unavailable implicit skills: {', '.join(resolved_skills.missing_skills)}."
        if resolved_skills.missing_skills
        else None
    )
    warning = merge_warnings(route_warning, missing_skills_warning)
    warning = merge_warnings(warning, continuation_warning)
    warning = merge_warnings(preflight_warning, warning)
    from meridian.lib.harness.adapter import SpawnParams

    inferred_tier = resolve_permission_tier_from_profile(
        profile=profile,
        default_tier=runtime_view.config.default_permission_tier,
    )
    # Only warn about tier escalation when the user explicitly chose an
    # agent via --agent.  The implicit default agent profile often has
    # sandbox > config default (e.g. workspace-write vs read-only), and
    # warning every time is noise for normal configurations.
    if payload.permission_tier is None and agent_explicitly_requested:
        warn_profile_tier_escalation(
            profile=profile,
            inferred_tier=inferred_tier,
            default_tier=runtime_view.config.default_permission_tier,
            warning_logger=logger,
        )
    permission_config = build_permission_config(
        payload.permission_tier or inferred_tier,
        approval="confirm",
        default_tier=runtime_view.config.default_permission_tier,
    )
    warning = merge_warnings(
        warning,
        validate_permission_config_for_harness(
            harness_id=harness.id,
            config=permission_config,
        ),
    )
    resolver = build_permission_resolver(
        allowed_tools=profile.allowed_tools if profile is not None else (),
        permission_config=permission_config,
        cli_permission_override=payload.permission_tier is not None,
    )

    # Claude loads skills natively via --agent; no explicit injection needed.
    appended_system_prompt = None

    preview_command = tuple(
        harness.build_command(
            SpawnParams(
                prompt=composed_prompt,
                model=ModelId(defaults.model),
                skills=resolved_skills.skill_names,
                agent=agent_for_params,
                adhoc_agent_json=adhoc_agent_json,
                repo_root=runtime_view.repo_root.as_posix(),
                mcp_tools=profile.mcp_tools if profile is not None else (),
                continue_harness_session_id=resolved_continue_harness_session_id,
                continue_fork=resolved_continue_fork,
                appended_system_prompt=appended_system_prompt,
            ),
            resolver,
        )
    )
    session_agent_path = ""
    if profile is not None and profile.path.is_absolute() and profile.path.exists():
        session_agent_path = profile.path.resolve().as_posix()
    session_skill_paths = tuple(
        Path(skill.path).expanduser().resolve().as_posix()
        for skill in resolved_skills.loaded_skills
    )

    return _PreparedCreate(
        model=defaults.model,
        harness_id=str(harness.id),
        warning=warning,
        composed_prompt=composed_prompt,
        skills=resolved_skills.skill_names,
        reference_files=tuple(str(reference.path) for reference in loaded_references),
        template_vars=parsed_template_vars,
        mcp_tools=profile.mcp_tools if profile is not None else (),
        agent_name=agent_for_params,
        session_agent=profile.name if profile is not None else "",
        session_agent_path=session_agent_path,
        skill_paths=session_skill_paths,
        cli_command=preview_command,
        permission_config=permission_config,
        permission_resolver=resolver,
        allowed_tools=profile.allowed_tools if profile is not None else (),
        continue_harness_session_id=resolved_continue_harness_session_id,
        continue_fork=resolved_continue_fork,
    )
