# S024: `LaunchContext` parity across runners (deterministic subset, C1)

- **Source:** design/edge-cases.md E24 + p1411 finding M6 + decisions.md C1 (revision round 3 — parity narrowed to deterministic subset)
- **Added by:** @design-orchestrator (design phase, updated in revision round 3 convergence pass)
- **Tester:** @unit-tester
- **Status:** verified

## Given
A single `SpawnPlan` (canonical test fixture with all fields populated — env vars, cwd, harness, model, prompt, etc.).

## When
`prepare_launch_context(plan, ...)` is called twice with identical inputs, and once from each runner (`runner.py` and `streaming_runner.py`).

## Then
- Both calls return `LaunchContext` instances that compare equal **on the deterministic subset** (C1):
  - `.spec == .spec`
  - `.run_params == .run_params`
  - `.child_cwd == .child_cwd`
  - `.env_overrides == .env_overrides` — the merged override mapping (plan + preflight + runtime), including all `MERIDIAN_*` keys produced by `RuntimeContext.child_context()`
- **`.env` (the full resolved environment) is explicitly NOT asserted equal**, because it depends on ambient `os.environ` which differs between runners, CI hosts, and developer machines. Asserting `.env == .env` would be flaky by design.
- The helper is deterministic on the subset above — no time-dependent, random, or PID-dependent fields leak into the deterministic subset.
- Both runners call the same `prepare_launch_context` helper; there is no parallel implementation.

## Verification
- Unit test: call `prepare_launch_context` twice, assert equality on the deterministic subset only (`spec`, `run_params`, `child_cwd`, `env_overrides`). Explicitly skip `env`.
- Unit test: invoke the helper through both runners' entrypoints (with stubbed subprocess launch) and assert both produce equal deterministic subsets.
- Assert `env_overrides` contains exactly the `MERIDIAN_*` keys emitted by `RuntimeContext.child_context()` and **no** `MERIDIAN_*` keys from plan or preflight (K5 cross-reference to S046 / S046b).
- Grep test (refactor check): `prepare_launch_context` has exactly one definition site.
- Negative test: re-call the helper with a slightly different plan (e.g., different `continue_fork`) and assert the deterministic subset diverges.
- Regression guard: a comment in the test explains **why** `env` is excluded and points at C1 in decisions.md so future refactors do not "fix" the apparent gap.

## Result (filled by tester)
- **Date:** 2026-04-10
- **Status:** verified
- **Evidence:** [tests/test_launch_process.py](/home/jimyao/gitrepos/meridian-channel/tests/test_launch_process.py:245) verifies deterministic-subset equality, immutable env views, and the explicit `env` exclusion note; [tests/test_launch_process.py](/home/jimyao/gitrepos/meridian-channel/tests/test_launch_process.py:299) verifies the deterministic tuple changes when `continue_fork` changes; [tests/test_launch_process.py](/home/jimyao/gitrepos/meridian-channel/tests/test_launch_process.py:343) invokes both runner entrypoints with stubbed launch flow and asserts equal deterministic tuples; [tests/test_launch_process.py](/home/jimyao/gitrepos/meridian-channel/tests/test_launch_process.py:426) confirms both runners reference `prepare_launch_context(...)`.
- **Result:** pass
