"""Harness-native directory layout helpers."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict


class HarnessLayout(BaseModel):
    """Directories a harness reads agents/skills from natively."""

    model_config = ConfigDict(frozen=True)

    agents: tuple[str, ...]
    skills: tuple[str, ...]
    global_agents: tuple[str, ...]
    global_skills: tuple[str, ...]


HARNESS_NATIVE_DIRS: dict[str, HarnessLayout] = {
    "claude": HarnessLayout(
        agents=(".claude/agents",),
        skills=(".claude/skills",),
        global_agents=("~/.claude/agents",),
        global_skills=("~/.claude/skills",),
    ),
    "codex": HarnessLayout(
        agents=(".agents/agents", ".codex/agents"),
        skills=(".agents/skills", ".codex/skills"),
        global_agents=("~/.codex/agents",),
        global_skills=("~/.codex/skills",),
    ),
    "opencode": HarnessLayout(
        agents=(".agents/agents", ".opencode/agents"),
        skills=(".agents/skills", ".opencode/skills"),
        global_agents=("~/.opencode/agents",),
        global_skills=("~/.opencode/skills",),
    ),
}


def harness_layout(harness_id: str) -> HarnessLayout | None:
    """Return native layout metadata for a harness ID, if known."""

    return HARNESS_NATIVE_DIRS.get(harness_id)


def resolve_native_dir(raw_path: str, repo_root: Path) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    return candidate.resolve()


def materialization_target_agents(layout: HarnessLayout, repo_root: Path) -> Path:
    """Resolve the first configured project-local agents path to an absolute target."""

    if not layout.agents:
        raise ValueError("HarnessLayout.agents must contain at least one path")
    return resolve_native_dir(layout.agents[0], repo_root)


def materialization_target_skills(layout: HarnessLayout, repo_root: Path) -> Path:
    """Resolve the first configured project-local skills path to an absolute target."""

    if not layout.skills:
        raise ValueError("HarnessLayout.skills must contain at least one path")
    return resolve_native_dir(layout.skills[0], repo_root)


def is_agent_native(agent_name: str, layout: HarnessLayout, repo_root: Path) -> bool:
    """Return whether an agent markdown file exists in any harness-native location."""

    agent_filename = f"{agent_name}.md"
    for raw_dir in (*layout.agents, *layout.global_agents):
        if (resolve_native_dir(raw_dir, repo_root) / agent_filename).is_file():
            return True
    return False


def is_skill_native(skill_name: str, layout: HarnessLayout, repo_root: Path) -> bool:
    """Return whether a skill directory with SKILL.md exists in any native location."""

    for raw_dir in (*layout.skills, *layout.global_skills):
        if (resolve_native_dir(raw_dir, repo_root) / skill_name / "SKILL.md").is_file():
            return True
    return False
