"""Doctor warning regressions."""

from pathlib import Path

import pytest

from meridian.lib.catalog import models as catalog_models
from meridian.lib.ops import diag
from meridian.lib.ops import mars as mars_ops
from meridian.lib.ops.config import ConfigShowInput, config_show_sync
from meridian.lib.ops.diag import DoctorInput, doctor_sync
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_runtime_state_root_for_write


@pytest.fixture(autouse=True)
def _isolate_runtime_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MERIDIAN_STATE_ROOT", raising=False)
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    monkeypatch.setenv("MERIDIAN_HOME", (tmp_path / "user-home").as_posix())


def _create_repo_root(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    return repo_root


def _warning_by_code(result: diag.DoctorOutput, code: str) -> diag.DoctorWarning:
    return next(warning for warning in result.warnings if warning.code == code)


def _create_agent_skill_dirs(
    repo_root: Path,
    *,
    create_agents_dir: bool = True,
    create_skills_dir: bool = True,
) -> None:
    if create_agents_dir:
        (repo_root / ".agents" / "agents").mkdir(parents=True, exist_ok=True)
    if create_skills_dir:
        (repo_root / ".agents" / "skills").mkdir(parents=True, exist_ok=True)


def _seed_active_spawn(repo_root: Path) -> str:
    state_root = resolve_runtime_state_root_for_write(repo_root)
    state_root.mkdir(parents=True, exist_ok=True)
    return spawn_store.start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="running",
    )


def _run_doctor_without_upgrade_noise(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> diag.DoctorOutput:
    monkeypatch.setattr(
        diag,
        "check_upgrade_availability",
        lambda *_args, **_kwargs: mars_ops.UpgradeAvailability(),
    )
    return doctor_sync(DoctorInput(repo_root=repo_root.as_posix()))


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
    if trigger == "missing_skills_directories":
        _create_agent_skill_dirs(repo_root, create_agents_dir=True, create_skills_dir=False)
    elif trigger == "missing_agent_profile_directories":
        _create_agent_skill_dirs(repo_root, create_agents_dir=False, create_skills_dir=True)
    elif trigger == "active_spawns_present":
        _create_agent_skill_dirs(repo_root)
        _seed_active_spawn(repo_root)
    else:  # pragma: no cover - defensive
        raise AssertionError(f"Unknown warning trigger: {trigger}")

    result = _run_doctor_without_upgrade_noise(repo_root, monkeypatch)

    assert isinstance(result.warnings, tuple)
    matching = [warning for warning in result.warnings if warning.code == expected_code]
    assert len(matching) == 1, f"expected exactly one {expected_code} warning"
    warning = matching[0]
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
    _create_agent_skill_dirs(repo_root)
    _seed_active_spawn(repo_root)
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    monkeypatch.setattr(
        diag,
        "check_upgrade_availability",
        lambda *_args, **_kwargs: mars_ops.UpgradeAvailability(),
    )

    result = doctor_sync(DoctorInput(repo_root=repo_root.as_posix()))

    assert "orphan_runs" not in result.repaired


def test_doctor_reports_no_warnings_when_conditions_are_clear(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _create_repo_root(tmp_path)
    _create_agent_skill_dirs(repo_root)

    result = _run_doctor_without_upgrade_noise(repo_root, monkeypatch)

    assert result.warnings == ()
    assert result.ok is True


def test_doctor_reports_outdated_dependency_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _create_repo_root(tmp_path)
    _create_agent_skill_dirs(repo_root)
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
    _create_agent_skill_dirs(repo_root)
    monkeypatch.setattr(diag, "check_upgrade_availability", lambda *_args, **_kwargs: None)

    result = doctor_sync(DoctorInput(repo_root=repo_root.as_posix()))

    updates_check = _warning_by_code(result, "updates_check_failed")
    assert updates_check.message == (
        "Could not check for dependency updates (`mars outdated --json` failed)."
    )
    assert updates_check.payload is None
    assert all(warning.code != "outdated_dependencies" for warning in result.warnings)


def test_doctor_warning_surface_matches_config_show_for_missing_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "missing-repo"
    shown = config_show_sync(ConfigShowInput(repo_root=repo_root.as_posix()))
    assert shown.warning is not None
    monkeypatch.setattr(
        diag,
        "check_upgrade_availability",
        lambda *_args, **_kwargs: mars_ops.UpgradeAvailability(),
    )

    result = doctor_sync(DoctorInput(repo_root=repo_root.as_posix()))

    assert shown.warning in {warning.message for warning in result.warnings}


def test_doctor_text_output_prefixes_warning_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _create_repo_root(tmp_path)
    _create_agent_skill_dirs(repo_root)
    monkeypatch.setattr(diag, "check_upgrade_availability", lambda *_args, **_kwargs: None)

    result = doctor_sync(DoctorInput(repo_root=repo_root.as_posix()))

    text = result.format_text()
    assert "warning: updates_check_failed: Could not check for dependency updates" in text


def test_doctor_surfaces_workspace_invalid_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _create_repo_root(tmp_path)
    _create_agent_skill_dirs(repo_root)
    (repo_root / "workspace.local.toml").write_text("[[context-roots]]\n", encoding="utf-8")

    result = _run_doctor_without_upgrade_noise(repo_root, monkeypatch)

    warning = _warning_by_code(result, "workspace_invalid")
    assert "Invalid workspace schema" in warning.message
    assert warning.payload == {"path": (repo_root / "workspace.local.toml").resolve().as_posix()}


def test_doctor_surfaces_workspace_unknown_and_missing_root_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _create_repo_root(tmp_path)
    _create_agent_skill_dirs(repo_root)
    (repo_root / "workspace.local.toml").write_text(
        'future = "value"\n'
        "[[context-roots]]\n"
        'path = "./missing-root"\n'
        'note = "kept"\n',
        encoding="utf-8",
    )

    result = _run_doctor_without_upgrade_noise(repo_root, monkeypatch)

    unknown = _warning_by_code(result, "workspace_unknown_key")
    assert unknown.payload == {"keys": ["future", "context-roots[1].note"]}
    missing = _warning_by_code(result, "workspace_missing_root")
    assert missing.payload == {
        "roots": [(repo_root / "missing-root").resolve().as_posix()],
    }


# test_doctor_surfaces_workspace_unsupported_harness_for_codex was removed
# because Codex now supports --add-dir for workspace projection.


def test_doctor_skips_model_resolution_for_config_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _create_repo_root(tmp_path)
    _create_agent_skill_dirs(repo_root)
    monkeypatch.setenv("MERIDIAN_DEFAULT_MODEL", "gpt-5.4")
    monkeypatch.setattr(
        diag,
        "check_upgrade_availability",
        lambda *_args, **_kwargs: mars_ops.UpgradeAvailability(),
    )

    def _unexpected_resolve_model(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("doctor config surface should not call model resolution")

    monkeypatch.setattr(catalog_models, "resolve_model", _unexpected_resolve_model)

    result = doctor_sync(DoctorInput(repo_root=repo_root.as_posix()))

    assert result.repo_root == repo_root.as_posix()
