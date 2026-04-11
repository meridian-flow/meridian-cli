"""Public launch API."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from meridian.lib.harness.registry import HarnessRegistry
    from meridian.lib.launch.command import (
        build_launch_env,
        normalize_system_prompt_passthrough_args,
    )
    from meridian.lib.launch.plan import ResolvedPrimaryLaunchPlan, resolve_primary_launch_plan
    from meridian.lib.launch.process import ProcessOutcome, run_harness_process
    from meridian.lib.launch.resolve import (
        ResolvedPolicies,
        ResolvedSkills,
        load_agent_profile_with_fallback,
        resolve_harness,
        resolve_policies,
        resolve_skills_from_profile,
    )
    from meridian.lib.launch.types import (
        LaunchRequest,
        LaunchResult,
        PrimarySessionMetadata,
        SessionIntent,
        SessionMode,
        build_primary_prompt,
    )


def _resolve_work_id_for_launch(state_root: Path, request: LaunchRequest) -> str | None:
    """Resolve work item before entering the launch layer (policy, not mechanism)."""

    from meridian.lib.ops.work_attachment import ensure_explicit_work_item

    explicit_work_id = (request.work_id or "").strip() or None
    if explicit_work_id is not None:
        return ensure_explicit_work_item(state_root, explicit_work_id)
    return None


def launch_primary(
    *,
    repo_root: Path,
    request: LaunchRequest,
    harness_registry: HarnessRegistry,
) -> LaunchResult:
    """Launch the primary agent process and wait for exit."""

    from .plan import resolve_primary_launch_plan
    from .process import run_harness_process
    from .types import LaunchResult

    plan = resolve_primary_launch_plan(
        repo_root=repo_root,
        request=request,
        harness_registry=harness_registry,
    )

    if request.dry_run:
        return LaunchResult(
            command=plan.command,
            exit_code=0,
            continue_ref=None,
            warning=plan.warning,
        )

    # Resolve work-item attachment at the policy layer (this entry-point
    # function), not inside process.py (the subprocess mechanism layer).
    resolved_work_id = _resolve_work_id_for_launch(plan.state_root, request)
    resolved_plan = plan.model_copy(update={"resolved_work_id": resolved_work_id})

    outcome = run_harness_process(resolved_plan, harness_registry)
    continue_ref = outcome.resolved_harness_session_id.strip() or None

    return LaunchResult(
        command=outcome.command,
        exit_code=outcome.exit_code,
        continue_ref=continue_ref,
        warning=plan.warning,
    )


def __getattr__(name: str) -> Any:
    """Lazily load launch exports to avoid import-time cycles."""

    mapping: dict[str, tuple[str, str]] = {
        "LaunchRequest": (".types", "LaunchRequest"),
        "LaunchResult": (".types", "LaunchResult"),
        "PrimarySessionMetadata": (".types", "PrimarySessionMetadata"),
        "ProcessOutcome": (".process", "ProcessOutcome"),
        "ResolvedPolicies": (".resolve", "ResolvedPolicies"),
        "ResolvedPrimaryLaunchPlan": (".plan", "ResolvedPrimaryLaunchPlan"),
        "ResolvedSkills": (".resolve", "ResolvedSkills"),
        "SessionIntent": (".types", "SessionIntent"),
        "SessionMode": (".types", "SessionMode"),
        "build_launch_env": (".command", "build_launch_env"),
        "build_primary_prompt": (".types", "build_primary_prompt"),
        "load_agent_profile_with_fallback": (".resolve", "load_agent_profile_with_fallback"),
        "normalize_system_prompt_passthrough_args": (
            ".command",
            "normalize_system_prompt_passthrough_args",
        ),
        "resolve_harness": (".resolve", "resolve_harness"),
        "resolve_policies": (".resolve", "resolve_policies"),
        "resolve_primary_launch_plan": (".plan", "resolve_primary_launch_plan"),
        "resolve_skills_from_profile": (".resolve", "resolve_skills_from_profile"),
        "run_harness_process": (".process", "run_harness_process"),
    }
    try:
        module_name, attr_name = mapping[name]
    except KeyError as exc:
        raise AttributeError(name) from exc

    from importlib import import_module

    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


__all__ = [
    "LaunchRequest",
    "LaunchResult",
    "PrimarySessionMetadata",
    "ProcessOutcome",
    "ResolvedPolicies",
    "ResolvedPrimaryLaunchPlan",
    "ResolvedSkills",
    "SessionIntent",
    "SessionMode",
    "build_launch_env",
    "build_primary_prompt",
    "launch_primary",
    "load_agent_profile_with_fallback",
    "normalize_system_prompt_passthrough_args",
    "resolve_harness",
    "resolve_policies",
    "resolve_primary_launch_plan",
    "resolve_skills_from_profile",
    "run_harness_process",
]
