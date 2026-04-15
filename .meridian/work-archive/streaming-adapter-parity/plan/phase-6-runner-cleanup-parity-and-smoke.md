# Phase 6: Runner Cleanup, Parity, and Smoke Matrix

## Scope

Finish the migration by deleting the remaining shared-runner duplication, removing transitional connection config state, and expanding the verification suite to cover subprocess-vs-streaming parity across all harnesses.

This phase is intentionally last. It assumes every transport already consumes specs.

## Files to Modify

- `src/meridian/lib/launch/claude_preflight.py` (new)
  Extract `_read_parent_claude_permissions()`, `_merge_allowed_tools_flag()`, `_dedupe_nonempty()`, `_split_csv_entries()`, and Claude child-CWD resolution helpers.
- `src/meridian/lib/launch/runner.py`
  Replace the duplicated Claude preflight block with calls into `claude_preflight.py`.
- `src/meridian/lib/launch/streaming_runner.py`
  Replace the duplicated Claude preflight block and remove the last dependency on `ConnectionConfig.model`.
- `src/meridian/lib/harness/connections/base.py`
  Remove `ConnectionConfig.model` once every connection reads model data from the spec.
- `src/meridian/lib/harness/connections/{codex_ws,opencode_http}.py`
  Finish the `ConnectionConfig.model` cleanup if any references remain.
- `tests/exec/test_claude_cwd_isolation.py`
  Keep coverage on the extracted Claude child-CWD behavior.
- `tests/exec/test_claude_session_symlink.py`
  Keep coverage on Claude session accessibility after extraction.
- `tests/harness/test_launch_spec_parity.py`
  Expand from subprocess-only cases into the full cross-transport matrix.
- `tests/harness/test_extraction.py`
  Finalize cross-harness session-id/report extraction expectations.
- `tests/smoke/streaming-adapter-parity.md` (new)
  Add a repeatable smoke guide that walks Claude, Codex, and OpenCode subprocess + streaming parity checks.

## Dependencies

- Requires: Phase 4 and Phase 5
- Produces: the final cleaned architecture and verification suite

## Interface Contract

At the end of this phase:

- `ConnectionConfig` is transport-only and no longer carries model state
- every connection gets its launch semantics exclusively from the spec
- Claude-specific runner preflight lives in `claude_preflight.py`
- `tests/harness/test_launch_spec_parity.py` covers:
  - `SpawnParams` -> spec completeness
  - subprocess projection coverage
  - streaming projection coverage
  - documented asymmetries, especially OpenCode unsupported fields

## Patterns to Follow

- Delete duplicated helper code instead of leaving wrappers behind.
- Keep the parity suite focused on semantic equivalence, not exact wire-format equality across transports.
- Use the existing smoke-doc style under `tests/smoke/` rather than inventing a new test format.

## Verification Criteria

- [ ] `uv run pytest-llm tests/exec/test_claude_cwd_isolation.py tests/exec/test_claude_session_symlink.py`
- [ ] `uv run pytest-llm tests/harness/test_launch_spec_parity.py tests/harness/test_extraction.py`
- [ ] `uv run pyright`
- [ ] `uv run ruff check .`
- [ ] Smoke guide in `tests/smoke/streaming-adapter-parity.md` is executed against Claude, Codex, and OpenCode

## Staffing

- Builder: `@coder` on `gpt-5.3-codex`
- Testing lanes: `@verifier` on `gpt-5.4-mini`, `@unit-tester` on `gpt-5.2`, `@smoke-tester` on `gpt-5.4`

## Constraints

- Do not leave `ConnectionConfig.model` behind as dead compatibility state.
- Do not keep both extracted and duplicated Claude preflight helpers.
- If parity cannot be full for a transport, encode the asymmetry explicitly in tests and smoke docs.
