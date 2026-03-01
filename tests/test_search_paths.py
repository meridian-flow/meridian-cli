"""Search-path configuration and discovery tests (Slice 7)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from meridian.lib.config._paths import bundled_agents_root, resolve_search_paths
from meridian.lib.config.agent import scan_agent_profiles
from meridian.lib.config.settings import SearchPathConfig, load_config
from meridian.lib.config.skill_registry import SkillRegistry

if TYPE_CHECKING:
    import pytest


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_config(repo_root: Path, content: str) -> None:
    _write(repo_root / ".meridian" / "config.toml", content)


def _write_agent(path: Path, *, name: str, model: str) -> None:
    _write(
        path,
        (
            "---\n"
            f"name: {name}\n"
            f"model: {model}\n"
            "---\n\n"
            f"# {name}\n"
        ),
    )


def _write_skill(path: Path, *, name: str, description: str) -> None:
    _write(
        path,
        (
            "---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            "---\n\n"
            f"# {name}\n"
        ),
    )


def test_load_config_parses_search_paths_table(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_config(
        repo_root,
        (
            "[search_paths]\n"
            "agents = ['.a/agents']\n"
            "skills = ['.a/skills']\n"
            "global_agents = ['~/.global/agents']\n"
            "global_skills = ['~/.global/skills']\n"
        ),
    )

    config = load_config(repo_root)

    assert config.search_paths == SearchPathConfig(
        agents=(".a/agents",),
        skills=(".a/skills",),
        global_agents=("~/.global/agents",),
        global_skills=("~/.global/skills",),
    )


def test_resolve_search_paths_expands_home_skips_missing_and_orders_local_before_global(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    local_primary = repo_root / ".agents" / "agents"
    local_secondary = repo_root / ".cursor" / "agents"
    global_agents = tmp_path / "home" / ".claude" / "agents"
    local_primary.mkdir(parents=True, exist_ok=True)
    local_secondary.mkdir(parents=True, exist_ok=True)
    global_agents.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    resolved = resolve_search_paths(
        SearchPathConfig(
            agents=(".agents/agents", ".missing/agents", ".cursor/agents"),
            global_agents=("~/.claude/agents", "~/.missing/agents"),
        ),
        repo_root,
    )

    assert resolved == [
        local_primary.resolve(),
        local_secondary.resolve(),
        global_agents.resolve(),
    ]


def test_scan_agent_profiles_multi_path_first_match_wins_with_warning(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    home_root = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_root))
    _write_config(
        repo_root,
        (
            "[search_paths]\n"
            "agents = ['.agents/agents', '.cursor/agents']\n"
            "global_agents = ['~/.claude/agents']\n"
        ),
    )

    first = repo_root / ".agents" / "agents" / "reviewer.md"
    second = repo_root / ".cursor" / "agents" / "reviewer.md"
    third = repo_root / ".cursor" / "agents" / "writer.md"
    global_profile = home_root / ".claude" / "agents" / "global.md"
    _write_agent(first, name="reviewer", model="gpt-5.3-codex")
    _write_agent(second, name="reviewer", model="claude-sonnet-4-6")
    _write_agent(third, name="writer", model="gpt-5.3-codex")
    _write_agent(global_profile, name="global", model="gpt-5.3-codex")

    caplog.set_level(logging.WARNING, logger="meridian.lib.config.agent")
    profiles = scan_agent_profiles(repo_root=repo_root)

    assert [profile.name for profile in profiles] == ["reviewer", "writer", "global"]
    assert profiles[0].path == first.resolve()
    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "Agent profile 'reviewer' found in multiple paths" in message
        for message in messages
    )


def test_skill_registry_scans_multi_path_and_first_match_wins_with_warning(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    home_root = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_root))
    _write_config(
        repo_root,
        (
            "[search_paths]\n"
            "skills = ['.agents/skills', '.cursor/skills']\n"
            "global_skills = ['~/.claude/skills']\n"
        ),
    )

    local_skill = repo_root / ".agents" / "skills" / "reviewing" / "SKILL.md"
    shadowed_skill = repo_root / ".cursor" / "skills" / "reviewing" / "SKILL.md"
    repo_extra = repo_root / ".cursor" / "skills" / "writing" / "SKILL.md"
    global_skill = home_root / ".claude" / "skills" / "global" / "SKILL.md"
    _write_skill(local_skill, name="reviewing", description="Repo-local")
    _write_skill(shadowed_skill, name="reviewing", description="Shadowed")
    _write_skill(repo_extra, name="writing", description="Repo-local extra")
    _write_skill(global_skill, name="global", description="Global skill")

    registry = SkillRegistry(
        repo_root=repo_root,
        db_path=repo_root / ".meridian" / "index" / "runs.db",
    )

    bundled_root = bundled_agents_root()
    assert bundled_root is not None
    assert registry.skills_dirs == (
        (repo_root / ".agents" / "skills").resolve(),
        (repo_root / ".cursor" / "skills").resolve(),
        (home_root / ".claude" / "skills").resolve(),
        (bundled_root / "skills").resolve(),
    )

    caplog.set_level(logging.WARNING, logger="meridian.lib.config.skill")
    report = registry.reindex()
    assert report.indexed_count >= 3  # may include bundled skills
    reviewing = registry.show("reviewing")
    assert Path(reviewing.path).resolve() == local_skill.resolve()
    messages = [record.getMessage() for record in caplog.records]
    assert any("Skill 'reviewing' found in multiple paths" in message for message in messages)
