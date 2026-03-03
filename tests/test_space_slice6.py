"""Slice 6 space/doctor integration checks."""

from __future__ import annotations

import importlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

import meridian.lib.ops.spawn as run_ops
from meridian.lib.ops.diag import DoctorInput, doctor_sync
from meridian.lib.ops.spawn import (
    SpawnActionOutput,
    SpawnContinueInput,
    SpawnCreateInput,
    spawn_continue_sync,
    spawn_create_sync,
)
from meridian.lib.ops.space import (
    SpaceResumeInput,
    SpaceStartInput,
    space_resume_sync,
    space_start_sync,
)
from meridian.lib.space import crud as space_crud
from meridian.lib.space.space_file import create_space, get_space
from meridian.lib.space.session_store import start_session, stop_session
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_space_dir


def _harness_command(package_root: Path, capture_path: Path) -> str:
    parts = [
        sys.executable,
        str(package_root / "tests" / "mock_harness.py"),
        "--duration",
        "0",
        "--capture-json",
        str(capture_path),
    ]
    return " ".join(shlex.quote(part) for part in parts)


def _capture_payload(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_space_start_creates_lock_sets_env_and_forwards_passthrough(
    package_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = tmp_path / "start-capture.json"
    monkeypatch.setenv("MERIDIAN_HARNESS_COMMAND", _harness_command(package_root, capture))

    result = space_start_sync(
        SpaceStartInput(
            name="slice6",
            autocompact=72,
            harness_args=("--demo-flag", "enabled"),
            repo_root=tmp_path.as_posix(),
        )
    )

    assert result.space_id == "s1"
    assert result.state == "active"
    assert result.exit_code == 0
    assert result.command == ()
    assert result.lock_path is not None
    assert not Path(result.lock_path).exists()

    payload = _capture_payload(capture)
    env = payload["env"]
    assert isinstance(env, dict)
    assert env["MERIDIAN_SPACE_ID"] == result.space_id
    assert isinstance(env["MERIDIAN_SPAWN_ID"], str)
    assert env["MERIDIAN_SPAWN_ID"].startswith("p")
    assert env["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] == "72"

    argv = payload["argv"]
    assert isinstance(argv, list)
    assert "--autocompact" not in argv
    assert "--demo-flag" in argv
    assert "enabled" in argv

    assert result.summary_path is not None
    assert Path(result.summary_path).exists()
    space_dir = resolve_space_dir(tmp_path, result.space_id)
    spawns = spawn_store.list_spawns(space_dir)
    assert len(spawns) == 1
    assert spawns[0].id == env["MERIDIAN_SPAWN_ID"]
    assert spawns[0].kind == "primary"
    assert spawns[0].status == "succeeded"
    assert spawns[0].exit_code == 0


def test_space_resume_fresh_omits_continuation_guidance(
    package_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space = create_space(tmp_path, name="fresh")

    capture = tmp_path / "fresh-capture.json"
    monkeypatch.setenv("MERIDIAN_HARNESS_COMMAND", _harness_command(package_root, capture))

    result = space_resume_sync(
        SpaceResumeInput(
            space=space.id,
            fresh=True,
            repo_root=tmp_path.as_posix(),
        )
    )
    assert result.state == "active"
    assert result.command == ()

    payload = _capture_payload(capture)
    env = payload["env"]
    assert isinstance(env, dict)
    prompt = env["MERIDIAN_SPACE_PROMPT"]
    assert isinstance(prompt, str)
    assert "Continuation Guidance" not in prompt
    assert "fresh primary conversation" in prompt


def test_space_resume_allows_closed_space(tmp_path: Path) -> None:
    """Resume should not reject a closed space — the state machine allows closed -> active."""
    created = create_space(tmp_path, name="resume-closed")
    space_crud.transition_space(tmp_path, created.id, "closed")

    # Verify space is closed
    space = space_crud.get_space_or_raise(tmp_path, created.id)
    assert space.state == "closed"

    # State machine should allow closed -> active (used by resume)
    assert space_crud.can_transition("closed", "active")

    # Transition directly to verify
    result = space_crud.transition_space(tmp_path, created.id, "active")
    assert result.state == "active"


def test_space_state_machine_allows_closed_to_active_for_resume(tmp_path: Path) -> None:
    """Closed spaces can transition back to active (for resume)."""
    created = create_space(tmp_path, name="terminal")

    space_crud.transition_space(tmp_path, created.id, "closed")
    result = space_crud.transition_space(tmp_path, created.id, "active")
    assert result.state == "active"


@pytest.mark.parametrize(
    "status",
    [
        pytest.param("running", id="running"),
        pytest.param("failed", id="failed"),
        pytest.param("succeeded", id="succeeded"),
    ],
)
def test_run_continue_works_for_running_failed_and_succeeded(
    status: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space = create_space(tmp_path, name="continue")
    space_dir = resolve_space_dir(tmp_path, space.id)
    monkeypatch.setenv("MERIDIAN_SPACE_ID", space.id)

    spawn_id = spawn_store.start_spawn(
        space_dir,
        chat_id="c1",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        prompt="original prompt",
        harness_session_id="sess-source",
    )
    if status != "running":
        spawn_store.finalize_spawn(
            space_dir,
            spawn_id,
            status,
            0 if status == "succeeded" else 1,
        )

    captured: dict[str, object] = {}

    def fake_run_create_sync(payload: SpawnCreateInput) -> SpawnActionOutput:
        captured["payload"] = payload
        return SpawnActionOutput(
            command="spawn.create",
            status="succeeded",
            spawn_id="r-next",
            message="ok",
        )

    monkeypatch.setattr(run_ops, "spawn_create_sync", fake_run_create_sync)

    result = spawn_continue_sync(
        SpawnContinueInput(
            spawn_id=str(spawn_id),
            prompt="",
            fork=True,
            repo_root=tmp_path.as_posix(),
        )
    )

    assert result.command == "spawn.continue"
    forwarded = captured["payload"]
    assert isinstance(forwarded, SpawnCreateInput)
    assert forwarded.prompt == "original prompt"
    assert forwarded.model == "gpt-5.3-codex"
    assert forwarded.continue_harness == "codex"
    assert forwarded.continue_harness_session_id == "sess-source"
    assert forwarded.continue_fork is True


def test_run_create_dry_run_fallbacks_for_harness_mismatch_and_missing_fork_support(
    tmp_path: Path,
) -> None:
    mismatch = spawn_create_sync(
        SpawnCreateInput(
            prompt="continue mismatch",
            model="gpt-5.3-codex",
            dry_run=True,
            repo_root=tmp_path.as_posix(),
            continue_harness_session_id="sess-a",
            continue_harness="claude",
            continue_fork=True,
        )
    )
    assert mismatch.status == "dry-run"
    assert "resume" not in mismatch.cli_command
    assert mismatch.warning is not None
    assert "target harness differs" in mismatch.warning

    no_fork_support = spawn_create_sync(
        SpawnCreateInput(
            prompt="continue codex",
            model="gpt-5.3-codex",
            dry_run=True,
            repo_root=tmp_path.as_posix(),
            continue_harness_session_id="sess-b",
            continue_harness="codex",
            continue_fork=True,
        )
    )
    assert no_fork_support.status == "dry-run"
    assert no_fork_support.cli_command[:4] == ("codex", "exec", "resume", "sess-b")
    assert no_fork_support.warning is not None
    assert "does not support session fork" in no_fork_support.warning


def test_doctor_rebuilds_stale_state_and_orphan_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)
    created = create_space(tmp_path, name="stuck-active")
    space_dir = resolve_space_dir(tmp_path, created.id)

    _ = spawn_store.start_spawn(
        space_dir,
        chat_id="c1",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        prompt="repair",
    )

    sessions_dir = space_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    stale_lock = sessions_dir / "c9.lock"
    stale_lock.write_text("", encoding="utf-8")

    repaired = doctor_sync(DoctorInput(repo_root=tmp_path.as_posix()))
    assert isinstance(repaired.ok, bool)
    assert "orphan_runs" in repaired.repaired
    assert "stale_session_locks" in repaired.repaired
    assert "stale_space_status" in repaired.repaired
    assert not stale_lock.exists()

    refreshed_space = get_space(tmp_path, created.id)
    assert refreshed_space is not None
    assert refreshed_space.status == "closed"


def test_doctor_marks_running_spawn_orphan_when_background_pid_is_dead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)
    created = create_space(tmp_path, name="dead-pid")
    space_dir = resolve_space_dir(tmp_path, created.id)
    spawn_id = spawn_store.start_spawn(
        space_dir,
        chat_id="c1",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        prompt="repair",
    )

    pid_path = space_dir / "spawns" / str(spawn_id) / "background.pid"
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("999999\n", encoding="utf-8")

    repaired = doctor_sync(DoctorInput(repo_root=tmp_path.as_posix()))
    assert "orphan_runs" in repaired.repaired

    row = spawn_store.get_spawn(space_dir, spawn_id)
    assert row is not None
    assert row.status == "failed"
    assert row.error == "orphan_run"


def test_doctor_keeps_running_spawn_when_background_pid_is_alive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MERIDIAN_SPACE_ID", raising=False)
    created = create_space(tmp_path, name="live-pid")
    space_dir = resolve_space_dir(tmp_path, created.id)
    spawn_id = spawn_store.start_spawn(
        space_dir,
        chat_id="c1",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        prompt="repair",
    )

    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        pid_path = space_dir / "spawns" / str(spawn_id) / "background.pid"
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        pid_path.write_text(f"{process.pid}\n", encoding="utf-8")

        repaired = doctor_sync(DoctorInput(repo_root=tmp_path.as_posix()))
        assert "orphan_runs" not in repaired.repaired

        row = spawn_store.get_spawn(space_dir, spawn_id)
        assert row is not None
        assert row.status == "running"
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_root_command_launches_and_forwards_options(
    package_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main_module = importlib.import_module("meridian.cli.main")
    capture = tmp_path / "start-top-level-capture.json"
    monkeypatch.setenv("MERIDIAN_HARNESS_COMMAND", _harness_command(package_root, capture))
    monkeypatch.setattr(main_module, "resolve_repo_root", lambda: tmp_path)

    with pytest.raises(SystemExit) as exc:
        main_module.app(["--autocompact", "72", "--harness-arg", "enabled"])
    assert int(exc.value.code) == 0
    captured = capsys.readouterr()
    assert "mock_harness.py" not in captured.out

    payload = _capture_payload(capture)
    env = payload["env"]
    assert isinstance(env, dict)
    assert env["MERIDIAN_SPACE_ID"] == "s1"
    assert isinstance(env["MERIDIAN_SPAWN_ID"], str)
    assert env["MERIDIAN_SPAWN_ID"].startswith("p")
    assert env["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] == "72"

    argv = payload["argv"]
    assert isinstance(argv, list)
    assert "--autocompact" not in argv
    assert "enabled" in argv


def test_root_continue_dry_run_resolves_space_and_passes_resume_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main_module = importlib.import_module("meridian.cli.main")
    first = create_space(tmp_path, name="first")
    second = create_space(tmp_path, name="second")
    first_dir = resolve_space_dir(tmp_path, first.id)
    second_dir = resolve_space_dir(tmp_path, second.id)

    first_chat = start_session(
        first_dir,
        harness="claude",
        harness_session_id="sess-first",
        model="claude-opus-4-6",
    )
    second_chat = start_session(
        second_dir,
        harness="claude",
        harness_session_id="sess-second",
        model="claude-opus-4-6",
    )
    stop_session(first_dir, first_chat)
    stop_session(second_dir, second_chat)

    monkeypatch.setattr(main_module, "resolve_repo_root", lambda: tmp_path)

    with pytest.raises(SystemExit) as exc:
        main_module.app(["--continue", "sess-second", "--dry-run"])
    assert int(exc.value.code) == 0

    captured = capsys.readouterr()
    assert f"Space {second.id} active (Space resume dry-run)" in captured.out
    assert "--resume sess-second" in captured.out


def test_root_continue_requires_disambiguation_without_space(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main_module = importlib.import_module("meridian.cli.main")
    first = create_space(tmp_path, name="first")
    second = create_space(tmp_path, name="second")
    first_dir = resolve_space_dir(tmp_path, first.id)
    second_dir = resolve_space_dir(tmp_path, second.id)

    first_chat = start_session(
        first_dir,
        harness="claude",
        harness_session_id="sess-first",
        model="claude-opus-4-6",
    )
    second_chat = start_session(
        second_dir,
        harness="claude",
        harness_session_id="sess-second",
        model="claude-opus-4-6",
    )
    stop_session(first_dir, first_chat)
    stop_session(second_dir, second_chat)

    monkeypatch.setattr(main_module, "resolve_repo_root", lambda: tmp_path)

    with pytest.raises(SystemExit) as exc:
        main_module.main(["--continue", "c1", "--dry-run"])
    assert int(exc.value.code) == 1
    captured = capsys.readouterr()
    assert "ambiguous across spaces" in captured.err


def test_root_continue_space_mismatch_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main_module = importlib.import_module("meridian.cli.main")
    first = create_space(tmp_path, name="first")
    second = create_space(tmp_path, name="second")
    second_dir = resolve_space_dir(tmp_path, second.id)

    second_chat = start_session(
        second_dir,
        harness="claude",
        harness_session_id="sess-second",
        model="claude-opus-4-6",
    )
    stop_session(second_dir, second_chat)

    monkeypatch.setattr(main_module, "resolve_repo_root", lambda: tmp_path)

    with pytest.raises(SystemExit) as exc:
        main_module.main(["--continue", "sess-second", "--space", first.id, "--dry-run"])
    assert int(exc.value.code) == 1
    captured = capsys.readouterr()
    assert f"not found in space '{first.id}'" in captured.err


def test_root_harness_override_builds_codex_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main_module = importlib.import_module("meridian.cli.main")
    monkeypatch.delenv("MERIDIAN_HARNESS_COMMAND", raising=False)
    monkeypatch.setattr(main_module, "resolve_repo_root", lambda: tmp_path)

    with pytest.raises(SystemExit) as exc:
        main_module.app(
            [
                "--model",
                "gpt-5.3-codex",
                "--harness",
                "codex",
                "--dry-run",
            ]
        )
    assert int(exc.value.code) == 0
    captured = capsys.readouterr()
    assert "codex exec" in captured.out


def test_root_harness_override_rejects_incompatible_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main_module = importlib.import_module("meridian.cli.main")
    monkeypatch.setattr(main_module, "resolve_repo_root", lambda: tmp_path)

    with pytest.raises(SystemExit) as exc:
        main_module.main(
            [
                "--model",
                "claude-opus-4-6",
                "--harness",
                "codex",
                "--dry-run",
            ]
        )
    assert int(exc.value.code) == 1
    captured = capsys.readouterr()
    assert "incompatible with model" in captured.err


def test_root_continue_rejects_harness_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main_module = importlib.import_module("meridian.cli.main")
    monkeypatch.setattr(main_module, "resolve_repo_root", lambda: tmp_path)

    with pytest.raises(SystemExit) as exc:
        main_module.main(["--continue", "any-session", "--harness", "claude", "--dry-run"])
    assert int(exc.value.code) == 1
    captured = capsys.readouterr()
    assert "Cannot combine --continue with --harness." in captured.err
