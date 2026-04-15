# CAS Memo: `running -> finalizing` and reconciler re-validation

## Problem

Round 1 added a `finalizing` state but not an atomic transition protocol. Today
`update_spawn(status=...)` appends blindly, `_record_from_events()` applies a
late `SpawnUpdateEvent.status` even after terminalization, and
`finalize_spawn()` appends terminal events without checking whether a concurrent
writer already moved the row out of `running` under the same flock. That leaves
two holes:

1. Runner can append `status="finalizing"` after a reconciler already finalized.
2. Reconciler can finalize based on a stale `running` read while runner is about
   to enter controlled cleanup.

The state-layer fix is a locked compare-and-swap for `running -> finalizing`
plus a locked re-validation gate for reconciler-origin terminal writes.

## 1. `mark_finalizing` CAS semantics

Add a dedicated `mark_finalizing(state_root, spawn_id) -> bool` in
`spawn_store.py`. It must take the same `spawns.jsonl.flock` used by
`finalize_spawn()` and `append_event()`, project current state from disk under
that lock, and append the update only when the current projected status is
exactly `running`.

Required pre-state:

- Allowed: `running`
- Rejected: `queued`, `finalizing`, any terminal status, missing row

Return value:

- `True`: this call appended the `SpawnUpdateEvent(status="finalizing")`
- `False`: CAS miss; no event written

Use `bool`, not raise. This race is expected, not exceptional. The runner
`finally:` path must be able to say "I lost the race" without converting a
benign concurrent finalize into an infrastructure failure. The caller can still
log or test on the boolean.

Pseudocode:

```text
with lock_file(spawns_flock):
    record = project(spawns.jsonl)[spawn_id]
    if record is None or record.status != "running":
        return False
    append update event {status: "finalizing"}
    return True
```

Which writer wins in the runner vs reconciler race:

- If runner gets the flock first, `running -> finalizing` commits first.
  Reconciler re-validation then sees `finalizing` and must drop its write.
  Runner wins because it has established controlled cleanup before the
  best-effort observer wrote a terminal guess.
- If reconciler gets the flock first and still sees `running`, it may append its
  terminal event. The runner's later CAS then returns `False`. At that point the
  projection layer, not the CAS, is responsible for letting a later
  runner-origin finalize supersede a prior reconciler-origin terminal finalize.
  The CAS protocol only guarantees atomicity of the state transition, not
  authority resolution between two terminal writers.

## 2. Reconciler re-validation on terminal writes

`finalize_spawn()` needs origin-aware guard semantics. For reconciler-origin
calls, it must re-read the projected row under the same flock immediately before
writing the `SpawnFinalizeEvent`.

Guard rule for reconciler origin:

- If current projected status is `finalizing` or any terminal status: return
  `False`, append nothing.
- If current projected status is `queued` or `running`: append the finalize
  event and return whether the row was active.
- If row is missing: return `False`, append nothing.

This is deliberately narrower than the authoritative writer path. Runner,
launcher, launch-failure, streaming/server finalize, and cancel keep current
"always append finalize" semantics so metadata is never lost. Reconciler is the
only best-effort writer and therefore the only writer that should drop its
terminal event when the row has already crossed into a more authoritative state.

The write-path contract is:

```text
with lock_file(spawns_flock):
    record = project(spawns.jsonl)[spawn_id]
    if origin == RECONCILER and (
        record is None
        or record.status == "finalizing"
        or record.status in TERMINAL
    ):
        return False
    append finalize event
    return record is active
```

This does not re-probe artifacts under lock. The reconciler's artifact-based
classification is still computed outside the lock; the store-level re-validation
only decides whether that classification is still admissible given the latest
projected lifecycle state.

## 3. Guard placement

Put the guard inside `finalize_spawn(..., origin=...)`, not in a separate
`reconciler_finalize_spawn()`.

Reasoning:

- One append path per event axis. Finalization is one axis; "authoritative vs
  best-effort" is a policy branch on that axis, not a different mechanism.
