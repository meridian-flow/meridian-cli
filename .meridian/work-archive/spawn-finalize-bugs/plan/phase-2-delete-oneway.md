# Phase 2: Delete One-Way Executor

## Scope
C-02: Remove the legacy one-way executor code that no bundled harness uses.

## What to Delete

### 1. runner.py — bulk deletion

In `src/meridian/lib/launch/runner.py`, delete:
- `spawn_and_stream()` (starts at line ~216, ~215 lines)
- `execute_with_finalization()` (starts at line ~434, ~480 lines)
- Helper functions used ONLY by these two:
  - `_raw_return_code_matches_sigterm()` — check if anything else uses it
  - `_touch_heartbeat_file()` — check if anything else uses it (note: streaming_runner.py has its own version)
  - `_read_captured_output()` — check if anything else uses it
  - `_persist_captured_artifacts()` — check if anything else uses it
  - `_terminate_after_cancellation()` — check if anything else uses it
  - `_report_watchdog()` (the subprocess version, ~line 180) — check if anything else uses it
  - `SpawnResult` class — check if exported/used elsewhere
- Remove now-unused imports at the top of runner.py

### 2. execute.py — remove fallback routing

In `src/meridian/lib/ops/spawn/execute.py`:
- Line 24: remove `from meridian.lib.launch.runner import execute_with_finalization`
- Line 462-476: the `if harness.capabilities.supports_bidirectional:` branch — just call `execute_with_streaming` directly (remove the conditional)
- Lines 773-794: same pattern in the background worker path — remove the else branch
- Remove the `supports_bidirectional` check entirely since all harnesses are bidirectional

### 3. adapter.py — remove capability flag

In `src/meridian/lib/harness/adapter.py`:
- Line 134: remove `supports_bidirectional: bool = False`
- Only if no other code reads this field

In each harness file (claude.py, codex.py, opencode.py):
- Remove `supports_bidirectional=True` from capabilities construction

### 4. Verify no other references remain

Grep for `execute_with_finalization`, `spawn_and_stream`, `supports_bidirectional` across the codebase. All references should be gone.

## Files Touched
- `src/meridian/lib/launch/runner.py` — bulk deletion
- `src/meridian/lib/ops/spawn/execute.py` — remove fallback routing
- `src/meridian/lib/harness/adapter.py` — remove capability flag
- `src/meridian/lib/harness/claude.py` — remove flag
- `src/meridian/lib/harness/codex.py` — remove flag
- `src/meridian/lib/harness/opencode.py` — remove flag
- `src/meridian/lib/launch/cwd.py` — references runner.py docstring, may need update

## Exit Criteria
- `uv run ruff check .` clean
- `uv run pyright` clean (0 errors)
- `uv run pytest-llm` passes
- No references to deleted functions/classes remain in source
