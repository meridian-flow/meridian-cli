# Cycle 2 Pre-Planning Notes

## Context
Cycle 1 fixed B-01/B-02/B-03 on CLI path via `_consume_subscriber_events()` in streaming_runner.py (which calls `_terminal_event_outcome()` and feeds `terminal_event_future`). But app path uses `_background_finalize()` which only awaits `DrainOutcome` from the completion future — terminal events are never consumed on that path.

## Key Observations from Source Probe

### C-01: Drain loop terminal event awareness
- `_terminal_event_outcome()` lives in `streaming_runner.py:245-298` — private module function
- Drain loop at `spawn_manager.py:250-361` streams events but never calls `_terminal_event_outcome()`
- Fix: drain loop itself must call `_terminal_event_outcome()` on each event, record last terminal outcome, prefer it in `finally` block
- Need to either: (a) move `_terminal_event_outcome` to shared module, or (b) import from streaming_runner and make it non-private
- `_TerminalEventOutcome` dataclass at streaming_runner.py:109-113 — also needs to be importable
- Drain loop `finally` block (lines 326-361) already has `cancel_sent` check from cycle 1 (line 343)
- New precedence: drain_cancelled > drain_error > cancel_sent > terminal_outcome > default succeeded

### C-02: One-way executor deletion
- `spawn_and_stream()` at runner.py:216-~760 and `execute_with_finalization()` at runner.py:434-~914
- Referenced from execute.py:24 (import), execute.py:476 (foreground fallback), execute.py:794 (background fallback)
- `supports_bidirectional` flag at adapter.py:134, claude.py:250, codex.py:326, opencode.py:197, execute.py:462, execute.py:773
- All three harnesses set `supports_bidirectional=True`
- Also check: runner.py:216 `spawn_and_stream` may have helper functions above it that only it uses

### C-03: OpenCode SIGKILL cleanup
- p1858 report: "Task exception was never retrieved" from `SpawnManager._drain_loop()` with `ClientPayloadError`
- Drain loop catches Exception at line 323-324 and re-raises — this should be fine
- The issue is likely that the drain task is abandoned without being awaited when the session cleanup happens
- Check `_cleanup_completed_session` and how drain_task is handled on connection errors

## Phase Parallelism Assessment
- C-01 and C-02 touch different files and functions — can parallelize
- C-03 is in spawn_manager.py same as C-01 — must sequence after C-01
- C-02 is pure deletion in runner.py and execute.py — independent of C-01/C-03

## Leaf Hypothesis
- Phase 1: C-01 (drain loop terminal event tracking) + C-03 (SIGKILL cleanup) — both in spawn_manager.py
- Phase 2: C-02 (one-way executor deletion) — runner.py + execute.py + adapter.py
- Phases can run in parallel since they touch different files
- But C-03 depends on understanding the drain loop shape after C-01, so C-01+C-03 should be one phase
