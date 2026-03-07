"""Harness-specific report extraction tests."""

from __future__ import annotations

from meridian.lib.extract.report import extract_or_fallback_report
from meridian.lib.harness.claude import ClaudeAdapter
from meridian.lib.harness.codex import CodexAdapter
from meridian.lib.harness.opencode import OpenCodeAdapter
from meridian.lib.harness.adapter import ArtifactStore
from meridian.lib.state.artifact_store import InMemoryStore, make_artifact_key
from meridian.lib.types import SpawnId


class _StubCodexAdapter(CodexAdapter):
    def __init__(self, *, report: str | None = None, raises: Exception | None = None) -> None:
        self._report = report
        self._raises = raises

    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        _ = artifacts, spawn_id
        if self._raises is not None:
            raise self._raises
        return self._report


def test_codex_extract_report_returns_last_agent_message_text() -> None:
    artifacts = InMemoryStore()
    spawn_id = SpawnId("r-codex-report-last")
    artifacts.put(
        make_artifact_key(spawn_id, "output.jsonl"),
        b'{"type":"item.completed","item":{"type":"agent_message","text":"first"}}\n'
        b'{"type":"item.completed","item":{"type":"command_execution","aggregated_output":"ignored"}}\n'
        b'{"type":"item.completed","item":{"type":"agent_message","text":"second"}}\n',
    )

    assert CodexAdapter().extract_report(artifacts, spawn_id) == "second"


def test_codex_extract_report_returns_none_when_no_agent_messages() -> None:
    artifacts = InMemoryStore()
    spawn_id = SpawnId("r-codex-report-none")
    artifacts.put(
        make_artifact_key(spawn_id, "output.jsonl"),
        b'{"type":"item.completed","item":{"type":"command_execution","aggregated_output":"ok"}}\n',
    )

    assert CodexAdapter().extract_report(artifacts, spawn_id) is None


def test_claude_extract_report_prefers_result_event_result_field() -> None:
    artifacts = InMemoryStore()
    spawn_id = SpawnId("r-claude-report-result-preferred")
    artifacts.put(
        make_artifact_key(spawn_id, "output.jsonl"),
        b'{"type":"assistant","content":[{"type":"text","text":"assistant fallback"}]}\n'
        b'{"type":"result","result":"final result report"}\n',
    )

    assert ClaudeAdapter().extract_report(artifacts, spawn_id) == "final result report"


def test_claude_extract_report_falls_back_to_last_assistant_content() -> None:
    artifacts = InMemoryStore()
    spawn_id = SpawnId("r-claude-report-assistant-fallback")
    artifacts.put(
        make_artifact_key(spawn_id, "output.jsonl"),
        b'{"type":"assistant","content":[{"type":"text","text":"first assistant"}]}\n'
        b'{"type":"assistant","content":[{"type":"text","text":"last assistant"}]}\n',
    )

    assert ClaudeAdapter().extract_report(artifacts, spawn_id) == "last assistant"


def test_opencode_extract_report_returns_last_assistant_message() -> None:
    artifacts = InMemoryStore()
    spawn_id = SpawnId("r-opencode-report-last")
    artifacts.put(
        make_artifact_key(spawn_id, "output.jsonl"),
        b'{"type":"assistant","message":"first message"}\n'
        b'{"type":"tool.call","message":"ignored"}\n'
        b'{"type":"assistant","message":"final message"}\n',
    )

    assert OpenCodeAdapter().extract_report(artifacts, spawn_id) == "final message"


def test_extract_or_fallback_report_prefers_adapter_result_over_generic() -> None:
    artifacts = InMemoryStore()
    spawn_id = SpawnId("r-report-adapter-over-generic")
    artifacts.put(
        make_artifact_key(spawn_id, "output.jsonl"),
        b'{"role":"assistant","content":"generic fallback"}\n',
    )

    extracted = extract_or_fallback_report(
        artifacts,
        spawn_id,
        adapter=_StubCodexAdapter(report="adapter report"),
    )

    assert extracted.content == "adapter report"
    assert extracted.source == "assistant_message"


def test_extract_or_fallback_report_prefers_report_md_over_adapter() -> None:
    artifacts = InMemoryStore()
    spawn_id = SpawnId("r-report-md-over-adapter")
    artifacts.put(make_artifact_key(spawn_id, "report.md"), b"report.md content\n")
    artifacts.put(
        make_artifact_key(spawn_id, "output.jsonl"),
        b'{"role":"assistant","content":"generic fallback"}\n',
    )

    extracted = extract_or_fallback_report(
        artifacts,
        spawn_id,
        adapter=_StubCodexAdapter(report="adapter report"),
    )

    assert extracted.content == "report.md content"
    assert extracted.source == "report_md"


def test_extract_or_fallback_report_with_no_adapter_uses_generic_fallback() -> None:
    artifacts = InMemoryStore()
    spawn_id = SpawnId("r-report-no-adapter")
    artifacts.put(
        make_artifact_key(spawn_id, "output.jsonl"),
        b'{"role":"assistant","content":"generic fallback"}\n',
    )

    extracted = extract_or_fallback_report(artifacts, spawn_id, adapter=None)

    assert extracted.content == "generic fallback"
    assert extracted.source == "assistant_message"


def test_extract_or_fallback_report_falls_back_when_adapter_raises() -> None:
    artifacts = InMemoryStore()
    spawn_id = SpawnId("r-report-adapter-raises")
    artifacts.put(
        make_artifact_key(spawn_id, "output.jsonl"),
        b'{"role":"assistant","content":"generic fallback"}\n',
    )

    extracted = extract_or_fallback_report(
        artifacts,
        spawn_id,
        adapter=_StubCodexAdapter(raises=RuntimeError("boom")),
    )

    assert extracted.content == "generic fallback"
    assert extracted.source == "assistant_message"


def test_codex_extract_report_skips_malformed_or_truncated_jsonl_lines() -> None:
    artifacts = InMemoryStore()
    spawn_id = SpawnId("r-codex-report-malformed-lines")
    artifacts.put(
        make_artifact_key(spawn_id, "output.jsonl"),
        b'{"type":"item.completed","item":{"type":"agent_message","text":"first"}}\n'
        b"{this is not valid json}\n"
        b'{"type":"item.completed","item":{"type":"agent_message","text":"second"}}\n'
        b'{"type":"item.completed","item":{"type":"agent_message","text":"unterminated"}\n',
    )

    assert CodexAdapter().extract_report(artifacts, spawn_id) == "second"


def test_extract_or_fallback_report_ignores_whitespace_only_adapter_output() -> None:
    artifacts = InMemoryStore()
    spawn_id = SpawnId("r-report-adapter-whitespace")
    artifacts.put(
        make_artifact_key(spawn_id, "output.jsonl"),
        b'{"role":"assistant","content":"generic fallback"}\n',
    )

    extracted = extract_or_fallback_report(
        artifacts,
        spawn_id,
        adapter=_StubCodexAdapter(report="   \n\t"),
    )

    assert extracted.content == "generic fallback"
    assert extracted.source == "assistant_message"
