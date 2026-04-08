import importlib
import json
import subprocess
from pathlib import Path

import pytest

cli_main = importlib.import_module("meridian.cli.main")
mars_ops = importlib.import_module("meridian.lib.ops.mars")


def test_resolve_mars_executable_prefers_current_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    scripts_dir = tmp_path / "bin"
    scripts_dir.mkdir()
    (scripts_dir / "mars").write_text("", encoding="utf-8")
    monkeypatch.setattr(mars_ops.sys, "executable", str(scripts_dir / "python"))
    monkeypatch.setattr(mars_ops.shutil, "which", lambda *_args, **_kwargs: "/usr/bin/mars")

    resolved = cli_main._resolve_mars_executable()

    assert resolved == str(scripts_dir / "mars")


def test_resolve_mars_executable_falls_back_to_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    scripts_dir = tmp_path / "bin"
    scripts_dir.mkdir()
    monkeypatch.setattr(mars_ops.sys, "executable", str(scripts_dir / "python"))
    monkeypatch.setattr(mars_ops.shutil, "which", lambda *_args, **_kwargs: "/usr/bin/mars")

    resolved = cli_main._resolve_mars_executable()

    assert resolved == "/usr/bin/mars"


def test_resolve_mars_executable_uses_symlink_parent_not_resolved_parent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool_bin = tmp_path / "tool-bin"
    real_bin = tmp_path / "real-bin"
    tool_bin.mkdir()
    real_bin.mkdir()
    (tool_bin / "mars").write_text("", encoding="utf-8")
    (tool_bin / "python3").symlink_to(real_bin / "python3")

    monkeypatch.setattr(mars_ops.sys, "executable", str(tool_bin / "python3"))
    monkeypatch.setattr(mars_ops.shutil, "which", lambda *_args, **_kwargs: "/usr/bin/mars")

    resolved = cli_main._resolve_mars_executable()

    assert resolved == str(tool_bin / "mars")


def test_parse_mars_passthrough_builds_sync_json_request() -> None:
    request = cli_main._parse_mars_passthrough(
        ["--root", "/tmp/demo", "sync"],
        output_format="json",
        executable="/usr/bin/mars",
    )

    assert request.command == ("/usr/bin/mars", "--json", "--root", "/tmp/demo", "sync")
    assert request.mars_args == ("--json", "--root", "/tmp/demo", "sync")
    assert request.is_sync is True
    assert request.wants_json is True
    assert request.root_override == Path("/tmp/demo")


def test_execute_mars_passthrough_captures_json_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = cli_main._MarsPassthroughRequest(
        command=("/usr/bin/mars", "--json", "sync"),
        mars_args=("--json", "sync"),
        is_sync=True,
        wants_json=True,
        root_override=None,
    )

    def _fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command == ["/usr/bin/mars", "--json", "sync"]
        assert kwargs.get("capture_output") is True
        assert kwargs.get("text") is True
        return subprocess.CompletedProcess(
            args=command,
            returncode=7,
            stdout='{"ok": false}\n',
            stderr="warning",
        )

    monkeypatch.setattr(cli_main.subprocess, "run", _fake_run)

    result = cli_main._execute_mars_passthrough(request)

    assert result.returncode == 7
    assert result.stdout_text == '{"ok": false}\n'
    assert result.stderr_text == "warning"


def test_execute_mars_passthrough_streams_text_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = cli_main._MarsPassthroughRequest(
        command=("/usr/bin/mars", "sync"),
        mars_args=("sync",),
        is_sync=True,
        wants_json=False,
        root_override=None,
    )

    def _fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command == ["/usr/bin/mars", "sync"]
        assert "capture_output" not in kwargs
        assert "text" not in kwargs
        return subprocess.CompletedProcess(args=command, returncode=3, stdout="", stderr="")

    monkeypatch.setattr(cli_main.subprocess, "run", _fake_run)

    result = cli_main._execute_mars_passthrough(request)

    assert result.returncode == 3
    assert result.stdout_text == ""
    assert result.stderr_text == ""


def test_augment_sync_result_prints_hint_lines_in_text_mode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = cli_main._MarsPassthroughRequest(
        command=("/usr/bin/mars", "sync"),
        mars_args=("sync",),
        is_sync=True,
        wants_json=False,
        root_override=Path("/tmp/repo"),
    )
    result = cli_main._MarsPassthroughResult(request=request, returncode=0)
    monkeypatch.setattr(
        cli_main,
        "check_upgrade_availability",
        lambda *_args, **_kwargs: mars_ops.UpgradeAvailability(
            within_constraint=("meridian-base",),
        ),
    )

    cli_main._augment_sync_result(result, output_format="text")

    captured = capsys.readouterr()
    assert "hint: 1 update available within your pinned constraint: meridian-base." in (
        captured.out
    )
    assert "Run `meridian mars upgrade` to apply." in captured.out


