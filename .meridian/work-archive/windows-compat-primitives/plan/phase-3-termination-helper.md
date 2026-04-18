# Phase 3: Cross-Platform Termination Helper

## Scope
Create a psutil-based process tree termination helper that works on both Unix and Windows.

## Files to Create/Modify

### 1. Create `src/meridian/lib/platform/terminate.py`

Cross-platform process tree termination using psutil:

```python
"""Cross-platform process tree termination using psutil."""

from __future__ import annotations

import asyncio
from contextlib import suppress

import psutil


async def terminate_tree(
    process: asyncio.subprocess.Process,
    *,
    grace_secs: float = 5.0,
) -> None:
    """Cross-platform process tree termination.
    
    Terminates the process and all its descendants using psutil for
    cross-platform compatibility. On timeout, escalates to force kill.
    
    Args:
        process: The asyncio subprocess to terminate
        grace_secs: Seconds to wait for graceful termination before force kill
    """
    if process.returncode is not None:
        return

    pid = process.pid
    if pid is None:
        return

    # Snapshot descendants before signaling
    root, children = _snapshot_tree(pid)
    if root is None:
        return

    # Graceful termination - children first, then root
    for proc in children + [root]:
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            proc.terminate()

    # Wait for processes to exit
    _, alive = await asyncio.to_thread(
        psutil.wait_procs,
        children + [root],
        timeout=grace_secs,
    )

    # Force kill survivors
    if alive:
        for proc in alive:
            with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                proc.kill()
        
        # Brief wait for kills to complete
        await asyncio.to_thread(
            psutil.wait_procs,
            alive,
            timeout=1.0,
        )


def _snapshot_tree(pid: int) -> tuple[psutil.Process | None, list[psutil.Process]]:
    """Snapshot process and its descendants.
    
    Returns:
        Tuple of (root_process, children_list). Root is None if process doesn't exist.
    """
    try:
        root = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return None, []

    children: list[psutil.Process] = []
    try:
        children = root.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    return root, children


__all__ = ["terminate_tree"]
```

### 2. Update `src/meridian/lib/launch/runner_helpers.py`

Update `terminate_process()` to use the new helper internally while preserving the existing API:

```python
# Add import at top:
from meridian.lib.platform.terminate import terminate_tree as _terminate_tree

# Update terminate_process():
async def terminate_process(
    process: asyncio.subprocess.Process,
    *,
    grace_seconds: float = DEFAULT_KILL_GRACE_SECONDS,
) -> None:
    """Gracefully terminate a process and force-kill if it does not exit."""
    await _terminate_tree(process, grace_secs=grace_seconds)
```

This provides cross-platform behavior while keeping the existing function signature.

### 3. Update `src/meridian/lib/launch/signals.py`

Make `signal_process_group()` platform-aware:

```python
import sys

def signal_process_group(
    process: asyncio.subprocess.Process,
    signum: signal.Signals,
) -> None:
    """Send one signal to the subprocess process group.
    
    On Windows, only sends to the process itself (no process groups).
    On POSIX, sends to the process group.
    """
    if process.returncode is not None:
        return

    pid = process.pid
    if pid is None:
        return

    if sys.platform == "win32":
        # Windows: no process groups, send to process directly
        try:
            process.send_signal(signum)
        except (ProcessLookupError, OSError):
            return
    else:
        # POSIX: send to process group
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signum)
        except ProcessLookupError:
            return
```

## Exit Criteria
- `src/meridian/lib/platform/terminate.py` exists and exports `terminate_tree()`
- `runner_helpers.py` uses the new helper
- `signals.py` is Windows-aware
- All existing tests pass
- `uv run pyright` passes
