"""Agent profile parser for `.agents/agents/*.md`."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import cast

from meridian.lib.config._paths import bundled_agents_root, resolve_path_list, resolve_repo_root
from meridian.lib.config.settings import SearchPathConfig, load_config
from meridian.lib.config.skill import split_markdown_frontmatter

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# Sentinel path used for built-in profiles that don't exist on disk.
_BUILTIN_PATH = Path("<builtin>")
_KNOWN_SANDBOX_VALUES = frozenset(
    {
        "read-only",
        "workspace-write",
        "full-access",
        "danger-full-access",
        "unrestricted",
    }
)


@dataclass(frozen=True, slots=True)
class AgentProfile:
    """Parsed agent profile with frontmatter defaults + markdown body."""

    name: str
    description: str
    model: str | None
    variant: str | None
    skills: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    mcp_tools: tuple[str, ...]
    sandbox: str | None
    variant_models: tuple[str, ...]
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


@lru_cache(maxsize=1)
def _known_mcp_tools() -> frozenset[str]:
    # Import lazily to avoid loading the full operations graph at module import time.
    from meridian.lib.ops.registry import get_mcp_tool_names

    return get_mcp_tool_names()


def _normalize_mcp_tools(value: object, *, profile_name: str) -> tuple[str, ...]:
    parsed = _normalize_string_list(value)
    if not parsed:
        return ()

    known_tools = _known_mcp_tools()
    known_tools_by_lower = {tool.lower(): tool for tool in known_tools}
    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in parsed:
        lowered = candidate.lower()
        canonical = known_tools_by_lower.get(lowered)
        if canonical is None:
            logger.warning(
                "Agent profile '%s' includes unknown MCP tool '%s'.",
                profile_name,
                candidate,
            )
            canonical = candidate
        if canonical in seen:
            continue
        seen.add(canonical)
        normalized.append(canonical)
    return tuple(normalized)


def parse_agent_profile(path: Path) -> AgentProfile:
    """Parse a single markdown agent profile file."""

    markdown = path.read_text(encoding="utf-8")
    frontmatter, body = split_markdown_frontmatter(markdown)

    name_value = frontmatter.get("name")
    description_value = frontmatter.get("description")
    model_value = frontmatter.get("model")
    variant_value = frontmatter.get("variant")
    sandbox_value = frontmatter.get("sandbox")

    profile_name = str(name_value).strip() if name_value is not None else path.stem
    sandbox = str(sandbox_value).strip() if sandbox_value is not None else None
    if sandbox is not None and sandbox and sandbox not in _KNOWN_SANDBOX_VALUES:
        logger.warning(
            "Agent profile '%s' has unknown sandbox '%s'.",
            profile_name,
            sandbox,
        )

    return AgentProfile(
        name=profile_name,
        description=str(description_value).strip() if description_value is not None else "",
        model=str(model_value).strip() if model_value is not None else None,
        variant=str(variant_value).strip() if variant_value is not None else None,
        skills=_normalize_string_list(frontmatter.get("skills")),
        allowed_tools=_normalize_string_list(frontmatter.get("allowed-tools")),
        mcp_tools=_normalize_mcp_tools(frontmatter.get("mcp-tools"), profile_name=profile_name),
        sandbox=sandbox,
        variant_models=_normalize_string_list(frontmatter.get("variant-models")),
        body=body,
        path=path.resolve(),
        raw_content=markdown,
    )


def _builtin_profiles() -> dict[str, AgentProfile]:
    """Hard-coded fallback profiles used when no file exists on disk."""
    return {
        "agent": AgentProfile(
            name="agent",
            description="Default agent",
            model="gpt-5.3-codex",
            variant=None,
            skills=(),
            allowed_tools=(),
            mcp_tools=("spawn_list", "spawn_show", "skills_list"),
            sandbox="workspace-write",
            variant_models=(),
            body="",
            path=_BUILTIN_PATH,
            raw_content="",
        ),
        "primary": AgentProfile(
            name="primary",
            description="Primary agent",
            model="claude-opus-4-6",
            variant=None,
            skills=(),
            allowed_tools=(),
            mcp_tools=(
                "spawn_create",
                "spawn_list",
                "spawn_show",
                "spawn_wait",
                "skills_list",
                "models_list",
            ),
            sandbox="unrestricted",
            variant_models=(),
            body="",
            path=_BUILTIN_PATH,
            raw_content="",
        ),
    }


def _agent_search_dirs(
    repo_root: Path,
    search_paths: SearchPathConfig | None = None,
) -> list[Path]:
    config_paths = search_paths or load_config(repo_root).search_paths
    return resolve_path_list(
        config_paths.agents,
        config_paths.global_agents,
        repo_root,
    )


def _files_have_equal_text(first: Path, second: Path) -> bool:
    try:
        return first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    except OSError:
        return False


def scan_agent_profiles(
    repo_root: Path | None = None,
    search_dirs: list[Path] | None = None,
    *,
    search_paths: SearchPathConfig | None = None,
) -> list[AgentProfile]:
    """Parse all agent profiles from configured search directories."""

    root = resolve_repo_root(repo_root)
    directories = (
        search_dirs
        if search_dirs is not None
        else _agent_search_dirs(root, search_paths=search_paths)
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
    search_paths: SearchPathConfig | None = None,
) -> AgentProfile:
    """Load one agent profile by filename stem or frontmatter name."""

    normalized = name.strip()
    if not normalized:
        raise ValueError("Agent profile name must not be empty.")

    root = resolve_repo_root(repo_root)

    for profile in scan_agent_profiles(repo_root=root, search_paths=search_paths):
        if profile.path.stem == normalized or profile.name == normalized:
            return profile

    bundled_root = bundled_agents_root()
    if bundled_root is not None:
        bundled_agents_dir = bundled_root / "agents"
        if bundled_agents_dir.is_dir():
            try:
                for profile in scan_agent_profiles(
                    repo_root=root,
                    search_dirs=[bundled_agents_dir],
                ):
                    if profile.path.stem == normalized or profile.name == normalized:
                        return profile
            except Exception as exc:
                # Bundled profile parsing must be best-effort so hard-coded fallbacks
                # still keep the CLI operational if package resources are unavailable.
                logger.warning(
                    "Unable to read bundled agent profiles from '%s': %s",
                    bundled_agents_dir,
                    exc,
                )

    # Fall back to hard-coded built-in profiles.
    builtin = _builtin_profiles().get(normalized)
    if builtin is not None:
        logger.info(
            "Using built-in profile '%s' (no user or bundled profile found).",
            normalized,
        )
        return builtin

    raise FileNotFoundError(f"Agent profile '{name}' not found in configured search paths.")
