from pathlib import Path

from meridian.lib.install.deps import resolve_skill_deps
from meridian.lib.install.discovery import DiscoveredItem


def _write_agent(tree: Path, name: str, skills: list[str] | None = None) -> None:
    agents_dir = tree / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    skills_yaml = ""
    if skills:
        items = ", ".join(skills)
        skills_yaml = f"skills: [{items}]\n"
    (agents_dir / f"{name}.md").write_text(
        f"---\nname: {name}\nmodel: gpt-5.3-codex\n{skills_yaml}---\nBody\n",
        encoding="utf-8",
    )


def _write_skill(tree: Path, name: str) -> None:
    skill_dir = tree / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test\n---\nContent\n",
        encoding="utf-8",
    )


def _discover(tree: Path) -> tuple[DiscoveredItem, ...]:
    from meridian.lib.install.discovery import discover_items

    return discover_items(tree)


def test_resolve_skill_deps_happy_path_collects_unique_skills_across_agents(tmp_path: Path) -> None:
    tree = tmp_path / "source"
    _write_agent(tree, "agent-a", skills=["shared-skill", "skill-a"])
    _write_agent(tree, "agent-b", skills=["shared-skill", "skill-b"])
    _write_skill(tree, "shared-skill")
    _write_skill(tree, "skill-a")
    _write_skill(tree, "skill-b")

    discovered = _discover(tree)
    result = resolve_skill_deps(
        tree_path=tree,
        agent_names={"agent-a", "agent-b"},
        discovered_items=discovered,
    )

    assert result == {"shared-skill", "skill-a", "skill-b"}


def test_resolve_skill_deps_ignores_missing_or_unresolvable_skill_refs(tmp_path: Path) -> None:
    tree = tmp_path / "source"
    _write_agent(tree, "orchestrator", skills=["missing-skill"])
    _write_agent(tree, "simple-agent")
    _write_skill(tree, "present-but-unused")

    discovered = _discover(tree)
    result = resolve_skill_deps(
        tree_path=tree,
        agent_names={"orchestrator", "simple-agent"},
        discovered_items=discovered,
    )

    assert result == set()
