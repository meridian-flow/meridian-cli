"""Model discovery and selection operations."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, cast

import pytest

from meridian.lib.config.aliases import AliasEntry
from meridian.lib.config.discovery import DiscoveredModel
from meridian.lib.ops import _spawn_prepare
from meridian.lib.ops import models as models_ops
from meridian.lib.types import HarnessId, ModelId


class _ModelValidationContextBuilder(Protocol):
    def __call__(self, requested_model: str, *, repo_root: Path | None) -> str: ...


def _discovered(
    *,
    model_id: str,
    name: str,
    provider: str,
    harness: str,
    release_date: str | None = None,
    cost_input: float | None = 1.0,
) -> DiscoveredModel:
    return DiscoveredModel(
        id=model_id,
        name=name,
        family=model_id.split("-", maxsplit=1)[0],
        provider=provider,
        harness=HarnessId(harness),
        cost_input=cost_input,
        cost_output=2.0,
        context_limit=128000,
        output_limit=64000,
        capabilities=("tool_call",),
        release_date=release_date,
    )


def test_models_list_sync_merges_discovered_and_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _aliases(repo_root: Path | None = None) -> list[AliasEntry]:
        _ = repo_root
        return [
            AliasEntry(alias="codex", model_id=ModelId("gpt-5.3-codex")),
            AliasEntry(alias="fast", model_id=ModelId("gpt-5.3-codex")),
            AliasEntry(alias="legacy", model_id=ModelId("claude-sonnet-4-6")),
        ]

    def _discovered_models() -> list[DiscoveredModel]:
        return [
            _discovered(
                model_id="gpt-5.3-codex",
                name="GPT-5.3 Codex",
                provider="openai",
                harness="codex",
            ),
            _discovered(
                model_id="gemini-3.1-pro",
                name="Gemini 3.1 Pro",
                provider="google",
                harness="opencode",
            ),
        ]

    monkeypatch.setattr(models_ops, "load_merged_aliases", _aliases)
    monkeypatch.setattr(models_ops, "load_discovered_models", _discovered_models)

    output = models_ops.models_list_sync(models_ops.ModelsListInput())
    by_id = {str(entry.model_id): entry for entry in output.models}

    assert set(by_id) == {"claude-sonnet-4-6", "gemini-3.1-pro", "gpt-5.3-codex"}
    assert tuple(alias.alias for alias in by_id["gpt-5.3-codex"].aliases) == ("codex", "fast")
    assert by_id["gemini-3.1-pro"].provider == "google"
    assert by_id["claude-sonnet-4-6"].provider is None


def test_models_list_default_filters_unusable_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(models_ops, "load_merged_aliases", lambda repo_root=None: [])
    monkeypatch.setattr(
        models_ops,
        "load_discovered_models",
        lambda: [
            _discovered(
                model_id="gpt-4",
                name="GPT-4",
                provider="openai",
                harness="codex",
                release_date="2023-11-06",
            ),
            _discovered(
                model_id="o3",
                name="o3",
                provider="openai",
                harness="codex",
                release_date="2025-04-16",
            ),
            _discovered(
                model_id="gemini-1.5-flash",
                name="Gemini 1.5 Flash",
                provider="google",
                harness="opencode",
                release_date="2024-05-14",
            ),
            _discovered(
                model_id="claude-3-haiku",
                name="Claude 3 Haiku",
                provider="anthropic",
                harness="claude",
                release_date="2024-03-13",
            ),
            _discovered(
                model_id="gpt-5.3-codex",
                name="GPT-5.3 Codex",
                provider="openai",
                harness="codex",
                release_date="2026-02-05",
            ),
        ],
    )

    output = models_ops.models_list_sync(models_ops.ModelsListInput())

    assert [str(model.model_id) for model in output.models] == ["gpt-5.3-codex"]


def test_models_list_default_keeps_aliased_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        models_ops,
        "load_merged_aliases",
        lambda repo_root=None: [
            AliasEntry(alias="legacy", model_id=ModelId("gpt-4o")),
        ],
    )
    monkeypatch.setattr(
        models_ops,
        "load_discovered_models",
        lambda: [
            _discovered(
                model_id="gpt-4o",
                name="GPT-4o",
                provider="openai",
                harness="codex",
                release_date="2024-05-13",
            ),
            _discovered(
                model_id="gpt-4",
                name="GPT-4",
                provider="openai",
                harness="codex",
                release_date="2023-11-06",
            ),
        ],
    )

    output = models_ops.models_list_sync(models_ops.ModelsListInput())

    assert [str(model.model_id) for model in output.models] == ["gpt-4o"]
    assert tuple(alias.alias for alias in output.models[0].aliases) == ("legacy",)


def test_models_list_all_shows_everything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(models_ops, "load_merged_aliases", lambda repo_root=None: [])
    monkeypatch.setattr(
        models_ops,
        "load_discovered_models",
        lambda: [
            _discovered(
                model_id="gpt-4",
                name="GPT-4",
                provider="openai",
                harness="codex",
            ),
            _discovered(
                model_id="o3",
                name="o3",
                provider="openai",
                harness="codex",
            ),
            _discovered(
                model_id="gpt-5.3-codex",
                name="GPT-5.3 Codex",
                provider="openai",
                harness="codex",
            ),
        ],
    )

    output = models_ops.models_list_sync(models_ops.ModelsListInput(all=True))

    assert [str(model.model_id) for model in output.models] == [
        "gpt-4",
        "gpt-5.3-codex",
        "o3",
    ]


def test_models_list_filters_latest_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(models_ops, "load_merged_aliases", lambda repo_root=None: [])
    monkeypatch.setattr(
        models_ops,
        "load_discovered_models",
        lambda: [
            _discovered(
                model_id="claude-sonnet-4-6-latest",
                name="Claude Sonnet 4.6 Latest",
                provider="anthropic",
                harness="claude",
                release_date="2026-02-17",
            ),
            _discovered(
                model_id="gpt-5.3-codex",
                name="GPT-5.3 Codex",
                provider="openai",
                harness="codex",
                release_date="2026-02-05",
            ),
        ],
    )

    output = models_ops.models_list_sync(models_ops.ModelsListInput())

    assert [str(model.model_id) for model in output.models] == ["gpt-5.3-codex"]


def test_models_list_filters_date_stamped_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(models_ops, "load_merged_aliases", lambda repo_root=None: [])
    monkeypatch.setattr(
        models_ops,
        "load_discovered_models",
        lambda: [
            _discovered(
                model_id="claude-opus-4-5",
                name="Claude Opus 4.5",
                provider="anthropic",
                harness="claude",
            ),
            _discovered(
                model_id="claude-opus-4-5-20251101",
                name="Claude Opus 4.5 (20251101)",
                provider="anthropic",
                harness="claude",
            ),
        ],
    )

    output = models_ops.models_list_sync(models_ops.ModelsListInput())

    assert [str(model.model_id) for model in output.models] == ["claude-opus-4-5"]


def test_models_list_includes_cost_tiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(models_ops, "load_merged_aliases", lambda repo_root=None: [])
    monkeypatch.setattr(
        models_ops,
        "load_discovered_models",
        lambda: [
            _discovered(
                model_id="cheap-model",
                name="Cheap",
                provider="openai",
                harness="codex",
                cost_input=0.5,
            ),
            _discovered(
                model_id="mid-model",
                name="Mid",
                provider="openai",
                harness="codex",
                cost_input=2.0,
            ),
            _discovered(
                model_id="expensive-model",
                name="Expensive",
                provider="openai",
                harness="codex",
                cost_input=15.0,
            ),
            _discovered(
                model_id="unknown-cost",
                name="Unknown",
                provider="openai",
                harness="codex",
                cost_input=None,
            ),
        ],
    )

    output = models_ops.models_list_sync(models_ops.ModelsListInput(all=True))
    by_id = {str(m.model_id): m for m in output.models}

    assert by_id["cheap-model"].cost_tier == "$"
    assert by_id["mid-model"].cost_tier == "$$"
    assert by_id["expensive-model"].cost_tier == "$$$"
    assert by_id["unknown-cost"].cost_tier is None


def test_models_show_sync_includes_discovery_and_alias_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _aliases(repo_root: Path | None = None) -> list[AliasEntry]:
        _ = repo_root
        return [
            AliasEntry(alias="fast", model_id=ModelId("gpt-5.3-codex"), role="Primary"),
            AliasEntry(alias="codex", model_id=ModelId("gpt-5.3-codex")),
        ]

    def _discovered_models() -> list[DiscoveredModel]:
        return [
            _discovered(
                model_id="gpt-5.3-codex",
                name="GPT-5.3 Codex",
                provider="openai",
                harness="codex",
            ),
        ]

    monkeypatch.setattr(models_ops, "load_merged_aliases", _aliases)
    monkeypatch.setattr(models_ops, "load_discovered_models", _discovered_models)

    entry = models_ops.models_show_sync(models_ops.ModelsShowInput(model="fast"))

    assert str(entry.model_id) == "gpt-5.3-codex"
    assert entry.provider == "openai"
    assert tuple(alias.alias for alias in entry.aliases) == ("codex", "fast")
    assert entry.aliases[1].role == "Primary"


def test_models_show_sync_falls_back_to_resolve_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _no_aliases(repo_root: Path | None = None) -> list[AliasEntry]:
        _ = repo_root
        return []

    def _no_discovered() -> list[DiscoveredModel]:
        return []

    def _resolve(model: str, repo_root: Path | None = None) -> AliasEntry:
        _ = repo_root
        return AliasEntry(alias="", model_id=ModelId(model))

    monkeypatch.setattr(models_ops, "load_merged_aliases", _no_aliases)
    monkeypatch.setattr(models_ops, "load_discovered_models", _no_discovered)
    monkeypatch.setattr(models_ops, "resolve_model", _resolve)

    entry = models_ops.models_show_sync(models_ops.ModelsShowInput(model="o3-mini"))

    assert str(entry.model_id) == "o3-mini"
    assert entry.harness == "codex"
    assert entry.aliases == ()


def test_models_refresh_sync_returns_refreshed_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _refresh() -> list[DiscoveredModel]:
        return [
            _discovered(
                model_id="claude-sonnet-4-6",
                name="Claude Sonnet 4.6",
                provider="anthropic",
                harness="claude",
            ),
            _discovered(
                model_id="gpt-5.3-codex",
                name="GPT-5.3 Codex",
                provider="openai",
                harness="codex",
            ),
        ]

    monkeypatch.setattr(models_ops, "refresh_models_cache", _refresh)

    output = models_ops.models_refresh_sync(models_ops.ModelsRefreshInput())
    assert output.refreshed == 2


def test_model_validation_context_includes_discovered_suggestions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _aliases(repo_root: Path | None = None) -> list[AliasEntry]:
        _ = repo_root
        return [
            AliasEntry(alias="codex", model_id=ModelId("gpt-5.3-codex")),
        ]

    def _discovered_models() -> list[DiscoveredModel]:
        return [
            _discovered(
                model_id="gpt-5.3-codex",
                name="GPT-5.3 Codex",
                provider="openai",
                harness="codex",
            ),
        ]

    monkeypatch.setattr(_spawn_prepare, "load_merged_aliases", _aliases)
    monkeypatch.setattr(_spawn_prepare, "load_discovered_models", _discovered_models)

    context_builder = cast(
        _ModelValidationContextBuilder,
        getattr(_spawn_prepare, "_model_validation_context"),
    )

    context = context_builder(
        "gpt-5.3-code",
        repo_root=Path("/tmp/repo"),
    )

    assert "Available aliases: codex -> gpt-5.3-codex [codex]" in context
    assert "Discovered models: gpt-5.3-codex" in context
    assert "Did you mean: gpt-5.3-codex?" in context
