from __future__ import annotations

from pathlib import Path

import pytest

from meridian.lib.catalog.models import (
    load_builtin_aliases,
    load_merged_aliases,
    load_user_aliases,
    resolve_alias,
    resolve_model,
)


def _write_user_aliases(repo_root: Path, payload: str) -> None:
    models_path = repo_root / ".meridian" / "models.toml"
    models_path.parent.mkdir(parents=True, exist_ok=True)
    models_path.write_text(payload, encoding="utf-8")


def test_load_builtin_aliases_exposes_expected_harnesses() -> None:
    entries = load_builtin_aliases()
    by_alias = {entry.alias: entry for entry in entries}

    assert str(by_alias["opus"].model_id) == "claude-opus-4-6"
    assert str(by_alias["gpt"].model_id) == "gpt-5.4"
    assert by_alias["codex"].harness == "codex"


def test_load_merged_aliases_prefers_user_entries_on_collision(tmp_path: Path) -> None:
    _write_user_aliases(
        tmp_path,
        "[aliases]\n"
        "opus = 'claude-sonnet-4-6'\n",
    )

    entries = load_merged_aliases(repo_root=tmp_path)
    by_alias = {entry.alias: entry for entry in entries}

    assert str(by_alias["opus"].model_id) == "claude-sonnet-4-6"


def test_resolve_model_supports_aliases_and_direct_model_ids(tmp_path: Path) -> None:
    _write_user_aliases(
        tmp_path,
        "[aliases]\n"
        "fast = 'gpt-5.3-codex'\n",
    )

    aliased = resolve_model("fast", repo_root=tmp_path)
    direct = resolve_model("gpt-5.3-codex", repo_root=tmp_path)

    assert aliased.alias == "fast"
    assert str(aliased.model_id) == "gpt-5.3-codex"
    assert direct.alias == ""
    assert str(direct.model_id) == "gpt-5.3-codex"
    assert direct.harness == "codex"


def test_resolve_alias_and_unknown_model_behavior(tmp_path: Path) -> None:
    _write_user_aliases(
        tmp_path,
        "[aliases]\n"
        "fast = 'gpt-5.3-codex'\n",
    )

    assert str(resolve_alias("fast", repo_root=tmp_path)) == "gpt-5.3-codex"
    assert resolve_alias("missing", repo_root=tmp_path) is None
    with pytest.raises(ValueError):
        resolve_model("unknown-model-x", repo_root=tmp_path)


def test_load_user_aliases_supports_alias_table_shape(tmp_path: Path) -> None:
    _write_user_aliases(
        tmp_path,
        "[aliases.fast]\n"
        "model_id = 'gpt-5.3-codex'\n"
        "role = 'Primary'\n"
        "strengths = 'Reliable coding'\n",
    )

    entries = load_user_aliases(repo_root=tmp_path)

    assert len(entries) == 1
    assert entries[0].alias == "fast"
    assert str(entries[0].model_id) == "gpt-5.3-codex"
    assert entries[0].role == "Primary"
    assert entries[0].strengths == "Reliable coding"
