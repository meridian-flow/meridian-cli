# S032: Codex approval rejection event visible on queue

- **Source:** design/edge-cases.md E32 + p1411 M9
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @unit-tester (+ @smoke-tester)
- **Status:** verified

## Given
Streaming Codex in confirm mode receives `requestApproval`.

## When
Approval handler rejects request.

## Then
- Rejection event is enqueued first.
- Only after enqueue does handler await `send_error`.
- Ordering assertions use call sequence / sequence number, not wall-clock timing.

## Verification
- Unit test with instrumented queue/send_error hooks asserts enqueue-before-await.
- Smoke test verifies event appears before terminal failure signal.

## Result (filled by tester)
Verified 2026-04-10 with extra coverage.

- `tests/harness/test_codex_ws.py:125` verifies `warning/approvalRejected` is visible on the queue for confirm-mode rejection.
- `tests/harness/test_codex_ws.py:180` verifies enqueue-before-await ordering by inspecting queue head inside instrumented `_send_jsonrpc_error`.
- This run re-executed both tests after adding adjacent adversarial coverage, so the queue-ordering guarantee was revalidated rather than inherited from the prior coder report.

### Smoke-tester re-verification (p1463, 2026-04-10)
Drove the real `CodexConnection._handle_server_request` directly with a synthetic `{"id": 42, "method": "execCommand/requestApproval", ...}` frame against a `PermissionConfig(approval="confirm")` spec. Wrapped `_event_queue.put` and `_send_jsonrpc_error` to capture call order; observed:

```
ordering log:
  ('put', 'warning/approvalRejected')
  ('send_error', (42, -32000, 'Codex websocket approval requests are unsupported in confirm mode.'))
```

The `put` call for `warning/approvalRejected` strictly precedes the `send_error` call — verified by sequence number, not timing. A consumer reading the event queue would see the rejection event before any downstream turn failure.
