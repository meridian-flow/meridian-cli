# Refactor Agenda (v2r2)

Structural prep the planner must sequence. Each entry names touchpoints,
the rearrangement, and why it is required before the behavioral change
it unblocks.

v2r2 changes from v2:
- R-09 RESTORED — two-lane cancel (D-03) requires the CLI cancel
  dispatcher to detect `launch_mode="app"` and route through HTTP or
  in-process cancel instead of SIGTERM.
- R-12 REMOVED — app-worker per-spawn SIGTERM handler is no longer
  needed. Two-lane cancel routes app-spawn cancellation through
  `manager.stop_spawn()` or HTTP, not SIGTERM to the shared worker.
- Phase hints updated to reflect two-lane cancel and D-17/D-19 changes.

v2 changes from v1:
- R-08 (authorization guard) moved UP in sequencing — must land BEFORE
  any refactor that exposes new lifecycle surfaces (resolves BL-5 major).
- R-10 (AF_UNIX transport) added — foundation for BL-3 + BL-6.
- R-11 (launch_mode schema) added — BL-2 prerequisite.

## R-01 — Extract heartbeat helper

- **Touch**: `runner.py`, `streaming_runner.py`, new `heartbeat.py`.
- **Change**: Move inline heartbeat loop into shared
  `heartbeat_loop(state_root, spawn_id, interval)`. No behavior change.
- **Unblocks**: LIV-003, app-server heartbeat.
- **Sequencing**: Foundation — land first.

## R-02 — Centralize inject/interrupt serialization

- **Touch**: `spawn_manager.py`, new `inject_lock.py`.
- **Change**: Per-spawn `asyncio.Lock`. Wrap `inject` and `interrupt`
  with lock scope including ack emission (v2 extended scope per D-05).
  `on_result` callback pattern for control-socket replies. Change
  `_record_inbound(...)` to return the appended line index and thread it
  through `InjectResult(inbound_seq, noop, error)`. HTTP clients use
  `inbound_seq` for ordering (D-18).
- **Unblocks**: INJ-002, INJ-003, INT-006, INT-007.
- **Sequencing**: Foundation — land before anyone relies on ordering.

## R-03 — Split `spawn_cancel_sync` into SignalCanceller

- **Touch**: `ops/spawn/api.py`, new `signal_canceller.py`.
- **Change**: Move cancel orchestration into `SignalCanceller` with
  two-lane dispatch (D-03): `launch_mode` in `("foreground", "background")`
  → SIGTERM to `runner_pid`; `launch_mode == "app"` → in-process
  `manager.stop_spawn()` or HTTP `POST /cancel`. Adds PID-reuse guard
  (D-15), finalizing gate (CAN-008). No SIGKILL in any path (D-13).
  Constructor accepts optional `manager: SpawnManager | None` for
  in-process app-spawn cancel.
- **Unblocks**: CAN-001..CAN-008.
- **Sequencing**: Requires R-08 (guard), R-09 (CLI dispatcher), and
  R-11 (schema). Land after all three so cancel surface is gated from
  the start.

## R-04 — Narrow `_terminal_event_outcome`

- **Touch**: `streaming_runner.py`.
- **Change**: `turn/completed` is never spawn-terminal. `turn` payloads
  reach `output.jsonl` but don't trigger `stop_spawn`.
- **Unblocks**: INT-001, INT-002, INT-003.
- **Sequencing**: Can land independently. Must precede interrupt
  end-to-end testing.

## R-05 — Reshape HTTP spawn-control surface

- **Touch**: `app/server.py`.
- **Change**:
  - Rewrite `InjectRequest` with pydantic `model_validator`.
  - Add custom exception handler to remap `ValueError` from
    `model_validator` to HTTP 400 (D-17). Schema validation stays 422.
  - Add `POST /api/spawns/{id}/cancel` (gated by R-08). Cancel handler
    passes `manager=app_state.manager` to `SignalCanceller` for
    in-process app-spawn cancel (D-03).
  - Remove `DELETE /api/spawns/{id}`; install 405 handler.
  - Remove inline cancel dispatch that called `SpawnManager.cancel`.
  - Update `require_authorization` to catch `PeercredFailure` and
    return 403 (D-19).
- **Unblocks**: HTTP-001..HTTP-006, CAN-004, CAN-005, INJ-005, INT-005.
- **Sequencing**: Requires R-03 (SignalCanceller), R-08 (guard), R-10
  (AF_UNIX). No ungated lifecycle surface.

## R-06 — Delete control-socket cancel and CLI `--cancel`

- **Touch**: `control_socket.py`, `spawn_inject.py`, `spawn_manager.py`.
- **Change**: Remove `"cancel"` branch from control socket; add reject.
  Remove `--cancel` from `spawn inject`. Delete `SpawnManager.cancel`.
