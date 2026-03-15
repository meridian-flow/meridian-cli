"""Harness extraction invariants for report, usage, and session metadata."""

from meridian.lib.core.types import SpawnId
from meridian.lib.harness.adapter import ArtifactStore
from meridian.lib.harness.claude import ClaudeAdapter
from meridian.lib.harness.codex import CodexAdapter
from meridian.lib.harness.opencode import OpenCodeAdapter
from meridian.lib.launch.report import extract_or_fallback_report
from meridian.lib.launch.written_files import extract_written_files
from meridian.lib.state.artifact_store import InMemoryStore, make_artifact_key


class _StubCodexAdapter(CodexAdapter):
    def __init__(self, *, report: str | None = None, raises: Exception | None = None) -> None:
        self._report = report
        self._raises = raises

    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        _ = artifacts, spawn_id
        if self._raises is not None:
            raise self._raises
        return self._report


def test_adapters_extract_usage_from_cross_harness_payloads() -> None:
    artifacts = InMemoryStore()

    run_claude = SpawnId("r-claude")
    artifacts.put(
        make_artifact_key(run_claude, "tokens.json"),
        b'{"input_tokens": 1200, "output_tokens": 320, "total_cost_usd": 0.55}',
    )
    claude_usage = ClaudeAdapter().extract_usage(artifacts, run_claude)
    assert claude_usage.input_tokens == 1200
    assert claude_usage.output_tokens == 320
    assert claude_usage.total_cost_usd == 0.55

    run_codex = SpawnId("r-codex")
    artifacts.put(
        make_artifact_key(run_codex, "usage.json"),
        b'{"usage": {"prompt_tokens": "44", "completion_tokens": "12", "cost_usd": "0.04"}}',
    )
    codex_usage = CodexAdapter().extract_usage(artifacts, run_codex)
    assert codex_usage.input_tokens == 44
    assert codex_usage.output_tokens == 12
    assert codex_usage.total_cost_usd == 0.04

    run_opencode = SpawnId("r-opencode")
    artifacts.put(
        make_artifact_key(run_opencode, "output.jsonl"),
        b'{"event":"response.completed","usage":{"input":9,"output":3},"cost":{"total_cost_usd":"0.015"}}\n',
    )
    opencode_usage = OpenCodeAdapter().extract_usage(artifacts, run_opencode)
    assert opencode_usage.input_tokens == 9
    assert opencode_usage.output_tokens == 3
    assert opencode_usage.total_cost_usd == 0.015


def test_extract_session_ids_from_resume_text_and_json_aliases() -> None:
    artifacts = InMemoryStore()

    codex_spawn = SpawnId("r-codex-resume-text")
    artifacts.put(
        make_artifact_key(codex_spawn, "output.jsonl"),
        b"To continue this session, run codex resume 019cb8d4-8d62-79d3-a925-d329f8310c5d\n",
    )
    assert (
        CodexAdapter().extract_session_id(artifacts, codex_spawn)
        == "019cb8d4-8d62-79d3-a925-d329f8310c5d"
    )

    opencode_json_spawn = SpawnId("r-opencode-sessionid-json")
    artifacts.put(
        make_artifact_key(opencode_json_spawn, "output.jsonl"),
        b'{"type":"session.updated","sessionID":"oc_session_abc123"}\n',
    )
    assert (
        OpenCodeAdapter().extract_session_id(artifacts, opencode_json_spawn) == "oc_session_abc123"
    )

    opencode_text_spawn = SpawnId("r-opencode-sessionid-text")
    artifacts.put(
        make_artifact_key(opencode_text_spawn, "output.jsonl"),
        b"Continue with: opencode --session oc_session_xyz789\n",
    )
    assert (
        OpenCodeAdapter().extract_session_id(artifacts, opencode_text_spawn) == "oc_session_xyz789"
    )


