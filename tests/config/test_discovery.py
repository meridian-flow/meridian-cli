from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from meridian.lib.config import discovery
from meridian.lib.config.discovery import DiscoveredModel
from meridian.lib.types import HarnessId


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


def _write_cache(cache_dir: Path, fetched_at: int, models: list[dict[str, object]]) -> None:
    cache_file = cache_dir / "models.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps({"fetched_at": fetched_at, "models": models}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_fetch_models_dev_filters_and_maps_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "anthropic": {
            "id": "anthropic",
            "models": {
                "claude-sonnet-4-6": {
                    "id": "claude-sonnet-4-6",
                    "name": "Claude Sonnet 4.6",
                    "tool_call": True,
                    "cost": {"input": 3, "output": 15},
                    "limit": {"context": 200000, "output": 64000},
                    "modalities": {"input": ["text"], "output": ["text"]},
                    "type": "chat",
                }
            },
        },
        "openai": {
            "id": "openai",
            "models": {
                "text-embedding-3-large": {
                    "id": "text-embedding-3-large",
                    "name": "Embeddings",
                    "tool_call": False,
                    "modalities": {"input": ["text"], "output": ["embedding"]},
                    "type": "embedding",
                }
            },
        },
        "google": {
            "id": "google",
            "models": {
                "gemini-3.1-pro": {
                    "id": "gemini-3.1-pro",
                    "name": "Gemini 3.1 Pro",
                    "tool_call": False,
                    "modalities": {"input": ["text"], "output": ["text"]},
                    "type": "chat",
                }
            },
        },
        "meta": {
            "id": "meta",
            "models": {
                "llama-4": {
                    "id": "llama-4",
                    "name": "Unsupported Provider",
                    "tool_call": True,
                    "modalities": {"input": ["text"], "output": ["text"]},
                    "type": "chat",
                }
            },
        },
    }

    def _urlopen(*_args: object, **_kwargs: object) -> _FakeResponse:
        return _FakeResponse(payload)

    monkeypatch.setattr(discovery.request, "urlopen", _urlopen)

    models = discovery.fetch_models_dev()

    assert models == [
        DiscoveredModel(
            id="claude-sonnet-4-6",
            name="Claude Sonnet 4.6",
            family="claude",
            provider="anthropic",
            harness=HarnessId("claude"),
            cost_input=3.0,
            cost_output=15.0,
            context_limit=200000,
            output_limit=64000,
            capabilities=("tool_call",),
            release_date=None,
        )
    ]


def test_fetch_models_dev_parses_release_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "openai": {
            "id": "openai",
            "models": {
                "gpt-5.3-codex": {
                    "id": "gpt-5.3-codex",
                    "name": "GPT-5.3 Codex",
                    "tool_call": True,
                    "release_date": "2026-02-05",
                }
            },
        },
    }

    def _urlopen(*_args: object, **_kwargs: object) -> _FakeResponse:
        return _FakeResponse(payload)

    monkeypatch.setattr(discovery.request, "urlopen", _urlopen)

    models = discovery.fetch_models_dev()

    assert len(models) == 1
    assert models[0].release_date == "2026-02-05"


def test_load_discovered_models_uses_fresh_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "cache"
    _write_cache(
        cache_dir,
        fetched_at=int(time.time()),
        models=[
            {
                "id": "gpt-5.3-codex",
                "name": "GPT-5.3 Codex",
                "family": "gpt",
                "provider": "openai",
                "harness": "codex",
                "cost_input": 1.25,
                "cost_output": 10.0,
                "context_limit": 400000,
                "output_limit": 128000,
                "capabilities": ["tool_call"],
            }
        ],
    )

    monkeypatch.setattr(
        discovery,
        "fetch_models_dev",
        lambda: pytest.fail("fetch_models_dev should not run for a fresh cache"),
    )

    models = discovery.load_discovered_models(cache_dir)

    assert models == [
        DiscoveredModel(
            id="gpt-5.3-codex",
            name="GPT-5.3 Codex",
            family="gpt",
            provider="openai",
            harness=HarnessId("codex"),
            cost_input=1.25,
            cost_output=10.0,
            context_limit=400000,
            output_limit=128000,
            capabilities=("tool_call",),
            release_date=None,
        )
    ]


