"""CLI run.show flag plumbing tests."""

from __future__ import annotations

from meridian.cli import run as run_cli
from meridian.lib.ops.run import RunDetailOutput, RunShowInput


def _detail() -> RunDetailOutput:
    return RunDetailOutput(
        run_id="r1",
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
    captured: dict[str, RunShowInput] = {}
    emitted: list[RunDetailOutput] = []

    def fake_run_show_sync(payload: RunShowInput) -> RunDetailOutput:
        captured["payload"] = payload
        return _detail()

    monkeypatch.setattr(run_cli, "run_show_sync", fake_run_show_sync)

    run_cli._run_show(
        emitted.append,
        run_id="r1",
        report=True,
    )

    assert captured["payload"].report is True
    assert emitted[0].run_id == "r1"
