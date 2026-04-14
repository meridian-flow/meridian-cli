# Cancel Pipeline

Realizes `spec/cancel.md` (CAN-001 .. CAN-008) and the cancel half of
`spec/authorization.md`.

## Module layout

```
src/meridian/lib/streaming/
  signal_canceller.py     # NEW — single cancel pipeline
src/meridian/lib/launch/
  runner.py               # SIGTERM-handling unchanged; finalize_spawn already cancelled-by-signal
  streaming_runner.py     # SIGTERM-handling unchanged; same
src/meridian/lib/ops/spawn/
  api.py                  # spawn_cancel_sync delegates to SignalCanceller
src/meridian/lib/app/
  server.py               # POST /api/spawns/{id}/cancel calls SignalCanceller
src/meridian/lib/streaming/
  control_socket.py       # rejects type="cancel" with stable error
  spawn_manager.py        # SpawnManager.cancel REMOVED
src/meridian/cli/
  spawn_inject.py         # --cancel REMOVED; --interrupt and text remain
```

## `SignalCanceller`

```python
@dataclass
class CancelOutcome:
    status: SpawnStatus           # "cancelled" or pre-existing terminal status
    origin: SpawnOrigin           # "runner" (preferred), "cancel" (fallback), or unchanged
    exit_code: int
    forced: bool                  # True if SIGKILL fallback fired
    already_terminal: bool

class SignalCanceller:
    def __init__(self, *, state_root: Path, grace_seconds: float = 5.0): ...

    async def cancel(self, spawn_id: SpawnId) -> CancelOutcome:
        record = spawn_store.get_spawn(state_root, spawn_id)
        if record is None: raise SpawnNotFound
        if _spawn_is_terminal(record.status):
            return CancelOutcome(... already_terminal=True)

        runner_pid = self._resolve_runner_pid(record)
        if runner_pid is None:
            # No process to signal — only finalize if reaper hasn't already.
            self._finalize_with_origin_cancel(record, exit_code=130, forced=False)
            return CancelOutcome(... origin="cancel")

        os.kill(runner_pid, signal.SIGTERM)
        outcome = await self._wait_for_terminal(spawn_id, deadline=now+grace)
        if outcome is not None:
            return outcome  # runner finalized first; origin="runner"

        # Grace expired — escalate.
        if _process_alive(runner_pid):
            os.kill(runner_pid, signal.SIGKILL)
        self._finalize_with_origin_cancel(record, exit_code=137, forced=True)
        return CancelOutcome(... origin="cancel", forced=True)
```

### Resolver: `_resolve_runner_pid`

Replaces today's `_resolve_cancel_pid` for cancel callers. Resolution order:

1. `record.runner_pid` if `> 0` and `is_process_alive(record.runner_pid)`.
2. `record.worker_pid` if `> 0` and `is_process_alive(...)` — fallback only,
   used when the runner has crashed but the harness still runs.
3. Background-launch sidecar PID file (existing
   `_read_background_pid` helper).

The current `_resolve_cancel_pid` prefers `worker_pid` for foreground; that
was correct when "cancel" meant "kill the harness directly". After this
change cancel means "signal the runner so it finalizes correctly", so the
order flips to runner-first.

### Termination wait: `_wait_for_terminal`

Polls `spawn_store.get_spawn` every 100ms for `grace_seconds`, returning the
terminal record when status leaves the active set. Cheap because it reads
through the existing projection cache the same way `spawn show` does.

## Finalize-path responsibilities

| Path | Who finalizes | Origin |
|---|---|---|
| `runner.py` / `streaming_runner.py` SIGTERM handler | runner | `runner` |
| `streaming_serve.py` outer wrapper after streaming_runner returns | wrapper | `launcher` (today's behavior, kept) |
| `SignalCanceller` SIGKILL fallback (CAN-003) | canceller | `cancel` |
| `SignalCanceller` no-runner-pid fallback | canceller | `cancel` |
| FastAPI background-finalize task | wrapper | `launcher` |

The reaper is unchanged: still origin=`reconciler`, still rejected when
already terminal.

## Why SIGTERM is the right primitive

- The runner already has a working SIGTERM handler with a documented
  exit-code mapping (143). That handler converges on
  `manager.stop_spawn(status="cancelled", error="cancelled")` →
  `finalize_spawn(origin="runner", status="cancelled")`. We are reusing a
  proven path, not inventing a new one.
- SIGTERM is what timeout-based external supervisors send today (smoke and
  unit tests rely on this). Routing the CLI/HTTP cancel through the same
  mechanism collapses three slightly-different "cancel" semantics into one.
- Process-group ownership: the runner spawned the harness with
  `start_new_session=True`, so its own SIGTERM handler can also cascade to
  the harness if needed. That keeps cleanup in one place rather than each
  surface chasing PIDs.

## Removed surface

- `SpawnManager.cancel` (and its inbound `cancel` action).
- `ControlSocketServer` routing for `type="cancel"`.
- `spawn_inject` `--cancel` flag.
- `DELETE /api/spawns/{id}` endpoint (replaced by `POST .../cancel`).

These removals are how we close #29: the buggy clean-shutdown path is
deleted; cancel only goes through the path that finalizes correctly.

## Operational properties

- **Idempotency** — `os.kill(pid, SIGTERM)` against a dead PID is
  `ProcessLookupError`, suppressed; the canceller falls through to the
  no-runner-pid branch and writes `origin=cancel` once. Callers may invoke
  cancel any number of times without producing duplicate finalize events
  (CAN-007).
- **Race between runner finalize and SIGKILL** — the runner masks SIGTERM
  during its finalize critical section (`signal_coordinator().mask_sigterm()`
  in `runner.py:876` and `streaming_runner.py:528`). If SIGKILL races, the
  finalize event still lands because it was being written before the
  process died (atomic file append). The canceller's
  `_finalize_with_origin_cancel` then becomes a no-op because
  `was_active=False`.
- **Backward-compat guard** — `SpawnManager.cancel` removal will break any
  test or out-of-tree caller. Audit + delete in the same commit; no
  shim layer.
