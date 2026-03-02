"""CLI plumbing tests for report command handlers."""

from __future__ import annotations

import io

from meridian.cli import report_cmd
from meridian.lib.ops.report import (
    ReportCreateInput,
    ReportCreateOutput,
    ReportSearchInput,
    ReportSearchOutput,
    ReportShowInput,
    ReportShowOutput,
)


def test_report_create_passes_spawn_and_stdin(monkeypatch) -> None:
    captured: dict[str, ReportCreateInput] = {}
    emitted: list[ReportCreateOutput] = []

    def fake_report_create_sync(payload: ReportCreateInput) -> ReportCreateOutput:
        captured["payload"] = payload
        return ReportCreateOutput(
            command="report.create",
            status="succeeded",
            spawn_id="p1",
            report_path="/tmp/report.md",
            bytes_written=12,
        )

    monkeypatch.setattr(report_cmd, "report_create_sync", fake_report_create_sync)
    monkeypatch.setattr(report_cmd.sys, "stdin", io.StringIO("from stdin"))

    report_cmd._report_create(
        emitted.append,
        content="ignored",
        stdin=True,
        spawn="@latest",
    )

    assert captured["payload"].spawn_id == "@latest"
    assert captured["payload"].content == "from stdin"
    assert emitted[0].spawn_id == "p1"


def test_report_show_passes_spawn_flag(monkeypatch) -> None:
    captured: dict[str, ReportShowInput] = {}
    emitted: list[ReportShowOutput] = []

    def fake_report_show_sync(payload: ReportShowInput) -> ReportShowOutput:
        captured["payload"] = payload
        return ReportShowOutput(
            spawn_id="p2",
            report_path="/tmp/p2/report.md",
            report="ok",
        )

    monkeypatch.setattr(report_cmd, "report_show_sync", fake_report_show_sync)

    report_cmd._report_show(
        emitted.append,
        spawn="p2",
    )

    assert captured["payload"].spawn_id == "p2"
    assert emitted[0].spawn_id == "p2"


def test_report_search_passes_query_limit_and_spawn(monkeypatch) -> None:
    captured: dict[str, ReportSearchInput] = {}
    emitted: list[ReportSearchOutput] = []

    def fake_report_search_sync(payload: ReportSearchInput) -> ReportSearchOutput:
        captured["payload"] = payload
        return ReportSearchOutput(results=())

    monkeypatch.setattr(report_cmd, "report_search_sync", fake_report_search_sync)

    report_cmd._report_search(
        emitted.append,
        query="needle",
        spawn="@latest",
        limit=5,
    )

    assert captured["payload"].query == "needle"
    assert captured["payload"].spawn_id == "@latest"
    assert captured["payload"].limit == 5
    assert emitted[0].results == ()
