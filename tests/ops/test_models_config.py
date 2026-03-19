from pathlib import Path

from meridian.lib.ops.models_config import (
    ModelsConfigGetInput,
    ModelsConfigInitInput,
    ModelsConfigResetInput,
    ModelsConfigSetInput,
    models_config_get_sync,
    models_config_init_sync,
    models_config_reset_sync,
    models_config_set_sync,
)


def test_models_config_init_scaffolds_models_toml(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    result = models_config_init_sync(ModelsConfigInitInput(repo_root=repo_root.as_posix()))

    assert result.created is True
    content = (repo_root / ".meridian" / "models.toml").read_text(encoding="utf-8")
    assert "[harness_patterns]" in content
    assert "[model_visibility]" in content


def test_models_config_set_get_and_reset_roundtrip(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    models_config_init_sync(ModelsConfigInitInput(repo_root=repo_root.as_posix()))

    set_result = models_config_set_sync(
        ModelsConfigSetInput(
            repo_root=repo_root.as_posix(),
            key="harness_patterns.codex",
            value='["gpt-*", "foo-*"]',
        )
    )
    assert set_result.value == ["gpt-*", "foo-*"]

    get_result = models_config_get_sync(
        ModelsConfigGetInput(repo_root=repo_root.as_posix(), key="harness_patterns.codex")
    )
    assert get_result.found is True
    assert get_result.value == ["gpt-*", "foo-*"]

    reset_result = models_config_reset_sync(
        ModelsConfigResetInput(repo_root=repo_root.as_posix(), key="harness_patterns.codex")
    )
    assert reset_result.removed is True

    get_after_reset = models_config_get_sync(
        ModelsConfigGetInput(repo_root=repo_root.as_posix(), key="harness_patterns.codex")
    )
    assert get_after_reset.found is False


def test_models_config_set_get_models_key(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    models_config_init_sync(ModelsConfigInitInput(repo_root=repo_root.as_posix()))

    # Test models.<name> shorthand
    set_result = models_config_set_sync(
        ModelsConfigSetInput(
            repo_root=repo_root.as_posix(),
            key="models.opus",
            value='"claude-opus-4-6"',
        )
    )
    assert set_result.value == "claude-opus-4-6"

    get_result = models_config_get_sync(
        ModelsConfigGetInput(repo_root=repo_root.as_posix(), key="models.opus")
    )
    assert get_result.found is True
    assert get_result.value == "claude-opus-4-6"

    # Test models.<name>.description
    set_desc = models_config_set_sync(
        ModelsConfigSetInput(
            repo_root=repo_root.as_posix(),
            key="models.opus.description",
            value='"Strong at reasoning"',
        )
    )
    assert set_desc.value == "Strong at reasoning"

    get_desc = models_config_get_sync(
        ModelsConfigGetInput(repo_root=repo_root.as_posix(), key="models.opus.description")
    )
    assert get_desc.found is True
    assert get_desc.value == "Strong at reasoning"

    # Test models.<name>.pinned
    set_pinned = models_config_set_sync(
        ModelsConfigSetInput(
            repo_root=repo_root.as_posix(),
            key="models.opus.pinned",
            value="true",
        )
    )
    assert set_pinned.value is True
