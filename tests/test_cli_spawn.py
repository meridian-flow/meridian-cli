import importlib
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from meridian.lib.ops.spawn.models import (
    SpawnActionOutput,
    SpawnCancelInput,
    SpawnContinueInput,
    SpawnCreateInput,
    SpawnListInput,
    SpawnListOutput,
)

spawn_cli = importlib.import_module("meridian.cli.spawn")
cli_main = importlib.import_module("meridian.cli.main")


class _FakeStdin(io.StringIO):
    def __init__(self, text: str, *, is_tty: bool) -> None:
        super().__init__(text)
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


class _InvalidUtf8Stdin:
    def isatty(self) -> bool:
        return False

    def read(self) -> str:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")


def _capture_create_prompt(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    captured: dict[str, object] = {}

    def _fake_spawn_create_sync(
        payload: SpawnCreateInput,
        *,
        sink=None,
    ) -> SpawnActionOutput:
        _ = sink
        captured["prompt"] = payload.prompt
        captured["files"] = payload.files
        return SpawnActionOutput(command="spawn.create", status="dry-run")

    monkeypatch.setattr(spawn_cli, "spawn_create_sync", _fake_spawn_create_sync)
    monkeypatch.setattr(spawn_cli, "current_output_sink", lambda: None)
    return captured


def _capture_continue_prompt(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    captured: dict[str, str] = {}

    def _fake_spawn_continue_sync(
        payload: SpawnContinueInput,
        *,
        sink=None,
    ) -> SpawnActionOutput:
        _ = sink
        captured["spawn_id"] = payload.spawn_id
        captured["prompt"] = payload.prompt
        return SpawnActionOutput(command="spawn.continue", status="dry-run")

    monkeypatch.setattr(spawn_cli, "spawn_continue_sync", _fake_spawn_continue_sync)
    monkeypatch.setattr(spawn_cli, "current_output_sink", lambda: None)
    return captured


def _capture_list_payload(monkeypatch: pytest.MonkeyPatch) -> dict[str, SpawnListInput]:
    captured: dict[str, SpawnListInput] = {}

    def _fake_spawn_list_sync(
        payload: SpawnListInput,
        *,
        sink=None,
    ) -> SpawnListOutput:
        _ = sink
        captured["payload"] = payload
        return SpawnListOutput(spawns=())

    monkeypatch.setattr(spawn_cli, "spawn_list_sync", _fake_spawn_list_sync)
    monkeypatch.setattr(spawn_cli, "current_output_sink", lambda: None)
    return captured


def test_spawn_create_literal_prompt_is_used_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_create_prompt(monkeypatch)
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("ignored stdin", is_tty=False))

    spawn_cli._spawn_create(lambda _payload: None, prompt="literal prompt")

    assert captured["prompt"] == "literal prompt"


def test_spawn_create_prompt_file_reads_prompt_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_create_prompt(monkeypatch)
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("line 1\nline 2\n", encoding="utf-8")
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("ignored stdin", is_tty=False))

    spawn_cli._spawn_create(lambda _payload: None, prompt_file=prompt_file.as_posix())

    assert captured["prompt"] == "line 1\nline 2\n"


def test_spawn_create_prompt_file_missing_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    missing_path = (tmp_path / "missing.md").as_posix()
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("", is_tty=True))

    with pytest.raises(ValueError) as exc_info:
        spawn_cli._spawn_create(lambda _payload: None, prompt_file=missing_path)

    assert str(exc_info.value) == f"prompt file not found: {missing_path}"


def test_spawn_create_prompt_file_empty_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prompt_file = tmp_path / "empty.md"
    prompt_file.write_text("", encoding="utf-8")
    prompt_path = prompt_file.as_posix()
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("", is_tty=True))

    with pytest.raises(ValueError) as exc_info:
        spawn_cli._spawn_create(lambda _payload: None, prompt_file=prompt_path)

    assert str(exc_info.value) == f"prompt file is empty: {prompt_path}"


