from pathlib import Path

import pytest

from meridian.lib.catalog import models as catalog_models
from meridian.lib.config import settings as settings_mod
from meridian.lib.config.settings import load_config
from meridian.lib.core.util import to_jsonable
from meridian.lib.ops import config as config_ops
from meridian.lib.ops.config import (
    ConfigGetInput,
    ConfigInitInput,
    ConfigResetInput,
    ConfigSetInput,
    ConfigShowInput,
    config_get_sync,
    config_init_sync,
    config_reset_sync,
    config_set_sync,
    config_show_sync,
    ensure_runtime_state_bootstrap_sync,
)
from meridian.lib.state.paths import resolve_runtime_state_root


@pytest.fixture(autouse=True)
def _clear_state_root_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERIDIAN_STATE_ROOT", raising=False)


def _repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    return repo_root


def test_config_init_creates_meridian_toml_and_is_idempotent(
    tmp_path: Path,
) -> None:
    repo_root = _repo(tmp_path)
    config_path = repo_root / "meridian.toml"

    first = config_init_sync(ConfigInitInput(repo_root=repo_root.as_posix()))
    config_path.write_text("[defaults]\nharness = \"claude\"\n", encoding="utf-8")
    second = config_init_sync(ConfigInitInput(repo_root=repo_root.as_posix()))

    assert first.created is True
    assert second.created is False
    assert first.path == config_path.as_posix()
    assert second.path == config_path.as_posix()
    assert config_path.is_file()
    assert config_path.read_text(encoding="utf-8") == "[defaults]\nharness = \"claude\"\n"
    assert not (repo_root / "mars.toml").exists()
    assert not (repo_root / ".mars").exists()


def test_runtime_bootstrap_does_not_create_meridian_toml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _repo(tmp_path)
    user_state_root = tmp_path / "user-state"
    monkeypatch.setenv("MERIDIAN_HOME", user_state_root.as_posix())

    ensure_runtime_state_bootstrap_sync(repo_root)
    runtime_root = resolve_runtime_state_root(repo_root)

    assert (repo_root / ".meridian").is_dir()
    assert (repo_root / ".meridian" / ".gitignore").is_file()
    assert not (repo_root / ".meridian" / "artifacts").exists()
    assert not (repo_root / ".meridian" / "cache").exists()
    assert not (repo_root / ".meridian" / "spawns").exists()
    project_uuid = (repo_root / ".meridian" / "id").read_text(encoding="utf-8").strip()
    assert runtime_root == user_state_root / "projects" / project_uuid
    assert runtime_root.is_dir()
    assert (runtime_root / "spawns").is_dir()
    assert not (repo_root / "meridian.toml").exists()
    assert not (repo_root / ".mars").exists()
    assert not (repo_root / "mars.toml").exists()


