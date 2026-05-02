"""Frontend launch contracts for ``meridian chat --dev``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class BackendEndpoint:
    """Backend address details needed by a frontend dev-server launcher."""

    bind_host: str
    port: int
    client_host: str
    http_origin: str
    ws_origin: str


class FrontendLaunchError(RuntimeError):
    """Raised when the dev frontend cannot be launched."""


class PortlessRouteOccupiedError(FrontendLaunchError):
    """Raised when the requested portless route is already occupied."""


@dataclass(frozen=True)
class LaunchResult:
    """Result of launching a dev frontend session plus display metadata."""

    session: FrontendSession
    share_url: str | None = None
    share_label: str | None = None
    share_mode: str | None = None
    service_name: str | None = None


class FrontendSession(Protocol):
    """Running dev frontend session managed by the supervisor."""

    @property
    def url(self) -> str:
        """Browser-facing URL for the dev frontend."""
        ...

    async def wait_until_ready(self, timeout: float) -> None:
        """Wait until the frontend can serve requests or startup fails."""
        ...

    def poll(self) -> int | None:
        """Return the process exit code if the session exited, otherwise ``None``."""
        ...

    def terminate(self, grace_period: float = 5.0) -> None:
        """Terminate the session, escalating after ``grace_period`` seconds."""
        ...


class FrontendLauncher(Protocol):
    """Factory for launching a dev frontend session."""

    def launch(self, frontend_root: Path, backend: BackendEndpoint) -> LaunchResult:
        """Launch a frontend session rooted at ``frontend_root``."""
        ...
