from pathlib import Path

from meridian.lib.core.context import RuntimeContext
from meridian.lib.ops.spawn.api import SpawnCreateInput, spawn_create_sync


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
            approval="auto",
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