def test_config_init_uses_env_repo_root_when_path_not_provided(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_repo_root = _repo(tmp_path)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.setenv("MERIDIAN_REPO_ROOT", env_repo_root.as_posix())
    monkeypatch.chdir(cwd)

    result = config_init_sync(ConfigInitInput())

    assert result.path == (env_repo_root / "meridian.toml").as_posix()
    assert (env_repo_root / "meridian.toml").is_file()
    assert not (cwd / "meridian.toml").exists()
    assert not (env_repo_root / "mars.toml").exists()


def test_config_set_requires_project_config_file(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)

    with pytest.raises(ValueError, match="no project config; run `meridian config init`"):
        config_set_sync(
            ConfigSetInput(
                repo_root=repo_root.as_posix(),
                key="defaults.model",
                value="gpt-5.4",
            )
        )


def test_config_reset_requires_project_config_file(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)

    with pytest.raises(ValueError, match="no project config; run `meridian config init`"):
        config_reset_sync(
            ConfigResetInput(
                repo_root=repo_root.as_posix(),
                key="defaults.model",
            )
        )


def test_config_show_reports_meridian_toml_path_when_absent(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)

    result = config_show_sync(ConfigShowInput(repo_root=repo_root.as_posix()))

    assert result.path == (repo_root / "meridian.toml").as_posix()


def test_config_show_reports_workspace_summary_when_workspace_is_absent(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)

    result = config_show_sync(ConfigShowInput(repo_root=repo_root.as_posix()))

    assert result.workspace.status == "none"
    assert result.workspace.path is None
    assert result.workspace.roots.count == 0
    assert result.workspace.roots.enabled == 0
    assert result.workspace.roots.missing == 0
    assert result.workspace.applicability == {
        "claude": "ignored:no_roots",
        "codex": "ignored:no_roots",
        "opencode": "ignored:no_roots",
    }
    assert result.workspace_findings == ()
    text = result.format_text()
    assert "workspace.status = none" in text
    assert "workspace.roots.count = 0" in text
    assert "workspace.applicability.claude = ignored:no_roots" in text
    assert "workspace.applicability.codex = ignored:no_roots" in text
    assert "workspace.applicability.opencode = ignored:no_roots" in text


def test_config_show_surfaces_workspace_findings(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)
    (repo_root / "workspace.local.toml").write_text(
        'future = "value"\n'
        "[[context-roots]]\n"
        'path = "./missing-root"\n'
        'extra = "yes"\n',
        encoding="utf-8",
    )

    result = config_show_sync(ConfigShowInput(repo_root=repo_root.as_posix()))

    assert result.workspace.status == "present"
    assert result.workspace.path == (repo_root / "workspace.local.toml").resolve().as_posix()
    assert result.workspace.roots.count == 1
    assert result.workspace.roots.enabled == 1
    assert result.workspace.roots.missing == 1
    finding_codes = {finding.code for finding in result.workspace_findings}
    assert finding_codes == {"workspace_unknown_key", "workspace_missing_root"}
    text = result.format_text()
    assert "warning: workspace_unknown_key:" in text
    assert "warning: workspace_missing_root:" in text


def test_config_show_json_workspace_omits_null_path_and_findings(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)

    result = config_show_sync(ConfigShowInput(repo_root=repo_root.as_posix()))
    payload = to_jsonable(result)

    assert "workspace_findings" not in payload
    workspace = payload["workspace"]
    assert "path" not in workspace
    assert workspace["status"] == "none"
    assert workspace["roots"] == {"count": 0, "enabled": 0, "missing": 0}
    assert workspace["applicability"] == {
        "claude": "ignored:no_roots",
        "codex": "ignored:no_roots",
        "opencode": "ignored:no_roots",
    }


def test_config_show_json_workspace_includes_path_when_present(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)
    workspace_path = repo_root / "workspace.local.toml"
    workspace_path.write_text(
        "[[context-roots]]\n"
        'path = "./missing-root"\n',
        encoding="utf-8",
    )

    result = config_show_sync(ConfigShowInput(repo_root=repo_root.as_posix()))
    payload = to_jsonable(result)

    workspace = payload["workspace"]
    assert workspace["path"] == workspace_path.resolve().as_posix()
    assert workspace["roots"] == {"count": 1, "enabled": 1, "missing": 1}
    assert workspace["applicability"] == {
        "claude": "ignored:no_roots",
        "codex": "ignored:no_roots",
        "opencode": "ignored:no_roots",
    }


def test_config_show_marks_codex_workspace_projection_as_unsupported_when_roots_exist(
    tmp_path: Path,
) -> None:
    repo_root = _repo(tmp_path)
    shared = repo_root / "shared"
    shared.mkdir()
    (repo_root / "workspace.local.toml").write_text(
        "[[context-roots]]\n"
        'path = "./shared"\n',
        encoding="utf-8",
    )

    result = config_show_sync(ConfigShowInput(repo_root=repo_root.as_posix()))

    assert result.workspace.applicability == {
        "claude": "active",
        "codex": "unsupported:requires_config_generation",
        "opencode": "active",
    }
    assert "workspace.applicability.codex = unsupported:requires_config_generation" in (
        result.format_text()
    )


def test_config_show_and_loader_share_project_config_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _repo(tmp_path)
    project_config = repo_root / "meridian.toml"
    project_config.write_text("[defaults]\nharness = \"claude\"\n", encoding="utf-8")
    user_config = tmp_path / "user-config.toml"
    user_config.write_text("[defaults]\nharness = \"opencode\"\n", encoding="utf-8")
    monkeypatch.setenv("MERIDIAN_CONFIG", user_config.as_posix())

    project_only = config_show_sync(ConfigShowInput(repo_root=repo_root.as_posix()))
    project_only_value = next(
        item for item in project_only.values if item.key == "defaults.harness"
    )

    assert project_only.path == project_config.as_posix()
    assert project_only_value.value == "claude"
    assert project_only_value.source == "file"
    assert load_config(repo_root).default_harness == "claude"

    monkeypatch.setenv("MERIDIAN_DEFAULT_HARNESS", "codex")

    resolved = config_show_sync(ConfigShowInput(repo_root=repo_root.as_posix()))
    resolved_value = next(item for item in resolved.values if item.key == "defaults.harness")

    assert resolved.path == project_config.as_posix()
    assert resolved_value.value == "codex"
    assert resolved_value.source == "env var"
    assert resolved_value.env_var == "MERIDIAN_DEFAULT_HARNESS"
    assert load_config(repo_root).default_harness == "codex"


def test_config_show_and_get_share_default_user_config_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _repo(tmp_path)
    user_config = tmp_path / "default-user-config.toml"
    user_config.write_text("[defaults]\nharness = \"opencode\"\n", encoding="utf-8")
    monkeypatch.delenv("MERIDIAN_CONFIG", raising=False)
    monkeypatch.setattr(settings_mod, "_DEFAULT_USER_CONFIG", user_config)

    shown = config_show_sync(ConfigShowInput(repo_root=repo_root.as_posix()))
    shown_value = next(item for item in shown.values if item.key == "defaults.harness")
    gotten = config_get_sync(ConfigGetInput(repo_root=repo_root.as_posix(), key="defaults.harness"))

    assert shown_value.value == "opencode"
    assert shown_value.source == "user-config"
    assert gotten.value == "opencode"
    assert gotten.source == "user-config"
    assert load_config(repo_root).default_harness == "opencode"


@pytest.mark.parametrize(
    ("runner", "expected_key"),
    [
        (
            lambda repo_root: config_show_sync(ConfigShowInput(repo_root=repo_root.as_posix())),
            None,
        ),
        (
            lambda repo_root: config_get_sync(
                ConfigGetInput(repo_root=repo_root.as_posix(), key="defaults.harness")
            ),
            "defaults.harness",
        ),
    ],
)
def test_config_show_and_get_resolve_env_selected_user_config_like_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: object,
    expected_key: str | None,
) -> None:
    repo_root = _repo(tmp_path)
    env_user_config = tmp_path / "env-user-config.toml"
    env_user_config.write_text("[defaults]\nharness = \"opencode\"\n", encoding="utf-8")
    monkeypatch.setenv("MERIDIAN_CONFIG", env_user_config.as_posix())

    result = runner(repo_root)

    if expected_key is None:
        value = next(item for item in result.values if item.key == "defaults.harness")
        assert value.value == "opencode"
        assert value.source == "user-config"
    else:
        assert result.key == expected_key
        assert result.value == "opencode"
        assert result.source == "user-config"

    assert load_config(repo_root).default_harness == "opencode"


