"""Harness adapter ownership tests for native layout and session detection."""

import json
import os
import time
from pathlib import Path
from uuid import uuid4

import pytest

from meridian.lib.harness.claude import ClaudeAdapter
from meridian.lib.harness.codex import CodexAdapter
from meridian.lib.harness.opencode import OpenCodeAdapter
from meridian.lib.harness.session_detection import infer_harness_from_untracked_session_ref


def test_claude_adapter_owns_native_layout_and_prompt_policy() -> None:
    adapter = ClaudeAdapter()

    layout = adapter.native_layout()
    assert layout is not None
    assert layout.agents == (".claude/agents",)
    assert layout.skills == (".claude/skills",)

    policy = adapter.run_prompt_policy()
    assert policy.include_agent_body is False
    assert policy.include_skills is False
    assert policy.skill_injection_mode == "append-system-prompt"


def test_codex_adapter_owns_session_detection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    fake_home = tmp_path / "home"
    monkeypatch.setenv("HOME", fake_home.as_posix())

    session_id = str(uuid4())
    rollout_dir = fake_home / ".codex" / "sessions" / "2026" / "03" / "08"
    rollout_dir.mkdir(parents=True)
    rollout_path = rollout_dir / f"rollout-2026-03-08T12-00-00-{session_id}.jsonl"
    rollout_path.write_text(
        "\n".join(
            (
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {"id": session_id, "cwd": repo_root.as_posix()},
                    }
                ),
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {"type": "message", "role": "assistant"},
                    }
                ),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    now = time.time()
    os.utime(rollout_path, (now, now))

    adapter = CodexAdapter()
    assert (
        adapter.detect_primary_session_id(
            repo_root=repo_root,
            started_at_epoch=now - 1,
            started_at_local_iso=None,
        )
        == session_id
    )
    assert adapter.owns_untracked_session(repo_root=repo_root, session_ref=session_id) is True
    assert infer_harness_from_untracked_session_ref(repo_root, session_id) == "codex"


def test_opencode_adapter_owns_session_detection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    fake_home = tmp_path / "home"
    monkeypatch.setenv("HOME", fake_home.as_posix())

    session_id = "session-123456"
    logs_dir = fake_home / ".local" / "share" / "opencode" / "log"
    logs_dir.mkdir(parents=True)
    log_path = logs_dir / "latest.log"
    log_path.write_text(
        (
            "INF 2026-03-08T12:00:05 +12ms service=session "
            f"id={session_id} directory={repo_root.as_posix()} created\n"
        ),
        encoding="utf-8",
    )
    now = time.time()
    os.utime(log_path, (now, now))

    adapter = OpenCodeAdapter()
    assert (
        adapter.detect_primary_session_id(
            repo_root=repo_root,
            started_at_epoch=now - 1,
            started_at_local_iso="2026-03-08T12:00:00",
        )
        == session_id
    )
    assert adapter.owns_untracked_session(repo_root=repo_root, session_ref=session_id) is True
    assert infer_harness_from_untracked_session_ref(repo_root, session_id) == "opencode"
