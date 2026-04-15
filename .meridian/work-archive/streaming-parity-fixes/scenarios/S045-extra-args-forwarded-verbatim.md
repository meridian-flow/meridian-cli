# S045: `extra_args` is forwarded verbatim to every transport

- **Source:** design/edge-cases.md E48 + decisions.md H1/D1 (revision round 3)
- **Added by:** @design-orchestrator (revision round 3)
- **Replaces:** [S037](S037-reserved-flag-stripping.md)
- **Tester:** @unit-tester + @smoke-tester
- **Status:** verified

## Given
A spawn configured with `extra_args = ("-c", "sandbox_mode=yolo", "--dangerous-flag", "--allowedTools", "C,D")`.

## When
The spec is projected to each harness's wire format — Claude subprocess, Claude streaming, Codex subprocess, Codex streaming (app-server command), OpenCode subprocess, OpenCode streaming (serve command). A smoke test launches the real harness end-to-end.

## Then
- Every `extra_args` element appears in the final command line or payload exactly as it was supplied, in the original order, at the passthrough tail position.
- Meridian does NOT strip `-c sandbox_mode=yolo`, `--dangerous-flag`, or `--allowedTools C,D`.
- Meridian does NOT rewrite or collapse any entry.
- Meridian DOES emit a debug log listing the verbatim `extra_args` at the projection boundary, so the audit trail makes it obvious what reached the harness.
- For Claude: the user's `--allowedTools C,D` coexists with any resolver-derived `--allowedTools A,B`. Both flags appear.
- For Codex: the user's `-c sandbox_mode=yolo` coexists with the resolver-derived `-c sandbox_mode="read-only"` (or whatever the permission config yields). Both appear. Codex's own argument handling decides the effective value.
- The harness either accepts the passthrough (smoke result: expected) or rejects it at its own startup (smoke result: harness-side error surfaces cleanly via S029).

## Verification
- Unit tests per projection (six total) asserting `extra_args` appears in the output exactly as supplied.
- Caplog assertion that the verbatim-passthrough debug log fires in `project_codex_spec_to_appserver_command` and `project_opencode_spec_to_serve_command`.
- Smoke test: launch a real streaming Codex spawn with `extra_args=("-c","sandbox_mode=yolo")`, capture process arguments via debug.jsonl, assert the user flag is present.
- Delta test: search the entire `projections/` package for `strip_reserved_passthrough`, `_RESERVED_CODEX_ARGS`, `_RESERVED_CLAUDE_ARGS`, `_reserved_flags.py` — assert zero matches.

## Result (filled by tester)
verified 2026-04-11

- Evidence:
  - `tests/harness/test_launch_spec_parity.py:837` — `test_claude_projection_forwards_extra_args_verbatim_across_transports`
  - `tests/harness/test_launch_spec_parity.py:1231` — `test_codex_projection_forwards_extra_args_verbatim_to_subprocess`
  - `tests/harness/test_launch_spec_parity.py:1254` — `test_codex_streaming_projection_logs_passthrough_args_once_and_skips_empty_tail`
  - `tests/harness/test_launch_spec_parity.py:1462` — `test_opencode_subprocess_projection_forwards_extra_args_verbatim`
  - `tests/harness/test_launch_spec_parity.py:1475` — `test_opencode_streaming_projection_logs_passthrough_args_once_and_skips_empty_tail`
  - `tests/harness/test_launch_spec_parity.py:1593` — `test_projection_package_contains_no_reserved_passthrough_stripping_helpers`
- Notes:
  - All transport projections keep user `extra_args` verbatim and in-order; streaming projections also emit the expected debug log once per call.

### Smoke-tester re-verification (2026-04-11)

- Subprocess dry-run projection preserved the passthrough tail verbatim for all three harnesses, including `/tmp/foo`, `--note=hello world`, and `--value=--dashy`:
  - Claude: `['claude', '-p', '--output-format', 'stream-json', '--verbose', '-', '--model', 'claude-sonnet-4-6', '--weird-flag', 'value', '/tmp/foo', '--note=hello world', '--value=--dashy']`
  - Codex: `['codex', 'exec', '--json', '--model', 'gpt-5.3-codex', '--weird-flag', 'value', '/tmp/foo', '--note=hello world', '--value=--dashy', '-']`
  - OpenCode: `['opencode', 'run', '--model', 'gpt-5.3-codex', '--weird-flag', 'value', '/tmp/foo', '--note=hello world', '--value=--dashy', '-']`
- Real subprocess binaries saw the forwarded flag directly:
  - Claude: exit `1`, stderr `error: unknown option '--weird-flag'`
  - Codex: exit `2`, stderr `error: unexpected argument '--weird-flag' found`
  - OpenCode: exit `1`, CLI help/usage surfaced cleanly from the real binary
- Streaming passthrough logging and command tails also matched expectations:
  - Codex projection logged `Forwarding passthrough args to codex app-server: ['--weird-flag', 'value', '/tmp/foo', '--note=hello world', '--value=--dashy']`
  - Codex projected command: `['codex', 'app-server', '--listen', 'ws://127.0.0.1:47991', '--weird-flag', 'value', '/tmp/foo', '--note=hello world', '--value=--dashy']`
  - Real `codex app-server ...` exited `2` with `error: unexpected argument '--weird-flag' found`
  - OpenCode projection logged `Forwarding passthrough args to opencode serve: ['--weird-flag', 'value', '/tmp/foo', '--note=hello world', '--value=--dashy']`
  - OpenCode projected command: `['opencode', 'serve', '--hostname', '127.0.0.1', '--port', '47992', '--weird-flag', 'value', '/tmp/foo', '--note=hello world', '--value=--dashy']`
  - Real `opencode serve ...` exited `1` and surfaced its own help/usage
- Managed-flag collision checks still preserved both values in order:
  - Claude projection with resolver `--allowedTools A,B` and user tail `--allowedTools C,D` produced `... '--allowedTools', 'A,B', '--foo', 'bar', '--allowedTools', 'C,D'`
  - Codex projection with resolver sandbox `read-only` and user tail `-c sandbox_mode=yolo` produced `... '--sandbox', 'read-only', '-c', 'approval_policy=\"on-request\"', '-c', 'sandbox_mode=yolo', '--weird-flag', 'value', '-'`
