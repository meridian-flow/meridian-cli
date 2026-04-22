"""Unit tests for ChildEnvContext resolution and projection."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from meridian.lib.config.project_paths import ProjectConfigPaths
from meridian.lib.core.resolved_context import ResolvedContext
from meridian.lib.launch.context import ChildEnvContext


def _project_paths(tmp_path: Path) -> ProjectConfigPaths:
    execution_cwd = tmp_path / "child-cwd"
    execution_cwd.mkdir()
    return ProjectConfigPaths(project_root=tmp_path, execution_cwd=execution_cwd)


def test_child_env_context_from_environment_uses_resolved_context_parent_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_paths = _project_paths(tmp_path)
    runtime_state_root = tmp_path / "runtime-state"
    runtime_state_root.mkdir()
    monkeypatch.setenv("MERIDIAN_WORK_ID", "work-explicit")

    def fake_from_environment(cls) -> ResolvedContext:
        _ = cls
        return ResolvedContext(depth=3, chat_id=" parent-chat ")

    monkeypatch.setattr(ResolvedContext, "from_environment", classmethod(fake_from_environment))

    resolved = ChildEnvContext.from_environment(
        project_paths=project_paths,
        runtime_root=runtime_state_root,
    )

    assert resolved == ChildEnvContext(
        parent_spawn_id=None,
        project_root=project_paths.execution_cwd.resolve(),
        runtime_root=runtime_state_root.resolve(),
        parent_chat_id="parent-chat",
        parent_depth=3,
        work_id="work-explicit",
        work_dir=(project_paths.execution_cwd / ".meridian" / "work" / "work-explicit").resolve(),
        kb_dir=(project_paths.execution_cwd / ".meridian" / "kb").resolve(),
    )


def test_child_env_context_from_environment_falls_back_to_session_lookup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_paths = _project_paths(tmp_path)
    runtime_state_root = tmp_path / "runtime-state"
    runtime_state_root.mkdir()
    monkeypatch.delenv("MERIDIAN_WORK_ID", raising=False)

    seen_lookup: list[tuple[Path, str]] = []

    def fake_from_environment(cls) -> ResolvedContext:
        _ = cls
        return ResolvedContext(depth=1, chat_id="chat-lookup")

    def fake_get_session_active_work_id(state_root: Path, chat_id: str) -> str | None:
        seen_lookup.append((state_root, chat_id))
        return "work-session"

    monkeypatch.setattr(ResolvedContext, "from_environment", classmethod(fake_from_environment))
    monkeypatch.setattr(
        "meridian.lib.launch.context.get_session_active_work_id",
        fake_get_session_active_work_id,
    )

    resolved = ChildEnvContext.from_environment(
        project_paths=project_paths,
        runtime_root=runtime_state_root,
    )

    assert seen_lookup == [(runtime_state_root.resolve(), "chat-lookup")]
    assert resolved.work_id == "work-session"
    assert resolved.work_dir == (
        project_paths.execution_cwd / ".meridian" / "work" / "work-session"
    ).resolve()
    assert resolved.kb_dir == (project_paths.execution_cwd / ".meridian" / "kb").resolve()


def test_child_env_context_from_environment_ignores_session_lookup_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_paths = _project_paths(tmp_path)
    runtime_state_root = tmp_path / "runtime-state"
    runtime_state_root.mkdir()
    monkeypatch.delenv("MERIDIAN_WORK_ID", raising=False)

    def fake_from_environment(cls) -> ResolvedContext:
        _ = cls
        return ResolvedContext(depth=2, chat_id="chat-lookup")

    def raising_lookup(state_root: Path, chat_id: str) -> str | None:
        _ = (state_root, chat_id)
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(ResolvedContext, "from_environment", classmethod(fake_from_environment))
    monkeypatch.setattr(
        "meridian.lib.launch.context.get_session_active_work_id",
        raising_lookup,
    )

    resolved = ChildEnvContext.from_environment(
        project_paths=project_paths,
        runtime_root=runtime_state_root,
    )

    assert resolved.work_id is None
    assert resolved.work_dir is None
    assert resolved.kb_dir == (project_paths.execution_cwd / ".meridian" / "kb").resolve()


def test_child_env_context_child_context_routes_through_contract_helpers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ctx = ChildEnvContext(
        parent_spawn_id=None,
        project_root=tmp_path / "repo",
        runtime_root=tmp_path / "runtime-state",
        parent_chat_id="chat-parent",
        parent_depth=5,
        work_id="work-55",
        work_dir=tmp_path / "repo/.meridian/work/work-55",
        kb_dir=tmp_path / "repo/.meridian/kb",
    )
    expected = {
        "MERIDIAN_DEPTH": "6",
        "MERIDIAN_PROJECT_DIR": ctx.project_root.as_posix(),
        "MERIDIAN_RUNTIME_DIR": ctx.runtime_root.as_posix(),
        "MERIDIAN_CHAT_ID": "chat-parent",
        "MERIDIAN_WORK_ID": "work-55",
        "MERIDIAN_WORK_DIR": ctx.work_dir.as_posix(),
        "MERIDIAN_KB_DIR": ctx.kb_dir.as_posix(),
        "MERIDIAN_FS_DIR": ctx.kb_dir.as_posix(),
    }
    seen: list[dict[str, str]] = []

    def fake_build_child_env_overrides(**kwargs: object) -> dict[str, str]:
        assert kwargs == {
            "parent_spawn_id": None,
            "project_root": ctx.project_root,
            "runtime_root": ctx.runtime_root,
            "parent_chat_id": "chat-parent",
            "parent_depth": 5,
            "work_id": "work-55",
            "work_dir": ctx.work_dir,
            "kb_dir": ctx.kb_dir,
        }
        return dict(expected)

    def fake_validate_child_env_keys(overrides: dict[str, str]) -> None:
        seen.append(dict(overrides))

    monkeypatch.setattr(
        "meridian.lib.launch.context.build_child_env_overrides",
        fake_build_child_env_overrides,
    )
    monkeypatch.setattr(
        "meridian.lib.launch.context.validate_child_env_keys",
        fake_validate_child_env_keys,
    )

    result = ctx.child_context()

    assert result == expected
    assert seen == [expected]
