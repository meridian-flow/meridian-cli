# Phase 3: Smoke Classification and Fallbacks

## Scope and Boundaries

Execute the approved smoke matrix against the patched build and classify every result using the baseline-first protocol.

In scope:

- run T-01 through T-12 from `design/smoke-matrix.md`
- for every Meridian test, run the equivalent raw-harness baseline first
- classify each result as `PASS`, `MERIDIAN-CAUSED`, `UPSTREAM-ONLY`, or `SKIP` where the matrix already permits skipping
- apply the known command correction for harness-specific tests: use `--harness`, not `-H`, for T-09, T-10, and T-11
- capture which harnesses/environments were actually exercised

Out of scope:

- editing the approved smoke-matrix source file during execution
- fixing upstream-only harness bugs
- broadening implementation beyond the PTY launch surface without reopening Phase 1

## Touched Files and Modules

- no source edits are planned
- runtime surface under test: `src/meridian/lib/launch/process.py`
- execution reference: `.meridian/work/pty-terminal-passthrough-investigation/design/smoke-matrix.md`

## Claimed EARS Statement IDs

- `PTY-01`
- `PTY-02`
- `PTY-03`
- `PTY-04`
- `PTY-05`
- `PTY-06`
- `PTY-07`
- `PTY-08`
- `PTY-09`
- `PTY-10`

## Touched Refactor IDs

- none

## Dependencies

- Phase 1 complete
- may run in parallel with Phase 2 once the patched tree exists

## Tester Lanes

- `@smoke-tester` mandatory

## Execution Notes

- Treat baseline comparison as mandatory evidence, not a suggestion.
- For T-09 through T-11, replace the matrix's stale harness examples with:
  - `uv run meridian --harness claude`
  - `uv run meridian --harness codex`
  - `uv run meridian --harness opencode`
- For T-12, accept `SKIP (no Windows environment)` only when a Windows environment is genuinely unavailable; otherwise verify direct-subprocess fallback behavior.
- If a Meridian-caused failure appears, reopen Phase 1 with the specific failing test IDs and baseline evidence before continuing.
- If the failure source is ambiguous after baseline comparison, inspect launch/session logs and escalate to a scoped reviewer instead of guessing.

## Exit Criteria

- every test in T-01 through T-12 has a recorded disposition
- every Meridian result is paired with baseline evidence or an allowed skip reason
- T-09 through T-11 are executed with corrected `--harness` commands
- all EARS statements `PTY-01` through `PTY-10` have evidence coverage or an explicit allowed skip for Windows-only availability constraints
