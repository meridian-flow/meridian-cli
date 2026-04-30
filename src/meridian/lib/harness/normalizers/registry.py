"""Harness normalizer registry."""

from __future__ import annotations

from collections.abc import Callable

from meridian.lib.harness.ids import HarnessId
from meridian.lib.harness.normalizers.base import EventNormalizer
from meridian.lib.harness.normalizers.claude import ClaudeNormalizer

NormalizerFactory = Callable[[str, str], EventNormalizer]

NORMALIZER_REGISTRY: dict[str, NormalizerFactory] = {
    HarnessId.CLAUDE.value: ClaudeNormalizer,
}


def get_normalizer_factory(harness_id: str | HarnessId) -> NormalizerFactory:
    """Return the normalizer factory for a harness id."""

    key = harness_id.value if isinstance(harness_id, HarnessId) else harness_id
    try:
        return NORMALIZER_REGISTRY[key]
    except KeyError as exc:
        raise KeyError(f"No chat event normalizer registered for harness {key!r}") from exc


__all__ = ["NORMALIZER_REGISTRY", "NormalizerFactory", "get_normalizer_factory"]
