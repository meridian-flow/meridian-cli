# Pre-Planning Notes — Spawn Control Plane Redesign

## Feasibility Re-verification (all current)

- `LaunchMode` at `spawn_store.py:54` is `Literal["background", "foreground"]` — R-11 adds `"app"`.
- `SpawnStartEvent.launch_mode` typed as `str | None` (line 103), `SpawnRecord.launch_mode` as `LaunchMode | None` (line 156). R-11 must tighten both.
- `SpawnManager.cancel` exists at `spawn_manager.py:365` — R-06 removes it.
- `app_cmd.py` uses TCP with `--host`/`--port` — R-10 replaces with AF_UNIX.
- No `authorization.py` exists yet — R-08 creates it fresh.
- No `signal_canceller.py` exists yet — R-03 creates it fresh.
- No `inject_lock.py` exists yet — R-02 creates it fresh.
- No `heartbeat.py` exists yet — R-01 creates it fresh.

## Module-Scoped Constraints

- `streaming_runner.py` has both SIGTERM handling and `_terminal_event_outcome` — R-04 touches only the classifier, R-03 depends on existing signal handling unchanged.
- `server.py` is large (app server) — R-05, R-07, R-10 all touch it. Must sequence R-10 first (transport change), then R-07 (liveness), then R-05 (HTTP reshape). Alternatively, R-07 can parallel with R-05 if they touch disjoint sections.
- `control_socket.py` touched by R-02 (lock scope for acks) and R-06 (reject cancel type). These are disjoint changes and can land in either order.

## Hard Constraints from Caller

- **R-08 (AuthorizationGuard) BEFORE R-05 and R-09** — no lifecycle surface exposed without the guard.
- **AF_UNIX transport (D-18)** — app server on Unix socket, not TCP.
- **Two-lane cancel (D-03)** — SIGTERM for CLI, in-process for app.
- **No SIGKILL (D-13)** — remove from pipeline entirely.
- **Peercred fail-closed (D-19)** — DENY, not operator fallback.
- **All integration phases need @smoke-tester** — AF_UNIX transport, SIGTERM handling, control-socket vocab change.

## Leaf Distribution Hypothesis

Phase clustering follows the refactors.md phase hints closely:

- **Phase A (foundation)**: R-01 + R-02 + R-11. Creates heartbeat.py, inject_lock.py, extends LaunchMode. Zero behavioral risk. ~3 files created, ~4 files modified.
- **Phase B (transport + auth)**: R-10 + R-08. AF_UNIX transport then auth guard. Two new files + significant server.py + app_cmd.py changes. Integration boundary — MUST smoke test AF_UNIX.
- **Phase C (cancel pipeline)**: R-09 + R-03 + R-06. SignalCanceller with two-lane dispatch, CLI cancel dispatcher, control-socket cancel removal. Integration boundary — MUST smoke test SIGTERM handling.
- **Phase D (classifier)**: R-04. Narrow `_terminal_event_outcome`. Small, independent. Can parallel with B/C.
- **Phase E (HTTP surface)**: R-05. Requires B + C. Major server.py rewrite.
- **Phase F (liveness)**: R-07. Requires A + R-11. App-server runner_pid + heartbeat.

Parallelism: A can run first (foundation). Then B, D, F can run in parallel. Then C (needs B). Then E (needs B+C).

## Probe Gaps

None — all 13 feasibility items verified, all closed. No stale entries.
