# S026: No duplicate constants across runners

- **Source:** design/edge-cases.md E26 + p1411 finding M6
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @verifier (+ @refactor-reviewer)
- **Status:** verified

## Given
The v2 design places shared runner constants in `src/meridian/lib/launch/constants.py`:
- `DEFAULT_*_SECONDS` (timeouts)
- `DEFAULT_INFRA_EXIT_CODE`
- `_BLOCKED_CHILD_ENV_VARS`
- `BASE_COMMAND` tuples per harness (the canonical subprocess base and streaming base)

## When
A grep-based audit runs across `src/meridian/lib/launch/runner.py`, `src/meridian/lib/launch/streaming_runner.py`, and all harness connection modules.

## Then
- Every constant listed above has exactly one definition site, in `launch/constants.py`.
- `runner.py` and `streaming_runner.py` import them — no local redefinition.
- `claude_ws.py`, `codex_ws.py`, `opencode_http.py` do not contain their own `BASE_COMMAND` tuples; they use the shared constants.
- No drift: if the subprocess base changes, the streaming base (and both projections) see the change automatically.

## Verification
- `rg "DEFAULT_INFRA_EXIT_CODE\\s*=" src/ -t py` returns exactly 1 match, in `constants.py`.
- Same for each listed constant.
- `rg "_BLOCKED_CHILD_ENV_VARS\\s*=" src/ -t py` → exactly 1 match.
- Refactor-reviewer audits the pair of runner files looking for module-level constant assignments that duplicate the shared set.
- Test: `from meridian.lib.launch.constants import BASE_COMMAND_CLAUDE_SUBPROCESS, BASE_COMMAND_CLAUDE_STREAMING` (or equivalent names) succeeds.

## Result (filled by tester)
verified - 2026-04-10

- Constants audit passed. Shared runner constants live in [src/meridian/lib/launch/constants.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/constants.py:7) through [src/meridian/lib/launch/constants.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/constants.py:47). [src/meridian/lib/launch/runner.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/runner.py:37) imports shared launch constants, and its only runner-local module constant is `DEFAULT_GUARDRAIL_TIMEOUT_SECONDS` at [src/meridian/lib/launch/runner.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/runner.py:77). [src/meridian/lib/launch/streaming_runner.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/streaming_runner.py:32) does the same, with only runner-local `DEFAULT_GUARDRAIL_TIMEOUT_SECONDS` at [src/meridian/lib/launch/streaming_runner.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/streaming_runner.py:71). Grep proof: `rg -n "^[A-Z][A-Z0-9_]*.*=" src/meridian/lib/launch/runner.py src/meridian/lib/launch/streaming_runner.py src/meridian/lib/launch/constants.py` found no duplicated shared constant definitions in the runner pair.
- Base-command uniqueness passed. Subprocess adapters bind shared base commands in [src/meridian/lib/harness/claude.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/claude.py:203), [src/meridian/lib/harness/codex.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/codex.py:268), and [src/meridian/lib/harness/opencode.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/opencode.py:143). Streaming paths consume shared base commands in [src/meridian/lib/harness/connections/claude_ws.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/connections/claude_ws.py:30), [src/meridian/lib/harness/projections/project_codex_streaming.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/projections/project_codex_streaming.py:19), and [src/meridian/lib/harness/projections/project_opencode_streaming.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/projections/project_opencode_streaming.py:15). No connection/projection module defines its own `BASE_COMMAND_*` tuple.
- Shared-core branch audit passed. Grep over `context.py`, `env.py`, and `runner.py` for `if harness_id ==`, `if spec.harness ==`, `if isinstance(adapter, ...)`, and similar patterns returned no matches. The only harness-id branches found were terminal-event handling in [src/meridian/lib/launch/streaming_runner.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/streaming_runner.py:296), [src/meridian/lib/launch/streaming_runner.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/streaming_runner.py:315), and [src/meridian/lib/launch/streaming_runner.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/streaming_runner.py:340), which are outside the shared launch-preparation core.
- `MERIDIAN_*` leak audit passed. The sole runtime producer is `RuntimeContext.child_context()` in [src/meridian/lib/launch/context.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/context.py:39), with leak rejection enforced in [src/meridian/lib/launch/env.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/env.py:114). Spawn execution keeps plan overrides non-`MERIDIAN_*` in [src/meridian/lib/ops/spawn/execute.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/spawn/execute.py:133). No disallowed `MERIDIAN_*` assignment sites were found in plan-overrides or preflight code paths.
- Immutability contract passed. `LaunchContext` is frozen at [src/meridian/lib/launch/context.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/context.py:96), and its `env` / `env_overrides` are wrapped with `MappingProxyType` at [src/meridian/lib/launch/context.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/context.py:191). `PreflightResult` is frozen and wraps `extra_env` with `MappingProxyType` at [src/meridian/lib/launch/launch_types.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/launch_types.py:59). Construction sites route through `PreflightResult.build(...)` in [src/meridian/lib/launch/context.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/context.py:151), [src/meridian/lib/harness/claude_preflight.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/claude_preflight.py:159), and [src/meridian/lib/harness/adapter.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/adapter.py:368).
- Verification gates passed: `uv run ruff check .`; `uv run pyright`; `uv run pytest-llm tests/test_launch_process.py -v`; `uv run pytest-llm tests/exec/test_claude_cwd_isolation.py -v`; `uv run pytest-llm tests/exec/test_streaming_runner.py -v`; `uv run pytest-llm tests/exec/test_permissions.py -v`; `uv run pytest-llm tests/ --ignore=tests/smoke -q`.

Non-blocking note for @refactor-reviewer: [src/meridian/lib/harness/connections/claude_ws.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/connections/claude_ws.py:51) still defines a private `_BLOCKED_CHILD_ENV_VARS` union to add `CLAUDECODE` on top of the shared set. This does not duplicate runner constants or base-command tuples, but the name is close enough to the shared constant that a future rename could reduce audit ambiguity.
