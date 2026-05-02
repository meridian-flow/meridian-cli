"""Output format smoke tests — JSON and text rendering.

Replaces: tests/e2e/output-formats.md
"""

import json


def test_json_flag_produces_json_spawn_dry_run(cli, scratch_dir):
    """--json flag produces valid JSON for spawn dry-run."""
    agents_dir = scratch_dir / ".mars" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "test.md").write_text("# Test\n", encoding="utf-8")
    
    result = cli("spawn", "-a", "test", "-p", "probe", "--dry-run", json_mode=True)
    result.assert_success()
    # Should parse as JSON
    data = result.json
    assert isinstance(data, dict)


def test_json_flag_produces_json_doctor(cli):
    """--json flag produces valid JSON for doctor."""
    result = cli("doctor", json_mode=True)
    result.assert_success()
    data = result.json
    assert isinstance(data, dict)


def test_json_flag_produces_json_work_current(cli):
    """--json flag produces valid JSON for work current."""
    result = cli("work", "current", json_mode=True)
    # May succeed or return null, but should be valid JSON
    if result.returncode == 0:
        data = result.json
        assert data is None or isinstance(data, (dict, str))


def test_format_text_produces_text(cli):
    """--format text produces human-readable non-JSON output."""
    result = cli("--format", "text", "doctor")
    result.assert_success()
    # Should not start with JSON
    stripped = result.stdout.strip()
    assert not stripped.startswith("{"), "Expected text, got JSON"


def test_format_json_explicit(cli, scratch_dir):
    """--format json produces valid JSON."""
    agents_dir = scratch_dir / ".mars" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "test.md").write_text("# Test\n", encoding="utf-8")
    
    result = cli("--format", "json", "spawn", "-a", "test", "-p", "test", "--dry-run")
    result.assert_success()
    data = json.loads(result.stdout)
    assert isinstance(data, dict)