- One flock scope. The function that decides admissibility should be the same
  function that appends the event.
- Lower drift risk. Two public finalize helpers would duplicate event
  construction, lock handling, and return semantics, and invite callers to pick
  the wrong one.
- Better auditability. A grep for `finalize_spawn(` still finds every terminal
  writer; origin is explicit at each call site.

Recommended signature shape:

```text
finalize_spawn(..., origin: SpawnFinalizeOrigin = AUTHORITATIVE) -> bool
```

Where `RECONCILER` is the only guarded origin. Keep the enum about write
authority, not provenance taxonomy. Provenance detail can be a separate field if
the origin-tagging work needs more granularity later.

## 4. Event schema and dead surface

Audit result: `update_spawn(status=...)` is not a general status-transition API
today. The only in-tree caller is `mark_spawn_running()` in `spawn_store.py`.
All other `update_spawn()` uses update metadata only (`runner_pid`,
`harness_session_id`, `execution_cwd`, `work_id`).

Implications:

- `SpawnUpdateEvent.status` should remain in the event schema because the JSONL
  still needs a non-terminal status event shape for `queued -> running` and
  `running -> finalizing`.
- The public `update_spawn(status=...)` kwarg is the wrong abstraction and
  should be removed or made private. It is dead as a general surface and would
  let future call sites bypass CAS.
- Replace it with explicit helpers:
  - `mark_spawn_running(...)`
  - `mark_finalizing(...)`
- Any direct status-bearing `SpawnUpdateEvent` outside those helpers should be
  treated as invalid new surface area.

Dead-code call-out: `validate_transition()` in
`src/meridian/lib/core/spawn_lifecycle.py` is currently unused. Either wire it
into the new helper layer or delete it; leaving an unwired lifecycle validator
next to an append-only event store is misleading.

## 5. Revised lifecycle table

Authoritative allowed transitions should be:

| From | To |
|---|---|
| `queued` | `running`, `succeeded`, `failed`, `cancelled` |
| `running` | `finalizing`, `succeeded`, `failed`, `cancelled` |
| `finalizing` | `succeeded`, `failed`, `cancelled` |
| `succeeded` | none |
| `failed` | none |
| `cancelled` | none |

`queued -> finalizing` is **not** legal.

Why:

- `finalizing` means post-run controlled cleanup after execution reached the
  runner's shutdown path.
- A queued spawn never entered execution, so direct `queued -> finalizing`
  would blur launch failure/cancel with post-exit cleanup.
- We already need `queued -> failed/cancelled` for launch failure and cancel
  before worker start, so there is no gap that requires `queued -> finalizing`.

## 6. Projection invariants required by this protocol

Projection work is parallel, but this transition protocol depends on two
non-negotiable invariants in `_record_from_events()`:

1. Once projected status is terminal, a later `SpawnUpdateEvent.status` never
   downgrades it. Late `running` or `finalizing` updates are ignored for status.
2. A later runner-authoritative finalize may supersede a prior
   reconciler-origin terminal finalize, but no `SpawnUpdateEvent` may do so.

Concretely, if the event stream is:

```text
start(running)
finalize(failed, origin=reconciler, error=orphan_run)
update(status=finalizing)
finalize(succeeded, origin=runner)
```

projection must behave as:

- ignore the late `update.status`
- allow the later runner finalize to replace the reconciler terminal status

Non-status metadata from late update events may still merge if desired, but
status monotonicity must hold.

## Open questions

- `mark_spawn_running()` is still an unconditional append helper. That is
  probably acceptable for this fix, but it is the next obvious place to apply
  lifecycle validation (`queued` only) if startup races surface later.
- Streaming/app-server finalize paths currently go `running -> terminal`
  directly. That is fine unless they also gain a meaningful post-exit cleanup
  window; if they do, they should opt into the same explicit `finalizing`
  protocol rather than invent a parallel one.
