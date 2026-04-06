from datetime import date, timedelta
from pathlib import Path

import pytest

from meridian.lib.catalog.model_policy import _model_lineage, compute_superseded_ids
from meridian.lib.catalog.models import (
    AliasEntry,
    DiscoveredModel,
    resolve_model,
)
from meridian.lib.core.types import HarnessId
from meridian.lib.ops.catalog import ModelsListInput, models_list_sync


def _model(
    model_id: str,
    *,
    provider: str = "openai",
    harness: HarnessId = HarnessId.CODEX,
    cost_input: float | None = 1.0,
    release_date: str | None = None,
) -> DiscoveredModel:
    return DiscoveredModel(
        id=model_id,
        name=model_id,
        family=model_id.split("-", 1)[0],
        provider=provider,
        harness=harness,
        cost_input=cost_input,
        cost_output=cost_input,
        context_limit=200000,
        output_limit=8000,
        capabilities=("tool_call",),
        release_date=release_date,
    )


def _init_repo(repo_root: Path) -> None:
    repo_root.mkdir()
    (repo_root / "mars.toml").write_text(
        "[settings]\n"
        'targets = [".agents"]\n',
        encoding="utf-8",
    )


# --- resolve_model with mars ---


def test_resolve_model_returns_concrete_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify resolve_model returns the concrete model_id, not the alias name."""

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
    """Raw model IDs that aren't aliases use pattern fallback."""

    def mock_mars_resolve(
        name: str, repo_root: object = None
    ) -> dict[str, object] | None:
        return None  # Not a known alias

    monkeypatch.setattr(
        "meridian.lib.catalog.models.run_mars_models_resolve",
        mock_mars_resolve,
    )
    result = resolve_model("claude-opus-4-6")
    assert str(result.model_id) == "claude-opus-4-6"
    assert result.alias == ""
    assert result.harness == HarnessId.CLAUDE


def test_resolve_model_mars_broken_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """When mars binary is unavailable, resolve_model raises RuntimeError."""

    def mock_mars_resolve(
        name: str, repo_root: object = None
    ) -> dict[str, object] | None:
        _ = (name, repo_root)
        raise RuntimeError("Mars binary not found.")

    monkeypatch.setattr(
        "meridian.lib.catalog.models.run_mars_models_resolve",
        mock_mars_resolve,
    )
    with pytest.raises(RuntimeError, match="Mars binary not found"):
        resolve_model("opus")


