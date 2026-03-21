"""Tests for auto-resolved builtin aliases and user alias specs."""

from __future__ import annotations

from pathlib import Path

from meridian.lib.catalog.model_aliases import (
    _BUILTIN_ALIAS_SPECS,
    _FALLBACK_ALIASES,
    _AliasSpec,
    _coerce_user_alias_specs,
    _resolve_alias_from_models,
    load_builtin_aliases,
    load_builtin_descriptions,
    load_user_aliases,
)
from meridian.lib.catalog.models import DiscoveredModel
from meridian.lib.core.types import HarnessId

_CL = HarnessId.CLAUDE
_OC = HarnessId.OPENCODE


def _model(
    model_id: str,
    *,
    provider: str = "openai",
    harness: HarnessId = HarnessId.CODEX,
    release_date: str | None = None,
) -> DiscoveredModel:
    return DiscoveredModel(
        id=model_id,
        name=model_id,
        family=model_id.split("-", 1)[0],
        provider=provider,
        harness=harness,
        cost_input=1.0,
        cost_output=1.0,
        context_limit=200000,
        output_limit=8000,
        capabilities=("tool_call",),
        release_date=release_date,
    )


def _anth(mid: str, date: str) -> DiscoveredModel:
    return _model(mid, provider="anthropic", harness=_CL, release_date=date)


def _goog(mid: str, date: str) -> DiscoveredModel:
    return _model(mid, provider="google", harness=_OC, release_date=date)


# --- _resolve_alias_from_models ---


class TestResolveAliasFromModels:
    def test_picks_latest_by_release_date(self) -> None:
        spec = _AliasSpec("anthropic", "opus", ())
        models = [
            _anth("claude-opus-4-5", "2025-04-14"),
            _anth("claude-opus-4-6", "2026-02-05"),
        ]
        assert _resolve_alias_from_models(spec, models) == "claude-opus-4-6"

    def test_returns_none_when_no_matches(self) -> None:
        spec = _AliasSpec("anthropic", "opus", ())
        models = [_model("gpt-5.4", release_date="2026-03-05")]
        assert _resolve_alias_from_models(spec, models) is None

    def test_exclude_patterns_filter_correctly(self) -> None:
        spec = _BUILTIN_ALIAS_SPECS["codex"]
        models = [
            _model("gpt-5.3-codex", release_date="2026-02-05"),
            _model("gpt-5.3-codex-mini", release_date="2026-02-10"),
            _model("gpt-5.3-codex-spark", release_date="2026-02-15"),
            _model("gpt-5.3-codex-max", release_date="2026-02-20"),
        ]
        assert _resolve_alias_from_models(spec, models) == "gpt-5.3-codex"

    def test_skips_latest_floating_refs(self) -> None:
        spec = _AliasSpec("anthropic", "sonnet", ())
        models = [
            _anth("claude-sonnet-4-6", "2026-02-17"),
            _anth("claude-sonnet-latest", "2099-01-01"),
        ]
        assert _resolve_alias_from_models(spec, models) == "claude-sonnet-4-6"

    def test_prefers_shorter_id_on_same_date(self) -> None:
        spec = _AliasSpec("anthropic", "haiku", ())
        models = [
            _anth("claude-haiku-4-5", "2025-10-15"),
            _anth("claude-haiku-4-5-20251001", "2025-10-15"),
        ]
        assert _resolve_alias_from_models(spec, models) == "claude-haiku-4-5"


# --- load_builtin_aliases ---


