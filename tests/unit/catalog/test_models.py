"""Unit coverage for catalog model resolution and superseding policy."""

import pytest

from meridian.lib.catalog.model_policy import (
    _model_lineage,
    compute_superseded_ids,
    pattern_fallback_harness,
)
from meridian.lib.catalog.models import resolve_model
from meridian.lib.core.types import HarnessId


def test_resolve_model_returns_concrete_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mock_mars_resolve(
        name: str, repo_root: object = None
    ) -> dict[str, object] | None:
        if name == "codex":
            return {
                "name": "codex",
                "model_id": "gpt-5.3-codex",
                "harness": "codex",
                "harness_source": "auto_detected",
            }
        return None

    monkeypatch.setattr(
        "meridian.lib.catalog.models.run_mars_models_resolve",
        mock_mars_resolve,
    )
    result = resolve_model("codex")
    assert str(result.model_id) == "gpt-5.3-codex"
    assert result.alias == "codex"
    assert result.harness == HarnessId.CODEX


def test_resolve_model_raw_model_id_pattern_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mock_mars_resolve(
        name: str, repo_root: object = None
    ) -> dict[str, object] | None:
        return None

    monkeypatch.setattr(
        "meridian.lib.catalog.models.run_mars_models_resolve",
        mock_mars_resolve,
    )
    result = resolve_model("claude-opus-4-6")
    assert str(result.model_id) == "claude-opus-4-6"
    assert result.alias == ""
    assert result.harness == HarnessId.CLAUDE


def test_resolve_model_unknown_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_mars_resolve(
        name: str, repo_root: object = None
    ) -> dict[str, object] | None:
        return None

    monkeypatch.setattr(
        "meridian.lib.catalog.models.run_mars_models_resolve",
        mock_mars_resolve,
    )
    with pytest.raises(ValueError, match="Unknown model"):
        resolve_model("some-unknown-model")


def test_resolve_model_unavailable_harness_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mock_mars_resolve(
        name: str, repo_root: object = None
    ) -> dict[str, object] | None:
        return {
            "name": "opus",
            "model_id": "claude-opus-4-6",
            "harness": None,
            "harness_source": "unavailable",
            "harness_candidates": ["claude", "opencode"],
        }

    monkeypatch.setattr(
        "meridian.lib.catalog.models.run_mars_models_resolve",
        mock_mars_resolve,
    )
    with pytest.raises(ValueError, match="No installed harness"):
        resolve_model("opus")


def test_resolve_model_empty_raises() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        resolve_model("")
    with pytest.raises(ValueError, match="must not be empty"):
        resolve_model("   ")


def test_pattern_fallback_harness() -> None:
    assert pattern_fallback_harness("claude-opus-4-6") == HarnessId.CLAUDE
    assert pattern_fallback_harness("gpt-5.3-codex") == HarnessId.CODEX
    assert pattern_fallback_harness("gemini-pro") == HarnessId.OPENCODE

    with pytest.raises(ValueError):
        pattern_fallback_harness("totally-unknown-model")


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("claude-opus-4-6", "claude-opus"),
        ("claude-3-5-sonnet-20241022", "claude-sonnet"),
        ("gpt-5.4-mini", "gpt-mini"),
        ("gpt-5.3-codex", "gpt-codex"),
        ("gemini-2.5-flash-lite-preview-06-17", "gemini-flash-lite"),
        ("claude-sonnet-latest", None),
    ],
)
def test_model_lineage_normalizes_version_tokens(model_id: str, expected: str | None) -> None:
    assert _model_lineage(model_id) == expected


def test_compute_superseded_ids_respects_lineage_and_provider_boundaries() -> None:
    superseded = compute_superseded_ids(
        [
            ("gpt-5.1", "openai", "2025-11-13"),
            ("gpt-5.2", "openai", "2025-12-11"),
            ("gpt-5.4", "openai", "2026-03-05"),
            ("gpt-5.3-codex", "openai", "2026-02-05"),
            ("gemini-pro", "google", "2025-01-01"),
            ("gemini-pro", "other", "2026-01-01"),
        ]
    )

    assert superseded == frozenset({"gpt-5.1", "gpt-5.2"})
