"""Materialize agents and skills into harness-native directories."""

import logging
import os
import shutil
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.catalog.agent import AgentProfile
from meridian.lib.harness.adapter import HarnessNativeLayout
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.core.types import HarnessId

logger = logging.getLogger(__name__)


def harness_layout(harness_id: str) -> HarnessNativeLayout | None:
    """Return adapter-provided native layout metadata for a harness ID."""

    registry = get_default_harness_registry()
    try:
        adapter = registry.get(HarnessId(harness_id))
    except KeyError:
        return None
    return adapter.native_layout()


def resolve_native_dir(raw_path: str, repo_root: Path) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    return candidate.resolve()


def materialization_target_agents(layout: HarnessNativeLayout, repo_root: Path) -> Path:
    """Resolve the first configured project-local agents path to an absolute target."""

    if not layout.agents:
        raise ValueError("HarnessNativeLayout.agents must contain at least one path")
    return resolve_native_dir(layout.agents[0], repo_root)


def materialization_target_skills(layout: HarnessNativeLayout, repo_root: Path) -> Path:
    """Resolve the first configured project-local skills path to an absolute target."""

    if not layout.skills:
        raise ValueError("HarnessNativeLayout.skills must contain at least one path")
    return resolve_native_dir(layout.skills[0], repo_root)


def is_agent_native(agent_name: str, layout: HarnessNativeLayout, repo_root: Path) -> bool:
    """Return whether an agent markdown file exists in any harness-native location."""

    agent_filename = f"{agent_name}.md"
    for raw_dir in (*layout.agents, *layout.global_agents):
        if (resolve_native_dir(raw_dir, repo_root) / agent_filename).is_file():
            return True
    return False


def is_skill_native(skill_name: str, layout: HarnessNativeLayout, repo_root: Path) -> bool:
    """Return whether a skill directory with SKILL.md exists in any native location."""

    for raw_dir in (*layout.skills, *layout.global_skills):
        if (resolve_native_dir(raw_dir, repo_root) / skill_name / "SKILL.md").is_file():
            return True
    return False


# ---------------------------------------------------------------------------
# Materialization logic
# ---------------------------------------------------------------------------


class MaterializeResult(BaseModel):
    """Result describing harness materialization behavior."""

    model_config = ConfigDict(frozen=True)

    agent_name: str
    materialized_agent: bool
    materialized_skills: tuple[str, ...]
    native: bool


_MATERIALIZED_STABLE_PREFIX = "__meridian--"


def _materialized_name(name: str) -> str:
    normalized = name.strip()
    if normalized.startswith(_MATERIALIZED_STABLE_PREFIX):
        return normalized
    return f"{_MATERIALIZED_STABLE_PREFIX}{normalized}"


def _is_stable_materialized_name(name: str) -> bool:
    return name.startswith(_MATERIALIZED_STABLE_PREFIX)


def _rewrite_agent_skills(raw_content: str, skill_mapping: dict[str, str]) -> str:
    """Rewrite `skills:` frontmatter values using python-frontmatter round-trip."""
    import frontmatter  # type: ignore[import-untyped]
    import yaml

    try:
        post = frontmatter.loads(raw_content)
    except yaml.YAMLError:
        return raw_content
    skills: object = post.metadata.get("skills")
    if isinstance(skills, list):
        from typing import cast

        items = cast("list[object]", skills)
        post.metadata["skills"] = [skill_mapping.get(str(s), str(s)) for s in items]
    elif isinstance(skills, str):
        post.metadata["skills"] = skill_mapping.get(skills, skills)
    return str(frontmatter.dumps(post))


def _rewrite_frontmatter_name(raw_content: str, new_name: str) -> str:
    """Rewrite the `name:` field in frontmatter to the materialized agent name."""
    import frontmatter  # type: ignore[import-untyped]
    import yaml

    try:
        post = frontmatter.loads(raw_content)
    except yaml.YAMLError:
        return raw_content
    if not post.metadata:
        return raw_content
    post.metadata["name"] = new_name
    return str(frontmatter.dumps(post))


def _rewrite_skill_frontmatter(raw_content: str, new_name: str) -> str:
    """Rewrite skill frontmatter for materialized copies.

    Materialized skills are implementation details. Force model auto-invocation
    off so Claude does not proactively route to these temporary copies.
    """
    import frontmatter  # type: ignore[import-untyped]
    import yaml

    try:
        post = frontmatter.loads(raw_content)
    except yaml.YAMLError:
        return raw_content

    post.metadata["name"] = new_name
    post.metadata["disable-model-invocation"] = True
    return str(frontmatter.dumps(post))


