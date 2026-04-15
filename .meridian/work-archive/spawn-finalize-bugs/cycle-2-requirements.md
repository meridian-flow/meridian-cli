# Cycle 2 — App-Path Finalize Fix + One-Way Executor Deletion

Follow-up to cycle 1 (commit cfefbcd + 1bed682). Cycle 1 fixed finalize
on CLI path but left app path broken for B-01 on all harnesses and
B-03 on Claude+Codex. This cycle closes those gaps and deletes the
legacy one-way executor that no harness uses anymore.

## Evidence

- `p1857/report.md` — Codex app-spawn smoke: B-01 falsified, B-03 falsified,
  B-02/B-04/B-05 verified.
- `p1858/report.md` — Claude + OpenCode app-spawn smoke: B-01 falsified
  on both; B-03 falsified on Claude, verified on OpenCode (by accident —
  `ClientPayloadError` raises in drain → `except` branch catches → failed).
- `research-stream-topology.md` — legacy `execute_with_finalization()` /
  `spawn_and_stream()` in `runner.py:216-431,434-760` is selected only
  for `harness.supports_bidirectional=False`; all three bundled harnesses
  declare `supports_bidirectional=True`, so it's unreachable.

## Scope

### C-01: App-path drain-loop consumes terminal events (generic fix)

Root cause (per investigation lane-b):
- CLI path uses `execute_with_streaming` which runs `_consume_subscriber_events()`
  to watch the event stream and feed `_terminal_event_outcome()` into the
  finalize path.
- App path uses `_background_finalize()` which only awaits `DrainOutcome`
  from the completion future. Terminal events are never consumed.
- Drain loop `finally` defaults to `succeeded/0` on clean connection close,
  regardless of whether a terminal event said otherwise.

Fix shape: make the drain loop itself observe terminal events.
As each event streams through, pass it through `_terminal_event_outcome()`.
If any event resolves to a terminal outcome, record it on the session.
On `finally`, prefer the recorded terminal outcome over the default
`succeeded/0` classification.

This is harness-agnostic and fixes B-01 + B-03 across Claude, Codex,
and OpenCode on the app path simultaneously.

Touches: `spawn_manager.py` drain loop; possibly `streaming_runner.py`
if `_terminal_event_outcome` needs to become more widely callable.

### C-02: Delete the one-way executor

Target: `src/meridian/lib/launch/runner.py`
- `execute_with_finalization()` (lines 216-431)
- `spawn_and_stream()` (lines 434-760)
- Any fallback-selection logic in `src/meridian/lib/ops/spawn/execute.py:462-476,773-794`
  that routes to these when `supports_bidirectional=False`.

Verification:
- All three bundled harnesses declare `supports_bidirectional=True`,
  so nothing should route into the deleted code.
- Remove `supports_bidirectional` capability flag entirely if it has no
  other consumer after deletion (all harnesses now assume bidirectional).

### C-03: OpenCode SIGKILL cleanup

From p1858 smoke: after OpenCode SIGKILL, the drain loop raises
`ClientPayloadError` which is caught into `drain_error` (good — that's
why B-03 accidentally works for OpenCode). But the app server logs
`Task exception was never retrieved` fallout. Catch/handle cleanly.

Touches: `spawn_manager.py` drain loop cleanup path.

## Out of scope

- Redesigning the harness connection protocol.
- Changing cancel-origin tagging (B-02 already verified fixed).
- Re-enabling the one-way executor as a supported path.

## Success criteria

- Smoke retest against `uv run meridian` app spawns for all three harnesses
  (Claude, Codex, OpenCode) shows B-01 folded away (idle → succeeded
  without intervention within ≤30s) and B-03 folded away (SIGKILL →
  failed with connection-closed error).
- `uv run ruff check .`, `uv run pyright` clean.
- Deleted one-way executor + no imports / no references remain.
- No "Task exception was never retrieved" noise on SIGKILL path.

## Artifacts to read

- `.meridian/work/spawn-finalize-bugs/investigation-lane-b.md` — root cause
- `.meridian/spawns/p1857/report.md` — Codex app-path smoke
- `.meridian/spawns/p1858/report.md` — Claude + OpenCode app-path smoke
- `.meridian/work/spawn-finalize-bugs/research-stream-topology.md` — one-way executor analysis
