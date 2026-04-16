"""Policy-resolution stage ownership for launch composition."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from meridian.lib.catalog.agent import AgentProfile
from meridian.lib.config.settings import MeridianConfig
from meridian.lib.core.overrides import RuntimeOverrides, resolve
from meridian.lib.core.types import HarnessId, ModelId
from meridian.lib.harness.adapter import SubprocessHarness
from meridian.lib.harness.registry import HarnessRegistry

from .prompt import dedupe_skill_names
from .resolve import (
    ResolvedSkills,
    load_agent_profile_with_fallback,
    resolve_harness,
    resolve_skills_from_profile,
)


@dataclass(frozen=True)
class ResolvedPolicies:
    profile: AgentProfile | None
    model: str
    harness: HarnessId
    adapter: SubprocessHarness
    resolved_skills: ResolvedSkills
    resolved_overrides: RuntimeOverrides
    warning: str | None = None


def _derive_harness_from_model(model_str: str, *, repo_root: Path) -> HarnessId:
    """Derive harness from model when no layer specifies harness."""

    from meridian.lib.catalog.models import resolve_model as resolve_model_entry

    resolved = resolve_model_entry(model_str, repo_root=repo_root)
    return resolved.harness


def _resolve_final_model(
    *,
    layer_model: str | None,
    harness_id: HarnessId,
    config: MeridianConfig,
    repo_root: Path,
) -> str:
    """Resolve final model string after harness is known."""

    from meridian.lib.catalog.models import resolve_model as resolve_model_entry

    if layer_model:
        try:
            catalog_entry = resolve_model_entry(layer_model, repo_root=repo_root)
            return str(catalog_entry.model_id)
        except ValueError:
            return layer_model
    harness_default = config.default_model_for_harness(str(harness_id))
    if harness_default:
        return harness_default
    if config.default_model:
        return config.default_model
    return ""


def _first_set_layer_index(
    layers: tuple[RuntimeOverrides, ...],
    field_name: str,
) -> int | None:
    for index, layer in enumerate(layers):
        if getattr(layer, field_name) is not None:
            return index
    return None


def resolve_policies(
    *,
    repo_root: Path,
    layers: tuple[RuntimeOverrides, ...],
    config_overrides: RuntimeOverrides,
    config: MeridianConfig,
    harness_registry: HarnessRegistry,
    configured_default_harness: str = "claude",
    skills_readonly: bool = True,
) -> ResolvedPolicies:
    """Resolve launch policies (model/harness/skills/profile) for one request."""

    pre_profile_resolved = resolve(*layers, config_overrides)
    requested_agent = resolve(*layers).agent
    configured_default_agent = pre_profile_resolved.agent if not requested_agent else ""

    profile, profile_warning = load_agent_profile_with_fallback(
        repo_root=repo_root,
        requested_agent=requested_agent,
        configured_default=configured_default_agent,
    )
    profile_overrides = RuntimeOverrides.from_agent_profile(profile)
    full_layers = (*layers, profile_overrides, config_overrides)
    resolved = resolve(*full_layers)
    model_layer_index = _first_set_layer_index(full_layers, "model")
    harness_layer_index = _first_set_layer_index(full_layers, "harness")
    pre_profile_layer_count = len(layers)
    model_set_in_pre_profile_layers = (
        model_layer_index is not None and model_layer_index < pre_profile_layer_count
    )
    harness_from_profile_or_config = (
        harness_layer_index is not None and harness_layer_index >= pre_profile_layer_count
    )

    if resolved.harness:
        harness_id = HarnessId(resolved.harness)
    elif resolved.model:
        harness_id = _derive_harness_from_model(resolved.model, repo_root=repo_root)
    else:
        harness_id = HarnessId(configured_default_harness or "claude")

    if resolved.model and model_set_in_pre_profile_layers and harness_from_profile_or_config:
        model_derived_harness = _derive_harness_from_model(resolved.model, repo_root=repo_root)
        if harness_id != model_derived_harness:
            harness_id = model_derived_harness

    try:
        adapter = harness_registry.get_subprocess_harness(harness_id)
    except (KeyError, TypeError) as exc:
        supported = ", ".join(str(harness) for harness in harness_registry.ids())
        raise ValueError(
            f"Unknown or unsupported harness '{harness_id}'. Available harnesses: {supported}"
        ) from exc

    final_model = _resolve_final_model(
        layer_model=resolved.model,
        harness_id=harness_id,
        config=config,
        repo_root=repo_root,
    )

    user_explicit_same_precedence = (
        model_layer_index is not None
        and harness_layer_index is not None
        and model_layer_index == harness_layer_index
        and model_layer_index < pre_profile_layer_count
    )
    if final_model and user_explicit_same_precedence:
        resolve_harness(
            model=ModelId(final_model),
            harness_override=str(harness_id),
            harness_registry=harness_registry,
            repo_root=repo_root,
        )

    profile_skills: tuple[str, ...] = ()
    if profile is not None:
        profile_skills = dedupe_skill_names(profile.skills)
    resolved_skills = resolve_skills_from_profile(
        profile_skills=profile_skills,
        repo_root=repo_root,
        readonly=skills_readonly,
    )

    return ResolvedPolicies(
        profile=profile,
        model=final_model,
        harness=harness_id,
        adapter=adapter,
        resolved_skills=resolved_skills,
        resolved_overrides=resolved,
        warning=profile_warning,
    )


__all__ = ["ResolvedPolicies", "resolve_policies"]
