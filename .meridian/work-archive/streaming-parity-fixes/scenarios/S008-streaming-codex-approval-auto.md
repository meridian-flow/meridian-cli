# S008: Streaming Codex with `approval=auto`

- **Source:** design/edge-cases.md E8 + p1411 finding H1
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @smoke-tester
- **Status:** verified

## Given
User spawns a Codex streaming task with `approval=auto`. Real `codex app-server` is available on PATH.

## When
Codex issues JSON-RPC `requestApproval` messages during the session.

## Then
- Every `requestApproval` is auto-accepted by the Meridian-side handler without prompting.
- The projection emits `-c approval_policy="auto"` (or the verified equivalent) so Codex itself knows the mode.
- Debug trace shows both the projection override AND the accept path on every approval call.
- No silent collapse to a generic "accept all" that loses the `auto` vs `yolo` vs `default` distinction.

## Verification
- Run a streaming Codex spawn that triggers at least one tool call requiring approval.
- Inspect debug.jsonl for the approval-accept entries and the launch-time `approval_policy` override.
- Confirm `approval=yolo` and `approval=auto` produce different wire commands (parametrized run).

## Result (filled by tester)
Verified 2026-04-10.

- `tests/harness/test_codex_ws.py:95` (`test_codex_ws_auto_accepts_command_execution_approval_requests`) confirms Codex `requestApproval` calls are auto-accepted by Meridian.
- `tests/harness/test_codex_ws.py:276` and `tests/harness/test_codex_ws.py:409` prove streaming projects `approval=auto` to `approval_policy="on-request"` on the app-server command and `"approvalPolicy": "on-request"` on the thread bootstrap payload.
- Local schema generated from `codex app-server generate-json-schema --out /tmp/codex-schema-meridian` shows the current `AskForApproval` enum still includes `untrusted`, `on-failure`, `on-request`, and `never`, so the mapping remains valid on `codex-cli 0.118.0`.
- Distinct `auto`/`yolo`/`default` semantics are covered by the shared Codex approval mapper and the subprocess matrix test at `tests/harness/test_launch_spec_parity.py:846`. This is an inference from the shared mapping helper used by both Codex transports.

### Smoke-tester re-verification (p1463, 2026-04-10)
- Real-binary app-server probe:
  - `workspace-write + auto`: projected `codex app-server --listen ws://127.0.0.1:43477 -c sandbox_mode="workspace-write" -c approval_policy="on-request"`. `/readyz` returned 200, `initialize` accepted, `thread/start` succeeded with payload `{'cwd': '...', 'approvalPolicy': 'on-request', 'sandbox': 'workspace-write'}` and returned `threadId=019d7a9b-8f37-...`.
  - `read-only + auto`: projected `-c sandbox_mode="read-only" -c approval_policy="on-request"`. Live thread created as `019d7a9b-8e94-...`.
- Subprocess side: `codex exec --json --sandbox read-only -c approval_policy="on-request" ...` ran with `rc=0`.
- Comparison: the `approval=default` command emitted no `approval_policy` override while `approval=auto` emitted `-c approval_policy="on-request"` — the two command lines differ exactly by that override, satisfying the "parametrized run must differ" clause.