def test_load_discovered_models_refreshes_stale_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "cache"
    cache_file = cache_dir / "models.json"
    _write_cache(cache_dir, fetched_at=1, models=[])

    monkeypatch.setattr(
        discovery,
        "fetch_models_dev",
        lambda: [
            DiscoveredModel(
                id="gemini-3.1-pro",
                name="Gemini 3.1 Pro",
                family="gemini",
                provider="google",
                harness=HarnessId("opencode"),
                cost_input=1.0,
                cost_output=4.0,
                context_limit=1048576,
                output_limit=65536,
                capabilities=("tool_call",),
                release_date=None,
            )
        ],
    )

    models = discovery.load_discovered_models(cache_dir)
    cached_payload = json.loads(cache_file.read_text(encoding="utf-8"))

    assert models[0].id == "gemini-3.1-pro"
    assert cached_payload["models"][0]["provider"] == "google"


def test_load_discovered_models_falls_back_to_stale_cache_on_refresh_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cache_dir = tmp_path / "cache"
    _write_cache(
        cache_dir,
        fetched_at=1,
        models=[
            {
                "id": "claude-sonnet-4-6",
                "name": "Claude Sonnet 4.6",
                "family": "claude",
                "provider": "anthropic",
                "harness": "claude",
                "cost_input": 3.0,
                "cost_output": 15.0,
                "context_limit": 200000,
                "output_limit": 64000,
                "capabilities": ["tool_call"],
            }
        ],
    )

    def _raise() -> list[DiscoveredModel]:
        raise OSError("network down")

    monkeypatch.setattr(discovery, "fetch_models_dev", _raise)

    with caplog.at_level("WARNING"):
        models = discovery.load_discovered_models(cache_dir)

    assert [model.id for model in models] == ["claude-sonnet-4-6"]
    assert "using cached models" in caplog.text


def test_fetch_models_dev_handles_multiple_supported_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "anthropic": {
            "id": "anthropic",
            "models": {
                "claude-sonnet-4-6": {
                    "id": "claude-sonnet-4-6",
                    "name": "Claude Sonnet 4.6",
                    "tool_call": True,
                    "modalities": {"input": ["text"], "output": ["text"]},
                    "type": "chat",
                }
            },
        },
        "openai": {
            "id": "openai",
            "models": {
                "gpt-5.3-codex": {
                    "id": "gpt-5.3-codex",
                    "name": "GPT-5.3 Codex",
                    "tool_call": True,
                    "modalities": {"input": ["text"], "output": ["text"]},
                    "type": "chat",
                }
            },
        },
    }

    def _urlopen(*_args: object, **_kwargs: object) -> _FakeResponse:
        return _FakeResponse(payload)

    monkeypatch.setattr(discovery.request, "urlopen", _urlopen)

    models = discovery.fetch_models_dev()

    assert [(model.provider, model.id, model.harness) for model in models] == [
        ("anthropic", "claude-sonnet-4-6", HarnessId("claude")),
        ("openai", "gpt-5.3-codex", HarnessId("codex")),
    ]


def test_fetch_models_dev_ignores_provider_with_empty_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "anthropic": {
            "id": "anthropic",
            "models": {},
        },
        "openai": {
            "id": "openai",
            "models": {
                "gpt-5.3-codex": {
                    "id": "gpt-5.3-codex",
                    "name": "GPT-5.3 Codex",
                    "tool_call": True,
                    "modalities": {"input": ["text"], "output": ["text"]},
                    "type": "chat",
                }
            },
        },
    }

    def _urlopen(*_args: object, **_kwargs: object) -> _FakeResponse:
        return _FakeResponse(payload)

    monkeypatch.setattr(discovery.request, "urlopen", _urlopen)

    models = discovery.fetch_models_dev()

    assert [model.id for model in models] == ["gpt-5.3-codex"]


def test_refresh_models_cache_returns_empty_when_fetch_fails_without_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cache_dir = tmp_path / "cache"

    def _raise() -> list[DiscoveredModel]:
        raise OSError("network down")

    monkeypatch.setattr(discovery, "fetch_models_dev", _raise)

    with caplog.at_level("WARNING"):
        models = discovery.refresh_models_cache(cache_dir)

    assert models == []
    assert "returning empty model list" in caplog.text
