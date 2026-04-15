# Spawn Finalize Bugs Investigation, Lane A

## Scope

Investigated the four surviving finalize-path bugs from
[`requirements.md`](/home/jimyao/gitrepos/meridian-cli/.meridian/work/spawn-finalize-bugs/requirements.md)
without code changes:

- B-01 idle-never-finalized
- B-02 cancel-mis-tagged
- B-03 sigkill-as-succeeded
- B-04 inject-400-vs-422

Question under test: does finalization read the wrong source of truth for exit
classification by preferring harness subprocess completion / final-message
completion over the stream's semantic terminal events?

## Verdict

Mostly confirmed.

B-01, B-02, and B-03 are one bug family: the finalization path does not treat
the Codex event stream as the authoritative terminal signal. Instead it falls
back to transport/drain completion and durable-report presence, and those
fallbacks classify too many cases as success or leave them running forever.

B-04 is separate. It is request-validation behavior in the HTTP inject
endpoint, not a finalize-path classification bug.

## B-01: Idle Never Finalized

### Repro and Evidence

`p1835` is the direct repro from this work item. Its materialized final answer
exists in
[`p1835-final-message.md`](/home/jimyao/gitrepos/meridian-cli/.meridian/work/spawn-finalize-bugs/p1835-final-message.md),
but no finalize row was ever written for the spawn.

Evidence from `p1835` output:

- `.meridian/spawns/p1835/output.jsonl:2405` shows the final answer completed.
- `.meridian/spawns/p1835/output.jsonl:2408` shows
  `thread/status/changed -> idle`.
- `.meridian/spawns/p1835/output.jsonl:2409` shows `turn/completed`.

Evidence from durable state:

- `.meridian/spawns.jsonl:9539` to `.meridian/spawns.jsonl:9542` contain only
  the start/update rows for `p1835`.
- There is no later `finalizing` or `finalize` row for `p1835`.

This is not unique to `p1835`. The smoke report captured earlier completed
spawns that stayed `running`:

- `.meridian/spawns/p1835/output.jsonl:1341` shows `meridian spawn show p1`
  still reporting `status=running`.
- `.meridian/spawns/p1835/output.jsonl:1398` shows the same for `p4`.
- `.meridian/spawns/p1835/output.jsonl:1400` records that `p4` still had only
  a start row in the scratch `spawns.jsonl`.

### Code Path

Codex semantic terminal events are not recognized in the streaming runner:

- [`streaming_runner.py`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/launch/streaming_runner.py:245)
  `_terminal_event_outcome()` explicitly ignores `turn/completed` at lines
  246-248.
- The same function has no handling for `thread/status/changed` with
  `idle`.

The app-side reconciliation path also does not inspect semantic terminal
events:

- [`reaper.py`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/state/reaper.py:145)
  `decide_reconciliation()` uses durable report presence and stale/no-activity
  heuristics, not stream event meaning.

### Causal Chain

1. Codex emits semantic completion in the stream (`turn/completed`,
   `thread/status/changed=idle`).
2. `_terminal_event_outcome()` does not treat those as terminal.
3. No completion outcome is latched from the stream.
4. If the connection stays open, neither the streaming runner nor the reaper
   has a reason to finalize immediately.
5. The spawn remains `running` despite having already produced the final
   message.

### Verdict

Confirmed. B-01 belongs to the main finalize-source-of-truth bug family.

## B-02: Cancel Mis-Tagged as Succeeded

### Repro and Evidence

`p4` is the concrete repro in the smoke artifacts.

Evidence from the cancel flow:

- `.meridian/spawns/p1835/output.jsonl:1995` shows
  `POST /api/spawns/p4/cancel HTTP/1.1 200 OK`.
- `.meridian/spawns/p1835/output.jsonl:1997` shows `after_alive=no`, so the
  target process was no longer alive after cancel handling.

But final persisted state is still success:

- `.meridian/spawns/p1835/output.jsonl:2006` records the final CLI result as
  `{"exit_code": 0, "spawn_id": "p4", "status": "succeeded"}`.
- The same output also reports `spawn show` returning `status=succeeded`,
  `exit_code=0`.
- The same evidence notes a trailing `cancelled` event in the output tail, so
  the semantic cancel signal existed but lost the race.

Control evidence for the intended behavior exists in `p1830`:

- `p1830` finalized in `.meridian/spawns.jsonl` as
  `status=cancelled`, `exit_code=143`, `origin=runner`.

### Code Path

The app and signal-cancel paths do emit cancellation:

- [`signal_canceller.py`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/streaming/signal_canceller.py:114)
  calls `manager.stop_spawn(status="cancelled", exit_code=143, error="cancelled")`.
- [`spawn_manager.py`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/streaming/spawn_manager.py:577)
  `_emit_cancelled_terminal_event()` writes a synthetic `cancelled` event.

But the completion future can already be locked to success:

- [`spawn_manager.py`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/streaming/spawn_manager.py:330)
  `_drain_loop()` resolves natural drain completion as `status="succeeded"`,
  `exit_code=0` when there was no drain exception and the task itself was not
  cancelled.
- [`spawn_manager.py`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/streaming/spawn_manager.py:695)
  `_resolve_completion_future()` returns the already-resolved completion future
  instead of replacing it with the later cancel outcome.

The app persists that completion future result:

- [`server.py`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/app/server.py:199)
  `_background_finalize()` writes the row from
  `spawn_manager.wait_for_completion(spawn_id)`.

