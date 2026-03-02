"""Spawn output streaming tests for slices 1-3."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from meridian.lib.domain import Spawn, TokenUsage
from meridian.lib.exec.spawn import execute_with_finalization
from meridian.lib.exec.terminal import (
    DEFAULT_VISIBLE_CATEGORIES,
    QUIET_VISIBLE_CATEGORIES,
    VERBOSE_VISIBLE_CATEGORIES,
    TerminalEventFilter,
    resolve_visible_categories,
)
from meridian.lib.harness._common import categorize_stream_event, parse_json_stream_event
from meridian.lib.harness.adapter import (
    ArtifactStore,
    HarnessCapabilities,
    PermissionResolver,
    SpawnParams,
    StreamEvent,
)
from meridian.lib.harness.claude import ClaudeAdapter
from meridian.lib.harness.codex import CodexAdapter
from meridian.lib.harness.opencode import OpenCodeAdapter
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.ops._spawn_execute import _emit_subrun_event
from meridian.lib.safety.permissions import PermissionConfig
from meridian.lib.space.space_file import create_space
from meridian.lib.state.artifact_store import LocalStore
from meridian.lib.state.paths import resolve_space_dir
from meridian.lib.types import HarnessId, ModelId, SpawnId, SpaceId


class _StreamingHarness:
    def __init__(self, *, script: Path, stdout_file: Path) -> None:
        self._script = script
        self._stdout_file = stdout_file
        self._parser = ClaudeAdapter()

    @property
    def id(self) -> HarnessId:
        return HarnessId("streaming-test")

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities(supports_stream_events=True)

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        _ = run
        return [
            sys.executable,
            str(self._script),
            "--stdout-file",
            str(self._stdout_file),
            *perms.resolve_flags(self.id),
        ]

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
        _ = config
        return {}

    def parse_stream_event(self, line: str) -> StreamEvent | None:
        return self._parser.parse_stream_event(line)

    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        _ = (artifacts, spawn_id)
        return TokenUsage()

    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        _ = (artifacts, spawn_id)
        return None


def test_harness_adapters_map_event_categories() -> None:
    claude = ClaudeAdapter()
    codex = CodexAdapter()
    opencode = OpenCodeAdapter()

    claude_result = claude.parse_stream_event('{"type":"result"}')
    claude_tool = claude.parse_stream_event('{"type":"tool_use"}')
    codex_reasoning = codex.parse_stream_event('{"type":"response.reasoning_summary.delta"}')
    codex_tool = codex.parse_stream_event('{"type":"tool.call.completed"}')
    opencode_subrun = opencode.parse_stream_event('{"type":"spawn.start"}')
    opencode_error = opencode.parse_stream_event('{"type":"error"}')

    assert claude_result is not None and claude_result.category == "lifecycle"
    assert claude_tool is not None and claude_tool.category == "tool-use"
    assert codex_reasoning is not None and codex_reasoning.category == "thinking"
    assert codex_tool is not None and codex_tool.category == "tool-use"
    assert opencode_subrun is not None and opencode_subrun.category == "sub-run"
    assert opencode_error is not None and opencode_error.category == "error"


def test_claude_extract_tasks_from_todowrite_events() -> None:
    adapter = ClaudeAdapter()
    event = adapter.parse_stream_event(
        json.dumps(
            {
                "type": "tool_use",
                "name": "TodoWrite",
                "input": {
                    "todos": [
                        {"id": "t1", "content": "Inspect schema", "status": "completed"},
                        {"id": "t2", "content": "Add run stats command", "status": "in_progress"},
                    ]
                },
            }
        )
    )
    assert event is not None
    assert adapter.extract_tasks(event) == [
        {"id": "t1", "content": "Inspect schema", "status": "completed"},
        {"id": "t2", "content": "Add run stats command", "status": "in_progress"},
    ]


def test_claude_extract_tasks_ignores_non_todo_events() -> None:
    adapter = ClaudeAdapter()
    event = adapter.parse_stream_event('{"type":"assistant","text":"hello"}')
    assert event is not None
    assert adapter.extract_tasks(event) is None


def test_subrun_event_emission_when_depth_gt_zero(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "0")
    _emit_subrun_event(
        {"t": "meridian.spawn.start", "id": "r34", "model": "claude-haiku-4-5", "d": 0}
    )
    assert capsys.readouterr().out == ""

    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    monkeypatch.setenv("MERIDIAN_SPAWN_ID", "p33")
    monkeypatch.setattr("meridian.lib.ops.spawn.time.time", lambda: 1740000000.123)
    _emit_subrun_event(
        {"t": "meridian.spawn.start", "id": "r34", "model": "claude-haiku-4-5", "d": 1}
    )
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["v"] == 1
    assert payload["t"] == "meridian.spawn.start"
    assert payload["id"] == "r34"
    assert payload["parent"] == "p33"
    assert payload["ts"] == 1740000000.123


def test_parse_json_stream_event_recognizes_meridian_protocol() -> None:
    start = parse_json_stream_event('{"t":"spawn.start","id":"r5","model":"claude-haiku-4-5","d":1}')
    assert start is not None
    assert start.event_type == "spawn.start"
    assert start.text == "r5 claude-haiku-4-5 started"
    assert categorize_stream_event(start).category == "sub-run"

    done = parse_json_stream_event('{"t":"spawn.done","id":"r5","exit":0,"secs":2.1,"tok":3200}')
    assert done is not None
    assert done.event_type == "spawn.done"
    assert done.text == "r5 completed 2.1s exit=0 tok=3200"
    assert categorize_stream_event(done).category == "sub-run"


def test_terminal_formatter_renders_subrun_from_meridian_protocol() -> None:
    buffer = io.StringIO()
    filterer = TerminalEventFilter(
        visible_categories=frozenset({"sub-run"}),
        output_stream=buffer,
        root_depth=0,
    )

    raw_start = parse_json_stream_event(
        '{"t":"spawn.start","id":"r34","model":"claude-haiku-4-5","agent":"reviewer","d":1}'
    )
    raw_done = parse_json_stream_event('{"t":"spawn.done","id":"r34","exit":0,"secs":2.1,"tok":3200}')
    assert raw_start is not None
    assert raw_done is not None

    filterer.observe(categorize_stream_event(raw_start))
    filterer.observe(categorize_stream_event(raw_done))

    lines = buffer.getvalue().splitlines()
    assert lines[0] == "├─ r34 claude-haiku-4-5 (reviewer) started"
    assert lines[1] == "├─ r34 completed 2.1s exit=0 tok=3200"


@pytest.mark.asyncio
async def test_execute_with_finalization_emits_categorized_events_to_observer(
    package_root: Path,
    tmp_path: Path,
) -> None:
    space = create_space(tmp_path, name="stream-events")
    run = Spawn(
        spawn_id=SpawnId("r1"),
        prompt="events",
        model=ModelId("gpt-5.3-codex"),
        status="queued",
        space_id=SpaceId(space.id),
    )
    space_dir = resolve_space_dir(tmp_path, space.id)
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    output_lines = tmp_path / "stream.jsonl"
    output_lines.write_text(
        "\n".join(
            (
                json.dumps({"type": "assistant", "text": "chunk"}),
                json.dumps({"type": "tool_use", "text": "apply_patch"}),
                json.dumps({"type": "result", "text": "done"}),
            )
        )
        + "\n",
        encoding="utf-8",
    )

    adapter = _StreamingHarness(
        script=package_root / "tests" / "mock_harness.py",
        stdout_file=output_lines,
    )
    registry = HarnessRegistry()
    registry.register(adapter)

    observed: list[StreamEvent] = []
    exit_code = await execute_with_finalization(
        run,
        repo_root=tmp_path,
        space_dir=space_dir,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
        event_observer=observed.append,
    )

    assert exit_code == 0
    assert [event.category for event in observed] == ["assistant", "tool-use", "lifecycle"]


def test_terminal_event_filter_honors_visibility_and_subrun_indentation() -> None:
    buffer = io.StringIO()
    filterer = TerminalEventFilter(
        visible_categories=frozenset({"error", "sub-run"}),
        output_stream=buffer,
        root_depth=0,
    )

    filterer.observe(
        StreamEvent(
            event_type="progress.tick",
            category="progress",
            raw_line='{"type":"progress.tick"}',
            text="tick",
        )
    )
    assert buffer.getvalue() == ""

    filterer.observe(
        StreamEvent(
            event_type="spawn.start",
            category="sub-run",
            raw_line='{"type":"spawn.start"}',
            text="r34 started",
            metadata={"d": 1},
        )
    )
    filterer.observe(
        StreamEvent(
            event_type="spawn.start",
            category="sub-run",
            raw_line='{"type":"spawn.start"}',
            text="r35 started",
            metadata={"d": 2},
        )
    )
    filterer.observe(
        StreamEvent(
            event_type="error",
            category="error",
            raw_line='{"type":"error"}',
            text="failed",
        )
    )

    lines = buffer.getvalue().splitlines()
    assert lines[0] == "├─ r34 started"
    assert lines[1] == "  ├─ r35 started"
    assert lines[2] == "failed"


def test_resolve_visible_categories_applies_flag_precedence() -> None:
    assert resolve_visible_categories(verbose=False, quiet=False) == DEFAULT_VISIBLE_CATEGORIES
    assert resolve_visible_categories(verbose=False, quiet=True) == QUIET_VISIBLE_CATEGORIES
    assert resolve_visible_categories(verbose=True, quiet=False) == VERBOSE_VISIBLE_CATEGORIES
    assert resolve_visible_categories(verbose=True, quiet=True) == VERBOSE_VISIBLE_CATEGORIES
