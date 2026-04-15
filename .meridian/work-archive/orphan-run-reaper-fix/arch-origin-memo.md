# Origin Tagging Design for `SpawnFinalizeEvent`

## Decision

Add first-class `origin` to `SpawnFinalizeEvent` and derived `terminal_origin` to `SpawnRecord`. Projection authority keys off `origin`, never `error`, except in a read-only legacy shim for old rows that predate the field.

Use the smallest enum that preserves the authority axis without lying about the writer surface:

- `runner`: terminal state written by the execution runner with direct exit/report/usage evidence.
- `launcher`: terminal state written by an outer controller that directly awaited child completion, but is not the inner runner.
- `launch_failure`: authoritative failure before normal runner/harness execution stabilized.
- `cancel`: authoritative user-driven cancellation.
- `reconciler`: best-effort probe written by read-path or doctor-style reconciliation.

`runner` and `streaming_runner` share `runner`: same epistemic position, different implementations. `process.py`, `streaming_serve.py`, and `app/server.py` share `launcher`: they are all outer control surfaces finalizing from directly observed child outcome. `launch_failure` stays separate from `launcher` because it marks a materially different phase boundary: the run never entered normal execution, so later repair/debugging can distinguish launch-time failure from post-start termination.

## Schema

In [spawn_store.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/state/spawn_store.py:153):

```python
type SpawnOrigin = Literal[
    "runner",
    "launcher",
    "launch_failure",
    "cancel",
    "reconciler",
]

AUTHORITATIVE_ORIGINS: frozenset[SpawnOrigin] = frozenset({
    "runner",
    "launcher",
    "launch_failure",
    "cancel",
})

class SpawnFinalizeEvent(BaseModel):
    ...
    origin: SpawnOrigin | None = None

class SpawnRecord(BaseModel):
    ...
    terminal_origin: SpawnOrigin | None = None
```

`origin` stays nullable only so legacy rows still parse. New writes should not be allowed to emit `None`: make `finalize_spawn(..., origin: SpawnOrigin, ...)` require the argument, with no default. That keeps compatibility at the event-reader boundary while forcing every current writer to opt into an explicit label.

`terminal_origin` is derived state, not an independently persisted store. It exists so projection can decide later authority transitions without rescanning prior finalize rows or re-deriving from `error`.

## Authority Rule

Projection keeps first-wins for authoritative terminals. The only override is reconciler-demotion: a projected reconciler terminal may be replaced by a later authoritative finalize.

```python
def apply_finalize(current: SpawnRecord, event: SpawnFinalizeEvent) -> SpawnRecord:
    incoming_origin = resolve_finalize_origin(event)
    incoming_authoritative = incoming_origin in AUTHORITATIVE_ORIGINS
    already_terminal = current.status in TERMINAL_SPAWN_STATUSES

    if not already_terminal:
        resolved_status = event.status or current.status
        resolved_exit_code = event.exit_code if event.exit_code is not None else current.exit_code
        resolved_error = (
            None
            if resolved_status == "succeeded"
            else event.error if event.error is not None else current.error
        )
        resolved_terminal_origin = incoming_origin
    elif current.terminal_origin == "reconciler" and incoming_authoritative:
        resolved_status = event.status or current.status
        resolved_exit_code = event.exit_code if event.exit_code is not None else current.exit_code
        resolved_error = (
            None
            if resolved_status == "succeeded"
            else event.error if event.error is not None else current.error
        )
        resolved_terminal_origin = incoming_origin
    else:
        resolved_status = current.status
        resolved_exit_code = current.exit_code
        resolved_error = current.error
        resolved_terminal_origin = current.terminal_origin

    return current.model_copy(
        update={
            "status": resolved_status,
            "exit_code": resolved_exit_code,
            "error": resolved_error,
            "terminal_origin": resolved_terminal_origin,
            "finished_at": event.finished_at if event.finished_at is not None else current.finished_at,
            "duration_secs": event.duration_secs if event.duration_secs is not None else current.duration_secs,
            "total_cost_usd": event.total_cost_usd if event.total_cost_usd is not None else current.total_cost_usd,
            "input_tokens": event.input_tokens if event.input_tokens is not None else current.input_tokens,
            "output_tokens": event.output_tokens if event.output_tokens is not None else current.output_tokens,
        }
    )
```

