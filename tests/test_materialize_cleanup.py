"""Tests for materialization cleanup and orphan reconciliation."""

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
    """Create a minimal .claude directory structure."""

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


def test_cleanup_orphaned_removes_inactive_keeps_active(claude_layout: Path) -> None:
    _create_materialized_agent(claude_layout, "c6", "primary")
    _create_materialized_skill(claude_layout, "c6", "orchestrate")
    _create_materialized_agent(claude_layout, "c99", "primary")
    _create_materialized_skill(claude_layout, "c99", "orchestrate")

    active = frozenset({"c6"})
    removed = cleanup_orphaned_materializations("claude", claude_layout, active)

    assert removed == 2
    assert (claude_layout / ".claude" / "agents" / "_meridian-c6-primary.md").exists()
    assert (claude_layout / ".claude" / "skills" / "_meridian-c6-orchestrate").exists()
    assert not (claude_layout / ".claude" / "agents" / "_meridian-c99-primary.md").exists()
    assert not (claude_layout / ".claude" / "skills" / "_meridian-c99-orchestrate").exists()


def test_cleanup_orphaned_with_empty_active_set(claude_layout: Path) -> None:
    _create_materialized_agent(claude_layout, "c1", "agent")
    _create_materialized_skill(claude_layout, "c1", "skill")

    removed = cleanup_orphaned_materializations("claude", claude_layout, frozenset())

    assert removed == 2


def test_cleanup_orphaned_no_artifacts(claude_layout: Path) -> None:
    removed = cleanup_orphaned_materializations("claude", claude_layout, frozenset({"c1"}))

    assert removed == 0


def test_cleanup_scoped_only_removes_matching_chat(claude_layout: Path) -> None:
    _create_materialized_agent(claude_layout, "c6", "primary")
    _create_materialized_agent(claude_layout, "c7", "primary")

    removed = cleanup_materialized("claude", claude_layout, "c6")

    assert removed == 1
    assert not (claude_layout / ".claude" / "agents" / "_meridian-c6-primary.md").exists()
    assert (claude_layout / ".claude" / "agents" / "_meridian-c7-primary.md").exists()
