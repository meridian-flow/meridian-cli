# S047: `mcp_tools` is projected into every harness's wire format

- **Source:** design/edge-cases.md E47 + decisions.md H4 (revision round 3 — restore `mcp_tools` as first-class forwarded field, supersedes round 2 D23)
- **Added by:** @design-orchestrator (revision round 3)
- **Tester:** @unit-tester
- **Status:** verified

## Given
A `ResolvedLaunchSpec` (per harness) with `mcp_tools = ("codex-mcp=/usr/local/bin/codex-mcp", "other=/opt/other")` (two entries in the Codex name=command form). For Claude, the same conceptual input uses path-style entries. For OpenCode streaming, the session-payload server list form. For OpenCode subprocess, the non-empty case is a **reject** path — the subprocess CLI has no wire encoding for MCP configuration.

## When
Each of the six projection functions runs on its respective spec subclass.

## Then
- Claude subprocess: command contains `--mcp-config codex-mcp=/usr/local/bin/codex-mcp --mcp-config other=/opt/other` (one `--mcp-config` per entry, in order).
- Claude streaming: same canonical ordering, identical to subprocess.
- Codex subprocess: command contains `-c mcp.servers.codex-mcp.command="/usr/local/bin/codex-mcp" -c mcp.servers.other.command="/opt/other"`.
- Codex streaming (`project_codex_spec_to_appserver_command`): same `-c mcp.servers.*.command=...` emission at the canonical position, before `spec.extra_args`.
- **OpenCode subprocess: non-empty `mcp_tools` raises `ValueError` with a clear message directing the user to the streaming transport.** Empty `mcp_tools = ()` is a no-op. The field is still claimed by the projection's `_PROJECTED_FIELDS` (K9 accounting) so the drift guard passes, but the projection function refuses to silently drop a non-empty value.
- OpenCode streaming (`project_opencode_spec_to_session_payload`): HTTP payload has `mcp: {"servers": ["codex-mcp=/usr/local/bin/codex-mcp", "other=/opt/other"]}`.
- Empty `mcp_tools = ()` produces no wire-level MCP state on any harness (no empty `--mcp-config`, no empty `-c mcp.servers`, no empty `mcp` key in the payload, no `ValueError` on OpenCode subprocess).

## Verification
- Five projection "happy path" unit tests (one per projection that carries MCP) asserting the exact wire output for the two-entry fixture.
- One OpenCode subprocess reject test asserting `ValueError` with the expected message substring (`"does not carry mcp_tools"`).
- Six empty-tuple unit tests asserting empty `mcp_tools` produces no MCP-related output (and no `ValueError` on OpenCode subprocess).
- Cross-check: assert `mcp_tools` appears in every projection's `_PROJECTED_FIELDS` set and every adapter's `handled_fields`.
- Drift guard: `_check_projection_drift` fails if any projection omits `mcp_tools`.

## Result (filled by tester)
verified 2026-04-11

- Evidence:
  - `tests/harness/test_launch_spec_parity.py:982` — `test_claude_projection_projects_mcp_tools_for_subprocess_and_streaming`
  - `tests/harness/test_launch_spec_parity.py:1342` — `test_codex_projection_projects_mcp_tools_for_subprocess_and_streaming`
  - `tests/harness/test_launch_spec.py:181` — `test_opencode_subprocess_rejects_mcp_tools`
  - `tests/harness/test_launch_spec_parity.py:1512` — `test_opencode_streaming_projection_projects_mcp_tools_in_session_payload`
  - `tests/harness/test_launch_spec_parity.py:1529` — `test_empty_mcp_tools_emit_no_wire_state_across_all_supported_projections`
  - `tests/harness/test_launch_spec_parity.py:1579` — `test_mcp_tools_is_accounted_for_by_all_projections_and_adapters`
- Notes:
  - Claude and Codex project `mcp_tools`; OpenCode subprocess fails closed with `HarnessCapabilityMismatch` (now a `ValueError` subtype), and OpenCode streaming uses `mcp: {servers: [...]}`.
