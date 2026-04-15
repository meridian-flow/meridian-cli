# S016: Codex permission matrix semantics

- **Source:** design/edge-cases.md E16 + p1411 H1
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @unit-tester (+ @smoke-tester)
- **Status:** verified

## Given
Sandbox x approval matrix over:

- sandbox: `default`, `read-only`, `workspace-write`, `danger-full-access`
- approval: `default`, `auto`, `yolo`, `confirm`

## When
Matrix is projected for subprocess and streaming Codex paths.

## Then
- Semantic behavior and audit trail are distinct per mode intent.
- Wire strings may collapse where Codex exposes fewer knobs.
- No silent collapse to permissive behavior.

## Verification
- Parametrized tests assert semantic expectations per cell.
- Smoke subset validates representative runtime behavior.
- Audit logs confirm mode-specific handling (`auto` vs `yolo` vs `confirm`).

## Result (filled by tester)
Verified 2026-04-10 with extra coverage.

- `tests/harness/test_launch_spec_parity.py:846` (`test_codex_build_command_permission_matrix_projection`) covers representative sandbox×approval cells across subprocess Codex projection.
- `tests/harness/test_launch_spec_parity.py:818` (`test_codex_build_command_keeps_colliding_approval_override_in_tail`) proves user tail overrides stay verbatim even when they collide with managed approval flags.
- `tests/harness/test_codex_ws.py:355` (`test_codex_streaming_projection_keeps_colliding_passthrough_config_args`) proves the streaming path also keeps colliding approval/sandbox overrides verbatim at the tail.
- `tests/harness/test_codex_ws.py:409` plus `tests/exec/test_streaming_runner.py:526` prove the streaming bootstrap payload and runner carry the resolved permission config through to the Codex connection.

### Smoke-tester re-verification (p1463, 2026-04-10)
Generated the canonical schema (`codex app-server generate-json-schema --experimental --out /tmp/codex-schema`) and verified the wire enums on `codex-cli 0.118.0`:

- `v2/ThreadStartParams.json → definitions.AskForApproval.oneOf[0].enum = ['untrusted','on-failure','on-request','never']`
- `v2/ThreadStartParams.json → definitions.SandboxMode.enum = ['read-only','workspace-write','danger-full-access']`

Cross-cell projection spot-check against real binary (representative cells):

| Meridian sandbox | Meridian approval | subprocess command tail              | streaming payload                                             |
|------------------|-------------------|--------------------------------------|---------------------------------------------------------------|
| default          | default           | `codex exec --json -`                | `{cwd: ...}`                                                  |
| read-only        | auto              | `--sandbox read-only -c approval_policy="on-request"` | `{cwd, approvalPolicy: on-request, sandbox: read-only}`       |
| workspace-write  | auto              | `--sandbox workspace-write -c approval_policy="on-request"` | `{..., sandbox: workspace-write}`                             |
| read-only        | confirm           | `--sandbox read-only -c approval_policy="untrusted"`  | `{..., approvalPolicy: untrusted, sandbox: read-only}`        |

All three `approval=auto` cells ran a full JSON-RPC round trip (initialize + thread/start) against the real `codex app-server` and returned valid threadIds. Subprocess read-only+auto ran a real `codex exec` with `rc=0`. No silent collapse: each intent produced a distinct wire string.
