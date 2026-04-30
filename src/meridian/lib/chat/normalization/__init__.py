"""Chat event normalization for raw harness events."""

from meridian.lib.chat.normalization.base import EventNormalizer
from meridian.lib.chat.normalization.claude import ClaudeNormalizer
from meridian.lib.chat.normalization.codex import CodexNormalizer
from meridian.lib.chat.normalization.opencode import OpenCodeNormalizer
from meridian.lib.chat.normalization.registry import NORMALIZER_REGISTRY, get_normalizer_factory

__all__ = [
    "NORMALIZER_REGISTRY",
    "ClaudeNormalizer",
    "CodexNormalizer",
    "EventNormalizer",
    "OpenCodeNormalizer",
    "get_normalizer_factory",
]
