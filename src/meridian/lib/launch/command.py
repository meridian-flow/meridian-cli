"""Command assembly for primary agent launch."""


import logging
import os
import shlex
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from meridian.lib.config.settings import resolve_repo_root
from meridian.lib.config.settings import MeridianConfig, load_config
from meridian.lib.core.context import RuntimeContext
from meridian.lib.harness.adapter import HarnessAdapter, SpawnParams
from meridian.lib.harness.materialize import materialize_for_harness
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.safety.permissions import (
    PermissionConfig,
    build_permission_config,
    build_permission_resolver,
    warn_profile_tier_escalation,
)
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.core.types import ModelId

from .env import (
    build_harness_child_env,
    inherit_child_env,
)
from .prompt import compose_skill_injections, resolve_run_defaults
from .resolve import (
    load_agent_profile_with_fallback,
    resolve_harness,
    resolve_permission_tier_from_profile,
    resolve_skills_from_profile,
)
from .types import LaunchRequest

logger = logging.getLogger(__name__)


class PrimaryHarnessContext(BaseModel):
    command: tuple[str, ...]
    adapter: HarnessAdapter | None = None
    run_params: SpawnParams | None = None
    permission_config: PermissionConfig | None = None

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)


def normalize_system_prompt_passthrough_args(
    passthrough_args: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Extract system-prompt passthroughs and return args without duplicate prompt flags."""

    cleaned: list[str] = []
    prompt_fragments: list[str] = []
    index = 0
    while index < len(passthrough_args):
        token = passthrough_args[index]

        if token in {"--append-system-prompt", "--system-prompt"}:
            if index + 1 >= len(passthrough_args):
                raise ValueError(f"{token} requires a value")
            prompt_fragments.append(passthrough_args[index + 1])
            index += 2
            continue

        if token.startswith("--append-system-prompt="):
            prompt_fragments.append(token.partition("=")[2])
            index += 1
            continue

        if token.startswith("--system-prompt="):
            prompt_fragments.append(token.partition("=")[2])
            index += 1
            continue

        cleaned.append(token)
        index += 1

    return tuple(cleaned), tuple(prompt_fragments)


def build_harness_context(
    *,
    repo_root: Path | None = None,
    request: LaunchRequest,
    prompt: str,
    harness_registry: HarnessRegistry,
    chat_id: str = "",
    config: MeridianConfig | None = None,
) -> PrimaryHarnessContext:
    """Build primary harness command and launch context for one primary session."""

    passthrough_args = request.passthrough_args

    override = os.getenv("MERIDIAN_HARNESS_COMMAND", "").strip()
    if override:
        command = [*shlex.split(override), *passthrough_args]
        if not command:
            raise ValueError("MERIDIAN_HARNESS_COMMAND resolved to an empty command.")
        return PrimaryHarnessContext(command=tuple(command))

    resolved_root = resolve_repo_root(repo_root)
    resolved_config = config if config is not None else load_config(resolved_root)
    profile = load_agent_profile_with_fallback(
        repo_root=resolved_root,
        search_paths=resolved_config.search_paths,
        requested_agent=request.agent,
        configured_default=resolved_config.default_primary_agent,
    )

    default_model = resolved_config.harness.claude
    requested_model = request.model
    if request.harness is not None and request.harness.strip():
        override_default = resolved_config.default_model_for_harness(request.harness)
        if override_default:
            default_model = override_default
            if not requested_model.strip():
                requested_model = override_default

    defaults = resolve_run_defaults(
        requested_model,
        profile=profile,
        default_model=default_model,
    )
    model = ModelId(defaults.model)
    harness = resolve_harness(
        model=model,
        harness_override=request.harness,
        harness_registry=harness_registry,
        repo_root=resolved_root,
    )
    adapter = harness_registry.get(harness)
    resolved_skills = resolve_skills_from_profile(
        profile_skills=defaults.skills,
        repo_root=resolved_root,
        search_paths=resolved_config.search_paths,
        readonly=True,
    )
    if resolved_skills.missing_skills:
        logger.warning(
            "Skipped unavailable skills for primary agent: %s",
            ", ".join(resolved_skills.missing_skills),
        )
    resolved_skill_sources = resolved_skills.skill_sources

    materialization_chat_id = chat_id.strip() or f"tmp-{uuid4().hex[:8]}"
    materialized = materialize_for_harness(
        profile,
        resolved_skill_sources,
        str(harness),
        resolved_root,
        materialization_chat_id,
        dry_run=request.dry_run,
    )

    passthrough_args, passthrough_prompt_fragments = normalize_system_prompt_passthrough_args(
        passthrough_args
    )
    harness_session_id = (
        request.continue_harness_session_id.strip()
        if request.continue_harness_session_id is not None
        else ""
    )
    primary_default_tier = resolved_config.primary.permission_tier
    inferred_tier = resolve_permission_tier_from_profile(
        profile=profile,
        default_tier=primary_default_tier,
        warning_logger=cast(Any, logger),
    )
    permission_tier_override = (
        request.permission_tier.strip()
        if request.permission_tier is not None and request.permission_tier.strip()
        else None
    )
    if permission_tier_override is None:
        warn_profile_tier_escalation(
            profile=profile,
            inferred_tier=inferred_tier,
            default_tier=primary_default_tier,
            warning_logger=cast(Any, logger),
        )
    resolved_tier = permission_tier_override or inferred_tier
    permission_config = build_permission_config(
        resolved_tier,
        approval=request.approval,
        default_tier=primary_default_tier,
    )
    resolver = build_permission_resolver(
        allowed_tools=profile.allowed_tools if profile is not None else (),
        permission_config=permission_config,
        cli_permission_override=permission_tier_override is not None,
    )

    # Let the adapter decide what prompt/skill content to include.
    # Resume launches typically suppress prompt and skill injection.
    is_resume = bool(harness_session_id)
    skill_injection = compose_skill_injections(resolved_skills.loaded_skills) or ""
    policy = adapter.filter_launch_content(
        prompt=prompt,
        skill_injection=skill_injection,
        is_resume=is_resume,
        harness_session_id=harness_session_id,
    )

    if policy.skill_injection is not None:
        appended_parts = [policy.prompt.strip()]
        appended_parts.extend(
            fragment.strip() for fragment in passthrough_prompt_fragments if fragment.strip()
        )
        if policy.skill_injection:
            appended_parts.append(policy.skill_injection)
        appended_prompt = "\n\n".join(part for part in appended_parts if part)
        appended_system_prompt = appended_prompt if appended_prompt else None
    else:
        appended_prompt = policy.prompt
        appended_system_prompt = None

    run_params = SpawnParams(
        prompt=appended_prompt,
        model=model,
        skills=resolved_skills.skill_names,
        agent=materialized.agent_name or None,
        extra_args=passthrough_args,
        repo_root=resolved_root.as_posix(),
        mcp_tools=profile.mcp_tools if profile is not None else (),
        interactive=True,
        continue_harness_session_id=harness_session_id or None,
        appended_system_prompt=appended_system_prompt,
    )
    command = tuple(adapter.build_command(run_params, resolver))
    return PrimaryHarnessContext(
        command=command,
        adapter=adapter,
        run_params=run_params,
        permission_config=permission_config,
    )


def build_harness_command(
    *,
    repo_root: Path,
    request: LaunchRequest,
    prompt: str,
    harness_registry: HarnessRegistry,
    chat_id: str = "",
    config: MeridianConfig | None = None,
) -> tuple[str, ...]:
    resolved_config = config if config is not None else load_config(repo_root)
    return build_harness_context(
        repo_root=repo_root,
        request=request,
        prompt=prompt,
        harness_registry=harness_registry,
        chat_id=chat_id,
        config=resolved_config,
    ).command


def build_launch_env(
    repo_root: Path,
    request: LaunchRequest,
    *,
    chat_id: str | None = None,
    default_autocompact_pct: int | None = None,
    spawn_id: str | None = None,
    harness_context: PrimaryHarnessContext | None = None,
) -> dict[str, str]:
    current_context = RuntimeContext.from_environment()
    resolved_chat_id = (
        chat_id.strip() if chat_id is not None and chat_id.strip() else current_context.chat_id
    )
    runtime_context = RuntimeContext(
        depth=current_context.depth,
        repo_root=repo_root.resolve(),
        state_root=resolve_state_paths(repo_root).root_dir.resolve(),
        chat_id=resolved_chat_id,
    )
    env_overrides = runtime_context.to_env_overrides()
    if spawn_id is not None and spawn_id.strip():
        env_overrides["MERIDIAN_SPAWN_ID"] = spawn_id.strip()
    autocompact_pct = (
        request.autocompact
        if request.autocompact is not None
        else default_autocompact_pct
    )
    if autocompact_pct is not None:
        env_overrides["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] = str(autocompact_pct)

    if (
        harness_context is not None
        and harness_context.adapter is not None
        and harness_context.run_params is not None
        and harness_context.permission_config is not None
    ):
        return build_harness_child_env(
            base_env=os.environ,
            adapter=harness_context.adapter,
            run_params=harness_context.run_params,
            permission_config=harness_context.permission_config,
            runtime_env_overrides=env_overrides,
        )

    return inherit_child_env(
        base_env=os.environ,
        env_overrides=env_overrides,
    )


__all__ = [
    "PrimaryHarnessContext",
    "build_harness_command",
    "build_harness_context",
    "build_launch_env",
    "normalize_system_prompt_passthrough_args",
]
