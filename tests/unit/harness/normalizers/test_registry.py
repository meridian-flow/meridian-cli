from meridian.lib.harness.ids import HarnessId
from meridian.lib.harness.normalizers.claude import ClaudeNormalizer
from meridian.lib.harness.normalizers.codex import CodexNormalizer
from meridian.lib.harness.normalizers.opencode import OpenCodeNormalizer
from meridian.lib.harness.normalizers.registry import NORMALIZER_REGISTRY, get_normalizer_factory


def test_registry_contains_claude_normalizer():
    assert NORMALIZER_REGISTRY["claude"] is ClaudeNormalizer
    assert get_normalizer_factory(HarnessId.CLAUDE) is ClaudeNormalizer


def test_registry_contains_multi_harness_normalizers():
    assert NORMALIZER_REGISTRY["codex"] is CodexNormalizer
    assert NORMALIZER_REGISTRY["opencode"] is OpenCodeNormalizer
    assert get_normalizer_factory(HarnessId.CODEX) is CodexNormalizer
    assert get_normalizer_factory(HarnessId.OPENCODE) is OpenCodeNormalizer
