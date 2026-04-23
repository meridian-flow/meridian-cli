"""Integration tests for ext CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _isolated_env(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["MERIDIAN_HOME"] = (tmp_path / "meridian-home").as_posix()
    env["MERIDIAN_PROJECT_DIR"] = (tmp_path / "project").as_posix()
    return env


def _run_ext(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "meridian", "ext", *args],
        capture_output=True,
        text=True,
        env=_isolated_env(tmp_path),
        check=False,
    )


def _write_project_uuid(project_root: Path, project_uuid: str) -> None:
    meridian_dir = project_root / ".meridian"
    meridian_dir.mkdir(parents=True, exist_ok=True)
    (meridian_dir / "id").write_text(project_uuid, encoding="utf-8")


def _write_stale_endpoint(tmp_path: Path, project_uuid: str) -> None:
    runtime_root = tmp_path / "meridian-home" / "projects" / project_uuid
    instance_dir = runtime_root / "app" / "999999999"
    instance_dir.mkdir(parents=True, exist_ok=True)
    (instance_dir / "token").write_text("stale-token", encoding="utf-8")
    (instance_dir / "endpoint.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "instance_id": "stale-instance",
                "transport": "tcp",
                "host": "127.0.0.1",
                "port": 9999,
                "project_uuid": project_uuid,
                "repo_root": (tmp_path / "project").as_posix(),
                "pid": 999999999,
                "started_at": "2026-04-23T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )


class TestExtCliIntegration:
    """Integration tests for ext CLI commands."""

    def test_ext_commands_json_has_expected_shape_and_cli_surface(self, tmp_path: Path) -> None:
        result = _run_ext(tmp_path, "commands", "--json")

        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert set(payload.keys()) == {"schema_version", "manifest_hash", "commands"}
        assert payload["schema_version"] == 1

        assert payload["commands"], "expected at least one CLI command"
        first = payload["commands"][0]
        assert set(first.keys()) == {
            "fqid",
            "extension_id",
            "command_id",
            "summary",
            "surfaces",
            "requires_app_server",
        }
        assert all("cli" in command["surfaces"] for command in payload["commands"])
        assert any(command["fqid"] == "meridian.workbench.ping" for command in payload["commands"])

    def test_ext_show_returns_extension_details_offline(self, tmp_path: Path) -> None:
        text_result = _run_ext(tmp_path, "show", "meridian.workbench")
        json_result = _run_ext(tmp_path, "show", "meridian.workbench", "--format", "json")

        assert text_result.returncode == 0
        assert "Extension: meridian.workbench" in text_result.stdout
        assert "ping" in text_result.stdout

        assert json_result.returncode == 0
        payload = json.loads(json_result.stdout)
        assert payload["extension_id"] == "meridian.workbench"
        assert payload["commands"] == [
            {
                "command_id": "ping",
                "summary": "Health check for extension system",
                "surfaces": ["cli", "http", "mcp"],
                "requires_app_server": True,
            }
        ]

    def test_ext_run_invalid_json_exits_7(self, tmp_path: Path) -> None:
        result = _run_ext(tmp_path, "run", "demo.cmd", "--args", "{bad")
        assert result.returncode == 7
        assert "Invalid JSON args" in result.stderr

    def test_ext_run_no_server_exits_2(self, tmp_path: Path) -> None:
        result = _run_ext(
            tmp_path,
            "run",
            "meridian.sessions.getSpawnStats",
            "--args",
            '{"spawn_id":"p123"}',
        )
        assert result.returncode == 2
        assert "No app server running" in result.stderr

    def test_ext_run_stale_endpoint_exits_3(self, tmp_path: Path) -> None:
        project_uuid = "project-stale-uuid"
        _write_project_uuid(tmp_path / "project", project_uuid)
        _write_stale_endpoint(tmp_path, project_uuid)

        result = _run_ext(
            tmp_path,
            "run",
            "meridian.sessions.getSpawnStats",
            "--args",
            '{"spawn_id":"p123"}',
        )

        assert result.returncode == 3
        assert "App server endpoint is stale" in result.stderr
