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
    path = repo_root / ".claude" / "agents" / f"__{name}-{chat_id}.md"
    path.write_text(f"---\nname: __{name}-{chat_id}\n---\n", encoding="utf-8")
    return path


def _create_materialized_skill(repo_root: Path, chat_id: str, name: str) -> Path:
    skill_dir = repo_root / ".claude" / "skills" / f"__{name}-{chat_id}"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: __{name}-{chat_id}\n---\n",
        encoding="utf-8",
    )
    return skill_dir


def test_extract_chat_id_from_materialized_name() -> None:
    assert _extract_chat_id_from_materialized("__primary-c6") == "c6"
    assert _extract_chat_id_from_materialized("__agent-c44") == "c44"
    assert _extract_chat_id_from_materialized("__primary-tmp-abc12345") == "tmp-abc12345"
    assert _extract_chat_id_from_materialized("not-a-meridian-file") is None
    assert _extract_chat_id_from_materialized("_single") is None
    # Names with dashes — chat_id is the suffix
    assert _extract_chat_id_from_materialized("__meridian-orchestrate-c55") == "c55"


def test_cleanup_orphaned_removes_inactive_and_keeps_active(claude_layout: Path) -> None:
    _create_materialized_agent(claude_layout, "c6", "primary")
    _create_materialized_skill(claude_layout, "c6", "orchestrate")
    _create_materialized_agent(claude_layout, "c99", "primary")
    _create_materialized_skill(claude_layout, "c99", "orchestrate")

    removed = cleanup_orphaned_materializations("claude", claude_layout, frozenset({"c6"}))

    assert removed == 2
    assert (claude_layout / ".claude" / "agents" / "__primary-c6.md").exists()
    assert (claude_layout / ".claude" / "skills" / "__orchestrate-c6").exists()
    assert not (claude_layout / ".claude" / "agents" / "__primary-c99.md").exists()
    assert not (claude_layout / ".claude" / "skills" / "__orchestrate-c99").exists()


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

    (agents_dir_2 / "__agent-c99.md").write_text("orphan agent", encoding="utf-8")
    skill_dir = skills_dir_2 / "__skill-c99"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("orphan skill", encoding="utf-8")
    (agents_dir_1 / "__agent-c1.md").write_text("active agent", encoding="utf-8")

    removed = cleanup_orphaned_materializations("codex", tmp_path, frozenset({"c1"}))

    assert removed == 2
    assert not (agents_dir_2 / "__agent-c99.md").exists()
    assert not (skills_dir_2 / "__skill-c99").exists()
    assert (agents_dir_1 / "__agent-c1.md").exists()


def test_cleanup_materialized_scopes_to_chat_and_scans_codex_layouts(
    claude_layout: Path,
    tmp_path: Path,
) -> None:
    _create_materialized_agent(claude_layout, "c6", "primary")
    _create_materialized_agent(claude_layout, "c7", "primary")

    removed = cleanup_materialized("claude", claude_layout, "c6")

    assert removed == 1
    assert not (claude_layout / ".claude" / "agents" / "__primary-c6.md").exists()
    assert (claude_layout / ".claude" / "agents" / "__primary-c7.md").exists()

    agents_dir_1 = tmp_path / ".agents" / "agents"
    agents_dir_2 = tmp_path / ".codex" / "agents"
    agents_dir_1.mkdir(parents=True)
    agents_dir_2.mkdir(parents=True)
    (agents_dir_1 / "__agent-c5.md").write_text("agent in .agents", encoding="utf-8")
    (agents_dir_2 / "__backup-c5.md").write_text("agent in .codex", encoding="utf-8")

    removed = cleanup_materialized("codex", tmp_path, "c5")

    assert removed == 2
    assert not (agents_dir_1 / "__agent-c5.md").exists()
    assert not (agents_dir_2 / "__backup-c5.md").exists()


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

    (agents_dir / "__agent-c99.md").write_text("orphan agent", encoding="utf-8")
    skill_dir = skills_dir / "__skill-c99"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("orphan skill", encoding="utf-8")

    removed = cleanup_orphaned_materializations("codex", repo_root, frozenset())

    assert removed == 2
    assert not (agents_dir / "__agent-c99.md").exists()
    assert not (skills_dir / "__skill-c99").exists()
