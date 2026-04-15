# S038: Codex fail-closed capability mismatch

- **Source:** design/edge-cases.md E38 + decisions.md D20 fail-closed policy
- **Added by:** @design-orchestrator (revision pass 1)
- **Tester:** @smoke-tester
- **Status:** verified

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
Verified 2026-04-10 with extra coverage.

- `tests/harness/test_launch_spec_parity.py:865` (`test_codex_build_command_fails_closed_when_approval_mode_unmappable`) proves subprocess Codex raises `HarnessCapabilityMismatch` before launch.
- `tests/harness/test_codex_ws.py:486` (`test_codex_ws_thread_bootstrap_fails_closed_on_unmappable_permission_mode`) proves the streaming bootstrap path fails closed the same way.
- Local `codex exec --help` and generated app-server schema confirm the currently supported approval values on `codex-cli 0.118.0`; the mismatch tests therefore cover the intentional fail-closed branch rather than an obsolete CLI surface.

### Smoke-tester re-verification (p1463, 2026-04-10)
Simulated future capability drift by monkeypatching `project_codex_subprocess._APPROVAL_POLICY_BY_MODE["confirm"] = None` and `_SANDBOX_MODE_BY_MODE["read-only"] = None` inside a smoke script. Exercised each projection entry point and captured the raised exception:

- `project_codex_spec_to_cli_args(spec_with_confirm)` → `HarnessCapabilityMismatch("Codex cannot express requested approval mode 'confirm' on this CLI/protocol version")`
- `project_codex_spec_to_appserver_command(spec_with_confirm)` → same structured error (streaming command build path)
- `project_codex_spec_to_thread_request(spec_with_confirm)` → same (streaming thread-bootstrap path)
- `project_codex_spec_to_cli_args(spec_with_read_only_sandbox)` → `HarnessCapabilityMismatch("Codex cannot express requested sandbox mode 'read-only' on this CLI/protocol version")`
- `project_codex_spec_to_thread_request(spec_with_read_only_sandbox)` → same

All five fail-closed paths raise before any process launch. The streaming projection inherits the fail-closed boundary via its direct `map_codex_approval_policy`/`map_codex_sandbox_mode` imports from `project_codex_subprocess`, so a future mapping table edit can only fail-closed; there is no silent-downgrade branch.

In the non-drift (default) configuration, `PermissionConfig` itself rejects invalid mode strings at the Pydantic layer before the projection is even called — an additional upstream guard complementing the projection-level fail-closed.
