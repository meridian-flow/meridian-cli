# Review — streaming-parity-fixes v2 design, structural / refactor focus

You are @refactor-reviewer. You are reviewing the v2 design for streaming adapter parity at design time — the highest-leverage moment to catch structural debt before it ships. The v1 design landed a tangled shape that shipped bugs the design warned about; v2 explicitly tries to fix the structure, but new structures can bring new problems.

## Your focus area

**Structural health and navigability.** You are not reviewing correctness (other reviewers handle that). You are reviewing:

1. **Module boundaries.** Does the v2 module graph (`launch_spec.py`, `adapter.py`, `projections/*.py`, `connections/*.py`, `launch/constants.py`, `launch/runner.py`, `launch/streaming_runner.py`) have clear seams? Can a human navigate from "where does a `--allowedTools` flag come from" to its definition in ≤ 2 hops? Are there hidden cycles via `TYPE_CHECKING` imports?
2. **Naming consistency.** Do `HarnessAdapter`, `HarnessConnection`, `HarnessBundle`, `ResolvedLaunchSpec`, `ClaudeLaunchSpec` form a consistent vocabulary? Are there accidental near-duplicates (e.g., `ClaudeLaunchSpec` vs `ClaudeSpec`) that will confuse greppers?
3. **Seams between subprocess and streaming.** The design's core claim is that v2 shares more code between subprocess and streaming paths. Does it actually? Is there a clear "shared projection + shared launch context + shared constants" core, or does each path still own most of its plumbing with only a thin shared veneer?
4. **Coupling.** Does `runner.py` or `streaming_runner.py` import from concrete harness modules, or only from the typed interfaces? Do projections import from connections, or vice versa? Is the dependency direction always from policy (dispatch, runner) → mechanism (adapter, projection, connection) with no reverse?
5. **Dead weight.** Does the design keep any v1 element alive "just in case" that should be deleted? (The orchestrator instructions explicitly allow aggressive deletion — no backwards compatibility.)
6. **D19 scope.** D19 defers full runner decomposition. Is the deferral genuine (the shared-core extraction unblocks the deferred work cleanly) or is it load-bearing (the deferral leaves runner.py in a state where the M6 fix is incomplete)?
7. **Signal counts.** Applying the dev-principles structural-health signals: does any module in the v2 design grow past 500 lines, hold > 3 responsibilities, or require > 5 files to change when adding a new variant? Flag each hit.

## What to read

- `.meridian/work/streaming-parity-fixes/design/overview.md`
- `.meridian/work/streaming-parity-fixes/design/typed-harness.md`
- `.meridian/work/streaming-parity-fixes/design/runner-shared-core.md` (primary)
- `.meridian/work/streaming-parity-fixes/design/transport-projections.md`
- `.meridian/work/streaming-parity-fixes/decisions.md` (especially D7, D12, D13, D19)
- Current source (to understand the baseline structure):
  - `src/meridian/lib/launch/runner.py`
  - `src/meridian/lib/launch/streaming_runner.py`
  - `src/meridian/lib/harness/launch_spec.py`
  - `src/meridian/lib/harness/adapter.py`
  - `src/meridian/lib/harness/connections/` (all three files)

## Deliverable

Structural findings with severity. For each:

- **What structural debt.**
- **Where (file/section).**
- **Concrete move** (not "consider refactoring" — actual "extract X into Y", "rename X to Y", "invert dependency between X and Y").
- **Why it matters** (what future change becomes harder if this is left unfixed).

End with an overall verdict: **Converged / Needs structural revision / Reject structural shape**.
