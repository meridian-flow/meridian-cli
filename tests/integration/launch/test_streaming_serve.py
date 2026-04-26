from __future__ import annotations

import json
from pathlib import Path
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
    monkeypatch.setattr(
        streaming_serve_module,
        "resolve_runtime_root_and_config",
        lambda project_root=None, *, sink=None: (project_root or tmp_path, None),
    )

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
    monkeypatch.setattr(
        streaming_serve_module,
        "resolve_runtime_root_and_config",
        lambda project_root=None, *, sink=None: (project_root or tmp_path, None),
    )

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
