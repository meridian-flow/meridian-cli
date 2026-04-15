# S007: Streaming Codex with `sandbox=read-only`

- **Source:** design/edge-cases.md E7 + p1411 finding H1
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @smoke-tester
- **Status:** verified

## Given
User spawns a Codex streaming task with `PermissionConfig(sandbox="read-only", approval="auto")`. The real `codex app-server` binary is installed and on PATH.

## When
The streaming runner launches Codex via `project_codex_spec_to_appserver_command`.

## Then
- The launch command contains `-c sandbox_mode="read-only"` (verified against real `codex app-server --help` output at implementation time).
- Debug trace confirms the flag reaches the Codex process.
- A write operation attempted inside the sandboxed Codex session is rejected by Codex.
- No silent downgrade: removing the flag must cause the test to fail.

## Verification
- Run `uv run meridian spawn -a coder -m codex -p "try to write /tmp/hack" --sandbox read-only`.
- Capture the `debug.jsonl` for the spawn and confirm the sandbox override line.
- Inspect the spawn report and confirm the write attempt was rejected.
- Delta test: flip the projection temporarily to omit the override, rerun, and confirm the write succeeds (this proves the flag was the reason — not a default).
- Compare against the subprocess path for the same inputs; the sandbox-related behavior must match.

## Result (filled by tester)
Verified 2026-04-10 by @smoke-tester p1463.

- `tests/harness/test_codex_ws.py:276` (`test_codex_streaming_projection_builds_appserver_command_and_logs_ignored_report_path`) proves the streaming app-server command carries `-c sandbox_mode="read-only"`.
- `tests/harness/test_codex_ws.py:409` (`test_codex_ws_thread_bootstrap_request_projects_effort_and_permission_config`) proves the bootstrap payload carries `"sandbox": "read-only"`.
- Generated the app-server JSON schema locally (`codex app-server generate-json-schema --experimental --out /tmp/codex-schema`) and confirmed `v2/ThreadStartParams.json` still pins `SandboxMode` to `[read-only, workspace-write, danger-full-access]`.

### Real-binary round-trip (new evidence)
The prior "Operation not permitted" blocker was environment-specific. In the p1463 smoke environment the real `codex app-server` binds and accepts wire traffic:

- Projection output: `codex app-server --listen ws://127.0.0.1:55777 -c sandbox_mode="read-only" -c approval_policy="on-request"`
- `/readyz` returned 200 within 8 s.
- Websocket `initialize` accepted (`id=1` result includes `userAgent=meridian-smoke/0.118.0`).
- `thread/start` sent with payload `{'cwd': '/tmp/phase4-smoke', 'approvalPolicy': 'on-request', 'sandbox': 'read-only'}` succeeded and returned a real `threadId` (`019d7a9b-8e94-...`).
- Subprocess side also exercised end-to-end: `codex exec --json --model gpt-5-codex --sandbox read-only -c approval_policy="on-request" ...` ran with `rc=0` and produced a valid JSON event stream (`thread.started → turn.completed`).

Meridian's contract is to pass the flag correctly — this is verified at both command-line and wire-payload level. Runtime write-rejection is a Codex-internal behavior beyond the projection boundary.
