# Phase 4: Codex Subprocess and Streaming Parity

## Scope

Implement the Codex-specific projection modules and streaming approval semantics around the approved fail-closed boundary. This phase owns the app-server command builder, the thread bootstrap request builder, confirm-mode rejection events, and the `report_output_path` split between subprocess and streaming.

## Protocol Validation First

- Probe `codex exec --help`
- Probe `codex app-server --help`
- Confirm the actual sandbox/approval knobs that exist today before finalizing projection mappings
- If a requested design semantic cannot be expressed by the observed app-server interface, pin the `HarnessCapabilityMismatch` rule instead of guessing

## Files to Modify

- `src/meridian/lib/harness/codex.py` — declare Codex field ownership, stop storing duplicated sandbox/approval state on the spec, call shared projections
- `src/meridian/lib/harness/projections/project_codex_subprocess.py` — new subprocess projection with drift guard
- `src/meridian/lib/harness/projections/project_codex_streaming.py` — new streaming projection module; split into `_fields`/`_appserver`/`_rpc` only if line budget triggers
- `src/meridian/lib/harness/connections/codex_ws.py` — use the shared app-server command and thread request builders, emit confirm-mode rejection event before `send_error`
- `tests/harness/test_codex_ws.py` — approval event ordering, thread method selection, streaming projection wiring
- `tests/harness/test_launch_spec.py` and `tests/harness/test_launch_spec_parity.py` — Codex spec and projection assertions
- `tests/exec/test_streaming_runner.py` — real runner threading of Codex resolver/spec values

## Dependencies

- Requires: Phase 2
- Independent of: Phase 3 and Phase 5
- Produces: Codex-specific projection and streaming behavior consumed by phases 7-8

## Constraints

- No silent downgrade when requested permission semantics cannot be expressed.
- `report_output_path` stays Codex-only and streaming must ignore it on the wire with a debug note.
- `extra_args` remain verbatim tail data; the projection may log collisions, not strip them.

## Verification Criteria

- `uv run pytest-llm tests/harness/test_codex_ws.py`
- `uv run pytest-llm tests/harness/test_launch_spec_parity.py -k codex`
- `uv run pytest-llm tests/exec/test_streaming_runner.py -k codex`
- Codex smoke runs against the real `codex app-server` binary

## Scenarios to Verify

- `S007`
- `S008`
- `S009`
- `S010`
- `S016`
- `S019`
- `S029`
- `S032`
- `S036`
- `S038`

Phase cannot close until every scenario above is marked `verified` in `scenarios/`.

## Agent Staffing

- `@coder` on `gpt-5.3-codex`
- `@unit-tester` on `gpt-5.4`
- `@smoke-tester` on `claude-opus-4-6`
- Escalate to `@reviewer` on `gpt-5.4` for Codex capability mapping, confirm-mode semantics, or lifecycle correctness issues
