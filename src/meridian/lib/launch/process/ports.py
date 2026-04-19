"""Process launcher contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from collections.abc import Callable


@dataclass(frozen=True)
class LaunchedProcess:
    """Completed process launch result."""

    exit_code: int
    pid: int | None


ChildStartedHook = Callable[[int], None]


class ProcessLauncher(Protocol):
    """Protocol for primary process launch strategies."""

    def launch(
        self,
        *,
        command: tuple[str, ...],
        cwd: Path,
        env: dict[str, str],
        output_log_path: Path | None,
        on_child_started: ChildStartedHook | None = None,
    ) -> LaunchedProcess: ...


ProcessLauncherSelector = Callable[[Path | None], ProcessLauncher]


__all__ = [
    "ChildStartedHook",
    "LaunchedProcess",
    "ProcessLauncher",
    "ProcessLauncherSelector",
]
