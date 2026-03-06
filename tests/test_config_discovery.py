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


def _write_cache(path: Path, fetched_at: int, models: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"fetched_at": fetched_at, "models": models}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_fetch_from_models_dev_filters_and_maps_models(
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
                    "tool_call": True,
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

    models = discovery.fetch_from_models_dev()

    assert models == [
        DiscoveredModel(
            id="claude-sonnet-4-6",
            name="Claude Sonnet 4.6",
            family="claude",
            provider="anthropic",
            harness_id=HarnessId("claude"),
            cost_input=3.0,
            cost_output=15.0,
            context_limit=200000,
            output_limit=64000,
            supports_tool_call=True,
        )
    ]


def test_load_discovered_models_uses_fresh_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "models-dev.json"
    _write_cache(
        cache_path,
        fetched_at=int(time.time()),
        models=[
            {
                "id": "gpt-5.3-codex",
                "name": "GPT-5.3 Codex",
                "family": "gpt",
                "provider": "openai",
                "harness_id": "codex",
                "cost_input": 1.25,
                "cost_output": 10.0,
                "context_limit": 400000,
                "output_limit": 128000,
                "supports_tool_call": True,
            }
        ],
    )
    monkeypatch.setattr(discovery, "_cache_path", lambda: cache_path)
    monkeypatch.setattr(
        discovery,
        "fetch_from_models_dev",
        lambda: pytest.fail("fetch_from_models_dev should not run for a fresh cache"),
    )

    models = discovery.load_discovered_models()

    assert models == [
        DiscoveredModel(
            id="gpt-5.3-codex",
            name="GPT-5.3 Codex",
            family="gpt",
            provider="openai",
            harness_id=HarnessId("codex"),
            cost_input=1.25,
            cost_output=10.0,
            context_limit=400000,
            output_limit=128000,
            supports_tool_call=True,
        )
    ]


def test_load_discovered_models_refreshes_stale_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "models-dev.json"
    _write_cache(cache_path, fetched_at=1, models=[])
    monkeypatch.setattr(discovery, "_cache_path", lambda: cache_path)
    monkeypatch.setattr(
        discovery,
        "fetch_from_models_dev",
        lambda: [
            DiscoveredModel(
                id="gemini-3.1-pro",
                name="Gemini 3.1 Pro",
                family="gemini",
                provider="google",
                harness_id=HarnessId("opencode"),
                cost_input=1.0,
                cost_output=4.0,
                context_limit=1048576,
                output_limit=65536,
                supports_tool_call=True,
            )
        ],
    )

    models = discovery.load_discovered_models()
    cached_payload = json.loads(cache_path.read_text(encoding="utf-8"))

    assert models[0].id == "gemini-3.1-pro"
    assert cached_payload["models"][0]["provider"] == "google"


def test_refresh_cache_returns_empty_when_fetch_fails_without_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cache_path = tmp_path / "models-dev.json"
    monkeypatch.setattr(discovery, "_cache_path", lambda: cache_path)

    def _raise() -> list[DiscoveredModel]:
        raise OSError("network down")

    monkeypatch.setattr(discovery, "fetch_from_models_dev", _raise)

    with caplog.at_level("WARNING"):
        models = discovery.refresh_cache()

    assert models == []
    assert "returning empty model list" in caplog.text
