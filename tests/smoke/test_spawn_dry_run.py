"""Spawn dry-run smoke tests — prompt assembly without harness invocation.

Replaces: tests/e2e/spawn/dry-run.md
"""


def test_basic_dry_run(cli, scratch_dir):
    """Basic dry-run outputs launch spec with composed prompt."""
    # Create minimal agent
    agents_dir = scratch_dir / ".mars" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "reviewer.md").write_text("# Reviewer\n", encoding="utf-8")

    result = cli(
        "spawn", "-a", "reviewer", "-p", "Write hello world",
        "--dry-run", json_mode=True
    )
    result.assert_success()
    data = result.json
    assert data["status"] == "dry-run"
    assert "Write hello world" in data["composed_prompt"]
    assert "model" in data


def test_model_override(cli, scratch_dir):
    """Model override is accepted in dry-run."""
    agents_dir = scratch_dir / ".mars" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "reviewer.md").write_text("# Reviewer\n", encoding="utf-8")
    # Seed mars.toml so model resolution works
    mars_content = "[settings]\nmodels_cache_ttl_hours = 24\n"
    (scratch_dir / "mars.toml").write_text(mars_content, encoding="utf-8")

    result = cli(
        "spawn", "-a", "reviewer", "-p", "test", "-m", "sonnet",
        "--dry-run", json_mode=True
    )
    result.assert_success()
    data = result.json
    assert data["status"] == "dry-run"
    assert data.get("model")  # Model should be set


def test_template_vars_substitution(cli, scratch_dir):
    """Template vars are substituted in prompt."""
    agents_dir = scratch_dir / ".mars" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "reviewer.md").write_text("# Reviewer\n", encoding="utf-8")

    result = cli(
        "spawn", "-a", "reviewer",
        "-p", "Review {{FILE_PATH}} for {{CONCERN}}",
        "--prompt-var", "FILE_PATH=src/main.py",
        "--prompt-var", "CONCERN=security",
        "--dry-run",
        json_mode=True
    )
    result.assert_success()
    data = result.json
    prompt = data["composed_prompt"]
    assert "src/main.py" in prompt
    assert "security" in prompt
    assert "{{FILE_PATH}}" not in prompt
    assert "{{CONCERN}}" not in prompt


def test_reference_files_attached(cli, scratch_dir, tmp_path):
    """Reference files are included in dry-run payload."""
    agents_dir = scratch_dir / ".mars" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "reviewer.md").write_text("# Reviewer\n", encoding="utf-8")

    # Create a reference file
    ref_file = tmp_path / "ref.md"
    ref_file.write_text("# Reference\n", encoding="utf-8")

    result = cli(
        "spawn", "-a", "reviewer",
        "-p", "Review this file",
        "-f", str(ref_file),
        "--dry-run",
        json_mode=True
    )
    result.assert_success()
    data = result.json
    # Reference files should be in the payload
    refs = data.get("reference_files", [])
    assert refs or "ref.md" in str(data)  # Either explicit refs or mentioned


def test_empty_prompt_handled_gracefully(cli, scratch_dir):
    """Empty prompt fails or succeeds cleanly without traceback."""
    agents_dir = scratch_dir / ".mars" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "reviewer.md").write_text("# Reviewer\n", encoding="utf-8")

    result = cli(
        "spawn", "-a", "reviewer", "-p", "", "--dry-run", json_mode=True
    )
    # May succeed or fail, but should not traceback
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr
