from pathlib import Path
from types import SimpleNamespace

import pytest

from meridian.cli.main import agent_mode_enabled
from meridian.lib.ops import diag


def test_agent_mode_enabled_uses_depth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERIDIAN_DEPTH", raising=False)
    assert agent_mode_enabled() is False

    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    assert agent_mode_enabled() is True


def test_doctor_sync_uses_depth_for_spawned_agent_detection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = SimpleNamespace(
        repo_root=tmp_path,
        config=SimpleNamespace(
            search_paths=SimpleNamespace(
                agents=(),
                global_agents=(),
                skills=(),
                global_skills=(),
            )
        ),
    )

    orphan_repairs = {"count": 0}

    def fake_repair_orphan_runs(repo_root: Path) -> int:
        assert repo_root == tmp_path
        orphan_repairs["count"] += 1
        return 0

    monkeypatch.setattr(diag, "build_runtime", lambda repo_root: runtime)
    monkeypatch.setattr(diag, "_repair_stale_session_locks", lambda repo_root: 0)
    monkeypatch.setattr(diag, "_repair_orphan_runs", fake_repair_orphan_runs)
    monkeypatch.setattr(diag, "_count_runs", lambda repo_root: 0)
    monkeypatch.setattr(diag, "resolve_path_list", lambda *args: [tmp_path])

    monkeypatch.setenv("MERIDIAN_DEPTH", "0")
    diag.doctor_sync(diag.DoctorInput(repo_root=tmp_path.as_posix()))
    assert orphan_repairs["count"] == 1

    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    diag.doctor_sync(diag.DoctorInput(repo_root=tmp_path.as_posix()))
    assert orphan_repairs["count"] == 1
