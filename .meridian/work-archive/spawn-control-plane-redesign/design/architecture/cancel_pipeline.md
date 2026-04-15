# Cancel Pipeline (v2r2)

Realizes `spec/cancel.md` (CAN-001..CAN-008) and the cancel half of
`spec/authorization.md`.

## Module layout

```
src/meridian/lib/streaming/
  signal_canceller.py     # NEW — single cancel entry point (two-lane dispatcher)
src/meridian/lib/launch/
  runner.py               # SIGTERM handling unchanged
  streaming_runner.py     # SIGTERM handling unchanged
src/meridian/lib/ops/spawn/
  api.py                  # spawn_cancel_sync delegates to SignalCanceller
src/meridian/lib/app/
  server.py               # POST /cancel calls SignalCanceller
src/meridian/lib/streaming/
  control_socket.py       # rejects type="cancel" with stable error
  spawn_manager.py        # SpawnManager.cancel REMOVED
src/meridian/cli/
  spawn_inject.py         # --cancel REMOVED
```

## `SignalCanceller` — two-lane dispatcher (v2r2 D-03)

```python
@dataclass
class CancelOutcome:
    status: SpawnStatus
    origin: SpawnOrigin
    exit_code: int
    already_terminal: bool = False
    finalizing: bool = False      # True if 503 path

class SignalCanceller:
    def __init__(self, *, state_root: Path, grace_seconds: float = 5.0,
                 manager: SpawnManager | None = None): ...

    async def cancel(self, spawn_id: SpawnId) -> CancelOutcome:
        record = spawn_store.get_spawn(state_root, spawn_id)
        if record is None:
            raise SpawnNotFound(spawn_id)
        if _spawn_is_terminal(record.status):
            return CancelOutcome(... already_terminal=True)

        # --- Finalizing gate (CAN-008) ---
        if record.status == "finalizing":
            outcome = await self._wait_for_terminal(spawn_id, deadline=now+grace)
            if outcome is not None:
                return CancelOutcome(... already_terminal=True)
            return CancelOutcome(... finalizing=True)  # 503 path

        # --- Dispatch by launch_mode (D-03 two-lane) ---
        if record.launch_mode == "app":
            return await self._cancel_app_spawn(spawn_id, record)
        else:
            return await self._cancel_cli_spawn(spawn_id, record)

    async def _cancel_cli_spawn(self, spawn_id, record) -> CancelOutcome:
        """Lane 1: SIGTERM for CLI-launched spawns."""
        runner_pid = self._resolve_runner_pid(record)
        if runner_pid is None:
            self._finalize_with_origin_cancel(record, exit_code=130)
            return CancelOutcome(... origin="cancel")

        os.kill(runner_pid, signal.SIGTERM)
        outcome = await self._wait_for_terminal(spawn_id, deadline=now+grace)
        if outcome is not None:
            return outcome  # runner finalized; origin="runner"

        # Grace expired — no SIGKILL (D-13). Return 503; reaper handles.
        return CancelOutcome(... finalizing=False)

    async def _cancel_app_spawn(self, spawn_id, record) -> CancelOutcome:
        """Lane 2: In-process cancel for app-managed spawns."""
        if self._manager is not None:
            # Same-process: direct in-process cancel
            await self._manager.stop_spawn(
                spawn_id, status="cancelled", error="cancelled", exit_code=143)
            return CancelOutcome(... origin="runner")
        else:
            # Cross-process: route through HTTP
            return await self._http_cancel(spawn_id)

    async def _http_cancel(self, spawn_id) -> CancelOutcome:
        """Send POST /api/spawns/{id}/cancel to the app server's AF_UNIX socket."""
        # Connect to .meridian/app.sock, POST /api/spawns/{id}/cancel
        # Parse response: 200 → success, 409 → already terminal, 503 → finalizing
        ...
```

### Why two lanes (D-03 rationale)

SIGTERM is a process-level signal with no per-spawn addressing. A shared
FastAPI worker hosts multiple spawns; SIGTERM-ing it cannot target one.
Per-spawn worker processes would solve this but are out of scope.

What IS unified: `SignalCanceller` is the single entry point. Both lanes
converge on `status="cancelled"`, `origin="runner"` (preferred) or
`origin="cancel"` (fallback). All surfaces call `SignalCanceller.cancel()`.

### Resolver: `_resolve_runner_pid`

Resolution order (CLI spawns only):

1. `record.runner_pid` if `> 0` and `is_process_alive(record.runner_pid,
   created_after_epoch=_epoch_from_started_at(record.started_at))`.
   PID-reuse guard (D-15). Note: `SpawnRecord.started_at` is ISO 8601
   string; convert to epoch float for `is_process_alive` comparison.
2. `record.worker_pid` if `> 0` and `is_process_alive(...)` with same
   guard. Fallback for runner-crashed-but-harness-alive.
3. Background-launch sidecar PID file.

Runner-first order. PID-reuse guard on ALL branches (p1795 finding).

### No SIGKILL (v2r2 D-13)

v2 initial design had SIGKILL escalation with a finalizing re-check.
Reviewer p1795 identified a TOCTOU race: the spawn can enter
`mark_finalizing` between the re-check and `os.kill(SIGKILL)`. Since
this race cannot be closed without cross-process locking, v2r2 removes
SIGKILL entirely. The reaper is the safety net for hung processes.

### Termination wait: `_wait_for_terminal`

Polls `spawn_store.get_spawn` every 100ms for `grace_seconds`. Returns
terminal record when status leaves the active set.

## Finalize-path responsibilities

| Path | Who finalizes | Origin |
|---|---|---|
| `streaming_runner.py` SIGTERM handler | runner | `runner` |
| `streaming_serve.py` outer wrapper | wrapper | `launcher` |
| App-server background-finalize task | runner (app IS the runner) | `runner` |
| `SignalCanceller` no-runner-pid fallback | canceller | `cancel` |

v2r2: no SIGKILL fallback row. App-server writes `origin="runner"`.

## Removed surface

- `SpawnManager.cancel` and its inbound `cancel` action.
- `ControlSocketServer` routing for `type="cancel"`.
- `spawn_inject` `--cancel` flag.
- `DELETE /api/spawns/{id}` endpoint.
- SIGKILL escalation in cancel pipeline.

## Test plan

### Unit tests
- SignalCanceller dispatch: `launch_mode="foreground"` → SIGTERM path;
  `launch_mode="app"` → in-process path.
- Happy path: SIGTERM → runner finalizes → `origin="runner"`.
- Grace expiry: SIGTERM → no finalize → returns 503 (no SIGKILL).
- Already terminal: no signal, returns existing status.
- Finalizing gate: no signal, waits, returns 503 or terminal.
- PID-reuse: stale `runner_pid` → no signal; both `runner_pid` and
  `worker_pid` branches guarded.
- App in-process cancel: `manager.stop_spawn` called directly.

### Smoke tests
- Scenario 1: CLI cancel → cancelled with origin=runner.
- Scenario 14: HTTP cancel → cancelled.
- Scenario 15: DELETE → 405.

### Fault-injection tests
- **Cancel-during-finalize**: verify no signal, 503, reaper reconciles.
- **PID-reuse**: verify no signal to reused PID.
- **Concurrent cancel**: verify exactly one finalize, idempotent second.
- **Grace-expiry stuck runner**: verify 503, reaper cleanup within 120s.
- **App cross-process cancel**: CLI → HTTP → in-process stop_spawn.
