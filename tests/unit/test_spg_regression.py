"""SPG (Sandbox Permission Gap) regression tests.

Each test maps to one EARS statement from the sandbox permission gap spec.
These tests ensure the sandbox fixes remain intact across refactoring.
"""

from __future__ import annotations

import logging
import subprocess
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest


def _diag_surface(project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        project_root=project_root,
        resolved_config=SimpleNamespace(state=SimpleNamespace(retention_days=30)),
        warning=None,
        workspace_findings=[],
    )


def _telemetry_stats() -> SimpleNamespace:
    return SimpleNamespace(
        total_segments=0,
        total_bytes=0,
        live_segments=0,
        orphaned_segments=0,
        expired_segments=0,
        deleted_segments=0,
        deleted_bytes=0,
    )


def _hook(
    *,
    remote: str | None = "https://example.com/acme/project.git",
    options: dict[str, object] | None = None,
):
    from meridian.plugin_api import Hook

    return Hook(
        name="git-autosync",
        event="spawn.start",
        source="project",
        builtin="git-autosync",
        remote=remote,
        options=options or {},
    )


def _hook_context():
    from meridian.plugin_api import HookContext

    return HookContext(
        event_name="spawn.start",
        event_id=uuid4(),
        timestamp="2026-05-04T00:00:00+00:00",
        project_root="/repo",
        runtime_root="/runtime",
        spawn_id="p1",
    )


