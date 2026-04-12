# Pre-Planning Notes: Spawn Lifecycle Rearchitecture

## Codebase Probes (Fresh)

### Files confirmed present
- `src/meridian/lib/launch/heartbeat.py` — 60 lines, async + threaded heartbeat writers
- `src/meridian/lib/launch/runner.py` — 868 lines, `execute_with_finalization` + `spawn_and_stream`
- `src/meridian/lib/launch/streaming_runner.py` — large, separate bidirectional runner
- `src/meridian/lib/launch/process.py` — 484 lines, primary process launch (PTY-based)
- `src/meridian/lib/ops/spawn/execute.py` — 918 lines, background/foreground spawn orchestration
- `src/meridian/lib/state/spawn_store.py` — 630 lines, event store + SpawnRecord
- `src/meridian/lib/state/reaper.py` — 493 lines, current state machine

### Heartbeat consumers (all must be cleaned)
1. `runner.py` line 53: imports `heartbeat_scope`, line 568: `heartbeat_path`, line 568: `async with heartbeat_scope`
2. `streaming_runner.py` line 49: imports `heartbeat_scope`, lines 405/421/744/872: heartbeat_path + usage
3. `process.py` line 46: imports `threaded_heartbeat_scope`, line 345: `with threaded_heartbeat_scope`
4. `sink.py`: `OutputSink.heartbeat()` — protocol method, keep as no-op stub
5. `output.py`: multiple heartbeat method impls — keep as stubs
6. `spawn_store.py` line 54: `_TERMINAL_RUNTIME_ARTIFACTS` includes "heartbeat"
7. `reaper.py`: heartbeat mtime checks in staleness detection
8. `cli/spawn.py` + `cli/doctor_cmd.py`: references to heartbeat
9. `ops/spawn/api.py`: references to heartbeat (likely in display context)

### cleanup_terminal_spawn_runtime_artifacts callers
1. `src/meridian/lib/ops/spawn/api.py` — two call sites (line ~161, line ~372)
2. `src/meridian/lib/state/spawn_store.py` — definition site

### PID file write sites
1. `runner.py` line 289-290: `atomic_write_text(log_dir / "harness.pid", ...)`
2. `streaming_runner.py` line 151/425/560: `harness.pid` writes
3. `process.py` line 375-378: `_record_primary_started` writes `harness.pid`
4. `execute.py` line 649: `atomic_write_text(log_dir / _BACKGROUND_PID_FILENAME, ...)`

### runner_pid source analysis
- Foreground: `os.getpid()` in runner.py's `execute_with_finalization`
- Background: wrapper PID (the `process.pid` from `subprocess.Popen` in execute.py)
- Primary: `os.getpid()` in process.py's `run_harness_process`
- Streaming: `os.getpid()` in streaming_runner.py

### Display layer
- `query.py:detail_from_row` — needs `exited_at` / `process_exit_code` display
- CLI formatters need post-exit annotation

## Leaf Distribution Hypothesis

Spec has 32 EARS statements (SLR-1 to SLR-34, minus SLR-24/25 removed).

Natural phase grouping:
- **Phase 1 (Foundation)**: RF-1 + RF-2 — psutil liveness module + SpawnExitedEvent + SpawnRecord changes. Covers SLR-2, SLR-3, SLR-11-14, SLR-22-23, partial SLR-20.
- **Phase 2 (Runner changes)**: All runner paths emit exited event + runner_pid + remove PID files + remove heartbeat. Covers SLR-1, SLR-4, SLR-15-17, SLR-21, SLR-29-33.
- **Phase 3 (Cleanup)**: RF-3 + RF-4 + RF-5 — delete heartbeat module, remove PID file writes (done in P2 but cleanup imports), remove cleanup function. Covers SLR-18-19.
- **Phase 4 (Reaper rewrite)**: RF-6 — replace reaper. Covers SLR-6-10, SLR-34.
- **Phase 5 (Display)**: Visibility changes. Covers SLR-26-28.

Phase 2 depends on Phase 1. Phase 3 depends on Phase 2. Phase 4 depends on Phase 1+2. Phase 5 depends on Phase 4.

Parallelism: Phase 2 and Phase 5 are sequential since Phase 5 needs new fields from Phase 1. However Phases 3 and 4 could potentially overlap once Phase 2 is done, since they touch different files.

## Constraints
- No backward compat needed — clean break
- psutil must be added as dependency first (Phase 1)
- `sink.py` heartbeat method: keep as protocol stub, don't break interface
- Pre-existing lint issues exist (import sort in 2 files) — not ours, ignore
- pyright and pytest not available in current env — smoke test via ruff + manual
- The streaming_runner is large and complex — must handle carefully

## Risk Areas
- streaming_runner.py heartbeat removal is spread across multiple code paths
- OutputSink.heartbeat() is a protocol interface — stub it, don't delete
- Background spawn wrapper_pid == runner_pid relationship must be precise
