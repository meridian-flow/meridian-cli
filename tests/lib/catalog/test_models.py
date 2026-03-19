from datetime import date, timedelta
from pathlib import Path

import pytest

from meridian.lib.catalog.model_policy import _model_lineage, compute_superseded_ids
from meridian.lib.catalog.models import (
    AliasEntry,
    DiscoveredModel,
    load_model_visibility,
    route_model,
)
from meridian.lib.core.types import HarnessId
from meridian.lib.ops.catalog import ModelsListInput, models_list_sync


def _write_models_toml(repo_root: Path, content: str) -> None:
    state_root = repo_root / ".meridian"
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "models.toml").write_text(content, encoding="utf-8")


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


def test_route_model_uses_user_harness_patterns(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_models_toml(
        repo_root,
        '[harness_patterns]\n'
        'codex = ["gpt-*", "foo-*"]\n'
        'claude = ["claude-*", "opus*", "sonnet*", "haiku*"]\n'
        'opencode = ["opencode-*", "gemini*", "*/*"]\n',
    )

    assert route_model("foo-bar", repo_root=repo_root).harness_id == HarnessId.CODEX


def test_route_model_rejects_ambiguous_harness_patterns(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_models_toml(
        repo_root,
        '[harness_patterns]\n'
        'codex = ["foo-*"]\n'
        'opencode = ["foo-*"]\n',
    )

    with pytest.raises(ValueError, match="matches multiple harness_patterns"):
        route_model("foo-bar", repo_root=repo_root)


def test_load_model_visibility_uses_user_overrides(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_models_toml(
        repo_root,
        "[model_visibility]\n"
        'exclude = ["gemini*"]\n'
        "max_input_cost = 100.0\n",
    )

    visibility = load_model_visibility(repo_root=repo_root)
    assert visibility.exclude == ("gemini*",)
    assert visibility.max_input_cost == 100.0


def test_models_list_uses_visibility_rules_and_keeps_aliased_models_visible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_models_toml(
        repo_root,
        "[models]\n"
        'gem = "gemini-3.1-pro"\n'
        "\n"
        "[model_visibility]\n"
        'exclude = ["gemini*"]\n',
    )

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
    repo_root.mkdir()
    _write_models_toml(repo_root, "")

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
    repo_root.mkdir()
    _write_models_toml(repo_root, "")

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
    repo_root.mkdir()
    _write_models_toml(repo_root, "")

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