def test_spawn_create_prompt_file_invalid_utf8_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prompt_file = tmp_path / "invalid.md"
    prompt_file.write_bytes(b"\xff\xfe")
    prompt_path = prompt_file.as_posix()
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("", is_tty=True))

    with pytest.raises(ValueError) as exc_info:
        spawn_cli._spawn_create(lambda _payload: None, prompt_file=prompt_path)

    assert str(exc_info.value) == f"prompt file is not valid UTF-8: {prompt_path}"


def test_spawn_create_prompt_file_empty_path_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("", is_tty=True))

    with pytest.raises(ValueError) as exc_info:
        spawn_cli._spawn_create(lambda _payload: None, prompt_file="   ")

    assert str(exc_info.value) == "prompt file path is empty"


def test_spawn_create_prompt_file_dash_reads_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_create_prompt(monkeypatch)
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("stdin prompt", is_tty=False))

    spawn_cli._spawn_create(lambda _payload: None, prompt_file="-")

    assert captured["prompt"] == "stdin prompt"


def test_spawn_create_prompt_file_dash_works_through_full_cli_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_create_prompt(monkeypatch)
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    monkeypatch.setattr(cli_main, "_interactive_terminal_attached", lambda: False)
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("stdin prompt", is_tty=False))

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["spawn", "-a", "reviewer", "--prompt-file", "-", "--dry-run"])

    assert exc_info.value.code == 0
    assert captured["prompt"] == "stdin prompt"


def test_spawn_create_prompt_file_dash_with_tty_stdin_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("", is_tty=True))

    with pytest.raises(ValueError) as exc_info:
        spawn_cli._spawn_create(lambda _payload: None, prompt_file="-")

    assert str(exc_info.value) == "--prompt-file - requires stdin to be piped or redirected"


def test_spawn_create_autodetect_stdin_prompt_when_piped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_create_prompt(monkeypatch)
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("piped prompt", is_tty=False))

    spawn_cli._spawn_create(lambda _payload: None)

    assert captured["prompt"] == "piped prompt"


def test_spawn_create_autodetect_stdin_invalid_utf8_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(spawn_cli.sys, "stdin", _InvalidUtf8Stdin())

    with pytest.raises(ValueError) as exc_info:
        spawn_cli._spawn_create(lambda _payload: None)

    assert str(exc_info.value) == "prompt stdin is not valid UTF-8"


def test_spawn_create_no_prompt_and_tty_stdin_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("", is_tty=True))

    with pytest.raises(ValueError) as exc_info:
        spawn_cli._spawn_create(lambda _payload: None)

    assert str(exc_info.value) == "prompt required: pass -p, --prompt-file, or pipe stdin"


def test_spawn_create_prompt_and_prompt_file_conflict(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("from file", encoding="utf-8")
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("", is_tty=True))

    with pytest.raises(ValueError) as exc_info:
        spawn_cli._spawn_create(
            lambda _payload: None,
            prompt="literal",
            prompt_file=prompt_file.as_posix(),
        )

    assert str(exc_info.value) == "cannot specify both -p and --prompt-file"


def test_spawn_create_autodetect_empty_piped_stdin_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("", is_tty=False))

    with pytest.raises(ValueError) as exc_info:
        spawn_cli._spawn_create(lambda _payload: None)

    assert str(exc_info.value) == "prompt stdin is empty"


def test_spawn_create_prompt_file_dash_empty_stdin_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("", is_tty=False))

    with pytest.raises(ValueError) as exc_info:
        spawn_cli._spawn_create(lambda _payload: None, prompt_file="-")

    assert str(exc_info.value) == "prompt stdin is empty"


def test_spawn_create_file_only_without_prompt_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_create_prompt(monkeypatch)
    emitted: list[SpawnActionOutput] = []
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("", is_tty=False))

    spawn_cli._spawn_create(
        lambda payload: emitted.append(payload),
        references=("README.md",),
        dry_run=True,
    )

    assert captured["prompt"] == ""
    assert captured["files"] == ("README.md",)
    assert emitted[0].status == "dry-run"
    assert emitted[0].command == "spawn.create"


