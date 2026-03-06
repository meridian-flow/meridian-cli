"""Prompt assembly helpers for skills and agent defaults."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from meridian.lib.config.agent import AgentProfile
from meridian.lib.config.skill_registry import SkillRegistry
from meridian.lib.domain import SkillContent

DEFAULT_MODEL = "claude-opus-4-6"


def dedupe_skill_names(names: Iterable[str]) -> tuple[str, ...]:
    """Normalize and de-duplicate skill names while preserving first-seen order."""

    seen: set[str] = set()
    ordered: list[str] = []
    for raw in names:
        normalized = raw.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)


def dedupe_skill_contents(skills: Sequence[SkillContent]) -> tuple[SkillContent, ...]:
    """De-duplicate loaded skill payloads by skill name preserving order."""

    seen: set[str] = set()
    ordered: list[SkillContent] = []
    for skill in skills:
        if skill.name in seen:
            continue
        seen.add(skill.name)
        ordered.append(skill)
    return tuple(ordered)


@dataclass(frozen=True, slots=True)
class SpawnPromptDefaults:
    """Resolved model + agent body + skill names for prompt composition."""

    model: str
    skills: tuple[str, ...]
    agent_body: str
    agent_name: str | None


def resolve_run_defaults(
    requested_model: str,
    *,
    profile: AgentProfile | None,
    default_model: str = DEFAULT_MODEL,
) -> SpawnPromptDefaults:
    """Merge explicit run options with agent-profile defaults."""

    merged = list(dedupe_skill_names(profile.skills)) if profile is not None else []

    resolved_model = requested_model.strip()
    if not resolved_model and profile is not None and profile.model:
        resolved_model = profile.model.strip()
    if not resolved_model:
        resolved_model = default_model
    try:
        from meridian.lib.config.catalog import resolve_model

        catalog_entry = resolve_model(resolved_model)
        resolved_model = str(catalog_entry.model_id)
    except ValueError:
        # Unknown model or ambiguous alias: defer to harness routing validation.
        pass

    return SpawnPromptDefaults(
        model=resolved_model,
        skills=dedupe_skill_names(merged),
        agent_body=profile.body.strip() if profile is not None else "",
        agent_name=profile.name if profile is not None else None,
    )


def load_skill_contents(
    registry: SkillRegistry,
    names: Sequence[str],
) -> tuple[SkillContent, ...]:
    """Load skill contents in deterministic deduplicated order."""

    deduped_names = dedupe_skill_names(names)
    if not deduped_names:
        return ()
    loaded = registry.load(list(deduped_names))
    return dedupe_skill_contents(loaded)
