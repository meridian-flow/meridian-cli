"""Cross-platform subprocess tree termination helpers."""

from __future__ import annotations

import asyncio
from contextlib import suppress

import psutil


def _snapshot_tree(pid: int) -> tuple[psutil.Process | None, list[psutil.Process]]:
    """Return a stable snapshot of root process and descendants."""

    try:
        root = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return None, []

    children: list[psutil.Process] = []
    with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
        children = root.children(recursive=True)
    return root, children


async def terminate_tree(
    process: asyncio.subprocess.Process,
    *,
    grace_secs: float = 5.0,
) -> None:
    """Terminate a subprocess tree, escalating to kill after a grace period."""

    if process.returncode is not None:
        return

    pid = process.pid
    root, children = _snapshot_tree(pid)
    if root is None:
        return

    tree = [*children, root]

    for proc in tree:
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            proc.terminate()

    _, alive = await asyncio.to_thread(psutil.wait_procs, tree, timeout=grace_secs)
    if not alive:
        return

    for proc in alive:
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            proc.kill()

    await asyncio.to_thread(psutil.wait_procs, alive, timeout=1.0)


__all__ = ["terminate_tree"]
