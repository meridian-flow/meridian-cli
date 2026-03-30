from pathlib import Path

import pytest

from meridian.lib.core.context import RuntimeContext
from meridian.lib.install.lock import InstallLock, LockedInstalledItem, write_lock
from meridian.lib.ops.spawn.api import SpawnCreateInput, spawn_create_sync
from meridian.lib.state.paths import resolve_state_paths


def _write_agent(path: Path, *, sandbox: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "---",
                "name: coder",
                "description: test coder",
                "model: gpt-5.3-codex",
                f"sandbox: {sandbox}",
                "---",
                "",
                "# Coder",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_spawn_dry_run_maps_profile_sandbox_and_harness_args(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_agent(repo_root / ".agents" / "agents" / "coder.md", sandbox="workspace-write")

    result = spawn_create_sync(
        SpawnCreateInput(
            prompt="do work",
            agent="coder",
            repo_root=repo_root.as_posix(),
            dry_run=True,
            passthrough_args=("--foo", "bar"),
        ),
    )

    assert result.status == "dry-run"
    assert result.harness_id == "codex"
    assert "--sandbox" in result.cli_command
    assert "workspace-write" in result.cli_command
    assert "--foo" in result.cli_command
    assert "bar" in result.cli_command


def test_spawn_dry_run_yolo_uses_bypass_flags(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_agent(repo_root / ".agents" / "agents" / "coder.md", sandbox="workspace-write")

    result = spawn_create_sync(
        SpawnCreateInput(
            prompt="do work",
            agent="coder",
            repo_root=repo_root.as_posix(),
            dry_run=True,
            approval="yolo",
        ),
    )

    assert result.status == "dry-run"
    assert "--dangerously-bypass-approvals-and-sandbox" in result.cli_command


def test_spawn_dry_run_allows_nested_context_without_permission_inheritance(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_agent(repo_root / ".agents" / "agents" / "coder.md", sandbox="workspace-write")

    result = spawn_create_sync(
        SpawnCreateInput(
            prompt="do work",
            agent="coder",
            repo_root=repo_root.as_posix(),
            dry_run=True,
        ),
        ctx=RuntimeContext(chat_id="c-parent", work_id="work-9"),
    )

    assert result.status == "dry-run"
    assert result.harness_id == "codex"


def test_spawn_dry_run_missing_default_agent_does_not_write_install_state(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    try:
        spawn_create_sync(
            SpawnCreateInput(
                prompt="do work",
                repo_root=repo_root.as_posix(),
                dry_run=True,
            ),
        )
    except FileNotFoundError as exc:
        assert "will not be auto-installed" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected missing default agent dry-run to fail.")

    assert not (repo_root / ".meridian" / "agents.toml").exists()
    assert not (repo_root / ".meridian" / "agents.lock").exists()
    assert not (repo_root / ".agents").exists()


def test_spawn_dry_run_includes_agent_and_skill_provenance(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_agent(repo_root / ".agents" / "agents" / "coder.md", sandbox="workspace-write")
    skill_path = repo_root / ".agents" / "skills" / "reviewing" / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text("# Reviewing\n\nReview carefully.\n", encoding="utf-8")
    write_lock(
        resolve_state_paths(repo_root).agents_lock_path,
        InstallLock(
            items={
                "agent:coder": LockedInstalledItem(
                    source_name="dev-fixture",
                    source_item_id="agent:coder",
                    destination_path=".agents/agents/coder.md",
                    content_hash="agent-hash",
                ),
                "skill:reviewing": LockedInstalledItem(
                    source_name="dev-fixture",
                    source_item_id="skill:reviewing",
                    destination_path=".agents/skills/reviewing",
                    content_hash="skill-hash",
                ),
            }
        ),
    )

    result = spawn_create_sync(
        SpawnCreateInput(
            prompt="do work",
            agent="coder",
            skills=("reviewing",),
            repo_root=repo_root.as_posix(),
            dry_run=True,
        ),
    )

    assert result.status == "dry-run"
    assert result.agent_path == (repo_root / ".agents" / "agents" / "coder.md").as_posix()
    assert result.agent_source == "dev-fixture"
    assert result.skills == ("reviewing",)
    assert result.skill_paths == (skill_path.as_posix(),)
    assert result.skill_sources == {"reviewing": "dev-fixture"}


def test_spawn_dry_run_rejects_tracked_continue_without_session_id(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_agent(repo_root / ".agents" / "agents" / "coder.md", sandbox="workspace-write")

    with pytest.raises(ValueError) as exc_info:
        spawn_create_sync(
            SpawnCreateInput(
                prompt="do work",
                agent="coder",
                repo_root=repo_root.as_posix(),
                dry_run=True,
                continue_harness="codex",
                continue_source_tracked=True,
                continue_source_ref="c42",
            ),
        )

    assert (
        str(exc_info.value)
        == "Session 'c42' has no recorded harness session — cannot continue/fork."
    )