def _reconstruct_builtin_agent(
    profile: AgentProfile, skill_names: list[str], *, materialized_name: str = ""
) -> str:
    """Reconstruct a minimal markdown profile for built-in agents."""
    import frontmatter  # type: ignore[import-untyped]

    agent_name = materialized_name if materialized_name else profile.name
    # frontmatter.Post(content, **metadata) — pass body as content, set metadata separately
    post = frontmatter.Post(profile.body or "")
    post.metadata["name"] = agent_name
    if profile.model is not None:
        post.metadata["model"] = profile.model
    post.metadata["skills"] = skill_names
    if profile.sandbox is not None:
        post.metadata["sandbox"] = profile.sandbox

    return str(frontmatter.dumps(post))


def _skill_final_name(skill_name: str, native: bool) -> str:
    if native:
        return skill_name
    return _materialized_name(skill_name)


def _compute_skill_mapping(
    skill_sources: dict[str, Path],
    missing_skills: set[str],
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for skill_name in skill_sources:
        mapping[skill_name] = _skill_final_name(
            skill_name=skill_name,
            native=skill_name not in missing_skills,
        )
    return mapping


def _copy_missing_skills(
    *,
    missing_skills: list[str],
    skill_sources: dict[str, Path],
    layout: HarnessNativeLayout,
    repo_root: Path,
) -> tuple[str, ...]:
    target_skills_root = materialization_target_skills(layout, repo_root)
    target_skills_root.mkdir(parents=True, exist_ok=True)

    materialized: list[str] = []
    for skill_name in missing_skills:
        materialized_name = _materialized_name(skill_name)
        target_dir = target_skills_root / materialized_name
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(skill_sources[skill_name], target_dir, symlinks=True)
        skill_file = target_dir / "SKILL.md"
        if skill_file.is_file():
            raw_skill = skill_file.read_text(encoding="utf-8")
            rewritten_skill = _rewrite_skill_frontmatter(raw_skill, materialized_name)
            skill_file.write_text(rewritten_skill, encoding="utf-8")
        materialized.append(materialized_name)

    return tuple(materialized)


def _materialize_agent(
    *,
    profile: AgentProfile,
    skill_mapping: dict[str, str],
    layout: HarnessNativeLayout,
    repo_root: Path,
) -> str:
    materialized_name = _materialized_name(profile.name)
    target_agents_root = materialization_target_agents(layout, repo_root)
    target_agents_root.mkdir(parents=True, exist_ok=True)

    final_skill_names = [skill_mapping.get(skill_name, skill_name) for skill_name in profile.skills]
    if profile.raw_content:
        rewritten = _rewrite_agent_skills(profile.raw_content, skill_mapping)
        rewritten = _rewrite_frontmatter_name(rewritten, materialized_name)
    else:
        rewritten = _reconstruct_builtin_agent(
            profile, final_skill_names, materialized_name=materialized_name
        )

    (target_agents_root / f"{materialized_name}.md").write_text(rewritten, encoding="utf-8")
    return materialized_name


_MATERIALIZED_GITIGNORE_PATTERNS = ("__meridian--*",)
"""Glob patterns matching materialized agent/skill artifacts."""


def _ensure_materialized_gitignore(repo_root: Path, layout: HarnessNativeLayout) -> None:
    """Ensure the root .gitignore excludes materialized artifacts.

    Appends ignore rules for each harness-native directory that doesn't
    already have a matching pattern.  Silently skips repos without git.
    """
    gitignore_path = repo_root / ".gitignore"
    if not (repo_root / ".git").exists():
        return

    existing = ""
    if gitignore_path.exists():
        existing = gitignore_path.read_text(encoding="utf-8")

    lines_to_add: list[str] = []
    for raw_dir in (*layout.agents, *layout.skills):
        if raw_dir.startswith("~"):
            continue
        for glob_pattern in _MATERIALIZED_GITIGNORE_PATTERNS:
            pattern = f"{raw_dir}/{glob_pattern}"
            if pattern not in existing:
                lines_to_add.append(pattern)

    if not lines_to_add:
        return

    suffix = "\n".join(lines_to_add) + "\n"
    if existing and not existing.endswith("\n"):
        suffix = "\n" + suffix

    try:
        tmp_path = gitignore_path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            fh.write(existing + suffix)
        os.replace(tmp_path, gitignore_path)
    except OSError:
        logger.debug("Could not update .gitignore", exc_info=True)


def materialize_for_harness(
    agent_profile: AgentProfile | None,
    skill_sources: dict[str, Path],
    harness_id: str,
    repo_root: Path,
    dry_run: bool = False,
) -> MaterializeResult:
    """Materialize non-native agents/skills for a specific harness."""

    original_agent_name = agent_profile.name if agent_profile is not None else ""
    layout = harness_layout(harness_id)
    if layout is None:
        return MaterializeResult(
            agent_name=original_agent_name,
            materialized_agent=False,
            materialized_skills=(),
            native=True,
        )

    missing_skills = [
        skill_name
        for skill_name in skill_sources
        if not is_skill_native(skill_name, layout=layout, repo_root=repo_root)
    ]
    missing_skills_set = set(missing_skills)

    agent_native = True
    if agent_profile is not None:
        agent_native = is_agent_native(agent_profile.name, layout=layout, repo_root=repo_root)

    skills_rewritten = bool(missing_skills)
    needs_agent_materialization = agent_profile is not None and (
        not agent_native or skills_rewritten
    )

    if agent_native and not missing_skills:
        return MaterializeResult(
            agent_name=original_agent_name,
            materialized_agent=False,
            materialized_skills=(),
            native=True,
        )

    skill_mapping = _compute_skill_mapping(skill_sources, missing_skills_set)
    final_agent_name = original_agent_name
    if needs_agent_materialization and agent_profile is not None:
        final_agent_name = _materialized_name(agent_profile.name)

    materialized_skills = tuple(_materialized_name(name) for name in missing_skills)
    if dry_run:
        return MaterializeResult(
            agent_name=final_agent_name,
            materialized_agent=needs_agent_materialization,
            materialized_skills=materialized_skills,
            native=False,
        )

    _ensure_materialized_gitignore(repo_root, layout)

    if missing_skills:
        materialized_skills = _copy_missing_skills(
            missing_skills=missing_skills,
            skill_sources=skill_sources,
            layout=layout,
            repo_root=repo_root,
        )

    if needs_agent_materialization and agent_profile is not None:
        final_agent_name = _materialize_agent(
            profile=agent_profile,
            skill_mapping=skill_mapping,
            layout=layout,
            repo_root=repo_root,
        )

    return MaterializeResult(
        agent_name=final_agent_name,
        materialized_agent=needs_agent_materialization,
        materialized_skills=materialized_skills,
        native=False,
    )


def _cleanup_matching(
    *,
    layout: HarnessNativeLayout,
    repo_root: Path,
    agents_pattern: str,
    skills_pattern: str,
) -> int:
    removed = 0

    for raw_dir in (*layout.agents, *layout.global_agents):
        agents_dir = resolve_native_dir(raw_dir, repo_root)
        if agents_dir.is_dir():
            for candidate in agents_dir.glob(agents_pattern):
                if candidate.is_file():
                    candidate.unlink()
                    removed += 1

    for raw_dir in (*layout.skills, *layout.global_skills):
        skills_dir = resolve_native_dir(raw_dir, repo_root)
        if skills_dir.is_dir():
            for candidate in skills_dir.glob(skills_pattern):
                if candidate.is_dir():
                    shutil.rmtree(candidate)
                    removed += 1

    return removed


def cleanup_materialized(harness_id: str, repo_root: Path) -> int:
    """Remove stable materialized files for one harness."""

    layout = harness_layout(harness_id)
    if layout is None:
        return 0

    return _cleanup_matching(
        layout=layout,
        repo_root=repo_root,
        agents_pattern=f"{_MATERIALIZED_STABLE_PREFIX}*.md",
        skills_pattern=f"{_MATERIALIZED_STABLE_PREFIX}*",
    )


def cleanup_all_materialized(harness_id: str, repo_root: Path) -> int:
    """Remove all materialized files for a harness regardless of chat scope."""

    layout = harness_layout(harness_id)
    if layout is None:
        return 0

    removed = 0

    for raw_dir in (*layout.agents, *layout.global_agents):
        agents_dir = resolve_native_dir(raw_dir, repo_root)
        if agents_dir.is_dir():
            for candidate in agents_dir.glob("__*.md"):
                if not candidate.is_file():
                    continue
                if _is_stable_materialized_name(candidate.stem):
                    candidate.unlink()
                    removed += 1

    for raw_dir in (*layout.skills, *layout.global_skills):
        skills_dir = resolve_native_dir(raw_dir, repo_root)
        if skills_dir.is_dir():
            for candidate in skills_dir.glob("__*"):
                if not candidate.is_dir():
                    continue
                if _is_stable_materialized_name(candidate.name):
                    shutil.rmtree(candidate)
                    removed += 1

    return removed


def cleanup_orphaned_materializations(
    harness_id: str,
    repo_root: Path,
    *,
    has_active_sessions: bool,
) -> int:
    """Remove stable materialized files when no sessions are active."""

    layout = harness_layout(harness_id)
    if layout is None:
        return 0

    removed = 0

    for raw_dir in (*layout.agents, *layout.global_agents):
        agents_dir = resolve_native_dir(raw_dir, repo_root)
        if agents_dir.is_dir():
            for candidate in agents_dir.glob("__*.md"):
                if not candidate.is_file():
                    continue
                if _is_stable_materialized_name(candidate.stem) and not has_active_sessions:
                    candidate.unlink()
                    removed += 1

    for raw_dir in (*layout.skills, *layout.global_skills):
        skills_dir = resolve_native_dir(raw_dir, repo_root)
        if skills_dir.is_dir():
            for candidate in skills_dir.glob("__*"):
                if not candidate.is_dir():
                    continue
                if _is_stable_materialized_name(candidate.name) and not has_active_sessions:
                    shutil.rmtree(candidate)
                    removed += 1

    return removed