def _patch_diag_minimum(monkeypatch: pytest.MonkeyPatch, project_root: Path) -> list[str]:
    calls: list[str] = []

    monkeypatch.setattr(
        "meridian.lib.ops.diag.build_config_surface",
        lambda root: _diag_surface(project_root),
    )
    monkeypatch.setattr(
        "meridian.lib.ops.diag.ensure_runtime_state_bootstrap_sync",
        lambda _: calls.append("bootstrap"),
    )
    monkeypatch.setattr(
        "meridian.lib.ops.diag.resolve_runtime_root",
        lambda _: project_root / "runtime",
    )
    monkeypatch.setattr("meridian.lib.ops.diag._repair_stale_session_locks", lambda _: 0)
    monkeypatch.setattr("meridian.lib.ops.diag._repair_orphan_runs", lambda _: 0)
    monkeypatch.setattr("meridian.lib.ops.diag.spawn_store.list_spawns", lambda _: [])
    monkeypatch.setattr(
        "meridian.lib.ops.diag.scan_stale_spawn_artifacts",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "meridian.lib.ops.diag.scan_telemetry_segments",
        lambda *args, **kwargs: _telemetry_stats(),
    )
    monkeypatch.setattr(
        "meridian.lib.ops.diag.run_retention_cleanup",
        lambda *args, **kwargs: _telemetry_stats(),
    )
    monkeypatch.setattr(
        "meridian.lib.ops.diag.check_upgrade_availability",
        lambda _: SimpleNamespace(count=0, within_constraint=(), beyond_constraint=()),
    )
    monkeypatch.setattr(
        "meridian.lib.ops.diag.format_upgrade_availability",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr("meridian.lib.ops.diag.is_root_side_effect_process", lambda: True)
    monkeypatch.setattr("meridian.lib.ops.diag.get_user_home", lambda: project_root / "user-home")
    (project_root / "runtime").mkdir(parents=True, exist_ok=True)
    (project_root / ".mars" / "agents").mkdir(parents=True, exist_ok=True)
    (project_root / ".mars" / "skills").mkdir(parents=True, exist_ok=True)
    return calls


def test_spg_1_1_no_doctor_cache_imports_in_main() -> None:
    """SPG-1.1: CLI startup has no global doctor-scan helpers."""
    import meridian.cli.main as main_mod

    source = Path(main_mod.__file__).read_text(encoding="utf-8")
    assert "consume_doctor_cache_warning" not in source
    assert "maybe_start_background_doctor_scan" not in source
    assert "_is_doctor_scan_launch_path" not in source


def test_spg_1_2_no_doctor_cache_json_access() -> None:
    """SPG-1.2: No startup/doctor code reads or writes doctor-cache.json."""
    import meridian.cli.main as main_mod
    import meridian.lib.ops.diag as diag_mod

    for mod in (main_mod, diag_mod):
        source = Path(mod.__file__).read_text(encoding="utf-8")
        assert "doctor-cache.json" not in source
        assert "doctor_cache_path" not in source


def test_spg_1_3_doctor_cache_artifacts_deleted() -> None:
    """SPG-1.3: doctor_cache module and dedicated tests remain deleted."""
    import meridian.lib.ops as ops_pkg

    ops_dir = Path(ops_pkg.__path__[0])
    assert not (ops_dir / "doctor_cache.py").exists()
    assert not (Path("tests/unit/ops") / "test_doctor_cache.py").exists()
    assert not any(Path("tests/integration").rglob("*doctor_cache*"))


def test_spg_1_4_primary_launch_schedules_background_repairs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPG-1.4: PRIMARY_LAUNCH schedules daemon repairs without sibling traversal."""
    import threading

    from meridian.cli.main import _maybe_schedule_background_repairs
    from meridian.cli.startup.policy import StartupClass

    started: list[threading.Thread] = []
    user_home_calls: list[str] = []

    def _track_start(self: threading.Thread) -> None:
        started.append(self)

    monkeypatch.setattr(threading.Thread, "start", _track_start)
    monkeypatch.setattr("meridian.cli.main.is_nested_meridian_process", lambda: False)
    monkeypatch.setattr(
        "meridian.lib.ops.diag.get_user_home",
        lambda: user_home_calls.append("get_user_home") or Path("/tmp/home"),
    )

    _maybe_schedule_background_repairs(
        startup_class=StartupClass.PRIMARY_LAUNCH,
        project_root=Path("/tmp/project"),
        bootstrap_skipped=False,
    )

    assert len(started) == 1
    assert started[0].daemon is True
    assert "repair" in started[0].name.lower()
    assert user_home_calls == []


def test_spg_2_1_nested_chat_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    """SPG-2.1: Nested `meridian chat` rejects with exit 1."""
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")

    from meridian.cli.chat_cmd import _require_root_process

    with pytest.raises(SystemExit) as exc_info:
        _require_root_process()

    assert exc_info.value.code == 1


def test_spg_2_2_nested_chat_rejects_before_user_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPG-2.2: Nested chat rejection happens before any user-home write path is touched."""
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    calls: list[str] = []
    monkeypatch.setattr(
        "meridian.cli.chat_cmd.get_user_home",
        lambda: calls.append("get_user_home") or Path("/should-not-run"),
    )

    from meridian.cli.chat_cmd import _require_root_process

    with pytest.raises(SystemExit):
        _require_root_process()

    assert calls == []


def test_spg_2_3_unconfigured_server_runtime_raises() -> None:
    """SPG-2.3: Unconfigured chat server runtime sentinel raises on method access."""
    from meridian.lib.chat.server import _UnconfiguredRuntime

    sentinel = _UnconfiguredRuntime()
    with pytest.raises(RuntimeError, match="not configured"):
        sentinel.start()
    with pytest.raises(RuntimeError, match="not configured"):
        sentinel.list_chats()


def test_spg_3_1_lock_permission_error_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    """SPG-3.1: file_lock PermissionError becomes skipped with lock_permission_error."""
    from meridian.lib.hooks.builtin.git_autosync import GitAutosync

    def _raise_permission(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("sandbox denied")

    monkeypatch.setattr(
        "meridian.lib.hooks.builtin.git_autosync.file_lock",
        MagicMock(side_effect=_raise_permission),
    )
    monkeypatch.setattr(
        "meridian.lib.hooks.builtin.git_autosync.resolve_clone_path",
        lambda _url: Path("/tmp/clone"),
    )
    monkeypatch.setattr(
        "meridian.lib.hooks.builtin.git_autosync.get_user_home",
        lambda: Path("/tmp/home"),
    )

    result = GitAutosync().execute(_hook_context(), _hook())

    assert result.success is True
    assert result.outcome == "skipped"
    assert result.skip_reason == "lock_permission_error"


def test_spg_3_2_lock_timeout_handling_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """SPG-3.2: TimeoutError handling remains a skipped lock_timeout outcome."""
    from meridian.lib.hooks.builtin.git_autosync import GitAutosync

    def _raise_timeout(*_args: object, **_kwargs: object) -> None:
        raise TimeoutError("timed out")

    monkeypatch.setattr(
        "meridian.lib.hooks.builtin.git_autosync.file_lock",
        MagicMock(side_effect=_raise_timeout),
    )
    monkeypatch.setattr(
        "meridian.lib.hooks.builtin.git_autosync.resolve_clone_path",
        lambda _url: Path("/tmp/clone"),
    )
    monkeypatch.setattr(
        "meridian.lib.hooks.builtin.git_autosync.get_user_home",
        lambda: Path("/tmp/home"),
    )

    result = GitAutosync().execute(_hook_context(), _hook())

    assert result.success is True
    assert result.outcome == "skipped"
    assert result.skip_reason == "lock_timeout"


def test_spg_3_3_clone_permission_failure_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    """SPG-3.3: Clone-directory permission failures keep clone_failed skip behavior."""
    from meridian.lib.hooks.builtin.git_autosync import GitAutosync

    @contextmanager
    def _fake_lock(*_args: object, **_kwargs: object):
        yield

    monkeypatch.setattr("meridian.lib.hooks.builtin.git_autosync.file_lock", _fake_lock)
    monkeypatch.setattr(
        "meridian.lib.hooks.builtin.git_autosync.resolve_clone_path",
        lambda _url: Path("/tmp/clone-target"),
    )
    monkeypatch.setattr(
        "meridian.lib.hooks.builtin.git_autosync.get_user_home",
        lambda: Path("/tmp/home"),
    )

    def _run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        _ = kwargs
        argv = list(args[0])
        if argv[:2] == ["git", "clone"]:
            return subprocess.CompletedProcess(
                argv,
                1,
                stdout="",
                stderr="Permission denied",
            )
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr("meridian.lib.hooks.builtin.git_autosync.subprocess.run", _run)

    result = GitAutosync().execute(_hook_context(), _hook())

    assert result.success is True
    assert result.outcome == "skipped"
    assert result.skip_reason == "clone_failed"


def test_spg_4_1_implicit_config_probe_oserror_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """SPG-4.1: Implicit default user-config probe OSError degrades to None."""
    from meridian.lib.config.project_root import resolve_user_config_path

    config_path = tmp_path / "blocked" / "config.toml"
    monkeypatch.delenv("MERIDIAN_CONFIG", raising=False)
    monkeypatch.setattr(
        "meridian.lib.state.user_paths.get_user_home",
        lambda: config_path.parent,
    )

    original_is_file = Path.is_file

    def _raise_on_target(self: Path) -> bool:
        if self == config_path:
            raise PermissionError("sandbox")
        return original_is_file(self)

    monkeypatch.setattr(Path, "is_file", _raise_on_target)

    assert resolve_user_config_path(None) is None


def test_spg_4_2_nested_probe_failure_logs_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SPG-4.2: Nested mode + probe failure logs warning including the attempted path."""
    from meridian.lib.config.project_root import resolve_user_config_path

    config_path = tmp_path / "noaccess" / "config.toml"
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    monkeypatch.delenv("MERIDIAN_CONFIG", raising=False)
    monkeypatch.setattr(
        "meridian.lib.state.user_paths.get_user_home",
        lambda: config_path.parent,
    )

    original_is_file = Path.is_file

    def _raise_on_target(self: Path) -> bool:
        if self == config_path:
            raise PermissionError("sandbox denied")
        return original_is_file(self)

    monkeypatch.setattr(Path, "is_file", _raise_on_target)

    with caplog.at_level(logging.WARNING, logger="meridian.lib.config.project_root"):
        assert resolve_user_config_path(None) is None

    assert any(str(config_path) in record.message for record in caplog.records)


def test_spg_4_3_explicit_missing_config_raises(tmp_path: Path) -> None:
    """SPG-4.3: Explicit config path missing raises FileNotFoundError."""
    from meridian.lib.config.project_root import resolve_user_config_path

    with pytest.raises(FileNotFoundError):
        resolve_user_config_path(tmp_path / "missing.toml")


def test_spg_5_1_local_doctor_never_enumerates_sibling_projects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """SPG-5.1: doctor_sync(global_=False) never enumerates sibling project dirs."""
    from meridian.lib.ops.diag import DoctorInput, doctor_sync

    calls = _patch_diag_minimum(monkeypatch, tmp_path)
    scan_calls: list[str] = []
    monkeypatch.setattr(
        "meridian.lib.ops.diag.scan_orphan_project_dirs",
        lambda *args, **kwargs: scan_calls.append("scan_orphan_project_dirs") or [],
    )

    result = doctor_sync(DoctorInput(project_root=tmp_path.as_posix(), global_=False))

    assert result.ok is True
    assert calls == ["bootstrap"]
    assert scan_calls == []


def test_spg_5_2_nested_global_doctor_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """SPG-5.2: Nested doctor_sync(global_=True) raises RuntimeError."""
    from meridian.lib.ops.diag import DoctorInput, doctor_sync

    _patch_diag_minimum(monkeypatch, tmp_path)
    monkeypatch.setattr("meridian.lib.ops.diag.is_root_side_effect_process", lambda: False)

    with pytest.raises(RuntimeError, match="root Meridian process"):
        doctor_sync(DoctorInput(project_root=tmp_path.as_posix(), global_=True))


def test_spg_5_3_global_guard_fires_before_cross_project_enumeration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """SPG-5.3: Global guard runs after per-project prep but before cross-project scan."""
    from meridian.lib.ops.diag import DoctorInput, doctor_sync

    calls = _patch_diag_minimum(monkeypatch, tmp_path)

    def _scan_orphans(*_args: object, **_kwargs: object) -> list[object]:
        raise AssertionError("cross-project enumeration should not run")

    monkeypatch.setattr("meridian.lib.ops.diag.scan_orphan_project_dirs", _scan_orphans)
    monkeypatch.setattr("meridian.lib.ops.diag.is_root_side_effect_process", lambda: False)

    with pytest.raises(RuntimeError, match="root Meridian process"):
        doctor_sync(DoctorInput(project_root=tmp_path.as_posix(), global_=True))

    assert calls == ["bootstrap"]


def test_spg_5_4_root_global_doctor_still_runs_cross_project_scan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """SPG-5.4: Root doctor_sync(global_=True) still performs cross-project scan."""
    from meridian.lib.ops.diag import DoctorInput, doctor_sync

    _patch_diag_minimum(monkeypatch, tmp_path)
    seen: list[tuple[Path, int, float]] = []

    def _scan_orphans(home: Path, retention_days: int, now: float) -> list[object]:
        seen.append((home, retention_days, now))
        return []

    monkeypatch.setattr("meridian.lib.ops.diag.scan_orphan_project_dirs", _scan_orphans)

    result = doctor_sync(DoctorInput(project_root=tmp_path.as_posix(), global_=True))

    assert result.ok is True
    assert len(seen) == 1
    assert seen[0][0] == tmp_path / "user-home"
    assert seen[0][1] == 30
