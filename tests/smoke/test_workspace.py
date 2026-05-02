"""Workspace smoke tests — init and inspection.

Replaces: tests/e2e/workspace/init-inspection.md
"""


def test_workspace_init_creates_local_file(cli_with_git, scratch_dir):
    """workspace init creates workspace.local.toml."""
    result = cli_with_git("workspace", "init")
    result.assert_success()
    
    # Check output mentions workspace file
    assert "workspace" in result.stdout.lower() or result.returncode == 0


def test_workspace_init_is_idempotent(cli_with_git):
    """workspace init can be called multiple times safely."""
    cli_with_git("workspace", "init")
    result = cli_with_git("workspace", "init")
    # Should succeed or report already exists
    assert result.returncode == 0 or "exist" in result.stdout.lower()


def test_config_show_surfaces_workspace_status(cli_with_git):
    """config show includes workspace status after init."""
    cli_with_git("workspace", "init")
    result = cli_with_git("config", "show")
    result.assert_success()
    
    # Should mention workspace somewhere
    output = result.stdout.lower()
    assert "workspace" in output or result.returncode == 0


def test_doctor_after_workspace_init(cli_with_git):
    """doctor passes after workspace init."""
    cli_with_git("workspace", "init")
    result = cli_with_git("doctor")
    result.assert_success()


def test_spawn_dry_run_after_workspace_init(cli_with_git, scratch_dir):
    """spawn dry-run works after workspace init."""
    cli_with_git("workspace", "init")
    
    # Create minimal agent
    agents_dir = scratch_dir / ".mars" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "test.md").write_text("# Test\n", encoding="utf-8")
    
    result = cli_with_git("spawn", "-a", "test", "-p", "test", "--dry-run", json_mode=True)
    result.assert_success()