- **Unblocks**: CAN-006.
- **Sequencing**: After R-03 so CLI users have `meridian spawn cancel`.

## R-07 — App-server runner_pid and heartbeat wiring

- **Touch**: `app/server.py`.
- **Change**: Set `runner_pid=os.getpid()` at spawn creation.
  `launch_mode="app"`. Start heartbeat via SpawnManager. Change
  background-finalize to `origin="runner"`.
- **Unblocks**: LIV-001, LIV-003, LIV-005.
- **Sequencing**: Requires R-01, R-11. Can parallel with R-03..R-06.

## R-08 — Introduce `AuthorizationGuard` (MOVED UP in v2)

- **Touch**: new `ops/spawn/authorization.py`; surfaces in
  `spawn_cancel.py`, `spawn_inject.py`, `app/server.py`,
  `control_socket.py`.
- **Change**: Implement `authorize()` with depth-aware deny (D-14).
  `caller_from_env` + `_caller_from_peercred` + `_caller_from_socket_peer`.
  `_caller_from_peercred` raises `PeercredFailure` on extraction failure;
  surfaces catch and DENY (D-19). Compose at all surfaces.
- **Unblocks**: AUTH-001..AUTH-007.
- **Sequencing**: **BEFORE R-03, R-05** — no lifecycle surface is exposed
  without the guard. This is the v2 fix for the BL-5 sequencing issue.

## R-09 — CLI cancel dispatcher for app-managed spawns (v2r2 RESTORED)

- **Touch**: `ops/spawn/api.py`, `signal_canceller.py`.
- **Change**: When `SignalCanceller.cancel()` detects
  `launch_mode == "app"` and `self._manager is None` (cross-process),
  route cancel via HTTP `POST /api/spawns/{id}/cancel` to the AF_UNIX
  socket at `.meridian/app.sock`. Parse response: 200 → success,
  409 → already terminal, 503 → finalizing.
- **Unblocks**: D-03 (two-lane cancel for app spawns from CLI).
- **Sequencing**: After R-10 (AF_UNIX transport). Before R-03 integration.

## R-10 — AF_UNIX transport for app server (v2 new)

- **Touch**: `cli/app_cmd.py`, `app/server.py`.
- **Change**: Replace `--host`/`--port` with `--uds`. Uvicorn binds to
  `.meridian/app.sock`. Add `--proxy` subcommand for browser access.
  Remove `--host` flag entirely.
- **Unblocks**: HTTP-006, AUTH transport (BL-3), network exposure (BL-6).
- **Sequencing**: Foundation for R-08's HTTP caller identification.
  Land before R-05 and R-08.

## R-11 — Extend `launch_mode` schema (v2 new)

- **Touch**: `state/spawn_store.py`.
- **Change**: `LaunchMode = Literal["background", "foreground", "app"]`.
  App server uses `"app"` in `start_spawn`. Tighten both
  `SpawnStartEvent.launch_mode` and `SpawnUpdateEvent.launch_mode` to
  `LaunchMode | None` (currently `SpawnStartEvent` uses `str | None`).
- **Unblocks**: BL-2 (durable owner discriminator). Required by R-07.
- **Sequencing**: Schema-only, no behavioral change. Land early.

## Phase hinting (v2r2 revised)

The planner is free to compose phases; this agenda clusters naturally:

- **Phase A (foundation)**: R-01, R-02, R-11.
- **Phase B (transport + auth)**: R-10, then R-08. Auth must land before
  any lifecycle surface. AF_UNIX must land before auth's HTTP path.
  R-08 includes D-19 (peercred failure → DENY).
- **Phase C (cancel pipeline)**: R-09, then R-03, then R-06.
  Requires Phase B. R-09 adds the HTTP cancel dispatch for app-managed
  spawns (cross-process path); R-03 integrates the two-lane dispatcher.
- **Phase D (classifier + interrupt)**: R-04, parallel with B/C.
- **Phase E (HTTP surface)**: R-05. Requires B + C. Includes D-17
  (400/422 validation split) and D-19 (peercred deny in auth dep).
- **Phase F (liveness)**: R-07. Requires A + schema from R-11.

Key sequencing constraints:
- **R-08 (auth) before R-03/R-05** — no lifecycle surface exposed
  without the guard (v2 fix for BL-5).
- **R-10 (AF_UNIX) before R-08** — auth's HTTP path needs AF_UNIX
  for SO_PEERCRED.
- **R-09 (HTTP cancel dispatch) before R-03** — two-lane cancel needs
  the cross-process HTTP path for app-managed spawns.
