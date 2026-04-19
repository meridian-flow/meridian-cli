from pathlib import Path

import pytest

from meridian.lib.catalog import models as catalog_models
from meridian.lib.core.util import to_jsonable
from meridian.lib.ops.config import (
    ConfigGetInput,
    ConfigShowInput,
    config_get_sync,
    config_show_sync,
)


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


@pytest.mark.parametrize(
    ("source", "expected_source"),
    [
        ("env", "env var"),
        ("project", "file"),
        ("user", "user-config"),
    ],
)
def test_config_inspection_skips_model_resolution_for_defaults_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    expected_source: str,
) -> None:
    repo_root = _repo(tmp_path)
    model = "gpt-5.4"
    monkeypatch.delenv("MERIDIAN_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("MERIDIAN_CONFIG", raising=False)

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