def test_spawn_create_file_only_with_literal_prompt_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_create_prompt(monkeypatch)
    emitted: list[SpawnActionOutput] = []
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("", is_tty=True))

    spawn_cli._spawn_create(
        lambda payload: emitted.append(payload),
        prompt="literal",
        references=("README.md",),
        dry_run=True,
    )

    assert captured["prompt"] == "literal"
    assert captured["files"] == ("README.md",)
    assert emitted[0].status == "dry-run"
    assert emitted[0].command == "spawn.create"


def test_spawn_create_literal_prompt_with_multiple_files_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_create_prompt(monkeypatch)
    emitted: list[SpawnActionOutput] = []
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("", is_tty=True))

    spawn_cli._spawn_create(
        lambda payload: emitted.append(payload),
        prompt="review the refactor",
        references=("src/a.py", "src/b.py", "src/c.py"),
        dry_run=True,
    )

    assert captured["prompt"] == "review the refactor"
    assert captured["files"] == ("src/a.py", "src/b.py", "src/c.py")
    assert emitted[0].status == "dry-run"
    assert emitted[0].command == "spawn.create"


def test_spawn_create_prompt_file_with_multiple_files_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_create_prompt(monkeypatch)
    emitted: list[SpawnActionOutput] = []
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("review from file\n", encoding="utf-8")
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("", is_tty=True))

    spawn_cli._spawn_create(
        lambda payload: emitted.append(payload),
        prompt_file=prompt_file.as_posix(),
        references=("src/a.py", "src/b.py", "src/c.py"),
        dry_run=True,
    )

    assert captured["prompt"] == "review from file\n"
    assert captured["files"] == ("src/a.py", "src/b.py", "src/c.py")
    assert emitted[0].status == "dry-run"
    assert emitted[0].command == "spawn.create"


def test_spawn_create_piped_stdin_prompt_with_multiple_files_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_create_prompt(monkeypatch)
    emitted: list[SpawnActionOutput] = []
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("prompt body\n", is_tty=False))

    spawn_cli._spawn_create(
        lambda payload: emitted.append(payload),
        references=("src/a.py", "src/b.py"),
        dry_run=True,
    )

    assert captured["prompt"] == "prompt body\n"
    assert captured["files"] == ("src/a.py", "src/b.py")
    assert emitted[0].status == "dry-run"
    assert emitted[0].command == "spawn.create"


def test_spawn_continue_without_new_prompt_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_continue_prompt(monkeypatch)
    emitted: list[SpawnActionOutput] = []
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("", is_tty=True))

    spawn_cli._spawn_create(
        lambda payload: emitted.append(payload),
        continue_from="p1",
        dry_run=True,
    )

    assert captured["spawn_id"] == "p1"
    assert captured["prompt"] == ""
    assert emitted[0].status == "dry-run"
    assert emitted[0].command == "spawn.continue"


def test_spawn_continue_with_explicit_prompt_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_continue_prompt(monkeypatch)
    emitted: list[SpawnActionOutput] = []
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("", is_tty=True))

    spawn_cli._spawn_create(
        lambda payload: emitted.append(payload),
        continue_from="p1",
        prompt="new prompt",
        dry_run=True,
    )

    assert captured["spawn_id"] == "p1"
    assert captured["prompt"] == "new prompt"
    assert emitted[0].status == "dry-run"
    assert emitted[0].command == "spawn.continue"


