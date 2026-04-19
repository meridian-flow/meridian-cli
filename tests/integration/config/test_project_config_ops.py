from pathlib import Path

import pytest

from meridian.lib.config.settings import load_config
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
def _isolate_config_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MERIDIAN_STATE_ROOT", raising=False)
    monkeypatch.delenv("MERIDIAN_REPO_ROOT", raising=False)
    monkeypatch.delenv("MERIDIAN_CONFIG", raising=False)
    monkeypatch.delenv("MERIDIAN_DEFAULT_HARNESS", raising=False)
    monkeypatch.delenv("MERIDIAN_DEFAULT_MODEL", raising=False)
    monkeypatch.setenv("MERIDIAN_HOME", (tmp_path / "user-home").as_posix())


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


@pytest.mark.parametrize("operation", ["set", "reset"])
def test_config_set_and_reset_require_project_config_file(
    tmp_path: Path,
    operation: str,
) -> None:
    repo_root = _repo(tmp_path)

    with pytest.raises(ValueError, match="no project config; run `meridian config init`"):
        if operation == "set":
            config_set_sync(
                ConfigSetInput(
                    repo_root=repo_root.as_posix(),
                    key="defaults.model",
                    value="gpt-5.4",
                )
            )
        else:
            config_reset_sync(
                ConfigResetInput(
                    repo_root=repo_root.as_posix(),
                    key="defaults.model",
                )
            )


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


def test_config_show_and_get_resolve_env_selected_user_config_like_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _repo(tmp_path)
    env_user_config = tmp_path / "env-user-config.toml"
    env_user_config.write_text("[defaults]\nharness = \"opencode\"\n", encoding="utf-8")
    monkeypatch.setenv("MERIDIAN_CONFIG", env_user_config.as_posix())

    shown = config_show_sync(ConfigShowInput(repo_root=repo_root.as_posix()))
    gotten = config_get_sync(ConfigGetInput(repo_root=repo_root.as_posix(), key="defaults.harness"))
    shown_value = next(item for item in shown.values if item.key == "defaults.harness")

    assert shown_value.value == "opencode"
    assert shown_value.source == "user-config"
    assert gotten.key == "defaults.harness"
    assert gotten.value == "opencode"
    assert gotten.source == "user-config"
    assert load_config(repo_root).default_harness == "opencode"
