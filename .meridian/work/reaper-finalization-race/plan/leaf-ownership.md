# Leaf Ownership Ledger

| EARS ID | Summary | Owning Phase | Status | Tester Lane | Evidence Pointer |
|---|---|---|---|---|---|
| SLR-1 | Runner appends `exited` immediately after `spawn_and_stream` returns and before enrichment/finalize work. | Phase 2 | planned | `@unit-tester`, `@smoke-tester` | — |
| SLR-2 | `exited` carries `spawn_id`, raw `exit_code`, and `exited_at`. | Phase 1 | planned | `@unit-tester` | — |
| SLR-3 | `exited` excludes report content, duration, cost, and token usage. | Phase 1 | planned | `@unit-tester` | — |
| SLR-4 | `exited` without `finalize` still projects as `running`. | Phase 1 | planned | `@unit-tester`, `@verifier` | — |
| SLR-5 | `finalize` remains the sole terminal event with unchanged first-terminal semantics. | Phase 1 | planned | `@unit-tester`, `@verifier` | — |
| SLR-6 | Pre-exit active spawns use `psutil` on the responsible PID and fail as `orphan_run` after startup grace. | Phase 4 | planned | `@unit-tester`, `@smoke-tester` | — |
| SLR-7 | Post-exit active spawns stay non-terminal while the runner PID is alive. | Phase 4 | planned | `@unit-tester`, `@smoke-tester` | — |
| SLR-8 | Post-exit dead-runner reconciliation uses durable-report completion or `orphan_finalization`. | Phase 4 | planned | `@unit-tester`, `@smoke-tester` | — |
| SLR-9 | Post-exit reconciliation uses no grace, heartbeat, or stale-threshold timers. | Phase 4 | planned | `@unit-tester`, `@verifier` | — |
| SLR-10 | Startup grace remains only for spawns with no `exited` and no `finalize`. | Phase 4 | planned | `@unit-tester` | — |
| SLR-11 | All liveness checks use `psutil.pid_exists()` and `psutil.Process(pid).create_time()`. | Phase 1 | planned | `@unit-tester` | — |
| SLR-12 | PID reuse compares `create_time()` against `started_at` plus tolerance. | Phase 1 | planned | `@unit-tester` | — |
| SLR-13 | Liveness logic works cross-platform without platform-specific branches. | Phase 1 | planned | `@verifier`, `@unit-tester` | — |
| SLR-14 | `NoSuchProcess` counts dead and `AccessDenied` counts alive. | Phase 1 | planned | `@unit-tester` | — |
| SLR-15 | Standard runner stops writing runtime coordination files to spawn directories. | Phase 2 | planned | `@unit-tester`, `@smoke-tester` | — |
| SLR-16 | Streaming runner stops writing `harness.pid` and heartbeat files. | Phase 2 | planned | `@unit-tester`, `@smoke-tester` | — |
| SLR-17 | Primary launcher stops writing `harness.pid` and heartbeat files. | Phase 2 | planned | `@unit-tester`, `@smoke-tester` | — |
| SLR-18 | Completed spawn directories contain only durable artifacts. | Phase 3 | planned | `@smoke-tester`, `@verifier` | — |
| SLR-19 | `cleanup_terminal_spawn_runtime_artifacts()` is removed or a no-op because runtime artifacts no longer exist. | Phase 3 | planned | `@verifier`, `@unit-tester` | — |
| SLR-20 | Reaper sources worker and wrapper PIDs from the event stream only. | Phase 4 | planned | `@unit-tester`, `@verifier` | — |
| SLR-21 | Launch flows record the finalizing process PID as `runner_pid` in the event stream. | Phase 2 | planned | `@unit-tester`, `@smoke-tester` | — |
| SLR-22 | `start` carries `runner_pid`. | Phase 1 | planned | `@unit-tester` | — |
| SLR-23 | No legacy fallback paths remain; active spawns are assumed to use `runner_pid` and `exited`. | Phase 4 | planned | `@verifier`, `@unit-tester` | — |
| SLR-26 | `spawn show` exposes `running (exited N, awaiting finalization)` during post-exit finalization. | Phase 3 | planned | `@unit-tester`, `@smoke-tester` | — |
| SLR-27 | `spawn list` keeps exited-but-not-finalized spawns in `running` with a visible exited sub-state indicator. | Phase 3 | planned | `@unit-tester`, `@smoke-tester` | — |
| SLR-28 | `spawn wait` still waits for `finalize` by default. | Phase 3 | planned | `@smoke-tester`, `@verifier` | — |
| SLR-29 | Background spawns keep `wrapper_pid` and `worker_pid` parity in the event stream. | Phase 2 | planned | `@unit-tester`, `@smoke-tester` | — |
| SLR-30 | Background wrapper writes `exited` when its harness child exits. | Phase 2 | planned | `@unit-tester`, `@smoke-tester` | — |
| SLR-31 | Background post-exit reconciliation checks wrapper liveness, not harness-child liveness. | Phase 4 | planned | `@unit-tester`, `@smoke-tester` | — |
| SLR-32 | Streaming runner writes `exited` when drain/subprocess completion is known. | Phase 2 | planned | `@unit-tester`, `@smoke-tester` | — |
| SLR-33 | Streaming runner writes no runtime PID or heartbeat files. | Phase 2 | planned | `@unit-tester`, `@smoke-tester` | — |
| SLR-34 | Reaper logic shrinks to the under-80-line trivial branch shape. | Phase 4 | planned | `@verifier`, `@reviewer` | — |
