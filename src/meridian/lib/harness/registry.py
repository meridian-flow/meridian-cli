"""Harness registry for built-in and custom adapters."""

from pathlib import Path
from typing import Literal, Self, cast, overload

from pydantic import BaseModel, ConfigDict, PrivateAttr

from meridian.lib.catalog.models import route_model
from meridian.lib.core.types import HarnessId
from meridian.lib.harness.adapter import (
    ConversationExtractingHarness,
    InProcessHarness,
    SubprocessHarness,
)

type HarnessEntry = SubprocessHarness | InProcessHarness


def _empty_adapters() -> dict[HarnessId, HarnessEntry]:
    return {}


class HarnessRegistry(BaseModel):
    """Registry keyed by HarnessId."""

    model_config = ConfigDict()

    _adapters: dict[HarnessId, HarnessEntry] = PrivateAttr(default_factory=_empty_adapters)

    @classmethod
    def with_defaults(cls) -> Self:
        from meridian.lib.harness.claude import ClaudeAdapter
        from meridian.lib.harness.codex import CodexAdapter
        from meridian.lib.harness.direct import DirectAdapter
        from meridian.lib.harness.opencode import OpenCodeAdapter

        registry = cls()
        registry.register(ClaudeAdapter())
        registry.register(CodexAdapter())
        registry.register(OpenCodeAdapter())
        registry.register(DirectAdapter())
        return registry

    def register(self, adapter: HarnessEntry) -> None:
        self._adapters[adapter.id] = adapter

    def get(self, harness_id: HarnessId) -> HarnessEntry:
        if harness_id not in self._adapters:
            raise KeyError(f"Unknown harness '{harness_id}'")
        return self._adapters[harness_id]

    def get_subprocess_harness(self, harness_id: HarnessId) -> SubprocessHarness:
        adapter = self.get(harness_id)
        has_execute = callable(getattr(adapter, "execute", None))
        has_build_command = callable(getattr(adapter, "build_command", None))
        if has_execute and not has_build_command:
            raise TypeError(f"Harness '{harness_id}' is not a subprocess harness.")
        return cast("SubprocessHarness", adapter)

    def get_in_process_harness(self, harness_id: HarnessId) -> InProcessHarness:
        adapter = self.get(harness_id)
        if not callable(getattr(adapter, "execute", None)):
            raise TypeError(f"Harness '{harness_id}' is not an in-process harness.")
        return cast("InProcessHarness", adapter)

    def get_conversation_harness(
        self,
        harness_id: HarnessId,
    ) -> ConversationExtractingHarness | None:
        adapter = self.get(harness_id)
        if isinstance(adapter, ConversationExtractingHarness):
            return adapter
        return None

    def ids(self) -> tuple[HarnessId, ...]:
        return tuple(sorted(self._adapters))

    @overload
    def route(
        self,
        model: str,
        mode: Literal["harness"] = "harness",
        *,
        repo_root: Path | None = None,
    ) -> tuple[SubprocessHarness, str | None]: ...

    @overload
    def route(
        self,
        model: str,
        mode: Literal["direct"],
        *,
        repo_root: Path | None = None,
    ) -> tuple[InProcessHarness, str | None]: ...

    def route(
        self,
        model: str,
        mode: Literal["harness", "direct"] = "harness",
        *,
        repo_root: Path | None = None,
    ) -> tuple[HarnessEntry, str | None]:
        if mode == "harness":
            from meridian.lib.catalog.models import resolve_model

            resolved = resolve_model(model, repo_root=repo_root)
            return self.get_subprocess_harness(resolved.harness), None

        decision = route_model(model=model, mode=mode)
        return self.get_in_process_harness(decision.harness_id), decision.warning


_default_registry: HarnessRegistry | None = None


def get_default_harness_registry() -> HarnessRegistry:
    """Return built-in registry, created on first access."""

    global _default_registry
    if _default_registry is None:
        _default_registry = HarnessRegistry.with_defaults()
    return _default_registry
