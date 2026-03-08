"""Materialize agents and skills into harness-native directories."""

from __future__ import annotations

import glob
import shutil
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.config.agent import AgentProfile
from meridian.lib.harness.layout import (
    HarnessLayout,
    harness_layout,
    is_agent_native,
    is_skill_native,
    materialization_target_agents,
    materialization_target_skills,
    resolve_native_dir,
)


class MaterializeResult(BaseModel):
    """Result describing harness materialization behavior."""

    model_config = ConfigDict(frozen=True)

    agent_name: str
    materialized_agent: bool
    materialized_skills: tuple[str, ...]
    native: bool


def _materialized_name(chat_id: str, name: str) -> str:
    return f"_meridian-{chat_id}-{name}"


def _extract_chat_id_from_materialized(name: str) -> str | None:
    """Extract the chat scope from a materialized artifact name."""

    prefix = "_meridian-"
    if not name.startswith(prefix):
        return None

    rest = name[len(prefix) :]
    dash_idx = rest.find("-")
    if dash_idx <= 0:
        return None
    return rest[:dash_idx]


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


def _reconstruct_builtin_agent(profile: AgentProfile, skill_names: list[str], *, materialized_name: str = "") -> str:
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


def _skill_final_name(skill_name: str, chat_id: str, native: bool) -> str:
    if native:
        return skill_name
    return _materialized_name(chat_id, skill_name)


def _compute_skill_mapping(
    skill_sources: dict[str, Path],
    missing_skills: set[str],
    chat_id: str,
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for skill_name in skill_sources:
        mapping[skill_name] = _skill_final_name(
            skill_name=skill_name,
            chat_id=chat_id,
            native=skill_name not in missing_skills,
        )
    return mapping


def _copy_missing_skills(
    *,
    missing_skills: list[str],
    skill_sources: dict[str, Path],
    chat_id: str,
    layout: HarnessLayout,
    repo_root: Path,
) -> tuple[str, ...]:
    target_skills_root = materialization_target_skills(layout, repo_root)
    target_skills_root.mkdir(parents=True, exist_ok=True)

    materialized: list[str] = []
    for skill_name in missing_skills:
        materialized_name = _materialized_name(chat_id, skill_name)
        target_dir = target_skills_root / materialized_name
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(skill_sources[skill_name], target_dir, symlinks=True)
        skill_file = target_dir / "SKILL.md"
        if skill_file.is_file():
            raw_skill = skill_file.read_text(encoding="utf-8")
            rewritten_skill = _rewrite_frontmatter_name(raw_skill, materialized_name)
            skill_file.write_text(rewritten_skill, encoding="utf-8")
        materialized.append(materialized_name)

    return tuple(materialized)


def _materialize_agent(
    *,
    profile: AgentProfile,
    skill_mapping: dict[str, str],
    chat_id: str,
    layout: HarnessLayout,
    repo_root: Path,
) -> str:
    materialized_name = _materialized_name(chat_id, profile.name)
    target_agents_root = materialization_target_agents(layout, repo_root)
    target_agents_root.mkdir(parents=True, exist_ok=True)

    final_skill_names = [skill_mapping.get(skill_name, skill_name) for skill_name in profile.skills]
    if profile.raw_content:
        rewritten = _rewrite_agent_skills(profile.raw_content, skill_mapping)
        rewritten = _rewrite_frontmatter_name(rewritten, materialized_name)
    else:
        rewritten = _reconstruct_builtin_agent(profile, final_skill_names, materialized_name=materialized_name)

    (target_agents_root / f"{materialized_name}.md").write_text(rewritten, encoding="utf-8")
    return materialized_name


def materialize_for_harness(
    agent_profile: AgentProfile | None,
    skill_sources: dict[str, Path],
    harness_id: str,
    repo_root: Path,
    chat_id: str,
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
    needs_agent_materialization = agent_profile is not None and (not agent_native or skills_rewritten)

    if agent_native and not missing_skills:
        return MaterializeResult(
            agent_name=original_agent_name,
            materialized_agent=False,
            materialized_skills=(),
            native=True,
        )

    skill_mapping = _compute_skill_mapping(skill_sources, missing_skills_set, chat_id)
    final_agent_name = original_agent_name
    if needs_agent_materialization and agent_profile is not None:
        final_agent_name = _materialized_name(chat_id, agent_profile.name)

    materialized_skills = tuple(_materialized_name(chat_id, name) for name in missing_skills)
    if dry_run:
        return MaterializeResult(
            agent_name=final_agent_name,
            materialized_agent=needs_agent_materialization,
            materialized_skills=materialized_skills,
            native=False,
        )

    if missing_skills:
        materialized_skills = _copy_missing_skills(
            missing_skills=missing_skills,
            skill_sources=skill_sources,
            chat_id=chat_id,
            layout=layout,
            repo_root=repo_root,
        )

    if needs_agent_materialization and agent_profile is not None:
        final_agent_name = _materialize_agent(
            profile=agent_profile,
            skill_mapping=skill_mapping,
            chat_id=chat_id,
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
    layout: HarnessLayout,
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


def cleanup_materialized(harness_id: str, repo_root: Path, chat_id: str) -> int:
    """Remove materialized files for a specific chat scope."""

    layout = harness_layout(harness_id)
    if layout is None:
        return 0

    prefix = f"_meridian-{glob.escape(chat_id)}-"
    return _cleanup_matching(
        layout=layout,
        repo_root=repo_root,
        agents_pattern=f"{prefix}*.md",
        skills_pattern=f"{prefix}*",
    )


def cleanup_all_materialized(harness_id: str, repo_root: Path) -> int:
    """Remove all materialized files for a harness regardless of chat scope."""

    layout = harness_layout(harness_id)
    if layout is None:
        return 0

    return _cleanup_matching(
        layout=layout,
        repo_root=repo_root,
        agents_pattern="_meridian-*.md",
        skills_pattern="_meridian-*",
    )


def cleanup_orphaned_materializations(
    harness_id: str,
    repo_root: Path,
    active_chat_ids: frozenset[str],
) -> int:
    """Remove materialized files not owned by any active session."""

    layout = harness_layout(harness_id)
    if layout is None:
        return 0

    removed = 0

    for raw_dir in (*layout.agents, *layout.global_agents):
        agents_dir = resolve_native_dir(raw_dir, repo_root)
        if agents_dir.is_dir():
            for candidate in agents_dir.glob("_meridian-*.md"):
                if not candidate.is_file():
                    continue
                chat_id = _extract_chat_id_from_materialized(candidate.stem)
                if chat_id is not None and chat_id not in active_chat_ids:
                    candidate.unlink()
                    removed += 1

    for raw_dir in (*layout.skills, *layout.global_skills):
        skills_dir = resolve_native_dir(raw_dir, repo_root)
        if skills_dir.is_dir():
            for candidate in skills_dir.glob("_meridian-*"):
                if not candidate.is_dir():
                    continue
                chat_id = _extract_chat_id_from_materialized(candidate.name)
                if chat_id is not None and chat_id not in active_chat_ids:
                    shutil.rmtree(candidate)
                    removed += 1

    return removed
