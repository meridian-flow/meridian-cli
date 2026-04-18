# Spec — Cross-Harness Enforcement Contract (`E-*`)

Fail-closed uniform guarantees that hold across all three supported harnesses.

## E-1 Fail-closed on unsupported sandbox

If a spawn request specifies `sandbox = "read-only"` (from CLI, profile,
or config) and the selected harness adapter does not declare
`supports_managed_sandbox = True` for that mode, then meridian shall raise
`HarnessCapabilityMismatch` during spawn preparation and shall not launch
the harness process.

## E-2 Fail-closed on unsupported allowlist

If a spawn request specifies a non-empty `allowed_tools` list (from
profile `tools:` frontmatter or future CLI) and the selected harness adapter
does not declare `supports_managed_allowlist = True`, then meridian shall
raise `HarnessCapabilityMismatch` during spawn preparation and shall not
launch the harness process.

## E-3 Fail-closed on unsupported denylist

If a spawn request specifies a non-empty `disallowed_tools` list and the
selected harness adapter does not declare `supports_managed_denylist = True`,
then meridian shall raise `HarnessCapabilityMismatch` during spawn
preparation and shall not launch the harness process.

## E-4 Passthrough for `default` sandbox

When `sandbox = "default"` (no meridian opinion) and tool lists are empty,
meridian shall not add any projected enforcement flags and shall not raise
a capability mismatch error.

## E-5 No silent strip

Meridian shall not drop or replace a user-declared enforcement flag
(`--sandbox`, `--allowedTools`, `--disallowedTools`, or any resolver-emitted
equivalent) with a log-only warning; every drop must either (a) be covered
by an equivalent managed mechanism on that harness, or (b) produce an
`HarnessCapabilityMismatch` per E-1/E-2/E-3.

## E-6 Uniform spawn-time rejection semantics

When meridian rejects a spawn per E-1/E-2/E-3, the error shall name:
(a) the harness id (`codex`/`claude`/`opencode`),
(b) the unsatisfied axis (`sandbox`/`allowed-tools`/`disallowed-tools`),
(c) the requested value,
and shall be recorded in the spawn record with status `failed` and
`exit_reason = "capability_mismatch"`.

## E-7 Profile `tools:` / `disallowed-tools:` reaches the harness

When a profile declares `tools: [...]` and/or `disallowed-tools: [...]`
and the selected harness declares support, meridian shall inject an
enforcement layer (per SC-*, SL-*, SO-* below) that rejects invocation of
tools outside the declared set, with a visible enforcement signal
(permission prompt, tool rejection, sandbox error) rather than a silent
pass.

## E-8 Refusal of write under `sandbox: read-only`

When a spawn is launched with `sandbox = "read-only"` and the spawned
agent attempts to write a file or execute a mutating shell command, the
harness process shall surface a visible refusal signal (non-zero tool
result, sandbox error, or permission denial) in its emitted events.

## E-9 Stable dry-run surface

When `meridian spawn --dry-run` is invoked for any supported harness with
an enforcement-carrying profile, the dry-run output shall include the
effective enforcement surface: (a) the `CODEX_HOME` path and generated
`config.toml` body for codex, (b) the `--permission-mode` and
`--disallowedTools` flags for claude, (c) the `OPENCODE_PERMISSION` env
value for opencode. See SD-*.
