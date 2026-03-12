"""Running-spawn query parser regressions and detail shaping."""


import json
from pathlib import Path

from meridian.lib.ops.spawn.models import SpawnDetailOutput
from meridian.lib.ops.spawn.query import detail_from_row, extract_last_assistant_message
from meridian.lib.state.spawn_store import SpawnRecord


def test_extract_last_assistant_message_ignores_codex_substrings() -> None:
    stderr_text = "\n".join(
        [
            "OpenAI Codex v0.107.0",
            "model=gpt-5.3-codex",
            "harness=codex",
            "provider=openai",
        ]
    )
    assert extract_last_assistant_message(stderr_text) is None


def test_extract_last_assistant_message_reads_lines_after_codex_marker() -> None:
    stderr_text = "\n".join(
        [
            "OpenAI Codex v0.107.0",
            "model: gpt-5.3-codex",
            "codex",
            "First response line.",
            "Second response line.",
            "exec",
            "/bin/bash -lc 'echo ok'",
            "codex",
            "Final assistant reply.",
        ]
    )
    assert extract_last_assistant_message(stderr_text) == "Final assistant reply."


def test_extract_last_assistant_message_keeps_json_assistant_events() -> None:
    stderr_text = "\n".join(
        [
            json.dumps({"type": "assistant", "text": "json assistant message"}),
            "exec",
        ]
    )
    assert extract_last_assistant_message(stderr_text) == "json assistant message"


def test_detail_from_row_carries_work_and_desc_fields(tmp_path: Path) -> None:
    row = SpawnRecord(
        id="p5",
        chat_id="c1",
        model="claude-opus-4-6",
        agent="agent",
        harness="claude",
        kind="child",
        desc="Implement step 2",
        work_id="auth-refactor",
        harness_session_id="session-1",
        launch_mode="foreground",
        wrapper_pid=None,
        worker_pid=None,
        status="running",
        prompt="ignored",
        started_at="2026-03-09T00:00:00Z",
        finished_at=None,
        exit_code=None,
        duration_secs=238.8,
        total_cost_usd=None,
        input_tokens=None,
        output_tokens=None,
        error=None,
    )

    result = detail_from_row(repo_root=tmp_path, row=row, report=False)

    assert result.work_id == "auth-refactor"
    assert result.desc == "Implement step 2"


def test_spawn_detail_format_text_shows_work_and_desc_when_present() -> None:
    payload = SpawnDetailOutput(
        spawn_id="p5",
        status="running",
        model="claude-opus-4-6",
        harness="claude",
        work_id="auth-refactor",
        desc="Implement step 2",
        started_at="2026-03-09T00:00:00Z",
        finished_at=None,
        duration_secs=238.8,
        exit_code=None,
        failure_reason=None,
        input_tokens=None,
        output_tokens=None,
        cost_usd=None,
        report_path="/tmp/.meridian/spawns/p5/report.md",
        report_summary=None,
        report=None,
        last_message=None,
        log_path=None,
    )

    assert payload.format_text() == "\n".join(
        [
            "Spawn: p5",
            "Status: running",
            "Model: claude-opus-4-6 (claude)",
            "Duration: 238.8s",
            "Work: auth-refactor",
            "Desc: Implement step 2",
            "Report: /tmp/.meridian/spawns/p5/report.md",
        ]
    )


def test_spawn_detail_format_text_omits_blank_work_and_desc() -> None:
    payload = SpawnDetailOutput(
        spawn_id="p5",
        status="running",
        model="claude-opus-4-6",
        harness="claude",
        work_id="   ",
        desc="",
        started_at="2026-03-09T00:00:00Z",
        finished_at=None,
        duration_secs=238.8,
        exit_code=None,
        failure_reason=None,
        input_tokens=None,
        output_tokens=None,
        cost_usd=None,
        report_path=None,
        report_summary=None,
        report=None,
        last_message=None,
        log_path=None,
    )

    assert payload.format_text() == "\n".join(
        [
            "Spawn: p5",
            "Status: running",
            "Model: claude-opus-4-6 (claude)",
            "Duration: 238.8s",
        ]
    )
