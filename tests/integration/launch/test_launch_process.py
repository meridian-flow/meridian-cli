from __future__ import annotations

import json
import os

# pyright: reportPrivateUsage=false
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pytest

from meridian.lib.config.settings import load_config
from meridian.lib.core.types import HarnessId
from meridian.lib.harness.adapter import SpawnParams
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.launch import process
from meridian.lib.launch.context import build_launch_context
from meridian.lib.launch.process.subprocess_launcher import SubprocessProcessLauncher
from meridian.lib.launch.request import (
    LaunchArgvIntent,
    LaunchCompositionSurface,
    LaunchRuntime,
    SessionRequest,
    SpawnRequest,
)
from meridian.lib.launch.types import SessionMode


def test_subprocess_launcher_captures_output_log(tmp_path: Path) -> None:
    output_log_path = tmp_path / "output.jsonl"
    launched = SubprocessProcessLauncher().launch(
        command=(
            sys.executable,
            "-c",
            (
                "import sys;"
                "sys.stdout.write('line-1\\n');"
                "sys.stdout.flush();"
                "sys.stderr.write('line-2\\n');"
                "sys.stderr.flush()"
            ),
        ),
        cwd=tmp_path,
        env=dict(os.environ),
        output_log_path=output_log_path,
    )

    assert launched.exit_code == 0
    assert output_log_path.read_text(encoding="utf-8").splitlines() == ["line-1", "line-2"]


def test_run_harness_process_fork_uses_new_chat_and_materialized_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("MERIDIAN_CHAT_ID", raising=False)
    repo_root = tmp_path
    (repo_root / "mars.toml").write_text(
        "[settings]\n"
        'targets = [".agents"]\n',
        encoding="utf-8",
    )
    harness_registry = get_default_harness_registry()
    config = load_config(repo_root)
    codex_adapter = harness_registry.get_subprocess_harness(HarnessId.CODEX)
    launch_context = build_launch_context(
        spawn_id="dry-run-primary",
        request=SpawnRequest(
            prompt="fork prompt",
            prompt_is_composed=False,
            model="gpt-5.4",
            harness=HarnessId.CODEX.value,
            session=SessionRequest(
                requested_harness_session_id="source-session",
                continue_chat_id="c7",
                forked_from_chat_id="c7",
                continue_fork=True,
                primary_session_mode=SessionMode.FORK.value,
            ),
        ),
        runtime=LaunchRuntime(
            argv_intent=LaunchArgvIntent.REQUIRED,
            composition_surface=LaunchCompositionSurface.PRIMARY,
            config_snapshot=config.model_dump(mode="json", exclude_none=True),
            state_root=(tmp_path / ".meridian").as_posix(),
            project_paths_repo_root=repo_root.as_posix(),
            project_paths_execution_cwd=repo_root.as_posix(),
        ),
        harness_registry=harness_registry,
        dry_run=True,
    )

    captured: dict[str, str | None] = {}

    def fake_build_command(run: SpawnParams, perms: object) -> list[str]:
        _ = perms
        captured["build_continue_session"] = run.continue_harness_session_id
        return ["codex", "resume", run.continue_harness_session_id or ""]

    def fake_fork_session(source_session_id: str) -> str:
        captured["fork_source_session"] = source_session_id
        return "forked-session"

    def fake_run_primary_process_with_capture(**kwargs: object) -> tuple[int, int]:
        captured["command_session"] = tuple(kwargs["command"])[2]
        captured["env_chat_id"] = dict(kwargs["env"]).get("MERIDIAN_CHAT_ID")
        started = kwargs.get("on_child_started")
        assert callable(started)
        started(111)
        return (0, 111)

    def fake_start_session(
        state_root: Path,
        harness: str,
        harness_session_id: str | None,
        model: str,
        chat_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        _ = (state_root, harness, model)
        captured["chat_id_arg"] = chat_id
        captured["start_harness_session_id"] = harness_session_id
        captured["forked_from_chat_id"] = kwargs.get("forked_from_chat_id")
        return "c999"

    monkeypatch.setattr(codex_adapter, "build_command", fake_build_command)
    monkeypatch.setattr(codex_adapter, "fork_session", fake_fork_session)
    monkeypatch.setattr(codex_adapter, "observe_session_id", lambda **kwargs: "forked-session")
    monkeypatch.setattr(
        process,
        "_run_primary_process_with_capture",
        fake_run_primary_process_with_capture,
    )
    monkeypatch.setattr(process, "stop_session", lambda *args, **kwargs: None)
    monkeypatch.setattr(process, "update_session_harness_id", lambda *args, **kwargs: None)
    monkeypatch.setattr(process, "start_session", fake_start_session)

    outcome = process.run_harness_process(launch_context, harness_registry)

    assert captured["fork_source_session"] == "source-session"
    assert captured["build_continue_session"] == "forked-session"
    assert captured["command_session"] == "forked-session"
    assert captured["chat_id_arg"] is None
    # I-10: session is created with the SOURCE session ID; fork happens after the row exists.
    assert captured["start_harness_session_id"] == "source-session"
    assert captured["forked_from_chat_id"] == "c7"
    assert captured["env_chat_id"] == "c999"
    assert outcome.chat_id == "c999"
    events = [
        json.loads(line)
        for line in (launch_context.state_root / "spawns.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    finalize_events = [event for event in events if event.get("event") == "finalize"]
    assert len(finalize_events) == 1
    assert finalize_events[0]["origin"] == "launcher"
