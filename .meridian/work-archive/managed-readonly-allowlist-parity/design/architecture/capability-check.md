# Architecture — Capability Check Gate

Implements E-1/E-2/E-3 fail-closed behavior. Single narrow interface in
`safety/permissions.py`.

## `HarnessCapabilities` extension

In `harness/adapter.py`, add three fields to `HarnessCapabilities`:

```python
class HarnessCapabilities(BaseModel):
    # ... existing fields ...
    supports_managed_sandbox: bool = False
    supports_managed_allowlist: bool = False
    supports_managed_denylist: bool = False
```

Each adapter advertises what it can enforce:

| Adapter  | sandbox | allowlist | denylist |
|----------|---------|-----------|----------|
| codex    | True (via CODEX_HOME config.toml) | True (features + apps._default) | True |
| claude   | True (plan + denylist union) | True (--allowedTools) | True (--disallowedTools) |
| opencode | True (OPENCODE_PERMISSION baseline) | True (OPENCODE_PERMISSION allow set) | True (OPENCODE_PERMISSION deny set) |

All three flip to `True` as part of this change. Before: codex had no
managed allowlist; claude had no managed sandbox; opencode had no managed
sandbox. The flags exist to make future capability regressions loud —
turning a flag to `False` immediately produces `HarnessCapabilityMismatch`
for existing profiles, which surfaces the regression in the smoke matrix.

## Check site

The check runs once in `resolve_permission_pipeline`:

```python
def resolve_permission_pipeline(
    *,
    sandbox: str | None,
    allowed_tools: tuple[str, ...] = (),
    disallowed_tools: tuple[str, ...] = (),
    approval: str = "default",
    harness_capabilities: HarnessCapabilities,
    harness_id: HarnessId,
) -> tuple[PermissionConfig, PermissionResolver]:
    # ... existing config/resolver construction ...

    _assert_supported(
        harness_id=harness_id,
        capabilities=harness_capabilities,
        config=config,
        allowed_tools=allowed_tools,
        disallowed_tools=disallowed_tools,
    )
    return config, resolver
```

where:

```python
def _assert_supported(*, harness_id, capabilities, config,
                     allowed_tools, disallowed_tools) -> None:
    if config.sandbox == "read-only" and not capabilities.supports_managed_sandbox:
        raise HarnessCapabilityMismatch(
            harness_id=harness_id,
            axis="sandbox",
            requested="read-only",
        )
    if allowed_tools and not capabilities.supports_managed_allowlist:
        raise HarnessCapabilityMismatch(
            harness_id=harness_id,
            axis="allowed-tools",
            requested=",".join(allowed_tools),
        )
    if disallowed_tools and not capabilities.supports_managed_denylist:
        raise HarnessCapabilityMismatch(
            harness_id=harness_id,
            axis="disallowed-tools",
            requested=",".join(disallowed_tools),
        )
```

`HarnessCapabilityMismatch` is the existing exception type from
`project_codex_subprocess.py:80` — already imported and used in the codex
projection. Reusing it keeps one error family instead of introducing a new
one.

## Error propagation

The exception raised in `resolve_permission_pipeline` is caught by
`prepare.py`'s spawn-prep orchestrator. The spawn is recorded with
`status = "failed"` and `exit_reason = "capability_mismatch"`. The CLI
renders a single-line error message naming the harness and axis; dry-run
mode surfaces the same message (per SD-4).

## Why this placement

- Single choke point. Adapters do not each repeat the check.
- Before any launch-layer side effect (atomic writes, env merges).
- Composable with future harnesses: a new harness adapter ships with the
  three capability flags set correctly and gets fail-closed behavior for
  free.
