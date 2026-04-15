# Phase 3: Claude Projection and Preflight Parity

## Scope

Move Claude launch assembly behind one shared projection module and one adapter-owned preflight path so subprocess and streaming produce the same spec-derived tail, the same deduped resolver output, and the same last-wins passthrough behavior.

## Protocol Validation First

- Probe `claude --help`
- Confirm the current flag surface for `--allowedTools`, `--disallowedTools`, `--append-system-prompt`, `--agents`, `--resume`, `--fork`, `--mcp-config`, and `--add-dir`
- Record any observed wire quirks in the phase worklog before implementation

## Files to Modify

- `src/meridian/lib/harness/claude.py` — declare Claude `consumed_fields`/`explicitly_ignored_fields`, call the shared projection, stop doing local command assembly
- `src/meridian/lib/harness/claude_preflight.py` — new Claude-owned preflight helpers for parent permission forwarding and `--add-dir` expansion
- `src/meridian/lib/harness/projections/project_claude.py` — new Claude projection module with import-time drift guard
- `src/meridian/lib/launch/text_utils.py` — shared Claude arg-list merge helpers (`dedupe_nonempty`, CSV splitting, allowed-tools merge)
- `src/meridian/lib/harness/connections/claude_ws.py` — consume the shared projection instead of local `_build_command(...)`
- `tests/harness/test_launch_spec_parity.py` — Claude parity and arg ordering tests
- `tests/harness/test_claude_ws.py` — streaming Claude projection wiring
- `tests/exec/test_claude_cwd_isolation.py` and related Claude smoke coverage — preflight/path parity

## Dependencies

- Requires: Phase 2
- Independent of: Phase 4 and Phase 5
- Produces: Claude-specific projection + preflight modules consumed by phases 6-8

## Interface Contract

```python
def project_claude_spec_to_cli_args(
    spec: ClaudeLaunchSpec,
    *,
    base_command: tuple[str, ...],
) -> list[str]: ...

def preflight(...) -> PreflightResult
```

## Constraints

- Claude projection owns ordering; runners and connection classes must not reshuffle Claude flags.
- Resolver-internal dedupe is allowed; dedupe across resolver output and user `extra_args` is forbidden.
- User passthrough `--append-system-prompt` and `--allowedTools` must remain in the tail.

## Verification Criteria

- `uv run pytest-llm tests/harness/test_launch_spec_parity.py -k claude`
- `uv run pytest-llm tests/harness/test_claude_ws.py`
- `uv run pytest-llm tests/exec/test_claude_cwd_isolation.py`
- Claude-specific smoke guide or targeted spawn run against the real `claude` binary

## Scenarios to Verify

- `S005`
- `S011`
- `S012`
- `S015`
- `S021`
- `S022`
- `S023`

Phase cannot close until every scenario above is marked `verified` in `scenarios/`.

## Agent Staffing

- `@coder` on `gpt-5.3-codex`
- `@unit-tester` on `gpt-5.4`
- `@smoke-tester` on `claude-sonnet-4-6`
- Escalate to `@reviewer` on `claude-opus-4-6` for real Claude CLI or parent-permission forwarding disagreements
