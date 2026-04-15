# S046: `preflight.extra_env` containing `MERIDIAN_*` key raises in merge helper

- **Source:** design/edge-cases.md E44 + decisions.md K5 (revision round 3)
- **Added by:** @design-orchestrator (revision round 3)
- **Tester:** @unit-tester
- **Status:** verified

## Given
A fixture adapter whose `preflight(...)` returns `PreflightResult.build(expanded_passthrough_args=(), extra_env={"MERIDIAN_DEPTH": "42", "CODEX_HOME": "/tmp/codex"})`. `RuntimeContext.child_context()` normally produces the canonical `MERIDIAN_DEPTH` value for the child spawn.

## When
`merge_env_overrides(plan_overrides={}, runtime_overrides=runtime_ctx.child_context(), preflight_overrides=preflight.extra_env)` runs inside `prepare_launch_context(...)`.

## Then
- `merge_env_overrides` raises `RuntimeError` with a message naming the offending key and its source (`"preflight_overrides"`).
- The spawn fails before launch — no child process is started.
- The runtime-context-produced `MERIDIAN_DEPTH` remains authoritative.
- The whitelist checked by `RuntimeContext.child_context()` includes `MERIDIAN_FS_DIR` and `MERIDIAN_WORK_DIR` so shared filesystem and work-item dirs flow through; preflight must not inject either of those either.

## Verification
- Unit test: construct the fixture preflight, call `merge_env_overrides` directly, assert `RuntimeError` with the expected message shape (contains `"MERIDIAN_DEPTH"` and `"preflight_overrides"`).
- Parameterized cases: try each whitelisted key (`MERIDIAN_REPO_ROOT`, `MERIDIAN_STATE_ROOT`, `MERIDIAN_DEPTH`, `MERIDIAN_CHAT_ID`, `MERIDIAN_FS_DIR`, `MERIDIAN_WORK_DIR`) as the leak and assert each is caught.
- Positive test: a preflight returning only `CODEX_HOME`, `CLAUDE_HOME`, or similar harness-specific keys succeeds and those keys survive the merge.
- Regression: temporarily relax the check to a log-only warning and verify the unit test fails loudly.
- Cross-check: search the `harness/` package for any `extra_env["MERIDIAN_*"]` patterns in real adapters — there should be zero.

## Result (filled by tester)
- **Date:** 2026-04-10
- **Status:** verified
- **Evidence:** [tests/exec/test_permissions.py](/home/jimyao/gitrepos/meridian-channel/tests/exec/test_permissions.py:303) checks the base `MERIDIAN_DEPTH` preflight leak path; [tests/exec/test_permissions.py](/home/jimyao/gitrepos/meridian-channel/tests/exec/test_permissions.py:312) parameterizes all allowed runtime `MERIDIAN_*` keys and asserts each preflight leak raises with `preflight_overrides` in the error; [tests/exec/test_permissions.py](/home/jimyao/gitrepos/meridian-channel/tests/exec/test_permissions.py:387) confirms non-`MERIDIAN_*` preflight keys still survive merge.
- **Result:** pass
- **Cross-check:** `rg -n 'extra_env.*MERIDIAN_|MERIDIAN_.*extra_env' src/meridian/lib/harness` returned 0 matches on 2026-04-10.
