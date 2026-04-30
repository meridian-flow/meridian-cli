from meridian.lib.harness.ids import HarnessId
from meridian.lib.harness.normalizers.claude import ClaudeNormalizer
from meridian.lib.harness.normalizers.registry import NORMALIZER_REGISTRY, get_normalizer_factory


def test_registry_contains_claude_normalizer():
    assert NORMALIZER_REGISTRY["claude"] is ClaudeNormalizer
    assert get_normalizer_factory(HarnessId.CLAUDE) is ClaudeNormalizer
