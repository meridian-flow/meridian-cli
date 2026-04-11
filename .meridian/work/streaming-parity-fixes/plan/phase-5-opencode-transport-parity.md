# Phase 5: OpenCode Transport Parity

## Scope

Bring OpenCode into the same typed projection model as Claude and Codex. This phase owns one-time model normalization, the single-authoritative skills channel, the subprocess-vs-streaming `mcp_tools` split, and explicit `HarnessConnection` inheritance for the HTTP transport.

## Protocol Validation First

- Probe `opencode run --help`
- Probe `opencode serve --help`
- Confirm the current HTTP session payload fields and session-control endpoints before finalizing the projection layer

## Files to Modify

- `src/meridian/lib/harness/opencode.py` — declare OpenCode field ownership, normalize `opencode-` model prefixes once, choose one skills delivery channel
- `src/meridian/lib/harness/projections/project_opencode_subprocess.py` — new subprocess projection with drift guard and explicit reject path for non-empty `mcp_tools`
- `src/meridian/lib/harness/projections/project_opencode_streaming.py` — new streaming projection module for `serve` command and HTTP session payload
- `src/meridian/lib/harness/connections/opencode_http.py` — consume shared projection helpers and inherit the generic `HarnessConnection[OpenCodeLaunchSpec]` contract explicitly
- `tests/harness/test_opencode_http.py` — HTTP payload, session creation, and inheritance coverage
- `tests/harness/test_launch_spec.py` — OpenCode spec normalization coverage
- `tests/exec/test_streaming_runner.py` — OpenCode plan/spec threading where needed

## Dependencies

- Requires: Phase 2
- Independent of: Phase 3 and Phase 4
- Produces: OpenCode projection modules consumed by phases 7-8

## Constraints

- Exactly one skills channel per launch.
- OpenCode subprocess must reject non-empty `mcp_tools` loudly instead of dropping them.
- `continue_fork` behavior must stay explicit even if the serve API cannot support it.

## Verification Criteria

- `uv run pytest-llm tests/harness/test_opencode_http.py`
- `uv run pytest-llm tests/harness/test_launch_spec.py -k opencode`
- Targeted smoke run against the real `opencode serve` binary

## Scenarios to Verify

- `S017`
- `S018`
- `S034`

Phase cannot close until every scenario above is marked `verified` in `scenarios/`.

## Agent Staffing

- `@coder` on `gpt-5.3-codex`
- `@unit-tester` on `gpt-5.4`
- `@smoke-tester` on `claude-sonnet-4-6`
- Escalate to `@reviewer` on `claude-opus-4-6` if the OpenCode HTTP/CLI contract disagrees with the design
