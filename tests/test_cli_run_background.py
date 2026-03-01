"""CLI integration checks for run.spawn --background behavior."""

from __future__ import annotations

import json
import re
import importlib
from pathlib import Path

from meridian.cli.output import OutputConfig
from meridian.lib.ops.run import RunActionOutput
from meridian.lib.space.space_file import create_space

cli_main = importlib.import_module("meridian.cli.main")


def test_run_create_background_prints_run_id_in_text_mode(
    run_meridian,
    cli_env: dict[str, str],
    tmp_path: Path,
) -> None:
    cli_env["MERIDIAN_REPO_ROOT"] = tmp_path.as_posix()
    space = create_space(tmp_path, name="cli-bg")
    cli_env["MERIDIAN_SPACE_ID"] = space.id

    created = run_meridian(
        [
            "--format",
            "text",
            "run",
            "--background",
            "--timeout-secs",
            "0.1",
            "-p",
            "background smoke",
        ],
        timeout=20,
    )
    assert created.returncode == 0, created.stderr
    run_id = created.stdout.strip()
    assert re.fullmatch(r"r[0-9]+", run_id), created.stdout

    waited = run_meridian(
        [
            "--json",
            "run",
            "wait",
            run_id,
            "--timeout-secs",
            "30",
        ],
        timeout=35,
    )
    payload = json.loads(waited.stdout)
    assert payload["run_id"] == run_id
    if payload["status"] == "succeeded":
        assert waited.returncode == 0, waited.stderr
    else:
        assert waited.returncode == 1, waited.stderr


def test_run_create_background_writes_metadata_to_stderr(
    run_meridian,
    cli_env: dict[str, str],
    tmp_path: Path,
) -> None:
    cli_env["MERIDIAN_REPO_ROOT"] = tmp_path.as_posix()
    space = create_space(tmp_path, name="cli-bg-meta")
    cli_env["MERIDIAN_SPACE_ID"] = space.id

    created = run_meridian(
        [
            "--format",
            "text",
            "run",
            "--background",
            "--timeout-secs",
            "0.1",
            "-p",
            "background metadata smoke",
        ],
        timeout=20,
    )
    assert created.returncode == 0, created.stderr
    run_id = created.stdout.strip()
    assert re.fullmatch(r"r[0-9]+", run_id), created.stdout
    assert f"run_id={run_id}" in created.stderr
    assert "status=running" in created.stderr


def test_run_spawn_text_emit_prints_report_to_stdout_and_metadata_to_stderr(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MERIDIAN_SPACE_ID", "s1")
    monkeypatch.setattr(cli_main, "resolve_repo_root", lambda: tmp_path)

    report_path = tmp_path / ".meridian" / ".spaces" / "s1" / "runs" / "r1" / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("# Report\n\ndone\n", encoding="utf-8")

    token = cli_main._GLOBAL_OPTIONS.set(cli_main.GlobalOptions(output=OutputConfig(format="text")))
    try:
        cli_main.emit(
            RunActionOutput(
                command="run.spawn",
                status="succeeded",
                run_id="r1",
                model="gpt-5.3-codex",
                harness_id="codex",
                duration_secs=1.2,
                exit_code=0,
            )
        )
    finally:
        cli_main._GLOBAL_OPTIONS.reset(token)

    captured = capsys.readouterr()
    assert "# Report" in captured.out
    assert "run_id=r1" in captured.err
    assert "status=succeeded" in captured.err
    assert "warning: no report extracted" not in captured.err


def test_run_spawn_text_emit_warns_when_report_is_missing(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setenv("MERIDIAN_SPACE_ID", "s1")
    monkeypatch.setattr(cli_main, "resolve_repo_root", lambda: tmp_path)

    token = cli_main._GLOBAL_OPTIONS.set(cli_main.GlobalOptions(output=OutputConfig(format="text")))
    try:
        cli_main.emit(
            RunActionOutput(
                command="run.spawn",
                status="failed",
                run_id="r2",
                model="gpt-5.3-codex",
                harness_id="codex",
                duration_secs=2.0,
                exit_code=1,
            )
        )
    finally:
        cli_main._GLOBAL_OPTIONS.reset(token)

    captured = capsys.readouterr()
    assert captured.out.strip() == ""
    assert "run_id=r2" in captured.err
    assert "status=failed" in captured.err
    assert "warning: no report extracted for run 'r2'" in captured.err
