"""Unit tests for ops context query centralization."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

from meridian.lib.core.resolved_context import ResolvedContext
from meridian.lib.ops.context import (
    ContextInput,
    WorkCurrentInput,
    _resolve_runtime_context,
    context_sync,
    work_current_sync,
)

if TYPE_CHECKING:
    from pytest import MonkeyPatch


def test_resolve_runtime_context_delegates_to_resolved_context(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("MERIDIAN_REPO_ROOT", raising=False)
    monkeypatch.delenv("MERIDIAN_STATE_ROOT", raising=False)

    seen_env: list[tuple[str | None, str | None]] = []
    expected = ResolvedContext(depth=7, work_id="w7", work_dir=Path("/repo/.meridian/work/w7"))

    def fake_from_environment(cls) -> ResolvedContext:
        _ = cls
        seen_env.append(
            (
                os.environ.get("MERIDIAN_REPO_ROOT"),
                os.environ.get("MERIDIAN_STATE_ROOT"),
            )
        )
        return expected

    monkeypatch.setattr(ResolvedContext, "from_environment", classmethod(fake_from_environment))

    resolved = _resolve_runtime_context(Path("/repo"), Path("/runtime/state"))

    assert resolved is expected
    assert seen_env == [("/repo", "/runtime/state")]
    assert os.environ.get("MERIDIAN_REPO_ROOT") is None
    assert os.environ.get("MERIDIAN_STATE_ROOT") is None


def test_context_sync_uses_resolved_context_for_runtime_fields(
    monkeypatch: MonkeyPatch,
) -> None:
    repo_root = Path("/repo")
    state_root = Path("/runtime/state")

    monkeypatch.setattr("meridian.lib.ops.context.resolve_project_root", lambda: repo_root)
    monkeypatch.setattr(
        "meridian.lib.ops.context.resolve_state_root_for_read",
        lambda _repo_root: state_root,
    )
    monkeypatch.setattr(
        "meridian.lib.ops.context.resolve_workspace_snapshot",
        lambda _repo: object(),
    )
    monkeypatch.setattr(
        "meridian.lib.ops.context.get_projectable_roots",
        lambda _snapshot: [repo_root, repo_root / "subdir"],
    )
    monkeypatch.setattr(
        "meridian.lib.ops.context._resolve_runtime_context",
        lambda _repo, _state: ResolvedContext(
            depth=9,
            work_id="w9",
            work_dir=Path("/repo/.meridian/work/w9"),
        ),
    )

    output = context_sync(ContextInput())

    assert output.work_dir == "/repo/.meridian/work/w9"
    assert output.depth == 9
    assert output.repo_root == "/repo"
    assert output.state_root == "/runtime/state"
    assert output.fs_dir == "/repo/.meridian/fs"
    assert output.context_roots == ["/repo", "/repo/subdir"]


def test_work_current_sync_uses_resolved_context(monkeypatch: MonkeyPatch) -> None:
    repo_root = Path("/repo")
    state_root = Path("/runtime/state")

    monkeypatch.setattr("meridian.lib.ops.context.resolve_project_root", lambda: repo_root)
    monkeypatch.setattr(
        "meridian.lib.ops.context.resolve_state_root_for_read",
        lambda _repo_root: state_root,
    )
    monkeypatch.setattr(
        "meridian.lib.ops.context._resolve_runtime_context",
        lambda _repo, _state: ResolvedContext(work_dir=Path("/repo/.meridian/work/current")),
    )

    output = work_current_sync(WorkCurrentInput())

    assert output.work_dir == "/repo/.meridian/work/current"


def test_ops_context_env_parsing_is_limited_to_repo_and_state_defaults() -> None:
    source_path = Path(__file__).resolve().parents[3] / "src/meridian/lib/ops/context.py"
    source = source_path.read_text(encoding="utf-8")
    meridian_keys = set(re.findall(r"MERIDIAN_[A-Z_]+", source))

    assert meridian_keys == {"MERIDIAN_REPO_ROOT", "MERIDIAN_STATE_ROOT"}
