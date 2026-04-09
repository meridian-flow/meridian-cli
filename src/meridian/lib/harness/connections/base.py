"""Core protocol and data contracts for bidirectional harness connections."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from meridian.lib.core.types import HarnessId, SpawnId


@dataclass(frozen=True)
class ConnectionCapabilities:
    """Feature flags describing one bidirectional connection implementation."""

    mid_turn_injection: Literal["queue", "interrupt_restart", "http_post"]
    supports_steer: bool
    supports_interrupt: bool
    supports_cancel: bool
    runtime_model_switch: bool
    structured_reasoning: bool


ConnectionState = Literal["created", "starting", "connected", "stopping", "stopped", "failed"]


class ConnectionNotReady(RuntimeError):
    """Raised when send operations are attempted before connection readiness."""


@dataclass(frozen=True)
class HarnessEvent:
    """One parsed event from a running harness connection."""

    event_type: str
    payload: dict[str, object]
    harness_id: str
    raw_text: str | None = None


@dataclass(frozen=True)
class ConnectionConfig:
    """Configuration inputs for starting one harness connection."""

    spawn_id: SpawnId
    harness_id: HarnessId
    model: str | None
    agent: str | None
    prompt: str
    repo_root: Path
    env_overrides: dict[str, str]
    extra_args: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    continue_session_id: str | None = None
    timeout_seconds: float | None = None
    ws_bind_host: str = "127.0.0.1"
    ws_port: int = 0


@runtime_checkable
class HarnessLifecycle(Protocol):
    """Lifecycle operations for one bidirectional harness connection."""

    @property
    def state(self) -> ConnectionState: ...

    async def start(self, config: ConnectionConfig) -> None: ...

    async def stop(self) -> None: ...

    def health(self) -> bool: ...


@runtime_checkable
class HarnessSender(Protocol):
    """Outbound control channel into one harness connection."""

    async def send_user_message(self, text: str) -> None: ...

    async def send_interrupt(self) -> None: ...

    async def send_cancel(self) -> None: ...


@runtime_checkable
class HarnessReceiver(Protocol):
    """Inbound event stream from one harness connection."""

    def events(self) -> AsyncIterator[HarnessEvent]: ...


@runtime_checkable
class HarnessConnection(HarnessLifecycle, HarnessSender, HarnessReceiver, Protocol):
    """Composite protocol for full-duplex harness connections."""

    @property
    def harness_id(self) -> HarnessId: ...

    @property
    def spawn_id(self) -> SpawnId: ...

    @property
    def capabilities(self) -> ConnectionCapabilities: ...


__all__ = [
    "ConnectionCapabilities",
    "ConnectionConfig",
    "ConnectionNotReady",
    "ConnectionState",
    "HarnessConnection",
    "HarnessEvent",
    "HarnessLifecycle",
    "HarnessReceiver",
    "HarnessSender",
]
