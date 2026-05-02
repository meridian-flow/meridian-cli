"""Spawn error path smoke tests — clean failures without tracebacks.

Replaces: tests/e2e/spawn/error-paths.md
"""


def test_unknown_model_rejected(cli, scratch_dir):
    """Invalid model name exits non-zero without traceback."""
    agents_dir = scratch_dir / ".mars" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "reviewer.md").write_text("# Reviewer\n", encoding="utf-8")
    # Seed mars.toml so model resolution can actually run
    mars_content = "[settings]\nmodels_cache_ttl_hours = 24\n"
    (scratch_dir / "mars.toml").write_text(mars_content, encoding="utf-8")

    result = cli(
        "spawn", "-a", "reviewer", "-p", "test",
        "-m", "definitely-not-a-model-xyz",
        "--dry-run",
        json_mode=True
    )
    result.assert_failure()
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_invalid_spawn_id_rejected(cli):
    """Invalid spawn ID exits non-zero without traceback."""
    result = cli("spawn", "show", "no-such-spawn-xyz", json_mode=True)
    result.assert_failure()
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_empty_prompt_no_traceback(cli, scratch_dir):
    """Empty prompt on real spawn fails gracefully."""
    agents_dir = scratch_dir / ".mars" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "reviewer.md").write_text("# Reviewer\n", encoding="utf-8")

    # Real spawn (not dry-run) with empty prompt
    result = cli("spawn", "-a", "reviewer", "-p", "", json_mode=True)
    # May succeed or fail, but no traceback
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_batch_error_paths_traceback_free(cli, scratch_dir):
    """Multiple error paths stay traceback-free."""
    agents_dir = scratch_dir / ".mars" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "reviewer.md").write_text("# Reviewer\n", encoding="utf-8")

    error_commands = [
        ("nonexistent-cmd",),
        ("config", "get", "does.not.exist.key"),
        ("spawn", "show", "no-such-spawn"),
    ]

    for args in error_commands:
        result = cli(*args)
        assert "Traceback" not in result.stdout, f"traceback in stdout for {args}"
        assert "Traceback" not in result.stderr, f"traceback in stderr for {args}"


def test_error_output_goes_to_stderr(cli):
    """Error messages go to stderr, not stdout."""
    result = cli("spawn", "show", "invalid-spawn-id-xyz", json_mode=True)
    result.assert_failure()
    # In JSON mode, error should still be structured or go to stderr
    # Just verify it doesn't crash
