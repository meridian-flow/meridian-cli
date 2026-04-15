# Spawn Control Plane Redesign

## Background

Smoke testing the `spawn inject` surface (smoke-gaps-followup work item) found four real bugs plus a missing authorization story. The bugs cluster around one architectural issue: the control socket carries both intra-turn operations (send text, interrupt) and process-lifecycle operations (cancel), and those don't belong on the same channel. Plus app-server-launched spawns don't satisfy the same liveness contract as CLI-launched spawns, recreating the #14 false-positive-reap class we just closed.

## Issues in scope

- **#28** — `spawn inject --interrupt` finalizes the spawn as `failed` instead of interrupting the current turn.
- **#29** — `spawn inject --cancel` leaves the spawn `succeeded` instead of `cancelled`.
- **#30** — HTTP-launched / app-managed spawns get spurious `missing_worker_pid` reaper stamps because they don't populate `runner_pid` the way CLI-launched spawns do. Same bug class as #14, still present on the app-server path.
- **#31** — Concurrent inject reverses order + drops one ack; HTTP inject schema doesn't accept interrupt/cancel (CLI/HTTP parity gap).

## Hard constraints

- **App server stays.** Web GUI is still a supported surface; design must include it, not propose removing it.
- **Reaper authority model stays.** The recent refactor's origin/authority rule (`AUTHORITATIVE_ORIGINS`, `origin=runner|launcher|cancel|launch_failure`, reconciler non-authoritative) is the foundation the fix builds on, not something to rework.
- **No real users, no backcompat.** Change schemas and surfaces freely.

## Direction (pre-design consensus to verify)

The design should evaluate this shape and either adopt it, refine it, or push back with a better one:

1. **Collapse cancel onto process signals.** `meridian spawn cancel <id>` reads `runner_pid` and sends SIGTERM (grace period then SIGKILL). Runner's existing signal handler calls `finalize_spawn(origin=cancel, status=cancelled)`. Same path for CLI, HTTP, and any future caller. Removes cancel from the control socket entirely.
2. **Interrupt stays on the control socket, but becomes non-fatal.** Interrupt stops the current turn's generation/tool call; the runner remains alive waiting for the next message. Distinct from cancel, which is lifecycle.
3. **App-managed spawns satisfy the liveness contract.** Either populate `runner_pid` on app-launched SpawnRecord, or introduce an equivalent signal (heartbeat touch from the FastAPI worker, an `app_pid` field, an `origin=app` convention). Reaper must be able to tell "app-managed + alive" from "dead, reap."
4. **HTTP surface parity.** `POST /api/spawns/{id}/inject` accepts `text` + `interrupt` (intra-turn). `POST /api/spawns/{id}/cancel` as a separate endpoint for lifecycle. Schema follows whatever shape #1 and #2 settle on.
5. **Authorization gate on cancel/interrupt.** Arbitrary LLM subagents should not be able to cancel or interrupt sibling/parent spawns. Design must propose the capability model (caller identity via `MERIDIAN_SPAWN_ID`? parent-ancestry check on spawn record? separate tool surface that agent profiles allowlist?). Text-inject is cooperative and stays open; lifecycle ops get gated.

## Success criteria

- #28, #29, #30, #31 all have clear fix paths in the design package.
- Reaper liveness contract is one contract, not two (CLI vs app).
- Cancel semantics are consistent across CLI invocation, HTTP endpoint, and timeout-based external kill for CLI-launched spawns; app-managed spawns document worker-wide timeout-kill behavior separately.
- Interrupt is actually non-fatal end-to-end.
- LLM-accessible surface for cancel/interrupt is explicitly scoped — either gated at meridian, restricted at profile level, or removed entirely.
- Design names what tests (unit, smoke, fault-injection) will prove each behavior before the implementation phase starts.

## Out of scope

- Reaper internals (decide/IO split, authority rule, heartbeat window) — keep as-is unless the fix genuinely needs to change them.
- Streaming runner internals unrelated to signal handling and control-socket message routing.
- Web GUI code beyond the thin HTTP endpoint layer.

## Artifacts to read

- `src/meridian/cli/spawn_inject.py`
- `src/meridian/cli/spawn.py` (CLI registration, `_spawn_inject`)
- `src/meridian/lib/streaming/control_socket.py`
- `src/meridian/lib/streaming/spawn_manager.py`
- `src/meridian/lib/app/server.py` (`inject_message`, spawn creation path)
- `src/meridian/lib/launch/runner.py` + `streaming_runner.py` (signal handling, finalize_spawn call sites)
- `src/meridian/lib/state/reaper.py` + `decide_reconciliation`
- `src/meridian/lib/state/spawn_store.py` (`SpawnOrigin`, authority rule)
- Smoke findings: `.meridian/work-archive/smoke-gaps-followup/smoke-inject.md` (once archived) or `.meridian/work/smoke-gaps-followup/smoke-inject.md`
- Recent reaper refactor design: `.meridian/work-archive/orphan-run-reaper-fix/design/` (context only, not to be reworked)