def test_spawn_create_reads_passthrough_from_global_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, tuple[str, ...]] = {}

    def _fake_spawn_create_sync(
        payload: SpawnCreateInput,
        *,
        sink=None,
    ) -> SpawnActionOutput:
        _ = sink
        captured["passthrough"] = payload.passthrough_args
        return SpawnActionOutput(command="spawn.create", status="dry-run")

    monkeypatch.setattr(spawn_cli, "spawn_create_sync", _fake_spawn_create_sync)
    monkeypatch.setattr(spawn_cli, "current_output_sink", lambda: None)
    monkeypatch.setattr(
        spawn_cli,
        "get_global_options",
        lambda: SimpleNamespace(harness=None, passthrough_args=("--add-dir", "/foo")),
    )
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("", is_tty=True))

    spawn_cli._spawn_create(lambda _payload: None, prompt="literal prompt")

    assert captured["passthrough"] == ("--add-dir", "/foo")


def test_spawn_continue_reads_passthrough_from_global_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, tuple[str, ...]] = {}

    def _fake_spawn_continue_sync(
        payload: SpawnContinueInput,
        *,
        sink=None,
    ) -> SpawnActionOutput:
        _ = sink
        captured["passthrough"] = payload.passthrough_args
        return SpawnActionOutput(command="spawn.continue", status="dry-run")

    monkeypatch.setattr(spawn_cli, "spawn_continue_sync", _fake_spawn_continue_sync)
    monkeypatch.setattr(spawn_cli, "current_output_sink", lambda: None)
    monkeypatch.setattr(
        spawn_cli,
        "get_global_options",
        lambda: SimpleNamespace(harness=None, passthrough_args=("--add-dir", "/foo")),
    )
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("", is_tty=True))

    spawn_cli._spawn_create(
        lambda _payload: None,
        continue_from="p1",
        prompt="new prompt",
        dry_run=True,
    )

    assert captured["passthrough"] == ("--add-dir", "/foo")


def test_spawn_create_exit_code_treats_finalizing_as_success() -> None:
    result = SpawnActionOutput(command="spawn.create", status="finalizing")
    assert spawn_cli._spawn_create_exit_code(result) == 0


def test_spawn_list_accepts_status_finalizing(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_list_payload(monkeypatch)

    spawn_cli._spawn_list(lambda _payload: None, status="finalizing")

    assert captured["payload"].status == "finalizing"
    assert captured["payload"].statuses is None


def test_spawn_list_active_view_includes_finalizing(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_list_payload(monkeypatch)

    spawn_cli._spawn_list(lambda _payload: None, view="active")

    assert captured["payload"].statuses is not None
    assert set(captured["payload"].statuses) == spawn_cli.ACTIVE_SPAWN_STATUSES
    assert "finalizing" in captured["payload"].statuses


def test_spawn_cancel_passes_resolved_spawn_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(spawn_cli, "resolve_runtime_root_and_config", lambda _: (Path("."), None))
    monkeypatch.setattr(spawn_cli, "resolve_spawn_reference", lambda _repo_root, _ref: "p1")
    monkeypatch.setattr(spawn_cli, "current_output_sink", lambda: None)

    captured: dict[str, SpawnCancelInput] = {}

    def _fake_cancel(payload: SpawnCancelInput, *, sink=None) -> SpawnActionOutput:
        _ = sink
        captured["payload"] = payload
        return SpawnActionOutput(
            command="spawn.cancel",
            status="cancelled",
            spawn_id=payload.spawn_id,
        )

    monkeypatch.setattr(spawn_cli, "spawn_cancel_sync", _fake_cancel)

    spawn_cli._spawn_cancel(lambda _payload: None, "p1")

    assert captured["payload"].spawn_id == "p1"


def test_spawn_inject_passes_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def _fake_inject(
        spawn_id: str,
        message: str | None,
        *,
        interrupt: bool = False,
    ) -> None:
        captured["spawn_id"] = spawn_id
        captured["message"] = message
        captured["interrupt"] = interrupt

    monkeypatch.setattr(spawn_cli, "inject_message", _fake_inject)

    spawn_cli._spawn_inject("p1", "", interrupt=True)

    assert captured == {
        "spawn_id": "p1",
        "message": None,
        "interrupt": True,
    }
