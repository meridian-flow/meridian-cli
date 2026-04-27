"""Policy-resolution stage ownership for launch composition."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from meridian.lib.catalog.agent import AgentModelEntry, AgentProfile
from meridian.lib.catalog.model_aliases import AliasEntry
from meridian.lib.catalog.models import load_merged_aliases
from meridian.lib.catalog.models import resolve_model as resolve_model_entry
from meridian.lib.config.settings import MeridianConfig
from meridian.lib.core.overrides import RuntimeOverrides, resolve
from meridian.lib.core.types import HarnessId
from meridian.lib.harness.adapter import SubprocessHarness
from meridian.lib.harness.registry import HarnessRegistry

from .prompt import dedupe_skill_names
from .resolve import (
    ResolvedSkills,
    load_agent_profile_with_fallback,
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


def _resolve_final_model(
    *,
    layer_model: str | None,
    resolved_entry: AliasEntry | None,
    harness_id: HarnessId,
    config: MeridianConfig,
    project_root: Path,
) -> tuple[str, AliasEntry | None]:
    """Resolve final model string after harness is known."""

    if layer_model:
        if resolved_entry is not None:
            return str(resolved_entry.model_id), resolved_entry
        return layer_model, None

    harness_default = config.default_model_for_harness(str(harness_id))
    fallback_model = harness_default or config.default_model or ""
    if not fallback_model:
        return "", None
    try:
        return fallback_model, resolve_model_entry(fallback_model, project_root=project_root)
    except ValueError:
        return fallback_model, None


def _first_set_layer_index(
    layers: tuple[RuntimeOverrides, ...],
    field_name: str,
) -> int | None:
    for index, layer in enumerate(layers):
        if getattr(layer, field_name) is not None:
            return index
    return None


def _merge_warnings(*warnings: str | None) -> str | None:
    normalized = [warning.strip() for warning in warnings if warning and warning.strip()]
    if not normalized:
        return None
    return "\n".join(normalized)


def _to_alias_map(entries: list[AliasEntry]) -> dict[str, AliasEntry]:
    by_alias: dict[str, AliasEntry] = {}
    for item in entries:
        alias = item.alias.strip()
        if not alias:
            continue
        by_alias[alias] = item
    return by_alias


def _entry_to_overrides(entry: AgentModelEntry) -> RuntimeOverrides:
    return RuntimeOverrides(
        effort=entry.effort,
        autocompact=entry.autocompact,
    )


def _resolve_model_overrides(
    *,
    profile: AgentProfile | None,
    selected_entry: AliasEntry | None,
    alias_catalog: dict[str, AliasEntry],
) -> tuple[RuntimeOverrides, str | None]:
    if profile is None or not profile.models or selected_entry is None:
        return RuntimeOverrides(), None

    selected_alias = selected_entry.alias.strip()
    if selected_alias and selected_alias in profile.models:
        return _entry_to_overrides(profile.models[selected_alias]), None

    selected_model_id = str(selected_entry.model_id)
    if selected_model_id in profile.models:
        return _entry_to_overrides(profile.models[selected_model_id]), None

    matched_keys: list[str] = []
    for key in profile.models:
        catalog_entry = alias_catalog.get(key)
        if catalog_entry is None:
            continue
        if catalog_entry.model_id == selected_entry.model_id:
            matched_keys.append(key)

    if not matched_keys:
        return RuntimeOverrides(), None

    winner = matched_keys[0]
    warning: str | None = None
    if len(matched_keys) > 1:
        warning = (
            f"Agent profile '{profile.name}' has multiple models entries matching "
            f"'{selected_entry.model_id}'. Using '{winner}' and ignoring: "
            f"{', '.join(matched_keys[1:])}."
        )
    return _entry_to_overrides(profile.models[winner]), warning


def _validate_same_layer_harness_override(
    *,
    final_model: str,
    selected_entry: AliasEntry | None,
    harness_id: HarnessId,
    harness_registry: HarnessRegistry,
) -> None:
    supported_primary_harnesses = tuple(
        harness_id_candidate
        for harness_id_candidate in harness_registry.ids()
        if harness_registry.get(harness_id_candidate).capabilities.supports_primary_launch
    )
    supported_primary_set = set(supported_primary_harnesses)
    if harness_id not in supported_primary_set:
        supported_text = ", ".join(str(harness) for harness in supported_primary_harnesses)
        raise ValueError(
            f"Unsupported harness '{harness_id}'. Expected one of: {supported_text}."
        )

    if selected_entry is None:
        return
    if harness_id != selected_entry.harness:
        raise ValueError(
            f"Harness '{harness_id}' is incompatible with model '{final_model}' "
            f"(routes to '{selected_entry.harness}')."
        )


def resolve_policies(
    *,
    project_root: Path,
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
        project_root=project_root,
        requested_agent=requested_agent,
        configured_default=configured_default_agent,
    )
    profile_overrides = RuntimeOverrides.from_agent_profile(profile)
    full_layers = (*layers, profile_overrides, config_overrides)
    resolved = resolve(*full_layers)
    resolved_entry: AliasEntry | None = None
    model_resolution_error: ValueError | None = None
    if resolved.model:
        try:
            resolved_entry = resolve_model_entry(resolved.model, project_root=project_root)
        except ValueError as exc:
            model_resolution_error = exc

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
        if model_resolution_error is not None:
            raise model_resolution_error
        assert resolved_entry is not None
        harness_id = resolved_entry.harness
    else:
        harness_id = HarnessId(configured_default_harness or "claude")

    if resolved.model and model_set_in_pre_profile_layers and harness_from_profile_or_config:
        if model_resolution_error is not None:
            raise model_resolution_error
        assert resolved_entry is not None
        model_derived_harness = resolved_entry.harness
        if harness_id != model_derived_harness:
            harness_id = model_derived_harness

    try:
        adapter = harness_registry.get_subprocess_harness(harness_id)
    except (KeyError, TypeError) as exc:
        supported = ", ".join(str(harness) for harness in harness_registry.ids())
        raise ValueError(
            f"Unknown or unsupported harness '{harness_id}'. Available harnesses: {supported}"
        ) from exc

    final_model, resolved_model_entry = _resolve_final_model(
        layer_model=resolved.model,
        resolved_entry=resolved_entry,
        harness_id=harness_id,
        config=config,
        project_root=project_root,
    )

    user_explicit_same_precedence = (
        model_layer_index is not None
        and harness_layer_index is not None
        and model_layer_index == harness_layer_index
        and model_layer_index < pre_profile_layer_count
    )
    if final_model and user_explicit_same_precedence:
        if model_resolution_error is not None:
            raise model_resolution_error
        _validate_same_layer_harness_override(
            final_model=final_model,
            selected_entry=resolved_model_entry,
            harness_id=harness_id,
            harness_registry=harness_registry,
        )
    selected_entry: AliasEntry | None = resolved_model_entry

    alias_catalog = _to_alias_map(load_merged_aliases(project_root))
    model_overrides, model_warning = _resolve_model_overrides(
        profile=profile,
        selected_entry=selected_entry,
        alias_catalog=alias_catalog,
    )
    alias_defaults = RuntimeOverrides.from_alias_entry(selected_entry)
    profile_effort_overrides = RuntimeOverrides(
        effort=profile_overrides.effort,
        autocompact=profile_overrides.autocompact,
    )
    user_effort_overrides = resolve(*layers, config_overrides)
    effort_resolved = resolve(
        RuntimeOverrides(
            effort=user_effort_overrides.effort,
            autocompact=user_effort_overrides.autocompact,
        ),
        model_overrides,
        profile_effort_overrides,
        alias_defaults,
    )
    resolved = resolved.model_copy(
        update={
            "effort": effort_resolved.effort,
            "autocompact": effort_resolved.autocompact,
        }
    )

    profile_skills: tuple[str, ...] = ()
    if profile is not None:
        profile_skills = dedupe_skill_names(profile.skills)
    resolved_skills = resolve_skills_from_profile(
        profile_skills=profile_skills,
        project_root=project_root,
        readonly=skills_readonly,
    )

    return ResolvedPolicies(
        profile=profile,
        model=final_model,
        harness=harness_id,
        adapter=adapter,
        resolved_skills=resolved_skills,
        resolved_overrides=resolved,
        warning=_merge_warnings(profile_warning, model_warning),
    )


__all__ = ["ResolvedPolicies", "resolve_policies"]
