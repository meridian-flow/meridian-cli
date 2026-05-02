"""Agent profile parser for `.mars/agents/*.md`."""

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from meridian.lib.catalog.skill import files_have_equal_text, split_markdown_frontmatter
from meridian.lib.config.project_root import resolve_project_root
from meridian.lib.core.overrides import (
    KNOWN_APPROVAL_VALUES,
    KNOWN_EFFORT_VALUES,
    RuntimeOverrides,
)

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# Re-export under private names for backward compatibility within this module.
_KNOWN_EFFORT_VALUES = KNOWN_EFFORT_VALUES
_KNOWN_APPROVAL_VALUES = KNOWN_APPROVAL_VALUES


class AgentModelEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    effort: str | None = None
    autocompact: int | None = None

    @field_validator("effort")
    @classmethod
    def _validate_effort(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if normalized not in _KNOWN_EFFORT_VALUES:
            raise ValueError(
                f"expected one of {sorted(_KNOWN_EFFORT_VALUES)}"
            )
        return normalized

    @field_validator("autocompact", mode="before")
    @classmethod
    def _reject_bool_autocompact(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("autocompact must be an integer, not a boolean")
        return value

    @field_validator("autocompact")
    @classmethod
    def _validate_autocompact(cls, value: int | None) -> int | None:
        if value is None:
            return None
        return RuntimeOverrides(autocompact=value).autocompact


class AgentProfile(BaseModel):
    """Parsed agent profile with frontmatter defaults + markdown body."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    model: str | None
    harness: str | None = None
    skills: tuple[str, ...]
    tools: tuple[str, ...]
    disallowed_tools: tuple[str, ...]
    mcp_tools: tuple[str, ...]
    sandbox: str | None
    effort: str | None
    approval: str | None = None
    autocompact: int | None = None
    models: Mapping[str, AgentModelEntry] = Field(default_factory=dict)
    body: str
    path: Path
    raw_content: str


def _normalize_string_list(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        normalized = value.strip()
        return (normalized,) if normalized else ()
    if isinstance(value, list):
        values = [str(item).strip() for item in cast("list[object]", value) if str(item).strip()]
        return tuple(values)
    return ()


def _normalize_deduplicated(value: object) -> tuple[str, ...]:
    """Normalize a string list and deduplicate while preserving order."""
    parsed = _normalize_string_list(value)
    seen: set[str] = set()
    result: list[str] = []
    for item in parsed:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return tuple(result)


def _parse_model_overrides(
    raw_models: object,
    *,
    profile_name: str,
) -> dict[str, AgentModelEntry]:
    if raw_models is None:
        return {}
    if not isinstance(raw_models, Mapping):
        logger.warning(
            "Agent profile '%s' has invalid models field: expected mapping.",
            profile_name,
        )
        return {}

    parsed: dict[str, AgentModelEntry] = {}
    for raw_key, raw_value in cast("Mapping[object, object]", raw_models).items():
        key = str(raw_key).strip()
        if not key:
            logger.warning(
                "Agent profile '%s' has empty models key; entry ignored.",
                profile_name,
            )
            continue
        if not isinstance(raw_value, Mapping):
            logger.warning(
                "Agent profile '%s' has invalid models entry for '%s': expected mapping.",
                profile_name,
                key,
            )
            continue
        try:
            parsed[key] = AgentModelEntry.model_validate(raw_value)
        except ValidationError:
            logger.warning(
                "Agent profile '%s' has invalid models entry for '%s'; entry ignored.",
                profile_name,
                key,
            )
    return parsed


def parse_agent_profile(path: Path) -> AgentProfile:
    """Parse a single markdown agent profile file."""

    markdown = path.read_text(encoding="utf-8")
    frontmatter, body = split_markdown_frontmatter(markdown)

    name_value = frontmatter.get("name")
    description_value = frontmatter.get("description")
    model_value = frontmatter.get("model")
    harness_value = frontmatter.get("harness")
    sandbox_value = frontmatter.get("sandbox")
    effort_value = frontmatter.get("effort")
    approval_value = frontmatter.get("approval")
    autocompact_value = frontmatter.get("autocompact")
    models_value = frontmatter.get("models")

    profile_name = str(name_value).strip() if name_value is not None else path.stem
    sandbox = str(sandbox_value).strip() if sandbox_value is not None else None
    effort = str(effort_value).strip() if effort_value is not None else None
    if effort is not None and effort and effort not in _KNOWN_EFFORT_VALUES:
        logger.warning(
            "Agent profile '%s' has unknown effort '%s'.",
            profile_name,
            effort,
        )

    approval = str(approval_value).strip() if approval_value is not None else None
    if approval is not None and approval and approval not in _KNOWN_APPROVAL_VALUES:
        logger.warning(
            "Agent profile '%s' has unknown approval '%s'.",
            profile_name,
            approval,
        )
        approval = None

    autocompact: int | None = None
    if autocompact_value is not None:
        try:
            autocompact = int(str(autocompact_value))
        except (TypeError, ValueError):
            logger.warning(
                "Agent profile '%s' has invalid autocompact '%s': expected int.",
                profile_name,
                autocompact_value,
            )
            autocompact = None
        if autocompact is not None:
            try:
                autocompact = RuntimeOverrides(autocompact=autocompact).autocompact
            except ValueError:
                logger.warning(
                    "Agent profile '%s' has autocompact %d outside valid range.",
                    profile_name,
                    autocompact,
                )
                autocompact = None

    models = _parse_model_overrides(models_value, profile_name=profile_name)

    return AgentProfile(
        name=profile_name,
        description=str(description_value).strip() if description_value is not None else "",
        model=str(model_value).strip() if model_value is not None else None,
        harness=str(harness_value).strip() if harness_value is not None else None,
        skills=_normalize_string_list(frontmatter.get("skills")),
        tools=_normalize_string_list(frontmatter.get("tools")),
        disallowed_tools=_normalize_string_list(frontmatter.get("disallowed-tools")),
        mcp_tools=_normalize_deduplicated(frontmatter.get("mcp-tools")),
        sandbox=sandbox,
        effort=effort,
        approval=approval,
        autocompact=autocompact,
        models=models,
        body=body,
        path=path.resolve(),
        raw_content=markdown,
    )


def _agent_search_dirs(project_root: Path) -> list[Path]:
    return [project_root / ".mars" / "agents"]


def scan_agent_profiles(
    project_root: Path | None = None,
    search_dirs: list[Path] | None = None,
    *,
    search_paths: object | None = None,
) -> list[AgentProfile]:
    """Parse all agent profiles from configured search directories."""

    root = resolve_project_root(project_root)
    _ = search_paths
    directories = search_dirs if search_dirs is not None else _agent_search_dirs(root)
    profiles: list[AgentProfile] = []
    selected_by_name: dict[str, AgentProfile] = {}

    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            profile = parse_agent_profile(path)
            existing = selected_by_name.get(profile.name)
            if existing is not None:
                if files_have_equal_text(existing.path, profile.path):
                    continue
                logger.warning(
                    "Agent profile '%s' found in multiple paths with conflicting content: %s, %s. "
                    "Using %s; conflicting duplicate ignored.",
                    profile.name,
                    existing.path,
                    profile.path,
                    existing.path,
                )
                continue
            selected_by_name[profile.name] = profile
            profiles.append(profile)
    return profiles


def load_agent_profile(
    name: str,
    project_root: Path | None = None,
    *,
    search_paths: object | None = None,
) -> AgentProfile:
    """Load one agent profile by filename stem or frontmatter name."""

    normalized = name.strip()
    if not normalized:
        raise ValueError("Agent profile name must not be empty.")

    root = resolve_project_root(project_root)

    for profile in scan_agent_profiles(project_root=root, search_paths=search_paths):
        if profile.path.stem == normalized or profile.name == normalized:
            return profile

    expected_path = Path(".mars") / "agents" / f"{normalized}.md"
    raise FileNotFoundError(
        "\n".join(
            (
                f"Agent '{normalized}' not found.",
                "",
                f"Expected: {expected_path.as_posix()}",
                "",
                "Run `meridian mars sync` to populate your agents directory, "
                "or see README.md for manual setup.",
            )
        )
    )
