# Architecture Overview — Spawn Control Plane

The spawn control plane is split along two axes:

1. **Operation kind** — *lifecycle* (cancel) vs. *intra-turn cooperative*
   (inject, interrupt). Lifecycle goes through OS process signals; intra-turn
   goes through the per-spawn control socket / `SpawnManager`.
2. **Surface** — *CLI*, *HTTP app server*, *control socket*, *agent tool*.
   Each surface composes the same underlying primitives; surfaces do not
   re-implement semantics.

```
                  ┌──────────────────────────────────────────────────────┐
                  │                       SURFACES                       │
                  │ CLI    HTTP app    Control socket    Agent tool      │
                  └─────┬────┬───────────────┬───────────────────────────┘
                        │    │               │
              lifecycle │    │ lifecycle     │ intra-turn (cooperative)
                  ┌─────▼────▼─────┐   ┌─────▼────────────────┐
                  │ AuthorizationG │   │ ControlSocketServer  │
                  │ uard           │   │ (per-spawn AF_UNIX)  │
                  └─────┬──────────┘   └─────┬────────────────┘
                        │                    │
                  ┌─────▼──────────┐   ┌─────▼────────────────┐
                  │ SignalCanceller│   │ SpawnManager.inject  │
                  │ (SIGTERM PID)  │   │ /interrupt + FIFO    │
                  └─────┬──────────┘   └─────┬────────────────┘
                        │                    │
                        │       ┌────────────▼─────────────┐
                        │       │ HarnessConnection.send_* │
                        │       └──────────────────────────┘
                        │
                        ▼ (signal lands in runner process)
                  ┌─────────────────────┐
                  │ Runner signal       │
                  │ handler →           │
                  │ stop_spawn          │
                  │ (status=cancelled,  │
                  │ origin=runner)      │
                  └─────────────────────┘
```

## Component Index

| File | Role |
|---|---|
| `architecture/cancel_pipeline.md` | Signal-driven cancel from any surface |
| `architecture/interrupt_pipeline.md` | Non-fatal interrupt routing and runner classification |
| `architecture/inject_serialization.md` | Per-spawn FIFO for control-socket and HTTP injects |
| `architecture/liveness_contract.md` | `runner_pid` + heartbeat ownership move |
| `architecture/http_endpoints.md` | HTTP shape, schema, error mapping |
| `architecture/authorization_guard.md` | Capability-by-ancestry guard |

## Cross-Cutting Decisions

- **Single source of truth for cancel semantics.** All cancel callers funnel
  through `SignalCanceller.cancel(spawn_id)` which encapsulates "resolve
  `runner_pid` → SIGTERM with grace → SIGKILL fallback → finalize-if-needed".
  The CLI command, HTTP endpoint, and timeout-based killers all share this
  one call.
- **Single source of truth for liveness.** `SpawnManager` owns the heartbeat
  for every spawn it manages. The legacy heartbeat in
  `runner.py` / `streaming_runner.py` becomes a thin wrapper that asks the
  manager for its session and lets the manager touch the file. Two-process
  runners that don't host a `SpawnManager` still touch the heartbeat via the
  same module-level helper, but the helper is the only writer.
- **Authorization at the surface.** `AuthorizationGuard` is a stateless
  function that surfaces import. `SpawnManager`, `SignalCanceller`, and
  `spawn_cancel_sync` remain unaware of caller identity; they trust their
  callers to have authorized the request.
- **Control socket loses lifecycle.** After this change the control socket
  vocabulary is `{user_message, interrupt}`. Any other `type` is rejected.
  This matches what the channel actually carries: data and intra-turn
  control.

## Why the FastAPI worker is "the runner"

The recurring confusion in #30 is that "runner" historically meant
"`runner.py`/`streaming_runner.py` the CLI process". After this change,
**runner** is whatever process owns the `HarnessConnection` and is
responsible for finalize. For the CLI, that's the streaming-runner process.
For the app server, that's the **FastAPI worker process**. The contract:

> The runner is the process whose PID is in `runner_pid` for an active
> spawn. It is responsible for heartbeat, terminal finalize (origin=runner
> or origin=launcher when an outer wrapper owns finalize), and SIGTERM
> handling.

This rephrasing closes the conceptual gap that produced #30.
