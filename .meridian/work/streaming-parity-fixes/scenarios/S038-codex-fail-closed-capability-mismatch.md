# S038: Codex fail-closed capability mismatch

- **Source:** design/edge-cases.md E38 + decisions.md D20 fail-closed policy
- **Added by:** @design-orchestrator (revision pass 1)
- **Tester:** @smoke-tester
- **Status:** pending

## Given
Requested sandbox/approval semantics cannot be represented by current `codex app-server` interface.

## When
Codex streaming projection resolves launch command.

## Then
- Projection raises `HarnessCapabilityMismatch`.
- Spawn fails before launch.
- No silent downgrade to defaults.

## Verification
- Inject unsupported capability mapping in test harness.
- Assert fail-before-launch error path and structured message.

## Result (filled by tester)
_pending_
