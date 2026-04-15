# Phase 4: Codex Streaming Spec Port

## Scope

Port Codex streaming to `CodexLaunchSpec`, including bootstrap projection and approval-mode handling.

This is a single-target integration phase. Treat the Codex app-server protocol as the external contract and verify it directly.

## Files to Modify

- `src/meridian/lib/harness/connections/codex_ws.py`
  Accept `CodexLaunchSpec`, project bootstrap parameters from the spec, and make approval decisions respect `spec.permission_config.approval`.
- `tests/harness/test_codex_ws.py`
  Cover bootstrap request shape, effort forwarding, and confirm-mode rejection behavior.
- `tests/exec/test_streaming_runner.py`
  Add a focused regression asserting the streaming runner can still start and finalize Codex spawns after the protocol change.
- `tests/harness/test_launch_spec_parity.py`
  Expand the parity fixture set with Codex streaming cases once the projection exists.

## Dependencies

- Requires: Phase 3
- Produces: spec-backed Codex streaming behavior
- Parallel with: Phase 5
- Blocks: Phase 6

## Interface Contract

Codex streaming must now derive:

- server launch args from the spec only where `app-server` supports them
- thread bootstrap method and params from `continue_session_id`, `continue_fork`, `model`, and `effort`
- approval-request decisions from `spec.permission_config.approval`

Required behavior:
- `yolo`, `auto`, `default` -> accept
- `confirm` -> reject and log a warning when no interactive approval channel exists

## Patterns to Follow

- Keep JSON-RPC method selection explicit: `thread/start`, `thread/resume`, `thread/fork`.
- Do not parse CLI-style permission flags inside `codex_ws.py`; map semantic approval values directly.
- Preserve current error-event behavior for unsupported server requests.

## Verification Criteria

- [ ] `uv run pytest-llm tests/harness/test_codex_ws.py tests/exec/test_streaming_runner.py`
- [ ] `uv run pytest-llm tests/harness/test_launch_spec_parity.py`
- [ ] `uv run pyright`
- [ ] Smoke: `uv run meridian streaming serve --harness codex --model gpt-5.3-codex --prompt "Reply READY and stop."`
- [ ] Focused regression proves `confirm` mode is not silently auto-accepted in the streaming adapter

## Staffing

- Builder: `@coder` on `gpt-5.3-codex`
- Testing lanes: `@verifier` on `gpt-5.4-mini`, `@smoke-tester` on `gpt-5.4`, `@unit-tester` on `gpt-5.2`

## Constraints

- Do not remove `ConnectionConfig.model` yet.
- Do not bundle OpenCode work into this phase.
- If the live app-server API cannot accept an effort field, log and document the asymmetry rather than faking parity.
