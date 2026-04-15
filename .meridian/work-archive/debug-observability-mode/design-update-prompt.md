# Task: Update --debug Observability Design for Post-Convergence Codebase

## Context

The --debug observability mode was designed before streaming convergence landed. The core design is sound (DebugTracer contract, JSONL schema, trace helpers, per-adapter hooks, 18 reviewed decisions). But the codebase structure changed significantly — hook locations, config propagation paths, and new files need updating.

## What Changed (Streaming Convergence)

1. **ConnectionConfig + SpawnParams split**: `ConnectionConfig` is now transport-only (~9 fields). `SpawnParams` carries command-building config. `connection.start(config, params)` signature.
2. **SpawnExtractor protocol**: New extraction protocol decouples extraction from SubprocessHarness. `StreamingExtractor` wraps `HarnessConnection`.
3. **streaming_runner.py**: New file that routes child spawns (`meridian spawn`) through the streaming pipeline (SpawnManager → HarnessConnection). This is the PRIMARY spawn path now.
4. **DrainOutcome**: Completion surface exposed by SpawnManager to callers without writing terminal state.
5. **Single-writer finalization**: SpawnManager never calls `spawn_store.finalize_spawn()` — the runner owns finalization.
6. **stop_connection()**: New SpawnManager method for cleanup without terminal-state writes.
7. **Report watchdog**: Watches for `report.md` appearing, grace period, then stop.
8. **Envelope format**: Drain loop writes `{event_type, harness_id, payload}` envelopes to output.jsonl.

## What to Update

1. **Config propagation**: Where does `debug_tracer` live now — ConnectionConfig or SpawnParams? ConnectionConfig is transport-only, but the tracer IS per-connection. Decide.
2. **SpawnManager hooks**: Drain loop, SpawnSession, cleanup paths, start_spawn() all changed. Update hook locations to match current code.
3. **streaming_runner.py integration**: How does `--debug` propagate from `meridian spawn --debug` through streaming_runner to SpawnManager? This is the main spawn path now.
4. **SpawnExtractor**: Does it need tracer awareness? It wraps HarnessConnection for extraction.
5. **CLI integration**: Add streaming_runner path alongside streaming serve and app.
6. **Files changed table**: Update to reflect current file structure.

## What NOT to Change

- DebugTracer class contract (D1, D6, D8)
- JSONL event schema
- Shared trace helpers pattern (D15)
- Neutral package placement (D7)
- Per-adapter hook tables (unless adapter code changed)
- Payload truncation (D4)
- No-op pattern (D6)

## Deliverables

- Updated design/overview.md
- Updated design/debug-tracer.md
- New decisions appended to decisions.md for any choices that differ from the original
