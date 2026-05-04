from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from meridian.cli import streaming_serve as streaming_serve_module
from meridian.lib.ops.runtime import resolve_runtime_root
from meridian.lib.state.spawn_store import get_spawn
from meridian.lib.streaming.spawn_manager import DrainOutcome


def _read_spawn_events(runtime_root: Path) -> list[dict[str, object]]:
    events_path = runtime_root / "spawns.jsonl"
    return [
        cast("dict[str, object]", json.loads(line))
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _fake_launch_context(
    *,
    spawn_id: str,
    child_cwd: Path,
    prompt: str = "projected prompt",
    system: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        resolved_request=SimpleNamespace(
            model="gpt-5.4",
            harness="codex",
            agent="coder",
            prompt=prompt,
            skills=(),
            skill_paths=(),
            session=SimpleNamespace(requested_harness_session_id=None),
            agent_metadata={
                "appended_system_prompt": system,
                "session_agent_path": str(child_cwd / "agent.md"),
            },
        ),
        child_cwd=child_cwd,
        work_id=None,
        env_overrides={
            "MERIDIAN_SPAWN_ID": spawn_id,
            "MERIDIAN_PARENT_SPAWN_ID": "p-parent",
            "EXTRA_ENV": "present",
        },
        spec=SimpleNamespace(name="fake-spec"),
    )


@pytest.mark.asyncio
async def test_streaming_serve_shutdown_finalizes_once_as_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = resolve_runtime_root(tmp_path)
    helper_calls: list[tuple[str, str]] = []

    async def _run_streaming_spawn(**kwargs: object) -> DrainOutcome:
        helper_calls.append((str(kwargs["spawn_id"]), str(kwargs["runtime_root"])))
        return DrainOutcome(status="cancelled", exit_code=1)

    monkeypatch.setattr(streaming_serve_module, "run_streaming_spawn", _run_streaming_spawn)
    monkeypatch.setattr(streaming_serve_module, "resolve_project_root", lambda: tmp_path)

    await streaming_serve_module.streaming_serve("codex", "hello")

    assert helper_calls == [("p1", str(runtime_root))]
    events = _read_spawn_events(runtime_root)
    assert [event["event"] for event in events] == ["start", "update", "finalize"]
    assert events[1]["status"] == "finalizing"
    assert events[-1]["status"] == "cancelled"

    row = get_spawn(runtime_root, "p1")
    assert row is not None
    assert row.status == "cancelled"
    assert row.exit_code == 1


@pytest.mark.asyncio
async def test_streaming_serve_start_failure_finalizes_failed_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = resolve_runtime_root(tmp_path)

    async def _run_streaming_spawn(**kwargs: object) -> DrainOutcome:
        _ = kwargs
        raise RuntimeError("boom")

    monkeypatch.setattr(streaming_serve_module, "run_streaming_spawn", _run_streaming_spawn)
    monkeypatch.setattr(streaming_serve_module, "resolve_project_root", lambda: tmp_path)

    with pytest.raises(RuntimeError, match="boom"):
        await streaming_serve_module.streaming_serve("codex", "hello")

    events = _read_spawn_events(runtime_root)
    assert [event["event"] for event in events] == ["start", "update", "finalize"]
    assert events[1]["status"] == "finalizing"
    assert events[-1]["status"] == "failed"
    assert events[-1]["error"] == "boom"

    row = get_spawn(runtime_root, "p1")
    assert row is not None
    assert row.status == "failed"
    assert row.error == "boom"


@pytest.mark.asyncio
async def test_streaming_serve_debug_keeps_projected_connection_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = resolve_runtime_root(tmp_path)
    child_cwd = tmp_path / "child-cwd"
    child_cwd.mkdir()
    runner_calls: list[dict[str, object]] = []

    def _build_launch_context(**kwargs: object) -> SimpleNamespace:
        return _fake_launch_context(
            spawn_id=str(kwargs["spawn_id"]),
            child_cwd=child_cwd,
            system="SYSTEM: projected",
        )

    async def _run_streaming_spawn(**kwargs: object) -> DrainOutcome:
        runner_calls.append(kwargs)
        return DrainOutcome(status="succeeded", exit_code=0)

    monkeypatch.setattr(
        "meridian.lib.core.spawn_service.build_launch_context",
        _build_launch_context,
    )
    monkeypatch.setattr(streaming_serve_module, "run_streaming_spawn", _run_streaming_spawn)
    monkeypatch.setattr(streaming_serve_module, "resolve_project_root", lambda: tmp_path)

    await streaming_serve_module.streaming_serve("codex", "hello", debug=True)

    assert len(runner_calls) == 1
    runner_call = runner_calls[0]
    config = runner_call["config"]
    assert str(runner_call["spawn_id"]) == "p1"
    assert runner_call["runtime_root"] == runtime_root
    assert runner_call["project_root"] == tmp_path
    assert runner_call["spec"].name == "fake-spec"
    assert config.spawn_id == "p1"
    assert config.prompt == "projected prompt"
    assert config.project_root == child_cwd
    assert config.system == "SYSTEM: projected"
    assert config.env_overrides["MERIDIAN_SPAWN_ID"] == "p1"
    assert config.env_overrides["MERIDIAN_PARENT_SPAWN_ID"] == "p-parent"
    assert config.env_overrides["EXTRA_ENV"] == "present"
    assert config.debug_tracer is not None

    events = _read_spawn_events(runtime_root)
    assert [event["event"] for event in events] == ["start", "update", "finalize"]
    assert events[-1]["status"] == "succeeded"

    row = get_spawn(runtime_root, "p1")
    assert row is not None
    assert row.execution_cwd == str(child_cwd)
    assert row.status == "succeeded"
