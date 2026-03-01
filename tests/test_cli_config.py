"""CLI integration checks for config commands (Slice 5)."""

from __future__ import annotations

import json
from pathlib import Path


def _source_by_key(payload: dict[str, object]) -> dict[str, str]:
    values = payload.get("values")
    assert isinstance(values, list)

    sources: dict[str, str] = {}
    for item in values:
        assert isinstance(item, dict)
        key = item.get("key")
        source = item.get("source")
        assert isinstance(key, str)
        assert isinstance(source, str)
        sources[key] = source
    return sources


def test_config_init_creates_file(tmp_path: Path, run_meridian, cli_env: dict[str, str]) -> None:
    cli_env["MERIDIAN_REPO_ROOT"] = tmp_path.as_posix()

    result = run_meridian(["config", "init"])

    assert result.returncode == 0
    config_path = tmp_path / ".meridian" / "config.toml"
    assert config_path.is_file()

    content = config_path.read_text(encoding="utf-8")
    assert "[defaults]" in content
    assert "# max_depth = 3" in content
    assert "[output]" in content


def test_config_set_get_roundtrip(tmp_path: Path, run_meridian, cli_env: dict[str, str]) -> None:
    cli_env["MERIDIAN_REPO_ROOT"] = tmp_path.as_posix()

    set_result = run_meridian(["config", "set", "defaults.max_depth", "9"])
    assert set_result.returncode == 0

    get_result = run_meridian(["--json", "config", "get", "defaults.max_depth"])
    assert get_result.returncode == 0

    payload = json.loads(get_result.stdout)
    assert payload["key"] == "defaults.max_depth"
    assert payload["value"] == 9
    assert payload["source"] == "file"


def test_config_legacy_primary_agent_alias_roundtrip(
    tmp_path: Path,
    run_meridian,
    cli_env: dict[str, str],
) -> None:
    cli_env["MERIDIAN_REPO_ROOT"] = tmp_path.as_posix()

    set_result = run_meridian(["config", "set", "defaults.primary_agent", "legacy-primary"])
    assert set_result.returncode == 0

    get_result = run_meridian(["--json", "config", "get", "default_primary_agent"])
    assert get_result.returncode == 0

    payload = json.loads(get_result.stdout)
    assert payload["key"] == "defaults.default_primary_agent"
    assert payload["value"] == "legacy-primary"
    assert payload["source"] == "file"


def test_config_reset_removes_key(tmp_path: Path, run_meridian, cli_env: dict[str, str]) -> None:
    cli_env["MERIDIAN_REPO_ROOT"] = tmp_path.as_posix()

    assert run_meridian(["config", "set", "defaults.max_depth", "9"]).returncode == 0
    reset_result = run_meridian(["config", "reset", "defaults.max_depth"])
    assert reset_result.returncode == 0

    config_path = tmp_path / ".meridian" / "config.toml"
    content = config_path.read_text(encoding="utf-8")
    assert "max_depth" not in content

    get_result = run_meridian(["--json", "config", "get", "defaults.max_depth"])
    assert get_result.returncode == 0
    payload = json.loads(get_result.stdout)
    assert payload["value"] == 3
    assert payload["source"] == "builtin"


def test_config_show_displays_sources(
    tmp_path: Path,
    run_meridian,
    cli_env: dict[str, str],
) -> None:
    cli_env["MERIDIAN_REPO_ROOT"] = tmp_path.as_posix()

    assert run_meridian(["config", "set", "defaults.max_retries", "6"]).returncode == 0
    cli_env["MERIDIAN_MAX_DEPTH"] = "11"

    show_result = run_meridian(["--json", "config", "show"])
    assert show_result.returncode == 0

    payload = json.loads(show_result.stdout)
    by_key = _source_by_key(payload)

    assert by_key["defaults.max_depth"] == "env var"
    assert by_key["defaults.max_retries"] == "file"
    assert by_key["defaults.default_primary_agent"] == "builtin"


def test_config_show_warns_when_repo_root_does_not_exist(
    run_meridian,
    cli_env: dict[str, str],
) -> None:
    cli_env["MERIDIAN_REPO_ROOT"] = "/does/not/exist"

    show_result = run_meridian(["--json", "config", "show"])
    assert show_result.returncode == 0

    payload = json.loads(show_result.stdout)
    warning = payload.get("warning")
    assert isinstance(warning, str)
    assert "does not exist on disk" in warning


def test_config_show_displays_user_config_source(
    tmp_path: Path,
    run_meridian,
    cli_env: dict[str, str],
) -> None:
    cli_env["MERIDIAN_REPO_ROOT"] = tmp_path.as_posix()

    assert run_meridian(["config", "set", "defaults.max_depth", "4"]).returncode == 0
    user_config = tmp_path / "user.toml"
    user_config.write_text("[defaults]\nmax_depth = 9\n", encoding="utf-8")

    show_result = run_meridian(
        ["--json", "--config", user_config.as_posix(), "config", "show"]
    )
    assert show_result.returncode == 0

    payload = json.loads(show_result.stdout)
    by_key = _source_by_key(payload)
    assert by_key["defaults.max_depth"] == "user-config"
