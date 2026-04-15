# Phase 5: OpenCode Streaming Spec Port

## Scope

Port OpenCode streaming to `OpenCodeLaunchSpec` and make any unsupported HTTP-session fields explicit rather than invisible.

This phase is separate from Codex by design. The OpenCode HTTP API has different failure modes and likely different unsupported-feature boundaries.

## Files to Modify

- `src/meridian/lib/harness/connections/opencode_http.py`
  Accept `OpenCodeLaunchSpec`, build session payloads from the spec, and log explicit warnings for unsupported streaming fields such as effort or fork if the HTTP API still lacks them.
- `tests/harness/test_opencode_http.py` (new)
  Add direct payload-construction coverage for model normalization, skills, agent name, and known unsupported fields.
- `tests/exec/test_streaming_runner.py`
  Add a focused regression that an OpenCode streaming run still starts and finalizes under the new spec path.
- `tests/harness/test_launch_spec_parity.py`
  Add OpenCode streaming cases and mark documented asymmetries explicitly.

## Dependencies

- Requires: Phase 3
- Produces: spec-backed OpenCode streaming behavior
- Parallel with: Phase 4
- Blocks: Phase 6

## Interface Contract

`OpenCodeConnection._create_session()` must build payloads from `OpenCodeLaunchSpec`, not from `ConnectionConfig.model` or raw `SpawnParams`.

Required behavior:
- normalized model string is already spec-owned
- agent and skills come from the spec
- unsupported streaming fields emit a debug or warning signal instead of disappearing silently

## Patterns to Follow

- Keep HTTP path probing behavior unchanged; only the payload source changes.
- Use explicit payload construction, not dict mutation scattered across helper methods.
- Reflect known asymmetries in the parity test expectations, not in hidden branches.

## Verification Criteria

- [ ] `uv run pytest-llm tests/harness/test_opencode_http.py tests/exec/test_streaming_runner.py`
- [ ] `uv run pytest-llm tests/harness/test_launch_spec_parity.py`
- [ ] `uv run pyright`
- [ ] Smoke: `uv run meridian streaming serve --harness opencode --model opencode-gemma-4-31b-it --prompt "Reply READY and stop."`
- [ ] Smoke lane confirms normalized model selection and session creation work through the real HTTP path

## Staffing

- Builder: `@coder` on `gpt-5.3-codex`
- Testing lanes: `@verifier` on `gpt-5.4-mini`, `@smoke-tester` on `gpt-5.4`

## Constraints

- Do not remove `ConnectionConfig.model` yet.
- Do not hide unsupported API features behind optimistic parity language.
- Keep passthrough-arg behavior explicit: forwarded as-is, with warnings where the server subcommand may not support them.
