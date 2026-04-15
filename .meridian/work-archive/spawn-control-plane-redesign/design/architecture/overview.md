# Architecture Overview — Spawn Control Plane (v2r2)

The spawn control plane is split along two axes:

1. **Operation kind** — *lifecycle* (cancel) vs. *intra-turn cooperative*
   (inject, interrupt). Lifecycle goes through `SignalCanceller` (two-lane
   dispatch by `launch_mode`); intra-turn goes through the per-spawn
   control socket / `SpawnManager`.
2. **Surface** — *CLI*, *AF_UNIX HTTP app server*, *control socket*,
   *agent tool*. Each surface composes the same underlying primitives;
   surfaces do not re-implement semantics.

```
                  ┌──────────────────────────────────────────────────────┐
                  │                       SURFACES                       │
                  │ CLI    AF_UNIX HTTP    Control socket    Agent tool  │
                  └─────┬────┬──────────────────┬────────────────────────┘
                        │    │                  │
              lifecycle │    │ lifecycle        │ intra-turn (cooperative)
                  ┌─────▼────▼─────┐      ┌─────▼────────────────┐
                  │ AuthorizationG │      │ ControlSocketServer  │
                  │ uard           │      │ (per-spawn AF_UNIX)  │
                  └─────┬──────────┘      └─────┬────────────────┘
                        │                       │
                  ┌─────▼──────────────┐  ┌─────▼────────────────┐
                  │ SignalCanceller    │  │ SpawnManager.inject  │
                  │ (two-lane D-03)   │  │ /interrupt + FIFO    │
                  └──┬────────────┬───┘  └─────┬────────────────┘
                     │            │             │
          CLI spawns │            │ app spawns  │
          (SIGTERM)  │            │ (in-proc)   │
                     ▼            ▼             ▼
          ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐
          │Runner SIGTERM│ │manager.stop_ │ │HarnessConnection   │
          │handler →     │ │spawn() or    │ │.send_*             │
          │stop_spawn    │ │HTTP POST     │ └────────────────────┘
          │(cancelled,   │ │/cancel       │
          │origin=runner)│ │(origin=runner│
          └──────────────┘ └──────────────┘
```

## v2r2 key change: two-lane cancel (D-03)

v1 had two cancel pipelines hidden behind one name. v2 initial attempt
tried to unify them via a cancel-target coordination file, but reviewers
(p1794, p1795) blocked: external SIGTERM (timeout supervisors, OOM killers)
to the shared FastAPI worker PID cannot target a specific spawn because
no cancel-target file exists in that code path.

v2r2 explicitly adopts two-lane cancel:

- **CLI-launched spawns** (`foreground`/`background`): SIGTERM to
  `runner_pid`. Runner's signal handler calls
  `manager.stop_spawn(status="cancelled")`.
- **App-managed spawns** (`app`): `SignalCanceller` detects
  `launch_mode == "app"` and calls `manager.stop_spawn()` in-process,
  or routes through HTTP `POST /cancel` when cross-process.

**What IS unified:** `SignalCanceller.cancel(spawn_id)` is the single
entry point for all cancel callers. Both lanes converge on
`status="cancelled"`, `origin="runner"`.

## Component Index

| File | Role |
|---|---|
| `architecture/cancel_pipeline.md` | Signal-driven cancel from any surface |
| `architecture/interrupt_pipeline.md` | Non-fatal interrupt routing and classification |
| `architecture/inject_serialization.md` | Per-spawn FIFO for control-socket and HTTP injects |
| `architecture/liveness_contract.md` | `runner_pid` + heartbeat ownership move |
| `architecture/http_endpoints.md` | HTTP shape, schema, error mapping, AF_UNIX transport |
| `architecture/authorization_guard.md` | Capability-by-ancestry guard via AF_UNIX SO_PEERCRED |

## Cross-Cutting Decisions

- **Single cancel entry point, two lanes.** `SignalCanceller.cancel(spawn_id)`
  is the only cancel entry point. It dispatches by `launch_mode`:
  CLI spawns → SIGTERM with PID-reuse guard (D-15); app spawns →
  in-process `stop_spawn` or HTTP `POST /cancel`. Both lanes check
  the finalizing gate (CAN-008). No SIGKILL in any path (D-13).
- **Single liveness contract.** `SpawnManager` owns heartbeat for every
  spawn it manages. The heartbeat helper is the only writer.
- **Authorization at the surface.** `AuthorizationGuard` is a stateless
  function imported by surfaces. Inner components trust their callers.
  Depth-aware deny (D-14) prevents env-drop auto-promotion. Peercred
  failure → DENY for lifecycle ops (D-19); operator mode only via CLI.
- **Control socket loses lifecycle.** Vocabulary: `{user_message,
  interrupt}`. Any `cancel` type is rejected with a stable error.
- **AF_UNIX transport.** App server binds AF_UNIX, not TCP. Resolves
  BL-3 (caller identity via SO_PEERCRED) and BL-6 (no network exposure).
- **HTTP validation split.** Schema errors → 422 (FastAPI default);
  semantic errors → 400 (custom handler per D-17).

## Why the FastAPI worker is "the runner"

**Runner** = whatever process owns the `HarnessConnection` and is
responsible for finalize. For CLI: `streaming_runner.py` process. For
app server: **FastAPI worker process**.

The contract:

> The runner is the process whose PID is in `runner_pid` for an active
> spawn. It is responsible for heartbeat, terminal finalize
> (`origin=runner`), and SIGTERM handling.

v2 structural change: app-managed spawns finalize with `origin="runner"`
(not `origin="launcher"`) because the FastAPI worker IS the runner. No
dual finalize ownership — the background-finalize task writes
`origin="runner"` because that's what the worker is. The "wrapper writes
launcher" path only exists in the `streaming_serve.py` outer wrapper for
`meridian streaming serve`, which is a separate code path from the app
server.
