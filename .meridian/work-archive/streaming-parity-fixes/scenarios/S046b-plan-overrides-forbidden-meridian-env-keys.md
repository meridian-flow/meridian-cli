# S046b: `plan_overrides` containing `MERIDIAN_*` key raises in merge helper

- **Source:** design/edge-cases.md E44 + decisions.md K5 (revision round 3 convergence pass, F9)
- **Added by:** @design-orchestrator (revision round 3 convergence pass)
- **Tester:** @unit-tester
- **Status:** verified

## Given
K5 makes `RuntimeContext.child_context()` the sole producer of `MERIDIAN_*` runtime overrides. S046 covers the `preflight_overrides` leak path. This scenario covers the **symmetric** leak path from `plan_overrides` — a plan builder (e.g., REST request handler, CLI plan assembler, profile materializer) that accidentally or maliciously injects a `MERIDIAN_CHAT_ID`, `MERIDIAN_DEPTH`, or similar key into the plan's env override set.

Without the symmetric check, a plan builder could spoof the parent chat id, reset the depth counter, or replace the fs/work dir paths. The defence-in-depth assertion on the plan side catches this at merge time, before any child process is launched.

## Given (fixture)
A `PreparedSpawnPlan` whose `env_overrides` contains `{"MERIDIAN_CHAT_ID": "spoofed-parent-id", "CUSTOM_TOOL_HOME": "/tmp/tool"}`. `RuntimeContext.child_context()` emits a different (correct) `MERIDIAN_CHAT_ID`.

## When
`merge_env_overrides(plan_overrides=plan.env_overrides, runtime_overrides=runtime_ctx.child_context(), preflight_overrides=preflight.extra_env)` runs inside `prepare_launch_context(...)`.

## Then
- `merge_env_overrides` raises `RuntimeError` whose message names the offending key and its source (`"plan_overrides"`).
- Both plan and preflight leaks are reported in a single error when both happen at once, so the fix loop surfaces every offender at once rather than one per run.
- The spawn fails before launch — no child process is started.
- The `CUSTOM_TOOL_HOME` non-MERIDIAN key is not affected and would flow through normally in the non-leaking case.

## Verification
- Unit test: build a fixture plan with `env_overrides={"MERIDIAN_CHAT_ID": "spoofed"}`, call `merge_env_overrides(...)` directly, assert `RuntimeError` whose message contains both `"MERIDIAN_CHAT_ID"` and `"plan_overrides"`.
- Parameterized cases: test each whitelisted key (`MERIDIAN_REPO_ROOT`, `MERIDIAN_STATE_ROOT`, `MERIDIAN_DEPTH`, `MERIDIAN_CHAT_ID`, `MERIDIAN_FS_DIR`, `MERIDIAN_WORK_DIR`) as the plan-side leak and assert each is caught.
- Combined-leak test: `plan_overrides={"MERIDIAN_CHAT_ID": "p"}, preflight_overrides={"MERIDIAN_DEPTH": "42"}`. Assert the raised `RuntimeError` names both keys with their respective sources, not just the first one found.
- Positive test: plan with only non-MERIDIAN keys (e.g., `{"CUSTOM_TOOL_HOME": "/tmp"}`) passes through untouched, and `CUSTOM_TOOL_HOME` appears in the final merged env with the plan-side value.
- Regression: grep `src/meridian/lib/` for any place that builds `PreparedSpawnPlan.env_overrides` — every builder must be verified clean of `MERIDIAN_*` key construction, and a comment pointing at K5 must sit next to any env-override assembly that accepts untrusted input.

## Result (filled by tester)
- **Date:** 2026-04-10
- **Status:** verified
- **Evidence:** [tests/exec/test_permissions.py](/home/jimyao/gitrepos/meridian-channel/tests/exec/test_permissions.py:324) checks the base `MERIDIAN_CHAT_ID` plan-side leak path; [tests/exec/test_permissions.py](/home/jimyao/gitrepos/meridian-channel/tests/exec/test_permissions.py:333) parameterizes all allowed runtime `MERIDIAN_*` keys and asserts each plan-side leak raises with `plan_overrides` in the error; [tests/exec/test_permissions.py](/home/jimyao/gitrepos/meridian-channel/tests/exec/test_permissions.py:345) verifies combined plan+preflight leaks are reported together; [tests/exec/test_permissions.py](/home/jimyao/gitrepos/meridian-channel/tests/exec/test_permissions.py:387) confirms non-`MERIDIAN_*` plan keys still pass through untouched.
- **Result:** pass
- **Note:** Merge order for non-`MERIDIAN_*` collisions is plan, then preflight, then runtime; [tests/exec/test_permissions.py](/home/jimyao/gitrepos/meridian-channel/tests/exec/test_permissions.py:401) confirms preflight beats plan for the same key, and [tests/exec/test_permissions.py](/home/jimyao/gitrepos/meridian-channel/tests/exec/test_permissions.py:368) confirms runtime remains the only accepted `MERIDIAN_*` producer.
