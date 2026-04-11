"""Harness and transport identifiers."""

from enum import StrEnum


class HarnessId(StrEnum):
    """Known harness identifiers."""

    CLAUDE = "claude"
    CODEX = "codex"
    OPENCODE = "opencode"
    DIRECT = "direct"


class TransportId(StrEnum):
    """Known transport identifiers."""

    SUBPROCESS = "subprocess"
    STREAMING = "streaming"

