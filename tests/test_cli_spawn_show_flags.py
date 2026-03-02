"""CLI spawn.show flag plumbing tests."""

from __future__ import annotations

from meridian.cli import spawn as run_cli
from meridian.lib.ops.spawn import SpawnDetailOutput, SpawnShowInput


def _detail() -> SpawnDetailOutput:
    return SpawnDetailOutput(
        spawn_id="r1",
        status="succeeded",
        model="gpt-5.3-codex",
        harness="codex",
        space_id="s1",
        started_at="2026-02-27T00:00:00Z",
        finished_at="2026-02-27T00:00:01Z",
        duration_secs=1.0,
        exit_code=0,
        failure_reason=None,
        input_tokens=None,
        output_tokens=None,
        cost_usd=None,
        report_path=None,
        report_summary=None,
        report=None,
        files_touched=None,
    )


def test_run_show_passes_report_flag(monkeypatch) -> None:
    captured: dict[str, SpawnShowInput] = {}
    emitted: list[SpawnDetailOutput] = []

    def fake_run_show_sync(payload: SpawnShowInput) -> SpawnDetailOutput:
        captured["payload"] = payload
        return _detail()

    monkeypatch.setattr(run_cli, "spawn_show_sync", fake_run_show_sync)

    run_cli._spawn_show(
        emitted.append,
        spawn_id="r1",
        report=True,
    )

    assert captured["payload"].report is True
    assert emitted[0].spawn_id == "r1"