def test_augment_sync_result_injects_hint_in_json_mode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = cli_main._MarsPassthroughRequest(
        command=("/usr/bin/mars", "--json", "sync"),
        mars_args=("--json", "sync"),
        is_sync=True,
        wants_json=True,
        root_override=None,
    )
    result = cli_main._MarsPassthroughResult(
        request=request,
        returncode=0,
        stdout_text='{"ok": true}\n',
    )
    monkeypatch.setattr(
        cli_main,
        "check_upgrade_availability",
        lambda *_args, **_kwargs: mars_ops.UpgradeAvailability(
            beyond_constraint=("meridian-base",),
        ),
    )

    cli_main._augment_sync_result(result, output_format="json")

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["upgrade_hint"] == {
        "within_constraint": [],
        "beyond_constraint": ["meridian-base"],
    }


def test_run_mars_passthrough_sync_detects_exact_pin_beyond_constraint_in_text_mode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_main, "_resolve_mars_executable", lambda: "/usr/bin/mars")
    monkeypatch.setattr(mars_ops, "resolve_mars_executable", lambda: "/usr/bin/mars")
    outdated_payload = [
        {
            "source": "meridian-base",
            "locked": "v0.0.11",
            "constraint": "v0.0.11",
            "updateable": "v0.0.11",
            "latest": "v0.0.12",
        }
    ]

    def _fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if len(command) >= 2 and command[1] == "outdated":
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=json.dumps(outdated_payload),
                stderr="",
            )
        assert "sync" in command
        assert "capture_output" not in kwargs
        assert "text" not in kwargs
        print("sync output")
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(cli_main.subprocess, "run", _fake_run)

    with pytest.raises(SystemExit) as exc_info:
        cli_main._run_mars_passthrough(["sync"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "sync output\n" in captured.out
    assert (
        "hint: 1 newer version available beyond your pinned constraint: meridian-base."
        in captured.out
    )
    assert (
        "Edit mars.toml to bump the version, then run `meridian mars sync`." in captured.out
    )


def test_run_mars_passthrough_sync_detects_exact_pin_beyond_constraint_in_json_mode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_main, "_resolve_mars_executable", lambda: "/usr/bin/mars")
    monkeypatch.setattr(mars_ops, "resolve_mars_executable", lambda: "/usr/bin/mars")
    outdated_payload = [
        {
            "source": "meridian-base",
            "locked": "v0.0.11",
            "constraint": "v0.0.11",
            "updateable": "v0.0.11",
            "latest": "v0.0.12",
        }
    ]

    def _fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if len(command) >= 2 and command[1] == "outdated":
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=json.dumps(outdated_payload),
                stderr="",
            )
        assert "sync" in command
        assert kwargs.get("capture_output") is True
        assert kwargs.get("text") is True
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout='{"ok": true}\n',
            stderr="",
        )

    monkeypatch.setattr(cli_main.subprocess, "run", _fake_run)

    with pytest.raises(SystemExit) as exc_info:
        cli_main._run_mars_passthrough(["sync"], output_format="json")

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["upgrade_hint"] == {
        "within_constraint": [],
        "beyond_constraint": ["meridian-base"],
    }


