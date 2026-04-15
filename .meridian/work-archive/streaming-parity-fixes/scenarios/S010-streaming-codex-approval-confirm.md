# S010: Streaming Codex with `approval=confirm` rejects and emits event

- **Source:** design/edge-cases.md E10 + p1411 finding H1 + M9
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @smoke-tester (+ @unit-tester for queue assertion)
- **Status:** verified

## Given
User spawns Codex streaming with `approval=confirm`. There is no interactive channel attached. Real `codex app-server` is available.

## When
Codex issues a JSON-RPC `requestApproval` during the session.

## Then
- Meridian rejects the approval request (returns a JSON-RPC error back to Codex).
- **Before** the JSON-RPC error response is sent, a `HarnessEvent("warning/approvalRejected", {"reason": "confirm_mode", "method": method})` is enqueued on the event stream.
- A warning is logged.
- The consumer observing the event queue sees the rejection event directly without having to infer from downstream turn failures.

## Verification
- Unit test: drive the `codex_ws` approval handler with a synthetic `requestApproval` frame and assert the event queue has the `warning/approvalRejected` event.
- Smoke test: run a real `approval=confirm` spawn that forces a tool call, capture the event stream, assert the warning event is present and appears before the final error.
- Confirm v1 behavior (log-only, no event) is now impossible — grep the handler for the log statement and ensure the event emission sits next to it.

## Result (filled by tester)
Verified 2026-04-10 with extra coverage.

- `tests/harness/test_codex_ws.py:125` (`test_codex_ws_rejects_approval_requests_in_confirm_mode_and_emits_warning_event`) proves confirm-mode approval requests are rejected and emit `warning/approvalRejected`.
- `tests/harness/test_codex_ws.py:180` (`test_codex_ws_confirm_mode_enqueues_rejection_event_before_send_error`) proves enqueue-before-await ordering using call sequence, not wall-clock timing.
- `tests/harness/test_codex_ws.py:486` (`test_codex_ws_thread_bootstrap_fails_closed_on_unmappable_permission_mode`) also guards the fail-closed side of confirm-mode mapping.

### Smoke-tester re-verification (p1463, 2026-04-10)
Drove the real `CodexConnection._handle_server_request` with a synthetic server frame `{"id": 42, "method": "execCommand/requestApproval", ...}` against a spec carrying `PermissionConfig(approval="confirm")`. Instrumented `_event_queue.put` and `_send_jsonrpc_error` to record call order:

```
ordering log:
  ('put', 'warning/approvalRejected')
  ('send_error', (42, -32000, 'Codex websocket approval requests are unsupported in confirm mode.'))
```

- Logger also emitted `Rejecting Codex server approval request in confirm mode: execCommand/requestApproval` before the enqueue.
- Projection layer cross-check: confirm mode on the subprocess command emits `-c approval_policy="untrusted"`; the app-server command emits the same; the thread bootstrap payload emits `approvalPolicy: "untrusted"` — matching the `AskForApproval` enum on the current `v2/ThreadStartParams.json`.