class TestLoadBuiltinAliases:
    def test_with_discovered_models_resolves_all(self) -> None:
        models = [
            _anth("claude-opus-4-6", "2026-02-05"),
            _anth("claude-sonnet-4-6", "2026-02-17"),
            _anth("claude-haiku-4-5", "2025-10-15"),
            _model("gpt-5.3-codex", release_date="2026-02-05"),
            _model("gpt-5.2", release_date="2025-12-11"),
            _model("gpt-5.4", release_date="2026-03-05"),
            _goog("gemini-3.1-pro-preview", "2026-02-19"),
        ]
        aliases = load_builtin_aliases(discovered_models=models)
        by_name = {a.alias: a.model_id for a in aliases}
        assert len(by_name) == 7
        assert by_name["opus"] == "claude-opus-4-6"
        assert by_name["sonnet"] == "claude-sonnet-4-6"
        assert by_name["haiku"] == "claude-haiku-4-5"
        assert by_name["codex"] == "gpt-5.3-codex"
        assert by_name["gpt"] == "gpt-5.4"
        assert by_name["gpt52"] == "gpt-5.2"
        assert by_name["gemini"] == "gemini-3.1-pro-preview"

    def test_with_none_falls_back(self) -> None:
        aliases = load_builtin_aliases(discovered_models=None)
        by_name = {a.alias: a.model_id for a in aliases}
        assert len(by_name) == 7
        for alias, model_id in _FALLBACK_ALIASES.items():
            assert by_name[alias] == model_id

    def test_with_empty_list_falls_back(self) -> None:
        aliases = load_builtin_aliases(discovered_models=[])
        by_name = {a.alias: a.model_id for a in aliases}
        for alias, model_id in _FALLBACK_ALIASES.items():
            assert by_name[alias] == model_id

    def test_partial_matches_mix_resolved_and_fallback(self) -> None:
        models = [_anth("claude-opus-4-6", "2026-02-05")]
        aliases = load_builtin_aliases(discovered_models=models)
        by_name = {a.alias: a.model_id for a in aliases}
        assert by_name["opus"] == "claude-opus-4-6"
        assert by_name["gpt"] == _FALLBACK_ALIASES["gpt"]
        assert by_name["gpt52"] == _FALLBACK_ALIASES["gpt52"]
        assert by_name["codex"] == _FALLBACK_ALIASES["codex"]


def test_builtin_descriptions_include_gpt52_reviewer_text() -> None:
    descriptions = load_builtin_descriptions()
    assert descriptions["gpt-5.2"] == "Extremely thorough reviewer, but slow."


# --- User auto-resolve specs ---


def _write_models_toml(repo_root: Path, content: str) -> None:
    state_root = repo_root / ".meridian"
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "models.toml").write_text(content, encoding="utf-8")


class TestUserAliasSpecs:
    def test_table_with_provider_include_parsed_as_spec(self) -> None:
        raw = {
            "fast": {
                "provider": "google",
                "include": "flash",
                "exclude": ["-lite"],
            },
        }
        specs = _coerce_user_alias_specs(raw)
        assert "fast" in specs
        assert specs["fast"] == _AliasSpec("google", "flash", ("-lite",))

    def test_pinned_alias_overrides_auto_resolve(
        self, tmp_path: Path
    ) -> None:
        _write_models_toml(
            tmp_path,
            '[models]\nopus = "claude-opus-4-5"\n\n'
            "[models.opus_auto]\n"
            'provider = "anthropic"\n'
            'include = "opus"\n',
        )
        models = [_anth("claude-opus-4-6", "2026-02-05")]
        aliases = load_user_aliases(tmp_path, discovered_models=models)
        by_name = {a.alias: a.model_id for a in aliases}
        assert by_name["opus"] == "claude-opus-4-5"
        assert by_name["opus_auto"] == "claude-opus-4-6"

    def test_auto_resolve_no_matches_silently_skipped(
        self, tmp_path: Path
    ) -> None:
        _write_models_toml(
            tmp_path,
            "[models.nope]\n"
            'provider = "anthropic"\n'
            'include = "nonexistent"\n',
        )
        models = [_model("gpt-5.4", release_date="2026-03-05")]
        aliases = load_user_aliases(tmp_path, discovered_models=models)
        assert len(aliases) == 0

    def test_exclude_list_in_user_spec_filters(
        self, tmp_path: Path
    ) -> None:
        _write_models_toml(
            tmp_path,
            "[models.fast]\n"
            'provider = "google"\n'
            'include = "flash"\n'
            'exclude = ["-lite"]\n',
        )
        models = [
            _goog("gemini-3-flash", "2026-01-01"),
            _goog("gemini-3-flash-lite", "2026-02-01"),
        ]
        aliases = load_user_aliases(tmp_path, discovered_models=models)
        by_name = {a.alias: a.model_id for a in aliases}
        assert by_name["fast"] == "gemini-3-flash"
