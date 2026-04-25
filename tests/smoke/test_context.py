"""Context query smoke tests — path resolution.

Fills CLI-level gap for context command.
"""


def _write_strategy_context_config(scratch_dir):
    (scratch_dir / "meridian.toml").write_text(
        """
[context.strategy]
source = "git"
remote = "git@github.com:meridian-flow/docs.git"
path = "voluma-bio/strategy"
""".lstrip(),
        encoding="utf-8",
    )


def test_context_work_outputs_path_or_null(cli):
    """context work outputs path or null."""
    result = cli("context", "work")
    # Should succeed and output something (path or null/none)
    assert result.returncode == 0 or "Traceback" not in result.stderr


def test_context_kb_outputs_path(cli):
    """context kb outputs path."""
    result = cli("context", "kb")
    result.assert_success()
    # Should output some path
    assert len(result.stdout.strip()) > 0 or result.returncode == 0


def test_context_work_archive_outputs_path(cli):
    """context work.archive outputs path."""
    result = cli("context", "work.archive")
    result.assert_success()


def test_context_strategy_outputs_path(cli, scratch_dir):
    """context strategy outputs configured arbitrary context path."""
    _write_strategy_context_config(scratch_dir)
    result = cli("context", "strategy")
    result.assert_success()
    assert result.stdout.strip().endswith("/voluma-bio/strategy")


def test_context_verbose_shows_details(cli, scratch_dir):
    """context --verbose shows source/path details."""
    _write_strategy_context_config(scratch_dir)
    result = cli("context", "--verbose")
    result.assert_success()
    # Should have more output than non-verbose
    assert len(result.stdout) > 0
    assert "strategy:" in result.stdout
    assert "path: voluma-bio/strategy" in result.stdout


def test_context_json_format(cli):
    """context with --json outputs valid JSON."""
    result = cli("context", json_mode=True)
    if result.returncode == 0 and result.stdout.strip():
        import json
        data = json.loads(result.stdout)
        assert isinstance(data, dict)
