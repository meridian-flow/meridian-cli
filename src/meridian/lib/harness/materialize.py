"""Materialize agents and skills into harness-native directories."""

from __future__ import annotations

import glob
import shutil
from dataclasses import dataclass
from pathlib import Path

from meridian.lib.config.agent import AgentProfile
from meridian.lib.harness.layout import (
    HarnessLayout,
    harness_layout,
    is_agent_native,
    is_skill_native,
    materialization_target_agents,
    materialization_target_skills,
)


@dataclass(frozen=True, slots=True)
class MaterializeResult:
    """Result describing harness materialization behavior."""

    agent_name: str
    materialized_agent: bool
    materialized_skills: tuple[str, ...]
    native: bool


def _materialized_name(chat_id: str, name: str) -> str:
    return f"_meridian-{chat_id}-{name}"


def _split_inline_list_items(raw: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False

    for char in raw:
        if quote is not None:
            current.append(char)
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == quote:
                quote = None
            continue

        if char in {'"', "'"}:
            quote = char
            current.append(char)
            continue
        if char == ",":
            items.append("".join(current).strip())
            current = []
            continue
        current.append(char)

    items.append("".join(current).strip())
    return [item for item in items if item]


def _split_inline_comment(raw: str) -> tuple[str, str]:
    quote: str | None = None
    for index, char in enumerate(raw):
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
            continue
        if char == "#":
            value = raw[:index].strip()
            comment = raw[index:].rstrip()
            return value, f" {comment}" if comment else ""
    return raw.strip(), ""


def _map_skill_name(raw_name: str, skill_mapping: dict[str, str]) -> str:
    token = raw_name.strip()
    if not token:
        return token

    quote: str | None = None
    if len(token) >= 2 and token[0] == token[-1] and token[0] in {'"', "'"}:
        quote = token[0]
        token = token[1:-1]

    mapped = skill_mapping.get(token, token)
    if quote is not None:
        return f"{quote}{mapped}{quote}"
    return mapped


def _rewrite_agent_skills(raw_content: str, skill_mapping: dict[str, str]) -> str:
    """Rewrite `skills:` frontmatter values while preserving the rest of the file."""

    lines = raw_content.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return raw_content

    frontmatter_end: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            frontmatter_end = index
            break
    if frontmatter_end is None:
        return raw_content

    skills_line_index: int | None = None
    skills_indent = ""
    for index in range(1, frontmatter_end):
        line = lines[index]
        line_no_nl = line.rstrip("\r\n")
        stripped = line_no_nl.lstrip()
        if not stripped.startswith("skills"):
            continue
        if ":" not in stripped:
            continue
        key, _rest = stripped.split(":", 1)
        if key.strip() != "skills":
            continue

        skills_line_index = index
        skills_indent = line_no_nl[: len(line_no_nl) - len(stripped)]
        break

    if skills_line_index is None:
        return raw_content

    skills_line = lines[skills_line_index]
    skills_no_nl = skills_line.rstrip("\r\n")
    line_ending = skills_line[len(skills_no_nl) :]
    stripped = skills_no_nl[len(skills_indent) :]
    _key, raw_value = stripped.split(":", 1)
    value = raw_value.strip()

    block_style = not value or value.startswith("#")
    if block_style:
        base_indent = len(skills_indent)
        index = skills_line_index + 1
        while index < frontmatter_end:
            line = lines[index]
            line_no_nl = line.rstrip("\r\n")
            item_line_ending = line[len(line_no_nl) :]

            if not line_no_nl.strip():
                index += 1
                continue

            current_indent = len(line_no_nl) - len(line_no_nl.lstrip(" "))
            if current_indent <= base_indent:
                break

            stripped_item = line_no_nl.lstrip()
            if stripped_item.startswith("-"):
                prefix, raw_item = stripped_item.split("-", 1)
                del prefix
                item_content = raw_item.strip()
                value_text, comment = _split_inline_comment(item_content)
                mapped_item = _map_skill_name(value_text, skill_mapping)
                item_indent = line_no_nl[: len(line_no_nl) - len(stripped_item)]
                lines[index] = f"{item_indent}- {mapped_item}{comment}{item_line_ending}"

            index += 1

        return "".join(lines)

    value_text, comment = _split_inline_comment(value)
    rewritten_value = value_text
    if value_text.startswith("[") and value_text.endswith("]"):
        inner = value_text[1:-1].strip()
        if inner:
            rewritten_items = [
                _map_skill_name(item, skill_mapping) for item in _split_inline_list_items(inner)
            ]
            rewritten_value = f"[{', '.join(rewritten_items)}]"
        else:
            rewritten_value = "[]"
    else:
        rewritten_value = _map_skill_name(value_text, skill_mapping)

    lines[skills_line_index] = f"{skills_indent}skills: {rewritten_value}{comment}{line_ending}"
    return "".join(lines)


def _format_skills_inline(skill_names: list[str]) -> str:
    if not skill_names:
        return "[]"
    return f"[{', '.join(skill_names)}]"


def _reconstruct_builtin_agent(profile: AgentProfile, skill_names: list[str]) -> str:
    """Reconstruct a minimal markdown profile for built-in agents."""

    frontmatter_lines = ["---", f"name: {profile.name}"]
    if profile.model is not None:
        frontmatter_lines.append(f"model: {profile.model}")
    frontmatter_lines.append(f"skills: {_format_skills_inline(skill_names)}")
    if profile.sandbox is not None:
        frontmatter_lines.append(f"sandbox: {profile.sandbox}")
    frontmatter_lines.append("---")

    content = "\n".join(frontmatter_lines) + "\n"
    if profile.body:
        content += profile.body
    return content


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
    else:
        rewritten = _reconstruct_builtin_agent(profile, final_skill_names)

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

    agents_dir = materialization_target_agents(layout, repo_root)
    if agents_dir.is_dir():
        for candidate in agents_dir.glob(agents_pattern):
            if candidate.is_file():
                candidate.unlink()
                removed += 1

    skills_dir = materialization_target_skills(layout, repo_root)
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
