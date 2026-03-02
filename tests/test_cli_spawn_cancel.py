"""CLI spawn.cancel flag plumbing."""

from __future__ import annotations

from meridian.cli import spawn as run_cli
from meridian.lib.ops.spawn import SpawnActionOutput, SpawnCancelInput


def test_spawn_cancel_passes_spawn_id_and_space(monkeypatch) -> None:
    captured: dict[str, SpawnCancelInput] = {}
    emitted: list[SpawnActionOutput] = []

    def fake_spawn_cancel_sync(payload: SpawnCancelInput) -> SpawnActionOutput:
        captured["payload"] = payload
        return SpawnActionOutput(command="spawn.cancel", status="cancelled", spawn_id="p1")

    monkeypatch.setattr(run_cli, "spawn_cancel_sync", fake_spawn_cancel_sync)

    run_cli._spawn_cancel(emitted.append, spawn_id="p1", space="s1")

    assert captured["payload"].spawn_id == "p1"
    assert captured["payload"].space == "s1"
    assert emitted[0].status == "cancelled"


def test_spawn_cancel_exits_for_failed_result(monkeypatch) -> None:
    def fake_spawn_cancel_sync(payload: SpawnCancelInput) -> SpawnActionOutput:
        _ = payload
        return SpawnActionOutput(command="spawn.cancel", status="failed", spawn_id="p1")

    monkeypatch.setattr(run_cli, "spawn_cancel_sync", fake_spawn_cancel_sync)

    import pytest

    with pytest.raises(SystemExit) as exc_info:
        run_cli._spawn_cancel(lambda _: None, spawn_id="p1")

    assert int(exc_info.value.code) == 1
