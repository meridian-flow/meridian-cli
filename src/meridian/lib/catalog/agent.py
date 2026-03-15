"""Agent profile parser for `.agents/agents/*.md`."""


import logging
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict

from meridian.lib.config.settings import resolve_repo_root
from meridian.lib.catalog.skill import split_markdown_frontmatter

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

_KNOWN_SANDBOX_VALUES = frozenset(
    {
        "read-only",
        "workspace-write",
        "full-access",
        "danger-full-access",
        "unrestricted",
    }
)
_KNOWN_THINKING_VALUES = frozenset({"low", "medium", "high", "xhigh"})


class AgentProfile(BaseModel):
    """Parsed agent profile with frontmatter defaults + markdown body."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    model: str | None
    harness: str | None = None
    skills: tuple[str, ...]
    tools: tuple[str, ...]
    mcp_tools: tuple[str, ...]
    sandbox: str | None
    thinking: str | None
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
        values = [
            str(item).strip()
            for item in cast("list[object]", value)
            if str(item).strip()
        ]
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


def parse_agent_profile(path: Path) -> AgentProfile:
    """Parse a single markdown agent profile file."""

    markdown = path.read_text(encoding="utf-8")
    frontmatter, body = split_markdown_frontmatter(markdown)

    name_value = frontmatter.get("name")
    description_value = frontmatter.get("description")
    model_value = frontmatter.get("model")
    harness_value = frontmatter.get("harness")
    sandbox_value = frontmatter.get("sandbox")
    thinking_value = frontmatter.get("thinking")

    profile_name = str(name_value).strip() if name_value is not None else path.stem
    sandbox = str(sandbox_value).strip() if sandbox_value is not None else None
    if sandbox is not None and sandbox and sandbox not in _KNOWN_SANDBOX_VALUES:
        logger.warning(
            "Agent profile '%s' has unknown sandbox '%s'.",
            profile_name,
            sandbox,
        )
    thinking = str(thinking_value).strip() if thinking_value is not None else None
    if thinking is not None and thinking and thinking not in _KNOWN_THINKING_VALUES:
        logger.warning(
            "Agent profile '%s' has unknown thinking '%s'.",
            profile_name,
            thinking,
        )

    return AgentProfile(
        name=profile_name,
        description=str(description_value).strip() if description_value is not None else "",
        model=str(model_value).strip() if model_value is not None else None,
        harness=str(harness_value).strip() if harness_value is not None else None,
        skills=_normalize_string_list(frontmatter.get("skills")),
        tools=_normalize_string_list(frontmatter.get("tools")),
        mcp_tools=_normalize_deduplicated(frontmatter.get("mcp-tools")),
        sandbox=sandbox,
        thinking=thinking,
        body=body,
        path=path.resolve(),
        raw_content=markdown,
    )


def _agent_search_dirs(repo_root: Path) -> list[Path]:
    return [repo_root / ".agents" / "agents"]


def _files_have_equal_text(first: Path, second: Path) -> bool:
    try:
        return first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    except OSError:
        return False


def scan_agent_profiles(
    repo_root: Path | None = None,
    search_dirs: list[Path] | None = None,
    *,
    search_paths: object | None = None,
) -> list[AgentProfile]:
    """Parse all agent profiles from configured search directories."""

    root = resolve_repo_root(repo_root)
    _ = search_paths
    directories = (
        search_dirs
        if search_dirs is not None
        else _agent_search_dirs(root)
    )
    profiles: list[AgentProfile] = []
    selected_by_name: dict[str, AgentProfile] = {}

    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            profile = parse_agent_profile(path)
            existing = selected_by_name.get(profile.name)
            if existing is not None:
                if _files_have_equal_text(existing.path, profile.path):
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
    repo_root: Path | None = None,
    *,
    search_paths: object | None = None,
) -> AgentProfile:
    """Load one agent profile by filename stem or frontmatter name."""

    normalized = name.strip()
    if not normalized:
        raise ValueError("Agent profile name must not be empty.")

    root = resolve_repo_root(repo_root)

    for profile in scan_agent_profiles(repo_root=root, search_paths=search_paths):
        if profile.path.stem == normalized or profile.name == normalized:
            return profile

    raise FileNotFoundError(f"Agent profile '{name}' not found in repo-local .agents.")
