"""Harness-native layout and lookup tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from meridian.lib.harness.layout import (
    HARNESS_NATIVE_DIRS,
    HarnessLayout,
    harness_layout,
    is_agent_native,
    is_skill_native,
    materialization_target_agents,
    materialization_target_skills,
)


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.mark.parametrize("harness_id", ("claude", "codex", "opencode"))
def test_harness_layout_returns_registered_layout(harness_id: str) -> None:
    assert harness_layout(harness_id) == HARNESS_NATIVE_DIRS[harness_id]


def test_harness_layout_returns_none_for_unknown_harness() -> None:
    assert harness_layout("unknown-harness") is None


def test_materialization_targets_resolve_first_paths(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    layout = HarnessLayout(
        agents=(".agents/agents", ".codex/agents"),
        skills=(".agents/skills", ".codex/skills"),
        global_agents=(),
        global_skills=(),
    )

    assert materialization_target_agents(layout, repo_root) == (
        repo_root / ".agents" / "agents"
    ).resolve()
    assert materialization_target_skills(layout, repo_root) == (
        repo_root / ".agents" / "skills"
    ).resolve()


def test_is_agent_native_found_in_project_dir(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    layout = HARNESS_NATIVE_DIRS["codex"]
    _write(repo_root / ".agents" / "agents" / "reviewer.md", "# reviewer\n")

    assert is_agent_native("reviewer", layout, repo_root)


def test_is_agent_native_found_in_home_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "repo"
    home_root = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_root))
    layout = HARNESS_NATIVE_DIRS["claude"]
    _write(home_root / ".claude" / "agents" / "global-reviewer.md", "# global\n")

    assert is_agent_native("global-reviewer", layout, repo_root)


def test_is_agent_native_false_when_missing(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    layout = HARNESS_NATIVE_DIRS["opencode"]

    assert not is_agent_native("missing-agent", layout, repo_root)


def test_is_skill_native_found_in_project_dir(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    layout = HARNESS_NATIVE_DIRS["codex"]
    _write(repo_root / ".agents" / "skills" / "reviewing" / "SKILL.md", "# reviewing\n")

    assert is_skill_native("reviewing", layout, repo_root)


def test_is_skill_native_found_in_home_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "repo"
    home_root = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_root))
    layout = HARNESS_NATIVE_DIRS["opencode"]
    _write(home_root / ".opencode" / "skills" / "global-skill" / "SKILL.md", "# global\n")

    assert is_skill_native("global-skill", layout, repo_root)


def test_is_skill_native_false_when_missing(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    layout = HARNESS_NATIVE_DIRS["claude"]

    assert not is_skill_native("missing-skill", layout, repo_root)