def test_harness_extract_report_uses_last_useful_assistant_output() -> None:
    artifacts = InMemoryStore()
    codex_spawn = SpawnId("r-codex-report-last")
    artifacts.put(
        make_artifact_key(codex_spawn, "output.jsonl"),
        b'{"type":"item.completed","item":{"type":"agent_message","text":"first"}}\n'
        b'{"type":"item.completed","item":{"type":"command_execution","aggregated_output":"ignored"}}\n'
        b'{"type":"item.completed","item":{"type":"agent_message","text":"second"}}\n',
    )
    assert CodexAdapter().extract_report(artifacts, codex_spawn) == "second"

    claude_spawn = SpawnId("r-claude-report-result-preferred")
    artifacts.put(
        make_artifact_key(claude_spawn, "output.jsonl"),
        b'{"type":"assistant","content":[{"type":"text","text":"assistant fallback"}]}\n'
        b'{"type":"result","result":"final result report"}\n',
    )
    assert ClaudeAdapter().extract_report(artifacts, claude_spawn) == "final result report"

    opencode_spawn = SpawnId("r-opencode-report-last")
    artifacts.put(
        make_artifact_key(opencode_spawn, "output.jsonl"),
        b'{"type":"assistant","message":"first message"}\n'
        b'{"type":"tool.call","message":"ignored"}\n'
        b'{"type":"assistant","message":"final message"}\n',
    )
    assert OpenCodeAdapter().extract_report(artifacts, opencode_spawn) == "final message"


def test_extract_or_fallback_report_tolerates_adapter_errors_and_bad_jsonl() -> None:
    artifacts = InMemoryStore()
    failing_spawn = SpawnId("r-report-adapter-raises")
    artifacts.put(
        make_artifact_key(failing_spawn, "output.jsonl"),
        b'{"role":"assistant","content":"generic fallback"}\n',
    )
    extracted = extract_or_fallback_report(
        artifacts,
        failing_spawn,
        adapter=_StubCodexAdapter(raises=RuntimeError("boom")),
    )
    assert extracted.content == "generic fallback"
    assert extracted.source == "assistant_message"


def test_extract_written_files_prefers_explicit_artifacts_only() -> None:
    artifacts = InMemoryStore()
    spawn_id = SpawnId("r-files-explicit")
    artifacts.put(
        make_artifact_key(spawn_id, "written_files.json"),
        (
            b'{"written_files":["src/kept.py"],"events":[{"path":"docs/also-kept.md"}],'
            b'"ignored":"tests/read_only_fixture.py"}'
        ),
    )
    artifacts.put(
        make_artifact_key(spawn_id, "written_files.txt"),
        b"scripts/finalize.sh\nsrc/kept.py\n",
    )
    artifacts.put(
        make_artifact_key(spawn_id, "output.jsonl"),
        b'{"type":"tool.call","tool":"read","path":"src/should_not_leak.py"}\n',
    )
    artifacts.put(
        make_artifact_key(spawn_id, "report.md"),
        b"Reviewed `docs/mentioned_only.md` while working.\n",
    )

    assert extract_written_files(artifacts, spawn_id) == (
        "src/kept.py",
        "docs/also-kept.md",
        "scripts/finalize.sh",
    )


def test_extract_written_files_ignores_report_and_output_without_explicit_signal() -> None:
    artifacts = InMemoryStore()
    spawn_id = SpawnId("r-files-no-fallback")
    artifacts.put(
        make_artifact_key(spawn_id, "output.jsonl"),
        b'{"type":"tool.call","tool":"read","path":"src/read_only.py"}\n',
    )
    artifacts.put(
        make_artifact_key(spawn_id, "report.md"),
        b"Referenced `docs/mentioned_only.md` and `scripts/check-mermaid.sh`.\n",
    )

    assert extract_written_files(artifacts, spawn_id) == ()


def test_extract_or_fallback_report_tolerates_malformed_jsonl_and_blank_adapter_output() -> None:
    artifacts = InMemoryStore()
    codex_spawn = SpawnId("r-codex-report-malformed-lines")
    artifacts.put(
        make_artifact_key(codex_spawn, "output.jsonl"),
        b'{"type":"item.completed","item":{"type":"agent_message","text":"first"}}\n'
        b"{this is not valid json}\n"
        b'{"type":"item.completed","item":{"type":"agent_message","text":"second"}}\n'
        b'{"type":"item.completed","item":{"type":"agent_message","text":"unterminated"}\n',
    )
    assert CodexAdapter().extract_report(artifacts, codex_spawn) == "second"

    whitespace_spawn = SpawnId("r-report-adapter-whitespace")
    artifacts.put(
        make_artifact_key(whitespace_spawn, "output.jsonl"),
        b'{"role":"assistant","content":"generic fallback"}\n',
    )
    extracted = extract_or_fallback_report(
        artifacts,
        whitespace_spawn,
        adapter=_StubCodexAdapter(report="   \n\t"),
    )
    assert extracted.content == "generic fallback"
    assert extracted.source == "assistant_message"
