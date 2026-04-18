# Overrides and CLI Changes

## `overrides.py` Changes

### Remove `KNOWN_SANDBOX_VALUES`

```python
# DELETE this:
KNOWN_SANDBOX_VALUES = frozenset({
    "read-only", "workspace-write", "full-access",
    "danger-full-access", "unrestricted",
})
```

### Remove `_validate_sandbox` validator

The `RuntimeOverrides.sandbox` field becomes a plain `str | None` with no validator — same as the `model` and `harness` fields, which are also free-form strings that the downstream consumer validates.

```python
class RuntimeOverrides(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str | None = None
    harness: str | None = None
    effort: str | None = None
    sandbox: str | None = None      # no validator — passthrough
    approval: str | None = None     # keeps validator (known set)
    autocompact: int | None = None
    timeout: float | None = None
```

### Update `__all__` exports

Remove `KNOWN_SANDBOX_VALUES` from `__all__`.

## `settings.py` Changes

### Remove `_validate_sandbox` from `PrimaryConfig`

`settings.py` has its **own independent** sandbox validator on the `PrimaryConfig` class (lines 631-642) that imports `KNOWN_SANDBOX_VALUES`:

```python
# DELETE this validator from PrimaryConfig:
@field_validator("sandbox")
@classmethod
def _validate_sandbox(cls, value: str | None) -> str | None:
    ...
    if normalized not in KNOWN_SANDBOX_VALUES:
        raise ValueError(...)
```

And remove `KNOWN_SANDBOX_VALUES` from the import on line 16.

Without this, `primary.sandbox: none` in `meridian.toml` would still be rejected even though CLI and env vars pass through.

## Agent Profile Loader (`catalog/agent.py`)

### Remove unknown sandbox warning

Currently:
```python
if sandbox is not None and sandbox and sandbox not in _KNOWN_SANDBOX_VALUES:
    logger.warning("Agent profile '%s' has unknown sandbox '%s'.", ...)
```

Remove the check and the `_KNOWN_SANDBOX_VALUES` import entirely. Any non-empty string is a valid sandbox value — the harness validates it.

## CLI (`cli/spawn.py`)

### Update `--sandbox` help text

Current:
```python
help=(
    "Sandbox mode: read-only, workspace-write, full-access, "
    "danger-full-access, unrestricted. Overrides agent profile."
),
```

Target:
```python
help="Sandbox mode passed to harness (e.g., read-only, workspace-write). Overrides agent profile.",
```

The help text becomes harness-agnostic — it gives examples but doesn't enumerate a fixed set.

## `execute.py` (spawn execution)

### Rename `permission_tier` to `sandbox` in `BackgroundWorkerParams`

```python
# was: permission_tier: str | None = None
sandbox: str | None = None
```

Call site (line ~542-545):
```python
# was:
permission_tier=(
    prepared.execution.permission_config.tier.value
    if prepared.execution.permission_config.tier is not None
    else None
),
# becomes:
sandbox=prepared.execution.permission_config.sandbox,
```

Consumer (line ~852-855):
```python
# was:
permission_config, permission_resolver = resolve_permission_pipeline(
    sandbox=params.permission_tier,
    ...
)
# becomes:
permission_config, permission_resolver = resolve_permission_pipeline(
    sandbox=params.sandbox,
    ...
)
```

## Test Changes (`tests/exec/test_permissions.py`)

- Remove all `PermissionTier` imports and enum comparisons
- `config.tier is PermissionTier.WORKSPACE_WRITE` becomes `config.sandbox == "workspace-write"`
- `test_codex_uses_exact_sandbox_tier_from_profile` — stays but asserts on string values
- `test_build_launch_env_never_exports_permission_tier` — rename test, verify `sandbox` field behavior

## Test Changes (5 other test files)

These files import `TieredPermissionResolver` to construct test fixtures:
- `tests/test_launch_process.py`
- `tests/exec/test_signals.py`
- `tests/exec/test_claude_cwd_isolation.py`
- `tests/exec/test_pipe_drain.py`
- `tests/exec/test_lifecycle.py`

All have the pattern:
```python
from meridian.lib.safety.permissions import PermissionConfig, TieredPermissionResolver
...
permission_resolver=TieredPermissionResolver(config=PermissionConfig()),
```

Keep the class name `TieredPermissionResolver` (see decision D6 update) — no rename needed, so these files only need import path verification, no code changes.
