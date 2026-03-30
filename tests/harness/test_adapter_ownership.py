"""Harness adapter ownership tests for non-trivial session detection."""

import json
import os
import time
from pathlib import Path
from uuid import uuid4

import pytest

from meridian.lib.harness.claude import ClaudeAdapter, project_slug
from meridian.lib.harness.codex import CodexAdapter
from meridian.lib.harness.opencode import OpenCodeAdapter
from meridian.lib.harness.session_detection import infer_harness_from_untracked_session_ref


def test_claude_adapter_detects_latest_project_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    fake_home = tmp_path / "home"
    monkeypatch.setenv("HOME", fake_home.as_posix())

    old_session_id = str(uuid4())
    new_session_id = str(uuid4())
    project_dir = fake_home / ".claude" / "projects" / project_slug(repo_root)
    project_dir.mkdir(parents=True)

    old_path = project_dir / f"{old_session_id}.jsonl"
    old_path.write_text(
        json.dumps({"type": "agent-setting", "sessionId": old_session_id}) + "\n",
        encoding="utf-8",
    )
    new_path = project_dir / f"{new_session_id}.jsonl"
    new_path.write_text(
        json.dumps({"type": "agent-setting", "sessionId": new_session_id}) + "\n",
        encoding="utf-8",
    )

    now = time.time()
    os.utime(old_path, (now - 10, now - 10))
    os.utime(new_path, (now, now))

    adapter = ClaudeAdapter()
    assert (
        adapter.detect_primary_session_id(
            repo_root=repo_root,
            started_at_epoch=now - 1,
            started_at_local_iso=None,
        )
        == new_session_id
    )
    assert adapter.owns_untracked_session(repo_root=repo_root, session_ref=new_session_id) is True
    assert infer_harness_from_untracked_session_ref(repo_root, new_session_id) == "claude"


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