### Causal Chain

1. A spawn reaches a state where the stream-drain path already resolved its
   completion future as `succeeded/0`.
2. Later, cancel is requested and a semantic `cancelled` event is emitted.
3. `stop_spawn()` cannot override the already-resolved completion future.
4. `_background_finalize()` persists the earlier success result.
5. Final state becomes `succeeded/0` even though the stream contains a later
   `cancelled` terminal signal.

### Verdict

Confirmed. B-02 is part of the same bug family as B-01: final persisted state
comes from drain/completion-future timing rather than semantic stream terminal
events.

## B-03: SIGKILL Finalized as Succeeded

### Repro and Evidence

`p6` is the concrete repro in the smoke artifacts.

Process evidence:

- `.meridian/spawns/p1835/output.jsonl:1803` to `:1806` capture the launcher
  PID `3679125` and vendor child PID `3679133`.
- `.meridian/spawns/p1835/output.jsonl:1827` to `:1867` record the tester
  intentionally sending `SIGKILL` to both.

Observed outcome:

- `.meridian/spawns/p1835/output.jsonl:2051` to `:2068` record that `p6`
  still finalized as `succeeded` after the confirmed worker kill.
- The work summary in
  [`p1835-final-message.md`](/home/jimyao/gitrepos/meridian-cli/.meridian/work/spawn-finalize-bugs/p1835-final-message.md:5)
  also calls out that `p6` ended as succeeded after only in-progress `sleep
  120` plus `error/connectionClosed`.

### Code Path

The streaming runner does not treat connection-closed as failure:

- [`streaming_runner.py`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/launch/streaming_runner.py:245)
  `_terminal_event_outcome()` has no mapping for `error/connectionClosed`.

So the flow falls back to drain completion:

- [`spawn_manager.py`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/streaming/spawn_manager.py:330)
  `_drain_loop()` marks natural drain completion as `succeeded/0`.
- [`server.py`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/app/server.py:199)
  `_background_finalize()` persists that completion-future result.

The generic lifecycle resolver also defaults to success when the caller does
not mark cancellation:

- [`spawn_lifecycle.py`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/core/spawn_lifecycle.py:68)
  `resolve_execution_terminal_state()` returns `succeeded` when `exit_code == 0`
  and `cancelled` was not set by the caller.

### Causal Chain

1. The underlying worker is killed with `SIGKILL`.
2. The observed terminal stream condition is `error/connectionClosed`.
3. `_terminal_event_outcome()` does not classify that as failure.
4. The drain loop exits without a semantic failure result and resolves the
   completion future as `succeeded/0`.
5. App finalization persists success.

### Verdict

Confirmed. B-03 is in the same bug family as B-01 and B-02.

## B-04: Inject Returns 400 Instead of 422

### Repro and Evidence

The failing behavior is recorded in the survivor summary:

- [`p1835-final-message.md`](/home/jimyao/gitrepos/meridian-cli/.meridian/work/spawn-finalize-bugs/p1835-final-message.md:5)
  notes that the missing-field inject case returns `400`, not `422`.

The written spec expects `422` for schema violations:

- [`inject.md`](/home/jimyao/gitrepos/meridian-cli/.meridian/work-archive/spawn-control-plane-redesign/design/spec/inject.md:29)
  (`INJ-005`) says missing fields and wrong types should be `422`.
- [`http_surface.md`](/home/jimyao/gitrepos/meridian-cli/.meridian/work-archive/spawn-control-plane-redesign/design/spec/http_surface.md:33)
  also separates schema-validation failures (`422`) from semantic request
  failures (`400`).

### Code Path

Current implementation intentionally forces this case to `400`:

- [`server.py`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/app/server.py:105)
  defines `InjectRequest` with optional `event_type` and `payload`.
- [`server.py`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/app/server.py:110)
  raises `ValueError` when both are missing.
- [`server.py`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/app/server.py:168)
  the custom validation handler catches that `ValueError` and converts it to an
  HTTP `400`.

### Causal Chain

1. The request model accepts the individual fields as optional.
2. The "must provide event_type or payload" rule is enforced by a model-level
   validator that raises `ValueError`.
3. The custom exception handler maps that validation error to `400`.
4. Therefore missing-field inject requests return `400` by implementation,
   despite the spec requiring `422`.

### Verdict

Confirmed mismatch, but separate bug family. This is request validation / HTTP
surface classification, not finalize-path source-of-truth.

## Overall Family Verdict

There are two buckets:

- **One shared finalize bug family:** B-01, B-02, B-03
- **One separate HTTP validation bug:** B-04

The shared family is broader than "reads harness subprocess exit" in the
narrow sense. The actual source-of-truth problem is:

- semantic Codex terminal events are incomplete or ignored in
  `streaming_runner.py`
- natural stream drain defaults to success in `spawn_manager.py`
- app finalization persists the completion future result from
  `wait_for_completion()` instead of re-deriving terminal state from semantic
  stream evidence
- reaper only sees report/no-activity heuristics, so it cannot repair semantic
  misclassification or missing idle completion promptly

So the working hypothesis is directionally right for B-01 through B-03, but the
precise failure is "transport/drain completion outranks semantic stream
terminal signals," not only "harness subprocess exit outranks them."

## Issue Tracking

No separate GitHub issue filed from this lane. The current work item already
tracks these four bugs, and this investigation did not uncover a distinct
out-of-scope defect that needed separate backlog visibility.
