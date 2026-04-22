from __future__ import annotations

import hashlib
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import ANY
from uuid import uuid4

from meridian.lib.hooks.builtin.git_autosync import GIT_AUTOSYNC
from meridian.plugin_api import Hook, HookContext, HookResult

if TYPE_CHECKING:
    import pytest


def _hook(
    *,
    remote: str | None = "https://example.com/acme/project.git",
    exclude: tuple[str, ...] = (),
) -> Hook:
    return Hook(
        name="git-autosync",
        event="work.done",
        source="project",
        builtin="git-autosync",
        remote=remote,
        exclude=exclude,
    )


def _context(work_dir: str | None = "/tmp/work") -> HookContext:
    return HookContext(
        event_name="work.done",
        event_id=uuid4(),
        timestamp="2026-04-20T00:00:00+00:00",
        project_root="/repo",
        runtime_root="/repo/.meridian",
        work_id="w123",
        work_dir=work_dir,
    )


def _cp(
    *,
    args: list[str],
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=args,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_git_autosync_declares_metadata() -> None:
    assert GIT_AUTOSYNC.name == "git-autosync"
    assert GIT_AUTOSYNC.requirements == ("git",)
    assert GIT_AUTOSYNC.default_events == (
        "spawn.start",
        "spawn.finalized",
        "work.started",
        "work.done",
    )
    assert GIT_AUTOSYNC.default_interval is None


def test_check_requirements_returns_false_when_git_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _which(_name: str) -> None:
        return None

    monkeypatch.setattr("meridian.lib.hooks.builtin.git_autosync.shutil.which", _which)

    ok, error = GIT_AUTOSYNC.check_requirements()

    assert ok is False
    assert error == "git CLI not found in PATH."


def test_execute_skips_when_repo_missing() -> None:
    result = GIT_AUTOSYNC.execute(_context(None), _hook(remote=None))

    assert result.outcome == "skipped"
    assert result.success is True
    assert result.skipped is True
    assert result.skip_reason == "missing_repo"


def test_execute_skips_when_lock_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _resolve_clone_path(_repo: str) -> Path:
        return Path("/tmp/clone")

    monkeypatch.setattr(
        "meridian.lib.hooks.builtin.git_autosync.resolve_clone_path",
        _resolve_clone_path,
    )

    def _raise_timeout(*_args: object, **_kwargs: object) -> None:
        raise TimeoutError("timed out")

    monkeypatch.setattr("meridian.lib.hooks.builtin.git_autosync.file_lock", _raise_timeout)

    result = GIT_AUTOSYNC.execute(_context(), _hook())

    assert result.outcome == "skipped"
    assert result.success is True
    assert result.skipped is True
    assert result.skip_reason == "lock_timeout"


def test_execute_delegates_to_execute_with_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = HookResult(
        hook_name="git-autosync",
        event="work.done",
        outcome="success",
        success=True,
    )

    def _resolve_clone_path(_repo: str) -> Path:
        return Path("/tmp/clone")

    monkeypatch.setattr(
        "meridian.lib.hooks.builtin.git_autosync.resolve_clone_path",
        _resolve_clone_path,
    )

    @contextmanager
    def _fake_lock(*_args: object, **_kwargs: object):
        yield

    monkeypatch.setattr("meridian.lib.hooks.builtin.git_autosync.file_lock", _fake_lock)

    def _execute_with_lock(
        context: HookContext,
        config: Hook,
        clone_path: Path,
        start: float,
    ) -> HookResult:
        _ = context, config, clone_path, start
        return expected

    monkeypatch.setattr(
        GIT_AUTOSYNC,
        "_execute_with_lock",
        _execute_with_lock,
    )

    result = GIT_AUTOSYNC.execute(_context(), _hook())

    assert result is expected


def test_execute_locks_under_user_state_outside_clone(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    remote = "https://example.com/acme/project.git"
    clone_path = tmp_path / "clones" / "remote"
    user_state_root = tmp_path / "user-state"
    lock_paths: list[Path] = []

    def _resolve_clone_path(_repo: str) -> Path:
        return clone_path

    monkeypatch.setattr(
        "meridian.lib.hooks.builtin.git_autosync.resolve_clone_path",
        _resolve_clone_path,
    )
    monkeypatch.setattr(
        "meridian.lib.hooks.builtin.git_autosync.get_user_home",
        lambda: user_state_root,
    )

    @contextmanager
    def _fake_lock(path: Path, timeout: float):
        _ = timeout
        lock_paths.append(path)
        yield

    monkeypatch.setattr("meridian.lib.hooks.builtin.git_autosync.file_lock", _fake_lock)

    expected = HookResult(
        hook_name="git-autosync",
        event="work.done",
        outcome="success",
        success=True,
    )

    def _execute_with_lock(
        context: HookContext,
        config: Hook,
        resolved_clone_path: Path,
        start: float,
    ) -> HookResult:
        _ = context, config, start
        assert resolved_clone_path == clone_path
        return expected

    monkeypatch.setattr(GIT_AUTOSYNC, "_execute_with_lock", _execute_with_lock)

    result = GIT_AUTOSYNC.execute(_context(), _hook(remote=remote))

    expected_hash = hashlib.sha256(str(clone_path.resolve()).encode("utf-8")).hexdigest()[
        :16
    ]
    assert result is expected
    assert lock_paths == [user_state_root / "locks" / f"clone-{expected_hash}.lock"]
    assert clone_path not in lock_paths[0].parents


def test_sync_runs_commit_first_then_pull_and_push(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    responses = iter(
        [
            _cp(args=["git", "add", "-A"]),
            _cp(args=["git", "diff", "--cached", "--quiet"], returncode=1),
            _cp(args=["git", "commit", "-m", "autosync: now"]),
            _cp(args=["git", "fetch", "origin"]),
            _cp(
                args=["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
                stdout="1 1\n",
            ),
            _cp(args=["git", "pull", "--rebase"]),
            _cp(
                args=["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
                stdout="1 0\n",
            ),
            _cp(args=["git", "push"]),
        ]
    )

    def fake_run_git(
        work_dir: str,
        args: list[str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        _ = work_dir, timeout
        calls.append(args)
        return next(responses)

    monkeypatch.setattr(GIT_AUTOSYNC, "_run_git", fake_run_git)

    outcome = GIT_AUTOSYNC._sync("/tmp/clone", ())

    assert outcome.outcome == "success"
    assert outcome.success is True
    assert outcome.skipped is False
    assert calls == [
        ["add", "-A"],
        ["diff", "--cached", "--quiet"],
        ["commit", "-m", ANY],
        ["fetch", "origin"],
        ["rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
        ["pull", "--rebase"],
        ["rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
        ["push"],
    ]


def test_sync_aborts_rebase_and_skips_on_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    responses = iter(
        [
            _cp(args=["git", "add", "-A"]),
            _cp(args=["git", "diff", "--cached", "--quiet"], returncode=1),
            _cp(args=["git", "commit", "-m", "autosync: now"]),
            _cp(args=["git", "fetch", "origin"]),
            _cp(
                args=["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
                stdout="1 1\n",
            ),
            _cp(
                args=["git", "pull", "--rebase"],
                returncode=1,
                stderr="pull failed",
            ),
            _cp(args=["git", "rebase", "--abort"]),
        ]
    )

    def fake_run_git(
        work_dir: str,
        args: list[str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        _ = work_dir, timeout
        calls.append(args)
        return next(responses)

    monkeypatch.setattr(GIT_AUTOSYNC, "_run_git", fake_run_git)
    def _is_rebase_in_progress(_clone: str) -> bool:
        return True

    monkeypatch.setattr(GIT_AUTOSYNC, "_is_rebase_in_progress", _is_rebase_in_progress)

    outcome = GIT_AUTOSYNC._sync("/tmp/clone", ())

    assert outcome.outcome == "skipped"
    assert outcome.success is True
    assert outcome.skip_reason == "rebase_conflict"
    assert calls == [
        ["add", "-A"],
        ["diff", "--cached", "--quiet"],
        ["commit", "-m", ANY],
        ["fetch", "origin"],
        ["rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
        ["pull", "--rebase"],
        ["rebase", "--abort"],
    ]


def test_sync_skips_push_when_nothing_to_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    responses = iter(
        [
            _cp(args=["git", "add", "-A"]),
            _cp(args=["git", "diff", "--cached", "--quiet"], returncode=0),
            _cp(args=["git", "fetch", "origin"]),
            _cp(
                args=["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
                stdout="0 0\n",
            ),
        ]
    )

    def fake_run_git(
        work_dir: str,
        args: list[str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        _ = work_dir, timeout
        calls.append(args)
        return next(responses)

    monkeypatch.setattr(GIT_AUTOSYNC, "_run_git", fake_run_git)

    outcome = GIT_AUTOSYNC._sync("/tmp/clone", ())

    assert outcome.outcome == "skipped"
    assert outcome.success is True
    assert outcome.skip_reason == "nothing_to_sync"
    assert calls == [
        ["add", "-A"],
        ["diff", "--cached", "--quiet"],
        ["fetch", "origin"],
        ["rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
    ]


def test_sync_applies_exclude_patterns_before_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    responses = iter(
        [
            _cp(args=["git", "add", "-A"]),
            _cp(
                args=["git", "diff", "--cached", "--name-only", "-z"],
                stdout="keep.txt\0debug.log\0tmp/cache.txt\0",
            ),
            _cp(args=["git", "reset", "--quiet", "--", "debug.log", "tmp/cache.txt"]),
            _cp(args=["git", "diff", "--cached", "--quiet"], returncode=1),
            _cp(args=["git", "commit", "-m", "autosync: now"]),
            _cp(args=["git", "fetch", "origin"]),
            _cp(
                args=["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
                stdout="1 0\n",
            ),
            _cp(args=["git", "push"]),
        ]
    )

    def fake_run_git(
        work_dir: str,
        args: list[str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        _ = work_dir, timeout
        calls.append(args)
        return next(responses)

    monkeypatch.setattr(GIT_AUTOSYNC, "_run_git", fake_run_git)

    outcome = GIT_AUTOSYNC._sync("/tmp/clone", ("*.log", "tmp/"))

    assert outcome.outcome == "success"
    assert outcome.success is True
    assert ["reset", "--quiet", "--", "debug.log", "tmp/cache.txt"] in calls


def test_sync_treats_push_failure_as_fail_open_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            _cp(args=["git", "add", "-A"]),
            _cp(args=["git", "diff", "--cached", "--quiet"], returncode=1),
            _cp(args=["git", "commit", "-m", "autosync: now"]),
            _cp(args=["git", "fetch", "origin"]),
            _cp(
                args=["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
                stdout="1 0\n",
            ),
            _cp(args=["git", "push"], returncode=1, stderr="fatal: Authentication failed"),
        ]
    )

    def _run_git(
        work_dir: str,
        args: list[str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        _ = work_dir, args, timeout
        return next(responses)

    monkeypatch.setattr(GIT_AUTOSYNC, "_run_git", _run_git)

    outcome = GIT_AUTOSYNC._sync("/tmp/clone", ())

    assert outcome.outcome == "skipped"
    assert outcome.success is True
    assert outcome.skipped is True
    assert outcome.skip_reason == "push_failed"


def test_is_excluded_path_matches_glob_and_directory_patterns() -> None:
    assert GIT_AUTOSYNC._is_excluded_path("logs/debug.log", ("*.log",)) is True
    assert GIT_AUTOSYNC._is_excluded_path("tmp/output.txt", ("tmp/",)) is True
    assert GIT_AUTOSYNC._is_excluded_path("src/main.py", ("tmp/", "*.log")) is False


def test_parse_nul_paths_handles_empty_and_normalized_content() -> None:
    assert GIT_AUTOSYNC._parse_nul_paths("") == ()
    assert GIT_AUTOSYNC._parse_nul_paths("a\0b\0") == ("a", "b")
