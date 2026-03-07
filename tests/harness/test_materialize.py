"""Harness materialization cleanup and orphan-reconciliation invariants."""

from __future__ import annotations

from pathlib import Path

import pytest

from meridian.lib.harness.materialize import (
    _extract_chat_id_from_materialized,
    cleanup_materialized,
    cleanup_orphaned_materializations,
)


@pytest.fixture
def claude_layout(tmp_path: Path) -> Path:
    agents_dir = tmp_path / ".claude" / "agents"
    skills_dir = tmp_path / ".claude" / "skills"
    agents_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)
    return tmp_path


def _create_materialized_agent(repo_root: Path, chat_id: str, name: str) -> Path:
    path = repo_root / ".claude" / "agents" / f"_meridian-{chat_id}-{name}.md"
    path.write_text(f"---\nname: _meridian-{chat_id}-{name}\n---\n", encoding="utf-8")
    return path


def _create_materialized_skill(repo_root: Path, chat_id: str, name: str) -> Path:
    skill_dir = repo_root / ".claude" / "skills" / f"_meridian-{chat_id}-{name}"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: _meridian-{chat_id}-{name}\n---\n",
        encoding="utf-8",
    )
    return skill_dir


def test_extract_chat_id_from_materialized_name() -> None:
    assert _extract_chat_id_from_materialized("_meridian-c6-primary") == "c6"
    assert _extract_chat_id_from_materialized("_meridian-c44-agent") == "c44"
    assert _extract_chat_id_from_materialized("_meridian-tmp-abc12345-primary") == "tmp"
    assert _extract_chat_id_from_materialized("not-a-meridian-file") is None
    assert _extract_chat_id_from_materialized("_meridian-") is None


def test_cleanup_orphaned_removes_inactive_and_keeps_active(claude_layout: Path) -> None:
    _create_materialized_agent(claude_layout, "c6", "primary")
    _create_materialized_skill(claude_layout, "c6", "orchestrate")
    _create_materialized_agent(claude_layout, "c99", "primary")
    _create_materialized_skill(claude_layout, "c99", "orchestrate")

    removed = cleanup_orphaned_materializations("claude", claude_layout, frozenset({"c6"}))

    assert removed == 2
    assert (claude_layout / ".claude" / "agents" / "_meridian-c6-primary.md").exists()
    assert (claude_layout / ".claude" / "skills" / "_meridian-c6-orchestrate").exists()
    assert not (claude_layout / ".claude" / "agents" / "_meridian-c99-primary.md").exists()
    assert not (claude_layout / ".claude" / "skills" / "_meridian-c99-orchestrate").exists()


def test_cleanup_orphaned_handles_empty_or_missing_layouts(claude_layout: Path) -> None:
    _create_materialized_agent(claude_layout, "c1", "agent")
    _create_materialized_skill(claude_layout, "c1", "skill")

    assert cleanup_orphaned_materializations("claude", claude_layout, frozenset()) == 2
    assert cleanup_orphaned_materializations("claude", claude_layout, frozenset({"c1"})) == 0


def test_cleanup_scans_all_materialization_directories(tmp_path: Path) -> None:
    agents_dir_1 = tmp_path / ".agents" / "agents"
    agents_dir_2 = tmp_path / ".codex" / "agents"
    skills_dir_1 = tmp_path / ".agents" / "skills"
    skills_dir_2 = tmp_path / ".codex" / "skills"
    for directory in (agents_dir_1, agents_dir_2, skills_dir_1, skills_dir_2):
        directory.mkdir(parents=True)

    (agents_dir_2 / "_meridian-c99-agent.md").write_text("orphan agent", encoding="utf-8")
    skill_dir = skills_dir_2 / "_meridian-c99-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("orphan skill", encoding="utf-8")
    (agents_dir_1 / "_meridian-c1-agent.md").write_text("active agent", encoding="utf-8")

    removed = cleanup_orphaned_materializations("codex", tmp_path, frozenset({"c1"}))

    assert removed == 2
    assert not (agents_dir_2 / "_meridian-c99-agent.md").exists()
    assert not (skills_dir_2 / "_meridian-c99-skill").exists()
    assert (agents_dir_1 / "_meridian-c1-agent.md").exists()


def test_cleanup_materialized_scopes_to_chat_and_scans_codex_layouts(
    claude_layout: Path,
    tmp_path: Path,
) -> None:
    _create_materialized_agent(claude_layout, "c6", "primary")
    _create_materialized_agent(claude_layout, "c7", "primary")

    removed = cleanup_materialized("claude", claude_layout, "c6")

    assert removed == 1
    assert not (claude_layout / ".claude" / "agents" / "_meridian-c6-primary.md").exists()
    assert (claude_layout / ".claude" / "agents" / "_meridian-c7-primary.md").exists()

    agents_dir_1 = tmp_path / ".agents" / "agents"
    agents_dir_2 = tmp_path / ".codex" / "agents"
    agents_dir_1.mkdir(parents=True)
    agents_dir_2.mkdir(parents=True)
    (agents_dir_1 / "_meridian-c5-agent.md").write_text("agent in .agents", encoding="utf-8")
    (agents_dir_2 / "_meridian-c5-backup.md").write_text("agent in .codex", encoding="utf-8")

    removed = cleanup_materialized("codex", tmp_path, "c5")

    assert removed == 2
    assert not (agents_dir_1 / "_meridian-c5-agent.md").exists()
    assert not (agents_dir_2 / "_meridian-c5-backup.md").exists()


def test_cleanup_orphaned_scans_global_codex_directories(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    fake_home = tmp_path / "home"
    monkeypatch.setenv("HOME", fake_home.as_posix())

    agents_dir = fake_home / ".codex" / "agents"
    skills_dir = fake_home / ".codex" / "skills"
    agents_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)

    (agents_dir / "_meridian-c99-agent.md").write_text("orphan agent", encoding="utf-8")
    skill_dir = skills_dir / "_meridian-c99-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("orphan skill", encoding="utf-8")

    removed = cleanup_orphaned_materializations("codex", repo_root, frozenset())

    assert removed == 2
    assert not (agents_dir / "_meridian-c99-agent.md").exists()
    assert not (skills_dir / "_meridian-c99-skill").exists()
