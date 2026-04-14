# Refactor Agenda

Structural prep the planner must sequence before or alongside feature work.
Each entry names a touchpoint, the rearrangement, and why it is required
before the behavioral change it unblocks.

## R-01 — Extract heartbeat helper

- **Touch**: `src/meridian/lib/launch/runner.py`, `streaming_runner.py`,
  new `src/meridian/lib/streaming/heartbeat.py`.
- **Change**: Move the inline heartbeat loop from both runners into a
  shared module-level `heartbeat_loop(state_root, spawn_id, interval)`
  coroutine. No behavior change in runners.
- **Unblocks**: LIV-003 (single writer) and app-server heartbeat adoption.
- **Sequencing**: Foundation — land first, before any `SpawnManager`
  ownership work.

## R-02 — Centralize inject/interrupt serialization

- **Touch**: `src/meridian/lib/streaming/spawn_manager.py`, new
  `src/meridian/lib/streaming/inject_lock.py`.
- **Change**: Introduce per-spawn `asyncio.Lock` registry and wrap
  `SpawnManager.inject` + `SpawnManager.interrupt` with it. No semantics
  change for sequential callers.
- **Unblocks**: INJ-002, INJ-003, INT-006, INT-007.
- **Sequencing**: Foundation — land before anyone relies on linearizable
  ordering in tests or surface code.

## R-03 — Split `spawn_cancel_sync` into a signal canceller class

- **Touch**: `src/meridian/lib/ops/spawn/api.py`, new
  `src/meridian/lib/streaming/signal_canceller.py`.
- **Change**: Move cancel orchestration (resolve pid, SIGTERM, wait, SIGKILL
  fallback, finalize-if-needed) into `SignalCanceller`. `spawn_cancel_sync`
  becomes a thin sync wrapper calling the async class with `anyio.run`.
  `_resolve_cancel_pid` renames to `_resolve_runner_pid` and the order
  flips from worker-first to runner-first.
- **Unblocks**: CAN-001..CAN-008, consolidated cancel pipeline.
- **Sequencing**: Prep — land before removing `SpawnManager.cancel` so
  callers have a replacement to import.

## R-04 — Narrow `_terminal_event_outcome`

- **Touch**: `src/meridian/lib/launch/streaming_runner.py`.
- **Change**: Classifier no longer treats `turn/completed` as spawn-terminal
  for codex (or any harness emitting per-turn status). `turn` payloads still
  reach `output.jsonl`; only the drain-loop side-effect changes.
- **Unblocks**: INT-001, INT-002, INT-003.
- **Sequencing**: Must land before interrupt routing goes live end-to-end;
  otherwise interrupt would still crash the spawn.

## R-05 — Reshape HTTP spawn-control surface

- **Touch**: `src/meridian/lib/app/server.py`.
- **Change**:
  - Rewrite `InjectRequest` with pydantic `model_validator` accepting text
    xor interrupt.
  - Add `POST /api/spawns/{id}/cancel`.
  - Remove `DELETE /api/spawns/{id}` route; install 405 handler.
  - Remove inline cancel dispatch that called `SpawnManager.cancel`.
- **Unblocks**: HTTP-001..HTTP-005, CAN-004, CAN-005, INJ-005, INT-005.
- **Sequencing**: Can land after R-03 and R-04; independent of R-01/R-02
  at the wire level, but needs R-02 to uphold FIFO guarantees in practice.

## R-06 — Delete control-socket cancel and CLI `--cancel`

- **Touch**: `src/meridian/lib/streaming/control_socket.py`,
  `src/meridian/cli/spawn_inject.py`,
  `src/meridian/lib/streaming/spawn_manager.py`.
- **Change**: Remove the `"cancel"` branch from the control-socket router;
  add an explicit reject with `{"ok": false, "error": "cancel is
  disabled on the control socket"}`. Remove the `--cancel` flag from
  `meridian spawn inject` (the CLI `meridian spawn cancel` already exists
  and will route through `SignalCanceller`). Delete `SpawnManager.cancel`
  and its inbound `cancel` handling.
- **Unblocks**: CAN-006.
- **Sequencing**: Land after R-03 / R-05 so CLI users always have a
  working cancel path through `meridian spawn cancel`.

## R-07 — App-server runner_pid and heartbeat wiring

- **Touch**: `src/meridian/lib/app/server.py`.
- **Change**: Populate `runner_pid=os.getpid()` when reserving a spawn;
  start the heartbeat loop via `SpawnManager._start_heartbeat()` in
  `_run_managed_spawn`; ensure cleanup path stops it.
- **Unblocks**: LIV-001, LIV-003, LIV-005.
- **Sequencing**: Requires R-01. Can land in parallel with R-03..R-06 in
  a different file.

## R-08 — Introduce `AuthorizationGuard` and compose at surfaces

- **Touch**: new `src/meridian/lib/ops/spawn/authorization.py`; surfaces in
  `src/meridian/cli/spawn_cancel.py`, `src/meridian/cli/spawn_inject.py`,
  `src/meridian/lib/app/server.py`,
  `src/meridian/lib/streaming/control_socket.py`.
- **Change**: Implement pure `authorize(...)` function + `caller_from_env`
  / `_caller_from_http` / `_caller_from_socket_peer` adapters. Compose in
  CLI, HTTP, control-socket surfaces per architecture.
- **Unblocks**: AUTH-001..AUTH-006.
- **Sequencing**: Independent of other refactors; can be the last feature
  landed.

## R-09 — CLI cancel dispatcher for app-managed spawns

- **Touch**: `src/meridian/cli/spawn_cancel.py`.
- **Change**: Detect app-managed spawns (via the spawn record's launch
  mode) and route cancel through HTTP `POST /cancel` instead of signaling
  the FastAPI worker directly. Non-app spawns continue to SIGTERM the
  runner pid. This avoids the FastAPI-worker-SIGTERM problem described
  in `liveness_contract.md`.
- **Unblocks**: CAN-001, CAN-002 for app-managed spawns.
- **Sequencing**: Must land alongside R-05 so the HTTP endpoint exists
  when the CLI dispatcher routes to it.

## Refactor-to-phase hinting

The planner is free to compose phases however works best, but this agenda
clusters naturally:

- **Phase A (foundation)**: R-01, R-02.
- **Phase B (cancel pipeline)**: R-03, then R-06.
- **Phase C (classifier + interrupt)**: R-04 in parallel with B.
- **Phase D (HTTP surface)**: R-05, R-09.
- **Phase E (liveness)**: R-07 (can parallelize with B–D given R-01 done).
- **Phase F (authorization)**: R-08 last.

Each R-entry is independently testable; the planner should exit each phase
on its own tester lane rather than bundling.