def test_resolve_model_unknown_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown model that isn't a mars alias and doesn't match patterns raises."""

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
    """Mars resolving a model with no installed harness raises a clear error."""

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
    """Empty model identifier raises ValueError."""
    with pytest.raises(ValueError, match="must not be empty"):
        resolve_model("")
    with pytest.raises(ValueError, match="must not be empty"):
        resolve_model("   ")


def test_pattern_fallback_harness() -> None:
    """pattern_fallback_harness routes known patterns correctly."""
    from meridian.lib.catalog.model_policy import pattern_fallback_harness

    assert pattern_fallback_harness("claude-opus-4-6") == HarnessId.CLAUDE
    assert pattern_fallback_harness("gpt-5.3-codex") == HarnessId.CODEX
    assert pattern_fallback_harness("gemini-pro") == HarnessId.OPENCODE

    with pytest.raises(ValueError):
        pattern_fallback_harness("totally-unknown-model")


def test_models_list_uses_visibility_rules_and_keeps_aliased_models_visible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)

    old_date = (date.today() - timedelta(days=365)).isoformat()
    monkeypatch.setattr(
        "meridian.lib.ops.catalog.load_discovered_models",
        lambda: [
            _model("gpt-5.4"),
            _model("gemini-3.1-pro", provider="google", harness=HarnessId.OPENCODE),
            _model(
                "claude-expensive",
                provider="anthropic",
                harness=HarnessId.CLAUDE,
                cost_input=12.0,
            ),
            _model(
                "claude-old",
                provider="anthropic",
                harness=HarnessId.CLAUDE,
                release_date=old_date,
            ),
        ],
    )
    monkeypatch.setattr(
        "meridian.lib.ops.catalog.load_merged_aliases",
        lambda repo_root=None: [
            AliasEntry(
                alias="gem",
                model_id="gemini-3.1-pro",
                resolved_harness=HarnessId.OPENCODE,
            )
        ],
    )

    output = models_list_sync(ModelsListInput(repo_root=repo_root.as_posix()))
    model_ids = {str(model.model_id) for model in output.models}
    assert model_ids == {"gpt-5.4", "gemini-3.1-pro"}


# --- _model_lineage ---


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("claude-opus-4-6", "claude-opus"),
        ("claude-opus-4-5", "claude-opus"),
        ("claude-sonnet-4-6", "claude-sonnet"),
        ("claude-3-5-sonnet-20241022", "claude-sonnet"),
        ("gpt-5.4", "gpt"),
        ("gpt-5.4-mini", "gpt-mini"),
        ("gpt-5.3-codex", "gpt-codex"),
        ("gpt-4o", "gpt-4o"),
        ("gemini-3.1-pro-preview", "gemini-pro"),
        ("gemini-2.5-flash", "gemini-flash"),
        ("gemini-2.5-flash-lite-preview-06-17", "gemini-flash-lite"),
        ("claude-sonnet-latest", None),
    ],
)
def test_model_lineage(model_id: str, expected: str | None) -> None:
    assert _model_lineage(model_id) == expected


# --- compute_superseded_ids ---


def test_compute_superseded_ids_picks_latest() -> None:
    models = [
        ("gpt-5.1", "openai", "2025-11-13"),
        ("gpt-5.2", "openai", "2025-12-11"),
        ("gpt-5.4", "openai", "2026-03-05"),
    ]
    superseded = compute_superseded_ids(models)
    assert "gpt-5.1" in superseded
    assert "gpt-5.2" in superseded
    assert "gpt-5.4" not in superseded


def test_compute_superseded_ids_separate_lineages() -> None:
    models = [
        ("gpt-5.3-codex", "openai", "2026-02-05"),
        ("gpt-5.4", "openai", "2026-03-05"),
    ]
    superseded = compute_superseded_ids(models)
    # Different lineages (gpt-codex vs gpt) — neither supersedes
    assert "gpt-5.3-codex" not in superseded
    assert "gpt-5.4" not in superseded


def test_compute_superseded_ids_cross_provider() -> None:
    models = [
        ("gemini-pro", "google", "2025-01-01"),
        ("gemini-pro", "other", "2026-01-01"),
    ]
    superseded = compute_superseded_ids(models)
    # Same ID but different providers — no superseding
    assert len(superseded) == 0


# --- models_list_sync with superseded ---


def test_models_list_hides_superseded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)

    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=30)).isoformat()
    monkeypatch.setattr(
        "meridian.lib.ops.catalog.load_discovered_models",
        lambda: [
            _model("gpt-5.4", release_date=today),
            _model("gpt-5.2", release_date=yesterday),
        ],
    )
    monkeypatch.setattr(
        "meridian.lib.ops.catalog.load_merged_aliases",
        lambda repo_root=None: [],
    )

    output = models_list_sync(
        ModelsListInput(repo_root=repo_root.as_posix())
    )
    model_ids = {str(m.model_id) for m in output.models}
    assert "gpt-5.4" in model_ids
    assert "gpt-5.2" not in model_ids


def test_models_list_show_superseded_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)

    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=30)).isoformat()
    monkeypatch.setattr(
        "meridian.lib.ops.catalog.load_discovered_models",
        lambda: [
            _model("gpt-5.4", release_date=today),
            _model("gpt-5.2", release_date=yesterday),
        ],
    )
    monkeypatch.setattr(
        "meridian.lib.ops.catalog.load_merged_aliases",
        lambda repo_root=None: [],
    )

    output = models_list_sync(
        ModelsListInput(
            repo_root=repo_root.as_posix(),
            show_superseded=True,
        )
    )
    model_ids = {str(m.model_id) for m in output.models}
    assert "gpt-5.4" in model_ids
    assert "gpt-5.2" in model_ids


def test_models_list_aliased_model_survives_superseded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)

    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=30)).isoformat()
    monkeypatch.setattr(
        "meridian.lib.ops.catalog.load_discovered_models",
        lambda: [
            _model("gpt-5.4", release_date=today),
            _model("gpt-5.2", release_date=yesterday),
        ],
    )
    monkeypatch.setattr(
        "meridian.lib.ops.catalog.load_merged_aliases",
        lambda repo_root=None: [
            AliasEntry(
                alias="old-gpt",
                model_id="gpt-5.2",
                resolved_harness=HarnessId.CODEX,
            )
        ],
    )

    output = models_list_sync(
        ModelsListInput(repo_root=repo_root.as_posix())
    )
    model_ids = {str(m.model_id) for m in output.models}
    # Aliased model survives superseded filtering
    assert "gpt-5.4" in model_ids
    assert "gpt-5.2" in model_ids