def test_config_show_uses_shared_config_surface_builder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _repo(tmp_path)
    calls: list[Path] = []
    original_builder = config_ops.build_config_surface

    def _tracked_builder(root: Path) -> object:
        calls.append(root)
        return original_builder(root)

    monkeypatch.setattr(config_ops, "build_config_surface", _tracked_builder)

    config_show_sync(ConfigShowInput(repo_root=repo_root.as_posix()))

    assert calls == [repo_root]


def test_config_get_uses_shared_config_surface_builder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _repo(tmp_path)
    calls: list[Path] = []
    original_builder = config_ops.build_config_surface

    def _tracked_builder(root: Path) -> object:
        calls.append(root)
        return original_builder(root)

    monkeypatch.setattr(config_ops, "build_config_surface", _tracked_builder)

    config_get_sync(ConfigGetInput(repo_root=repo_root.as_posix(), key="defaults.harness"))

    assert calls == [repo_root]


@pytest.mark.parametrize(
    ("source", "expected_source"),
    [
        ("env", "env var"),
        ("project", "file"),
        ("user", "user-config"),
    ],
)
def test_config_inspection_skips_mars_model_resolution_for_defaults_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    expected_source: str,
) -> None:
    repo_root = _repo(tmp_path)
    model = "gpt-5.4"
    monkeypatch.delenv("MERIDIAN_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("MERIDIAN_CONFIG", raising=False)
    monkeypatch.setattr(settings_mod, "_DEFAULT_USER_CONFIG", tmp_path / "missing-default.toml")

    if source == "env":
        monkeypatch.setenv("MERIDIAN_DEFAULT_MODEL", model)
    elif source == "project":
        (repo_root / "meridian.toml").write_text(
            f"[defaults]\nmodel = \"{model}\"\n",
            encoding="utf-8",
        )
    else:
        user_config = tmp_path / "user-config.toml"
        user_config.write_text(
            f"[defaults]\nmodel = \"{model}\"\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("MERIDIAN_CONFIG", user_config.as_posix())

    def _unexpected_resolve_model(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("config inspection should not call model resolution")

    monkeypatch.setattr(catalog_models, "resolve_model", _unexpected_resolve_model)

    shown = config_show_sync(ConfigShowInput(repo_root=repo_root.as_posix()))
    shown_value = next(item for item in shown.values if item.key == "defaults.model")
    gotten = config_get_sync(ConfigGetInput(repo_root=repo_root.as_posix(), key="defaults.model"))

    assert shown_value.value == model
    assert shown_value.source == expected_source
    assert gotten.value == model
    assert gotten.source == expected_source
    if expected_source == "env var":
        assert shown_value.env_var == "MERIDIAN_DEFAULT_MODEL"
        assert gotten.env_var == "MERIDIAN_DEFAULT_MODEL"
    else:
        assert shown_value.env_var is None
        assert gotten.env_var is None