Explicit consequences:

- Reconciler over reconciler: no-op on terminal tuple.
- Authoritative over authoritative: no-op on terminal tuple.
- Reconciler over authoritative: blocked.
- Reconciler then authoritative: authoritative replaces `(status, exit_code, error)` and `terminal_origin`.
- Duration/cost/token metadata always merges regardless of origin.

## Legacy Shim

Demote S-PR-003 to one helper only:

```python
LEGACY_RECONCILER_ERRORS: frozenset[str] = frozenset({
    "orphan_run",
    "orphan_finalization",
    "missing_worker_pid",
    "harness_completed",
})

def resolve_finalize_origin(event: SpawnFinalizeEvent) -> SpawnOrigin:
    if event.origin is not None:
        return event.origin
    return "reconciler" if event.error in LEGACY_RECONCILER_ERRORS else "runner"
```

This shim is read-only. No new code path may infer origin from `error`, and no writer may omit `origin`.

Removal window: delete `resolve_finalize_origin()`'s fallback branch in the first release after **6 consecutive weeks** where every current `finalize` row in actively used state roots carries `origin`, meaning the oldest live rows have aged past the upgrade boundary. Until then, keep the constant isolated in `spawn_store.py` and referenced nowhere else.

## `SpawnUpdateEvent`

Do not add `origin` to `SpawnUpdateEvent` now.

- The projection authority rule only adjudicates competing terminal writes.
- Current non-terminal updates are launcher/runner bookkeeping (`running`, `wrapper_pid`, `runner_pid`, future `finalizing` CAS), not reconciler probes.
- There is no reconciler path today that emits a non-terminal `SpawnUpdateEvent`.

If a future reconciler starts writing non-terminal updates, add origin there at that time. Doing it now widens schema and call sites without buying correctness.

## Writer Audit

| writer_path_line | origin_value | authoritative? | comment |
|---|---|---:|---|
| `src/meridian/lib/launch/runner.py:851` | `runner` | yes | Primary execution runner finalizes from direct exit/report/usage evidence. |
| `src/meridian/lib/launch/streaming_runner.py:1184` | `runner` | yes | Streaming runner has the same evidence position as the primary runner. |
| `src/meridian/lib/launch/process.py:426` | `launcher` | yes | Outer process wrapper finalizes primary spawn from observed harness exit outcome. |
| `src/meridian/cli/streaming_serve.py:115` | `launcher` | yes | CLI streaming controller finalizes from `run_streaming_spawn()` outcome, not from probe heuristics. |
| `src/meridian/lib/app/server.py:145` | `launcher` | yes | App server background finalizer awaits `spawn_manager.wait_for_completion()` and writes the observed outcome. |
| `src/meridian/lib/app/server.py:256` | `launch_failure` | yes | API launch failed before the spawned run started normally. |
| `src/meridian/lib/ops/spawn/execute.py:578` | `launch_failure` | yes | Background launch failed while persisting worker params; runner never reached steady execution. |
| `src/meridian/lib/ops/spawn/execute.py:637` | `launch_failure` | yes | Background launch failed on `subprocess.Popen`; no normal runner execution exists to contradict it. |
| `src/meridian/lib/ops/spawn/execute.py:881` | `launch_failure` | yes | Background worker could not load persisted params, so failure is authoritative pre-execution setup failure. |
| `src/meridian/lib/ops/spawn/api.py:493` | `cancel` | yes | Explicit user-driven cancellation should remain visible as distinct authority, not collapsed into launcher/runner. |
| `src/meridian/lib/state/reaper.py:57` | `reconciler` | no | Best-effort read-path probe only; may be superseded by a later authoritative finalize. |

No writer in new code remains on `origin=None`.

## Deletion / Follow-up Prompts

- `S-PR-003` is no longer a mechanism; it becomes the isolated `resolve_finalize_origin()` legacy shim above.
- Remove every other `error`-based origin inference path. Authority must come from `origin` or the one shim.
- `exited_at` no longer decides `orphan_finalization` vs `orphan_run`; that distinction now comes from `status == "finalizing"` under the parallel CAS design.
- Keep `exited_at` for now because legacy rows and mixed-version projections still use it as observational data, but mark it as a later removal candidate once the finalizing-state rollout and legacy-row window are complete.
