"""HCP capability defaults by harness."""

from dataclasses import dataclass


@dataclass(frozen=True)
class HcpCapabilities:
    can_list_sessions: bool = False
    can_fork: bool = False
    can_resume: bool = True
    supports_permissions: bool = True
    supports_model_switch: bool = False


CLAUDE_CAPABILITIES = HcpCapabilities(can_fork=True, can_resume=True)
CODEX_CAPABILITIES = HcpCapabilities(can_fork=True, can_resume=True)
OPENCODE_CAPABILITIES = HcpCapabilities(can_fork=False, can_resume=True)


__all__ = [
    "CLAUDE_CAPABILITIES",
    "CODEX_CAPABILITIES",
    "OPENCODE_CAPABILITIES",
    "HcpCapabilities",
]
