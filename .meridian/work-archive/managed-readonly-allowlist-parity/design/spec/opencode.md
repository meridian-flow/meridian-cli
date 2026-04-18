# Spec — OpenCode Enforcement (`SO-*`)

Projection happens via `OPENCODE_PERMISSION` env JSON through
`env_overrides(config)` on `OpenCodeAdapter` and the
`opencode_permission_json_for_*` helpers in
`src/meridian/lib/safety/permissions.py`.

## SO-1 Managed read-only → synthetic deny-baseline JSON

When the spawn's `sandbox` is `read-only` and the harness is opencode,
meridian shall synthesize an `OPENCODE_PERMISSION` JSON value with
`"*": "deny"` as the baseline and `allow` entries only for the documented
read-shaped tool names (`read`, `grep`, `glob`, `list`, `webfetch`
explicitly excluded).

## SO-2 Read-only + allowlist composition

When the spawn's `sandbox` is `read-only` **and** `allowed_tools` is
non-empty, meridian shall intersect the allowlist with the read-only
baseline — emitting a JSON with `"*": "deny"` plus `allow` only for tools
that appear in both the allowlist and the read-shaped set. A tool
declared in `allowed_tools` but known-mutating (`edit`, `write`,
`patch`, `bash`) shall not be promoted to `allow` under read-only; this
is a contradiction and shall raise `HarnessCapabilityMismatch` at spawn
preparation (per E-2).

## SO-3 Allowlist-only (no read-only)

When the spawn's `allowed_tools` is non-empty and `sandbox != "read-only"`,
the existing `opencode_permission_json_for_allowed_tools` path in
`permissions.py:130` shall remain the mechanism, unchanged.

## SO-4 Denylist-only

When the spawn's `disallowed_tools` is non-empty and `sandbox != "read-only"`,
the existing `opencode_permission_json_for_disallowed_tools` path in
`permissions.py:142` shall remain the mechanism, unchanged.

## SO-5 Env projection unchanged

The `OpenCodeAdapter.env_overrides(config)` implementation shall continue
to return `{"OPENCODE_PERMISSION": config.opencode_permission_override}`
when the override is populated; meridian shall write the synthesized
read-only JSON into `config.opencode_permission_override` during
`resolve_permission_pipeline` rather than in the adapter.

## SO-6 Streaming parity

When opencode is launched in streaming mode, the synthesized
`OPENCODE_PERMISSION` shall flow through the same env injection path as
subprocess mode; the explicit ignore at
`project_opencode_streaming.py:52-55` remains only for sandbox/approval
flags that opencode's HTTP session cannot accept, not for the env
`OPENCODE_PERMISSION` override.

## SO-7 Capability declaration

The opencode harness adapter shall declare
`supports_managed_sandbox = True` (for `read-only`),
`supports_managed_allowlist = True`, and
`supports_managed_denylist = True`.

## SO-8 Write attempt refusal under read-only

When an opencode spawn is launched with `sandbox = "read-only"` and the
agent attempts to call a mutating tool (`write`, `edit`, `patch`,
`bash`), opencode shall refuse the tool call per the
`OPENCODE_PERMISSION "*": "deny"` rule with a visible permission-deny
signal in the emitted events.

## SO-9 Non-allowlisted tool refusal

When an opencode spawn is launched with
`allowed_tools = [Read, Grep, Glob]`, the synthesized JSON shall emit
`{"*": "deny", "read": "allow", "grep": "allow", "glob": "allow"}` and
opencode shall refuse any tool outside that allow-set.
