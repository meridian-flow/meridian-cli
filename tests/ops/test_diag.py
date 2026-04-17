"""Doctor warning regressions."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from meridian.lib.catalog import models as catalog_models
from meridian.lib.ops import diag
from meridian.lib.ops import mars as mars_ops
from meridian.lib.ops.config import ConfigShowInput, config_show_sync
from meridian.lib.ops.diag import DoctorInput, doctor_sync


def _create_repo_root(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    return repo_root


def _warning_by_code(result: diag.DoctorOutput, code: str) -> diag.DoctorWarning:
    return next(warning for warning in result.warnings if warning.code == code)


def _setup_warning_shape_case(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    create_agents_dir: bool = True,
    create_skills_dir: bool = True,
) -> None:
    if create_agents_dir:
        (repo_root / ".agents" / "agents").mkdir(parents=True, exist_ok=True)
    if create_skills_dir:
        (repo_root / ".agents" / "skills").mkdir(parents=True, exist_ok=True)

    # Keep warning tests focused on one producer at a time.
    monkeypatch.setattr(diag, "_repair_stale_session_locks", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(diag, "_repair_orphan_runs", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        diag,
        "check_upgrade_availability",
        lambda *_args, **_kwargs: mars_ops.UpgradeAvailability(),
    )
    monkeypatch.setattr(
        diag.spawn_store,
        "list_spawns",
        lambda *_args, **_kwargs: [],
    )


def _apply_warning_trigger(
    trigger: str,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if trigger == "missing_skills_directories":
        _setup_warning_shape_case(
            repo_root,
            monkeypatch,
            create_agents_dir=True,
            create_skills_dir=False,
        )
        return
    if trigger == "missing_agent_profile_directories":
        _setup_warning_shape_case(
            repo_root,
            monkeypatch,
            create_agents_dir=False,
            create_skills_dir=True,
        )
        return
    if trigger == "active_spawns_present":
        _setup_warning_shape_case(repo_root, monkeypatch)
        monkeypatch.setattr(
            diag.spawn_store,
            "list_spawns",
            lambda *_args, **_kwargs: [SimpleNamespace(id="p999", status="running")],
        )
        return
    msg = f"Unknown warning trigger: {trigger}"
    raise AssertionError(msg)


@pytest.mark.parametrize(
    ("trigger", "expected_code", "expected_payload_keys"),
    [
        ("missing_skills_directories", "missing_skills_directories", ()),
        ("missing_agent_profile_directories", "missing_agent_profile_directories", ()),
        ("active_spawns_present", "active_spawns_present", ("spawn_ids",)),
    ],
)
def test_doctor_warning_shape_for_non_mars_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    trigger: str,
    expected_code: str,
    expected_payload_keys: tuple[str, ...],
) -> None:
    repo_root = _create_repo_root(tmp_path)
    _apply_warning_trigger(trigger, repo_root, monkeypatch)

    result = doctor_sync(DoctorInput(repo_root=repo_root.as_posix()))

    assert isinstance(result.warnings, tuple)
    matching = [warning for warning in result.warnings if warning.code == expected_code]
    assert len(matching) == 1, f"expected exactly one {expected_code} warning"
    warning = matching[0]
    assert warning in result.warnings
    assert warning.message.strip(), f"{expected_code} warning has empty message"
    if expected_payload_keys:
        assert warning.payload is not None
        assert set(expected_payload_keys).issubset(warning.payload.keys())
    else:
        assert warning.payload is None


def test_doctor_skips_orphan_run_repair_when_depth_is_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _create_repo_root(tmp_path)
    _setup_warning_shape_case(repo_root, monkeypatch)
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    called = False

    def _unexpected_repair(*_args, **_kwargs) -> int:
        nonlocal called
        called = True
        raise AssertionError("_repair_orphan_runs should be skipped when MERIDIAN_DEPTH > 0")

    monkeypatch.setattr(diag, "_repair_orphan_runs", _unexpected_repair)

    result = doctor_sync(DoctorInput(repo_root=repo_root.as_posix()))

    assert called is False
    assert "orphan_runs" not in result.repaired


def test_doctor_reports_no_warnings_when_conditions_are_clear(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _create_repo_root(tmp_path)
    _setup_warning_shape_case(repo_root, monkeypatch)

    result = doctor_sync(DoctorInput(repo_root=repo_root.as_posix()))

    assert result.warnings == ()
    assert result.ok is True


def test_doctor_reports_outdated_dependency_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _create_repo_root(tmp_path)
    monkeypatch.setattr(
        diag,
        "check_upgrade_availability",
        lambda *_args, **_kwargs: mars_ops.UpgradeAvailability(
            within_constraint=("meridian-dev-workflow",),
            beyond_constraint=("meridian-base",),
        ),
    )

    result = doctor_sync(DoctorInput(repo_root=repo_root.as_posix()))

    outdated = _warning_by_code(result, "outdated_dependencies")
    assert outdated.payload == {
        "within_constraint": ["meridian-dev-workflow"],
        "beyond_constraint": ["meridian-base"],
    }
    assert "1 update available within your pinned constraint: meridian-dev-workflow." in (
        outdated.message
    )
    assert "Run `meridian mars upgrade` to apply." in outdated.message
    assert "1 newer version available beyond your pinned constraint: meridian-base." in (
        outdated.message
    )
    assert "Edit mars.toml to bump the version, then run `meridian mars sync`." in (
        outdated.message
    )
    assert all(warning.code != "updates_check_failed" for warning in result.warnings)


def test_doctor_reports_update_check_failure_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _create_repo_root(tmp_path)
    monkeypatch.setattr(
        diag,
        "check_upgrade_availability",
        lambda *_args, **_kwargs: None,
    )

    result = doctor_sync(DoctorInput(repo_root=repo_root.as_posix()))

    updates_check = _warning_by_code(result, "updates_check_failed")
    assert updates_check.message == (
        "Could not check for dependency updates (`mars outdated --json` failed)."
    )
    assert updates_check.payload is None
    assert all(warning.code != "outdated_dependencies" for warning in result.warnings)


def test_doctor_surfaces_beyond_constraint_warning_from_outdated_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _create_repo_root(tmp_path)
    monkeypatch.setattr(mars_ops, "resolve_mars_executable", lambda: "/usr/bin/mars")
    real_run = subprocess.run
    outdated_payload = [
        {
            "source": "meridian-base",
            "locked": "v0.0.11",
            "constraint": "v0.0.11",
            "updateable": "v0.0.11",
            "latest": "v0.0.12",
        }
    ]

    def _fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if len(command) >= 2 and command[1] == "outdated":
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=json.dumps(outdated_payload),
                stderr="",
            )
        return real_run(command, **kwargs)

    monkeypatch.setattr(mars_ops.subprocess, "run", _fake_run)

    result = doctor_sync(DoctorInput(repo_root=repo_root.as_posix()))

    outdated = _warning_by_code(result, "outdated_dependencies")
    assert outdated.payload == {
        "within_constraint": [],
        "beyond_constraint": ["meridian-base"],
    }
    assert "1 newer version available beyond your pinned constraint: meridian-base." in (
        outdated.message
    )
    assert "Edit mars.toml to bump the version, then run `meridian mars sync`." in (
        outdated.message
    )


def test_doctor_uses_shared_config_surface_builder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _create_repo_root(tmp_path)
    _setup_warning_shape_case(repo_root, monkeypatch)
    calls: list[Path] = []
    original_builder = diag.build_config_surface

    def _tracked_builder(root: Path) -> object:
        calls.append(root)
        return original_builder(root)

    monkeypatch.setattr(diag, "build_config_surface", _tracked_builder)

    doctor_sync(DoctorInput(repo_root=repo_root.as_posix()))

    assert calls == [repo_root]


def test_doctor_warning_surface_matches_config_show_for_missing_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "missing-repo"
    shown = config_show_sync(ConfigShowInput(repo_root=repo_root.as_posix()))
    assert shown.warning is not None

    monkeypatch.setattr(diag, "_repair_stale_session_locks", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(diag, "_repair_orphan_runs", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        diag,
        "check_upgrade_availability",
        lambda *_args, **_kwargs: mars_ops.UpgradeAvailability(),
    )
    monkeypatch.setattr(
        diag.spawn_store,
        "list_spawns",
        lambda *_args, **_kwargs: [],
    )

    result = doctor_sync(DoctorInput(repo_root=repo_root.as_posix()))

    assert shown.warning in {warning.message for warning in result.warnings}


def test_doctor_text_output_prefixes_warning_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _create_repo_root(tmp_path)
    monkeypatch.setattr(
        diag,
        "check_upgrade_availability",
        lambda *_args, **_kwargs: None,
    )

    result = doctor_sync(DoctorInput(repo_root=repo_root.as_posix()))

    text = result.format_text()
    assert "warning: updates_check_failed: Could not check for dependency updates" in text


def test_doctor_surfaces_workspace_invalid_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _create_repo_root(tmp_path)
    _setup_warning_shape_case(repo_root, monkeypatch)
    (repo_root / "workspace.local.toml").write_text("[[context-roots]]\n", encoding="utf-8")

    result = doctor_sync(DoctorInput(repo_root=repo_root.as_posix()))

    warning = _warning_by_code(result, "workspace_invalid")
    assert "Invalid workspace schema" in warning.message
    assert warning.payload == {"path": (repo_root / "workspace.local.toml").resolve().as_posix()}


def test_doctor_surfaces_workspace_unknown_and_missing_root_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _create_repo_root(tmp_path)
    _setup_warning_shape_case(repo_root, monkeypatch)
    (repo_root / "workspace.local.toml").write_text(
        'future = "value"\n'
        "[[context-roots]]\n"
        'path = "./missing-root"\n'
        'note = "kept"\n',
        encoding="utf-8",
    )

    result = doctor_sync(DoctorInput(repo_root=repo_root.as_posix()))

    unknown = _warning_by_code(result, "workspace_unknown_key")
    assert unknown.payload == {"keys": ["future", "context-roots[1].note"]}
    missing = _warning_by_code(result, "workspace_missing_root")
    assert missing.payload == {
        "roots": [(repo_root / "missing-root").resolve().as_posix()],
    }


def test_doctor_surfaces_workspace_unsupported_harness_for_codex(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _create_repo_root(tmp_path)
    _setup_warning_shape_case(repo_root, monkeypatch)
    (repo_root / "shared").mkdir()
    (repo_root / "workspace.local.toml").write_text(
        "[[context-roots]]\n"
        'path = "./shared"\n',
        encoding="utf-8",
    )

    result = doctor_sync(DoctorInput(repo_root=repo_root.as_posix()))

    warning = _warning_by_code(result, "workspace_unsupported_harness")
    assert warning.payload == {
        "harness": "codex",
        "applicability": "unsupported:requires_config_generation",
    }


def test_doctor_skips_mars_model_resolution_for_config_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _create_repo_root(tmp_path)
    monkeypatch.setenv("MERIDIAN_DEFAULT_MODEL", "gpt-5.4")
    monkeypatch.setattr(diag, "_repair_stale_session_locks", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(diag, "_repair_orphan_runs", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        diag,
        "check_upgrade_availability",
        lambda *_args, **_kwargs: mars_ops.UpgradeAvailability(),
    )
    monkeypatch.setattr(
        diag.spawn_store,
        "list_spawns",
        lambda *_args, **_kwargs: [],
    )

    def _unexpected_resolve_model(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("doctor config surface should not call model resolution")

    monkeypatch.setattr(catalog_models, "resolve_model", _unexpected_resolve_model)

    result = doctor_sync(DoctorInput(repo_root=repo_root.as_posix()))

    assert result.repo_root == repo_root.as_posix()
