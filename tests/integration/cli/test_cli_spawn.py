import importlib
import io

import pytest

from meridian.lib.ops.spawn.models import (
    SpawnActionOutput,
    SpawnContinueInput,
    SpawnCreateInput,
    SpawnListInput,
    SpawnListOutput,
)

cli_main = importlib.import_module("meridian.cli.main")
spawn_cli = importlib.import_module("meridian.cli.spawn")


class _FakeStdin(io.StringIO):
    def __init__(self, text: str, *, is_tty: bool) -> None:
        super().__init__(text)
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


def test_spawn_prompt_file_dash_reads_stdin_through_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    captured: dict[str, object] = {}

    def _fake_spawn_create_sync(
        payload: SpawnCreateInput,
        *,
        sink: object | None = None,
    ) -> SpawnActionOutput:
        _ = sink
        captured["prompt"] = payload.prompt
        return SpawnActionOutput(command="spawn.create", status="dry-run")

    monkeypatch.setattr(spawn_cli, "spawn_create_sync", _fake_spawn_create_sync)
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("stdin prompt", is_tty=False))

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["spawn", "-a", "reviewer", "--prompt-file", "-", "--dry-run"])

    assert exc_info.value.code == 0
    assert captured["prompt"] == "stdin prompt"


def test_spawn_rejects_prompt_and_prompt_file_together(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("", is_tty=True))

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["--human", "spawn", "-p", "literal", "--prompt-file", "-", "--dry-run"])

    assert exc_info.value.code == 1
    assert "cannot specify both -p and --prompt-file" in capsys.readouterr().err


def test_spawn_file_only_without_prompt_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    captured: dict[str, object] = {}

    def _fake_spawn_create_sync(
        payload: SpawnCreateInput,
        *,
        sink: object | None = None,
    ) -> SpawnActionOutput:
        _ = sink
        captured["prompt"] = payload.prompt
        captured["files"] = payload.files
        return SpawnActionOutput(command="spawn.create", status="dry-run")

    monkeypatch.setattr(spawn_cli, "spawn_create_sync", _fake_spawn_create_sync)
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("", is_tty=False))

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["spawn", "--file", "README.md", "--dry-run"])

    assert exc_info.value.code == 0
    assert captured["prompt"] == ""
    assert captured["files"] == ("README.md",)


def test_spawn_continue_without_prompt_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    captured: dict[str, object] = {}

    def _fake_spawn_continue_sync(
        payload: SpawnContinueInput,
        *,
        sink: object | None = None,
    ) -> SpawnActionOutput:
        _ = sink
        captured["spawn_id"] = payload.spawn_id
        captured["prompt"] = payload.prompt
        return SpawnActionOutput(command="spawn.continue", status="dry-run")

    monkeypatch.setattr(spawn_cli, "spawn_continue_sync", _fake_spawn_continue_sync)
    monkeypatch.setattr(spawn_cli.sys, "stdin", _FakeStdin("", is_tty=True))

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["spawn", "--continue", "p1", "--dry-run"])

    assert exc_info.value.code == 0
    assert captured == {"spawn_id": "p1", "prompt": ""}


def test_spawn_list_active_view_includes_finalizing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    captured: dict[str, SpawnListInput] = {}

    def _fake_spawn_list_sync(
        payload: SpawnListInput,
        *,
        sink: object | None = None,
    ) -> SpawnListOutput:
        _ = sink
        captured["payload"] = payload
        return SpawnListOutput(spawns=())

    monkeypatch.setattr(spawn_cli, "spawn_list_sync", _fake_spawn_list_sync)

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["spawn", "list", "--view", "active"])

    assert exc_info.value.code == 0
    statuses = captured["payload"].statuses
    assert statuses is not None
    assert "finalizing" in statuses


def test_spawn_list_status_accepts_finalizing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    captured: dict[str, SpawnListInput] = {}

    def _fake_spawn_list_sync(
        payload: SpawnListInput,
        *,
        sink: object | None = None,
    ) -> SpawnListOutput:
        _ = sink
        captured["payload"] = payload
        return SpawnListOutput(spawns=())

    monkeypatch.setattr(spawn_cli, "spawn_list_sync", _fake_spawn_list_sync)

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["spawn", "list", "--status", "finalizing"])

    assert exc_info.value.code == 0
    assert captured["payload"].status == "finalizing"
    assert captured["payload"].statuses is None


def test_spawn_children_resolves_parent_reference_before_filtering(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_root = repo_root / ".meridian"
    seen: dict[str, object] = {}

    monkeypatch.setattr(spawn_cli, "resolve_project_root", lambda: repo_root)
    monkeypatch.setattr(spawn_cli, "resolve_state_root_for_read", lambda _root: state_root)
    monkeypatch.setattr(
        spawn_cli,
        "resolve_spawn_reference",
        lambda _repo_root, ref: "p77" if ref == "c213" else ref,
    )
    monkeypatch.setattr(
        spawn_cli.spawn_store,
        "list_spawns",
        lambda _state_root, filters=None: _capture_filters_and_return_empty(seen, filters),
    )
    monkeypatch.setattr(
        "meridian.lib.state.reaper.reconcile_spawns",
        lambda _state_root, spawns: spawns,
    )

    emitted: list[SpawnListOutput] = []
    spawn_cli._spawn_children(emitted.append, "c213")

    assert seen["filters"] == {"parent_id": "p77"}
    assert len(emitted) == 1
    assert emitted[0].spawns == ()


def _capture_filters_and_return_empty(
    seen: dict[str, object],
    filters: object,
) -> list[object]:
    seen["filters"] = filters
    return []
