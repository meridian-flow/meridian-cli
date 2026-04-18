# Spec — Claude Enforcement (`SL-*`)

Projection happens in `_permission_flags_for_harness` +
`project_claude_spec_to_cli_args`.

## SL-1 Managed read-only → plan mode + denylist

When the spawn's `sandbox` is `read-only` and the harness is claude,
meridian shall project `--permission-mode plan` onto the claude command
line.

## SL-2 Read-only enforces a hard mutating-tool denylist

When the spawn's `sandbox` is `read-only` and the harness is claude,
meridian shall union a mutating-tool denylist
(`Edit`, `Write`, `MultiEdit`, `NotebookEdit`, `Bash`, `WebFetch`) into
the projected `--disallowedTools` tokens, de-duplicated with any
profile-declared `disallowed-tools:` list.

## SL-3 Approval-mode precedence

When the spawn's `approval` is `yolo`, `auto`, or `confirm`, the claude
permission-mode mapping established in `adapter.py:60-83` shall continue
to win over SL-1 — the `sandbox: read-only` → `plan` projection only
applies when `approval = "default"` (no explicit approval override).

## SL-4 Allowlist projection (unchanged mechanism, tightened contract)

When the spawn declares `tools: [...]`, meridian shall project those
tokens into `--allowedTools` on the claude command line via the existing
`ExplicitToolsResolver` path, and claude's permission precedence
(`deny > allow`) shall hold when SL-2 also emits deny tokens for the
same tool name.

## SL-5 Denylist projection (unchanged mechanism, tightened contract)

When the spawn declares `disallowed-tools: [...]`, meridian shall
project those tokens into `--disallowedTools` on the claude command
line via the existing `DisallowedToolsResolver` path, merged with SL-2's
union.

## SL-6 Capability declaration

The claude harness adapter shall declare
`supports_managed_sandbox = True` (for `read-only`),
`supports_managed_allowlist = True`, and
`supports_managed_denylist = True`.

## SL-7 Write attempt refusal under read-only

When a claude spawn is launched with `sandbox = "read-only"` and the
agent attempts to call `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, or
`Bash`, claude shall refuse the tool call with a visible permission-deny
signal in the emitted events (per SL-2 denylist).

## SL-8 Non-allowlisted tool refusal

When a claude spawn is launched with
`allowed_tools = [Read, Grep, Glob]` and the agent attempts to invoke a
tool outside that set, claude shall refuse the tool call with a visible
permission-deny signal.
