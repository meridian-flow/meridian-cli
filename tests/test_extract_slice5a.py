"""Slice 5a extraction tests."""

from __future__ import annotations

from pathlib import Path

from meridian.lib.extract.files_touched import extract_files_touched
from meridian.lib.extract.finalize import enrich_finalize
from meridian.lib.extract.report import extract_or_fallback_report
from meridian.lib.harness.claude import ClaudeAdapter
from meridian.lib.harness.codex import CodexAdapter
from meridian.lib.harness.opencode import OpenCodeAdapter
from meridian.lib.state.artifact_store import InMemoryStore, make_artifact_key
from meridian.lib.types import SpawnId


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
        b'{"event":"response.completed","usage":{"input":9,"output":3},'
        b'"cost":{"total_cost_usd":"0.015"}}\n',
    )
    opencode_usage = OpenCodeAdapter().extract_usage(artifacts, run_opencode)
    assert opencode_usage.input_tokens == 9
    assert opencode_usage.output_tokens == 3
    assert opencode_usage.total_cost_usd == 0.015


def test_report_uses_last_assistant_message_when_report_missing() -> None:
    artifacts = InMemoryStore()
    spawn_id = SpawnId("r-report-fallback")
    artifacts.put(
        make_artifact_key(spawn_id, "output.jsonl"),
        b'{"role":"assistant","content":"first answer"}\n'
        b'{"role":"user","content":"follow up"}\n'
        b'{"role":"assistant","content":[{"type":"text","text":"final assistant message"}]}\n',
    )

    extracted = extract_or_fallback_report(artifacts, spawn_id)
    assert extracted.source == "assistant_message"
    assert extracted.content == "final assistant message"


def test_report_prefers_report_md_when_both_sources_exist() -> None:
    artifacts = InMemoryStore()
    spawn_id = SpawnId("r-report-prefer-file")
    artifacts.put(
        make_artifact_key(spawn_id, "output.jsonl"),
        b'{"role":"assistant","content":"assistant summary"}\n',
    )
    artifacts.put(
        make_artifact_key(spawn_id, "report.md"),
        b"# File Report\n\nUse this one.\n",
    )

    extracted = extract_or_fallback_report(artifacts, spawn_id)
    assert extracted.source == "report_md"
    assert extracted.content == "# File Report\n\nUse this one."


def test_extract_files_touched_from_structured_output_and_text() -> None:
    artifacts = InMemoryStore()
    spawn_id = SpawnId("r-files")
    artifacts.put(
        make_artifact_key(spawn_id, "output.jsonl"),
        b'{"files_touched":["src/story/ch1.md","src/story/ch2.md"]}\n'
        b'{"role":"assistant","content":"Updated _docs/plans/roadmap.md"}\n'
        b"Touched path frontend/src/app.ts during cleanup.\n",
    )

    touched = extract_files_touched(artifacts, spawn_id)
    assert touched == (
        "src/story/ch1.md",
        "src/story/ch2.md",
        "_docs/plans/roadmap.md",
        "frontend/src/app.ts",
    )


def test_enrich_finalize_materializes_report_from_assistant_message(tmp_path: Path) -> None:
    artifacts = InMemoryStore()
    spawn_id = SpawnId("r-finalize")
    artifacts.put(
        make_artifact_key(spawn_id, "output.jsonl"),
        b'{"role":"assistant","content":"updated src/chapters/ch03.md","session_id":"sess-42"}\n'
        b'{"role":"assistant","content":"final result"}\n',
    )

    enrichment = enrich_finalize(
        artifacts=artifacts,
        adapter=ClaudeAdapter(),
        spawn_id=spawn_id,
        log_dir=tmp_path / "logs" / "r-finalize",
    )

    assert enrichment.report.source == "assistant_message"
    assert enrichment.report_path is not None
    assert enrichment.report_path.exists()
    assert "final result" in enrichment.report_path.read_text(encoding="utf-8")
    assert enrichment.harness_session_id == "sess-42"
    assert enrichment.files_touched == ("src/chapters/ch03.md",)
    assert enrichment.output_is_empty is False
