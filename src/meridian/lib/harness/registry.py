"""Harness registry for built-in and custom adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from meridian.lib.config.routing import route_model
from meridian.lib.harness.adapter import HarnessAdapter
from meridian.lib.harness.claude import ClaudeAdapter
from meridian.lib.harness.codex import CodexAdapter
from meridian.lib.harness.direct import DirectAdapter
from meridian.lib.harness.opencode import OpenCodeAdapter
from meridian.lib.types import HarnessId


def _empty_adapters() -> dict[HarnessId, HarnessAdapter]:
    return {}


@dataclass(slots=True)
class HarnessRegistry:
    """Registry keyed by HarnessId."""

    _adapters: dict[HarnessId, HarnessAdapter] = field(default_factory=_empty_adapters)

    @classmethod
    def with_defaults(cls) -> HarnessRegistry:
        registry = cls()
        registry.register(ClaudeAdapter())
        registry.register(CodexAdapter())
        registry.register(OpenCodeAdapter())
        registry.register(DirectAdapter())
        return registry

    def register(self, adapter: HarnessAdapter) -> None:
        self._adapters[adapter.id] = adapter

    def get(self, harness_id: HarnessId) -> HarnessAdapter:
        if harness_id not in self._adapters:
            raise KeyError(f"Unknown harness '{harness_id}'")
        return self._adapters[harness_id]

    def ids(self) -> tuple[HarnessId, ...]:
        return tuple(sorted(self._adapters))

    def route(
        self,
        model: str,
        mode: Literal["harness", "direct"] = "harness",
        *,
        repo_root: Path | None = None,
    ) -> tuple[HarnessAdapter, str | None]:
        if mode == "harness":
            from meridian.lib.config.catalog import resolve_model

            resolved = resolve_model(model, repo_root=repo_root)
            return self.get(resolved.harness), None

        decision = route_model(model=model, mode=mode)
        return self.get(decision.harness_id), decision.warning


_DEFAULT_REGISTRY = HarnessRegistry.with_defaults()


def get_default_harness_registry() -> HarnessRegistry:
    """Return built-in registry initialized at import time."""

    return _DEFAULT_REGISTRY