def test_run_mars_passthrough_sync_prints_within_constraint_hint_in_text_mode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_main, "_resolve_mars_executable", lambda: "/usr/bin/mars")
    monkeypatch.setattr(
        cli_main,
        "check_upgrade_availability",
        lambda *_args, **_kwargs: mars_ops.UpgradeAvailability(
            within_constraint=("meridian-base",),
        ),
    )

    def _fake_run(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert "capture_output" not in kwargs
        assert "text" not in kwargs
        print("sync output")
        return subprocess.CompletedProcess(
            args=["/usr/bin/mars", "sync"],
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(cli_main.subprocess, "run", _fake_run)

    with pytest.raises(SystemExit) as exc_info:
        cli_main._run_mars_passthrough(["sync"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "sync output\n" in captured.out
    assert "hint: 1 update available within your pinned constraint: meridian-base." in captured.out
    assert "Run `meridian mars upgrade` to apply." in captured.out


def test_run_mars_passthrough_sync_prints_beyond_constraint_hint_in_text_mode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_main, "_resolve_mars_executable", lambda: "/usr/bin/mars")
    monkeypatch.setattr(
        cli_main,
        "check_upgrade_availability",
        lambda *_args, **_kwargs: mars_ops.UpgradeAvailability(
            beyond_constraint=("meridian-base",),
        ),
    )

    def _fake_run(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert "capture_output" not in kwargs
        assert "text" not in kwargs
        print("sync output")
        return subprocess.CompletedProcess(
            args=["/usr/bin/mars", "sync"],
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(cli_main.subprocess, "run", _fake_run)

    with pytest.raises(SystemExit) as exc_info:
        cli_main._run_mars_passthrough(["sync"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "sync output\n" in captured.out
    assert (
        "hint: 1 newer version available beyond your pinned constraint: meridian-base."
        in captured.out
    )
    assert (
        "Edit mars.toml to bump the version, then run `meridian mars sync`." in captured.out
    )


def test_run_mars_passthrough_sync_prints_both_upgrade_categories_in_text_mode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_main, "_resolve_mars_executable", lambda: "/usr/bin/mars")
    monkeypatch.setattr(
        cli_main,
        "check_upgrade_availability",
        lambda *_args, **_kwargs: mars_ops.UpgradeAvailability(
            within_constraint=("foo", "bar"),
            beyond_constraint=("meridian-base",),
        ),
    )

    def _fake_run(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert "capture_output" not in kwargs
        assert "text" not in kwargs
        print("sync output")
        return subprocess.CompletedProcess(
            args=["/usr/bin/mars", "sync"],
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(cli_main.subprocess, "run", _fake_run)

    with pytest.raises(SystemExit) as exc_info:
        cli_main._run_mars_passthrough(["sync"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "sync output\n" in captured.out
    assert "hint: 2 updates available within your pinned constraint: foo, bar." in captured.out
    assert "Run `meridian mars upgrade` to apply." in captured.out
    assert (
        "1 newer version available beyond your pinned constraint: meridian-base."
        in captured.out
    )
    assert (
        "Edit mars.toml to bump the version, then run `meridian mars sync`." in captured.out
    )


def test_run_mars_passthrough_sync_injects_upgrade_hint_in_json_mode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_main, "_resolve_mars_executable", lambda: "/usr/bin/mars")
    monkeypatch.setattr(
        cli_main,
        "check_upgrade_availability",
        lambda *_args, **_kwargs: mars_ops.UpgradeAvailability(
            within_constraint=("foo", "bar"),
            beyond_constraint=("meridian-base",),
        ),
    )
    commands: list[list[str]] = []
    run_kwargs: list[dict[str, object]] = []

    def _fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        run_kwargs.append(dict(_kwargs))
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout='{"ok": true, "installed": 0}\n',
            stderr="",
        )

    monkeypatch.setattr(cli_main.subprocess, "run", _fake_run)

    with pytest.raises(SystemExit) as exc_info:
        cli_main._run_mars_passthrough(["sync"], output_format="json")

    assert exc_info.value.code == 0
    assert commands and "--json" in commands[0]
    assert run_kwargs and run_kwargs[0].get("capture_output") is True
    assert run_kwargs[0].get("text") is True
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["upgrade_hint"] == {
        "within_constraint": ["foo", "bar"],
        "beyond_constraint": ["meridian-base"],
    }


def test_run_mars_passthrough_sync_stays_silent_when_upgrade_check_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_main, "_resolve_mars_executable", lambda: "/usr/bin/mars")
    monkeypatch.setattr(
        cli_main,
        "check_upgrade_availability",
        lambda *_args, **_kwargs: None,
    )

    def _fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        print("sync output")
        return subprocess.CompletedProcess(
            args=["/usr/bin/mars", "sync"],
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(cli_main.subprocess, "run", _fake_run)

    with pytest.raises(SystemExit) as exc_info:
        cli_main._run_mars_passthrough(["sync"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert captured.out == "sync output\n"


def test_main_mars_defaults_to_json_in_agent_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    monkeypatch.setattr(cli_main, "_interactive_terminal_attached", lambda: False)
    captured: dict[str, object] = {}

    def _fake_passthrough(args: object, *, output_format: str | None = None) -> None:
        captured["args"] = args
        captured["output_format"] = output_format
        raise SystemExit(0)

    monkeypatch.setattr(cli_main, "_run_mars_passthrough", _fake_passthrough)

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["mars", "sync"])

    assert exc_info.value.code == 0
    assert captured["args"] == ["sync"]
    assert captured["output_format"] == "json"


def test_run_mars_passthrough_list_honors_json_mode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_main, "_resolve_mars_executable", lambda: "/usr/bin/mars")
    commands: list[list[str]] = []
    run_kwargs: list[dict[str, object]] = []

    def _fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        run_kwargs.append(dict(_kwargs))
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout='{"packages": []}\n',
            stderr="",
        )

    monkeypatch.setattr(cli_main.subprocess, "run", _fake_run)

    with pytest.raises(SystemExit) as exc_info:
        cli_main._run_mars_passthrough(["list"], output_format="json")

    assert exc_info.value.code == 0
    assert commands and commands[0] == ["/usr/bin/mars", "--json", "list"]
    assert run_kwargs and run_kwargs[0].get("capture_output") is True
    assert run_kwargs[0].get("text") is True
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload == {"packages": []}


def test_agent_mode_mars_list_emits_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    monkeypatch.setattr(cli_main, "_interactive_terminal_attached", lambda: False)
    monkeypatch.setattr(cli_main, "_resolve_mars_executable", lambda: "/usr/bin/mars")
    commands: list[list[str]] = []
    run_kwargs: list[dict[str, object]] = []

    def _fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        run_kwargs.append(dict(_kwargs))
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout='{"packages": []}\n',
            stderr="",
        )

    monkeypatch.setattr(cli_main.subprocess, "run", _fake_run)

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["mars", "list"])

    assert exc_info.value.code == 0
    assert commands and commands[0] == ["/usr/bin/mars", "--json", "list"]
    assert run_kwargs and run_kwargs[0].get("capture_output") is True
    assert run_kwargs[0].get("text") is True
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload == {"packages": []}
