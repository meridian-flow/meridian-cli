from datetime import date, timedelta
from pathlib import Path

import pytest

from meridian.lib.catalog.models import AliasEntry, DiscoveredModel
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


@pytest.mark.parametrize(
    ("show_superseded", "expected_model_ids"),
    [
        (False, {"gpt-5.4"}),
        (True, {"gpt-5.4", "gpt-5.2"}),
    ],
)
def test_models_list_superseded_visibility_toggle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    show_superseded: bool,
    expected_model_ids: set[str],
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
            show_superseded=show_superseded,
        )
    )
    model_ids = {str(model.model_id) for model in output.models}
    assert model_ids == expected_model_ids


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

    output = models_list_sync(ModelsListInput(repo_root=repo_root.as_posix()))
    model_ids = {str(model.model_id) for model in output.models}
    assert "gpt-5.4" in model_ids
    assert "gpt-5.2" in model_ids
