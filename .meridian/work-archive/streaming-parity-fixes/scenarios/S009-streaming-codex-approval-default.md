# S009: Streaming Codex with `approval=default`

- **Source:** design/edge-cases.md E9 + p1411 finding H1
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @smoke-tester
- **Status:** verified

## Given
User spawns Codex streaming with `approval=default`. Real `codex app-server` is available.

## When
The streaming runner launches Codex.

## Then
- `codex app-server` launch command contains **no** `approval_policy` override. Codex applies its own default (accept-all in exec mode).
- No Meridian-side approval-accept logic runs (confirmed by debug trace showing no `requestApproval` entries from the Meridian handler).
- The spawn succeeds with the harness-native default behavior.
- Removing the override-suppression (making v2 behave like v1) causes this test to fail.

## Verification
- Run a streaming Codex spawn with `approval=default`.
- Inspect the debug trace: no `-c approval_policy=...` override in the launch command line.
- Inspect the Meridian handler log: no "auto-accepted approval" entries.
- Compare the launch command for `approval=default` vs `approval=auto` — they must differ in the presence/absence of the override.

## Result (filled by tester)
Verified 2026-04-10 by @smoke-tester p1463.

- `tests/harness/test_codex_ws.py:307` (`test_codex_streaming_projection_default_approval_emits_no_policy_override`) proves the streaming projection emits no `approval_policy` override and omits `approvalPolicy` from the bootstrap payload.
- `tests/harness/test_codex_ws.py:334` (`test_codex_streaming_projection_with_no_overrides_emits_clean_baseline_command`) adds the clean baseline command case with no passthrough noise.

### Real-binary round-trip (new evidence)
Ran a full JSON-RPC round trip against the real `codex app-server` binary with `PermissionConfig(sandbox="default", approval="default")`:

- Projection output: `['codex', 'app-server', '--listen', 'ws://127.0.0.1:58653']` — no `-c approval_policy`, no `-c sandbox_mode`, no passthrough.
- Compared against `approval=auto` baseline: `['codex', 'app-server', '--listen', 'ws://127.0.0.1:...', '-c', 'sandbox_mode="..."', '-c', 'approval_policy="on-request"']` — the two commands differ exactly in the presence/absence of the override, matching the scenario's "must differ" clause.
- Real app-server started, `/readyz` returned 200, websocket `initialize` succeeded.
- `thread/start` sent with payload `{'cwd': '/tmp/phase4-smoke'}` — no `approvalPolicy`, no `sandbox` — and Codex returned a valid thread `019d7a9b-8fd7-...` without error.
- No Meridian-side approval-accept path runs because no `requestApproval` server request was issued in the default flow (the handler at `CodexConnection._handle_server_request` only accepts if the method lands in confirm mode; otherwise the harness defaults apply).

The projection's no-override-in-default contract holds at both command-line and wire-payload levels, and the real binary accepts the clean baseline.
