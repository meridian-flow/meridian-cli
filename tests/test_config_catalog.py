from __future__ import annotations

from pathlib import Path

import pytest

from meridian.lib.config.catalog import (
    load_builtin_aliases,
    load_merged_aliases,
    load_user_aliases,
    resolve_model,
)


def _write_user_aliases(repo_root: Path, payload: str) -> None:
    models_path = repo_root / ".meridian" / "models.toml"
    models_path.parent.mkdir(parents=True, exist_ok=True)
    models_path.write_text(payload, encoding="utf-8")


def test_load_builtin_aliases_from_resource() -> None:
    entries = load_builtin_aliases()
    by_alias = {entry.alias: entry for entry in entries}

    assert str(by_alias["opus"].model_id) == "claude-opus-4-6"
    assert by_alias["opus"].role == "Default / all-rounder"
    assert by_alias["codex"].harness == "codex"


def test_load_user_aliases_ignores_legacy_models_section(tmp_path: Path) -> None:
    _write_user_aliases(
        tmp_path,
        """
[aliases]
custom = "claude-sonnet-4-6"

[models.custom]
id = "gpt-5.3-codex"
""".strip(),
    )

    entries = load_user_aliases(repo_root=tmp_path)

    assert [(entry.alias, str(entry.model_id)) for entry in entries] == [
        ("custom", "claude-sonnet-4-6"),
    ]


def test_load_merged_aliases_user_wins_on_collision(tmp_path: Path) -> None:
    _write_user_aliases(
        tmp_path,
        """
[aliases]
opus = "claude-sonnet-4-6"
""".strip(),
    )

    entries = load_merged_aliases(repo_root=tmp_path)
    by_alias = {entry.alias: entry for entry in entries}

    assert str(by_alias["opus"].model_id) == "claude-sonnet-4-6"
    assert by_alias["opus"].role == ""


def test_resolve_model_alias_and_direct_passthrough(tmp_path: Path) -> None:
    _write_user_aliases(
        tmp_path,
        """
[aliases]
fast = "gpt-5.3-codex"
""".strip(),
    )

    aliased = resolve_model("fast", repo_root=tmp_path)
    direct = resolve_model("gpt-5.3-codex", repo_root=tmp_path)

    assert aliased.alias == "fast"
    assert str(aliased.model_id) == "gpt-5.3-codex"
    assert direct.alias == ""
    assert str(direct.model_id) == "gpt-5.3-codex"
    assert direct.harness == "codex"


def test_resolve_model_unknown_family_raises_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _ = resolve_model("unknown-model-x", repo_root=tmp_path)
