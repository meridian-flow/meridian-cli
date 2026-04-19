from __future__ import annotations

import pytest

from meridian.cli import primary_launch


def test_run_primary_launch_rejects_continue_cross_harness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_resolve_session_reference(_repo_root: object, _ref: str) -> object:
        return type(
            "Resolved",
            (),
            {
                "harness_session_id": "session-1",
                "source_chat_id": "c1",
                "harness": "claude",
                "source_model": "gpt-5.4",
                "source_agent": "coder",
                "source_work_id": None,
                "source_execution_cwd": None,
                "tracked": True,
                "warning": None,
            },
        )()

    monkeypatch.setattr(
        primary_launch,
        "resolve_session_reference",
        _fake_resolve_session_reference,
    )
    with pytest.raises(ValueError, match="Cannot continue across harnesses"):
        primary_launch.run_primary_launch(
            continue_ref="session-1",
            fork_ref=None,
            model="",
            harness="codex",
            agent=None,
            work="",
            yolo=False,
            approval=None,
            autocompact=None,
            effort=None,
            sandbox=None,
            timeout=None,
            dry_run=True,
            passthrough=(),
        )
