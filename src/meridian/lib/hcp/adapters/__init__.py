"""HCP adapter registry."""

from __future__ import annotations

from meridian.lib.harness.ids import HarnessId

from .base import HcpAdapter


def get_hcp_adapter(harness_id: HarnessId) -> HcpAdapter:
    """Return the HCP adapter for one harness."""

    from .claude import ClaudeHcpAdapter
    from .codex import CodexHcpAdapter
    from .opencode import OpenCodeHcpAdapter

    adapters: dict[HarnessId, type[HcpAdapter]] = {
        HarnessId.CLAUDE: ClaudeHcpAdapter,
        HarnessId.CODEX: CodexHcpAdapter,
        HarnessId.OPENCODE: OpenCodeHcpAdapter,
    }
    cls = adapters.get(harness_id)
    if cls is None:
        raise ValueError(f"No HCP adapter for {harness_id}")
    return cls()


__all__ = ["HcpAdapter", "get_hcp_adapter"]
