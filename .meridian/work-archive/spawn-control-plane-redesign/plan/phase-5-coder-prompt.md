# Phase 5: Cancel Core (R-03, R-06)

Implement the shared cancel semantics and remove old control-socket cancel path.

## What to Build

### R-03: Create `src/meridian/lib/streaming/signal_canceller.py`

This is the single cancel entry point with two-lane dispatch (D-03):

```python
@dataclass
class CancelOutcome:
    status: SpawnStatus
    origin: SpawnOrigin
    exit_code: int
    already_terminal: bool = False
    finalizing: bool = False  # True if 503 path

class SignalCanceller:
    def __init__(self, *, state_root: Path, grace_seconds: float = 5.0,
                 manager: SpawnManager | None = None): ...

    async def cancel(self, spawn_id: SpawnId) -> CancelOutcome:
        # 1. Get spawn record
        # 2. If terminal → return CancelOutcome(already_terminal=True)
        # 3. If finalizing → wait for terminal (CAN-008), return 503 path if grace expires
        # 4. Dispatch by launch_mode:
        #    - "foreground"/"background" → _cancel_cli_spawn (SIGTERM)
        #    - "app" → _cancel_app_spawn (in-process or HTTP)

    async def _cancel_cli_spawn(self, spawn_id, record) -> CancelOutcome:
        # Resolve runner PID with PID-reuse guard (D-15)
        # Send SIGTERM, wait grace_seconds
        # No SIGKILL ever (D-13)
        # If grace expires → return 503 path (reaper handles)

    async def _cancel_app_spawn(self, spawn_id, record) -> CancelOutcome:
        # If manager available → in-process stop_spawn
        # Else → HTTP POST /cancel to AF_UNIX socket (R-09, but stub for now)
```

Key details:
- PID-reuse guard: use `is_process_alive(runner_pid, created_after_epoch=...)` matching reaper's approach (D-15, D-23)
- Convert `SpawnRecord.started_at` (ISO 8601) to epoch for the guard
- Finalizing gate: no SIGTERM when status=="finalizing" (CAN-008)
- No SIGKILL in any path (D-13)
- Two-lane dispatch on `launch_mode` (D-03)

### R-06: Remove control-socket cancel

In `src/meridian/lib/streaming/control_socket.py`:
- Remove the `"cancel"` branch from the message handler
- Add rejection: respond with `{"ok": false, "error": "cancel is not supported on the control socket; use meridian spawn cancel <id>"}`

In `src/meridian/lib/streaming/spawn_manager.py`:
- Delete `SpawnManager.cancel()` method entirely

In `src/meridian/cli/spawn_inject.py`:
- Remove `--cancel` flag

### Update `src/meridian/lib/ops/spawn/api.py`
- Replace existing `spawn_cancel_sync` with delegation to `SignalCanceller`
- The CLI `meridian spawn cancel` should use `SignalCanceller.cancel()`
- Add authorization check using the guard from Phase 2

### Update `src/meridian/cli/spawn.py`
- Wire `spawn cancel` to use the new `SignalCanceller` path

## EARS Statements

- CAN-001: SIGTERM to runner finalizes as cancelled
- CAN-003: Grace period bounded, no SIGKILL escalation
- CAN-006: Control-socket cancel removed
- CAN-007: Cancel idempotent on terminal spawns
- CAN-008: Cancel under finalizing waits, never escalates

## Key Decisions

- D-03: Two-lane cancel (SIGTERM for CLI, in-process for app)
- D-08: Delete SpawnManager.cancel outright
- D-13: No SIGKILL
- D-15: PID-reuse guard
- D-23: Convert started_at at read time

## What NOT to Change

- Do NOT add HTTP POST /cancel endpoint yet (Phase 6)
- Do NOT implement the cross-process HTTP cancel dispatch yet (Phase 6)
- Do NOT change interrupt behavior
- Do NOT change app_cmd.py transport

## Files to Read

- `src/meridian/lib/ops/spawn/api.py` — existing cancel logic to replace
- `src/meridian/lib/state/liveness.py` — is_process_alive with PID-reuse guard
- `src/meridian/lib/state/reaper.py` — reference for how reaper uses the guard
- `src/meridian/lib/ops/spawn/authorization.py` — auth guard from Phase 2

## Verification

```bash
uv run ruff check .
uv run pyright
uv run pytest-llm
```
