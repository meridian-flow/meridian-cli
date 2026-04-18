# Phase 1: Core Refactor — Remove PermissionTier and Simplify Sandbox Passthrough

## Scope

Remove the `PermissionTier` enum and all validation/parsing functions around it. Rename `PermissionConfig.tier` to `.sandbox` (type `str | None`). Remove `KNOWN_SANDBOX_VALUES` and all validators that reference it. Update all production code consumers to use the new field name.

## Files to Modify

### Primary: `src/meridian/lib/safety/permissions.py`

- **Delete** `PermissionTier` StrEnum (lines 15-22)
- **Delete** `parse_permission_tier()` function (lines 40-53)
- **Delete** `permission_tier_from_profile()` function (lines 56-76)
- **Delete** `_parse_permission_tier_value()` function (lines 79-90)
- **Rename** `PermissionConfig.tier: PermissionTier | None` to `sandbox: str | None = None`
- **Simplify** `build_permission_config()`: remove tier parsing, just normalize whitespace: `normalized = sandbox.strip().lower() if sandbox else None`
- **Simplify** `permission_flags_for_harness()`: change `tier = config.tier` to `sandbox = config.sandbox`, change `tier.value` to `sandbox`
- **Update** `resolve_permission_pipeline()`: use `config.sandbox` instead of `config.tier` in any internal references
- **Keep** `TieredPermissionResolver` name unchanged (decision D6)
- **Keep** `_parse_approval_value()`, all tool resolvers, `opencode_permission_json_*` functions unchanged
- **Remove** `PermissionTier` from module `__all__` if present, and the `StrEnum` import if no longer needed

### Validation removal: `src/meridian/lib/core/overrides.py`

- **Delete** `KNOWN_SANDBOX_VALUES` frozenset (lines 20-28)
- **Delete** `_validate_sandbox` field validator from `RuntimeOverrides` (lines 95-106)
- **Remove** `KNOWN_SANDBOX_VALUES` from `__all__` export list (line 236)

### Validation removal: `src/meridian/lib/config/settings.py`

- **Remove** `KNOWN_SANDBOX_VALUES` from import line (lines 13-17)
- **Delete** `_validate_sandbox` field validator from `PrimaryConfig` (lines 631-642)

### Warning removal: `src/meridian/lib/catalog/agent.py`

- **Remove** `KNOWN_SANDBOX_VALUES` / `_KNOWN_SANDBOX_VALUES` import (lines 11-15, 24)
- **Delete** unknown sandbox warning check (lines 92-97)

### Field rename: `src/meridian/lib/ops/spawn/execute.py`

- **Rename** `BackgroundWorkerParams.permission_tier` to `sandbox` (line 83)
- **Update** serialization site (~line 542-546): `sandbox=prepared.execution.permission_config.sandbox` (was `permission_tier=...tier.value...`)
- **Update** consumer site (~line 852-855): `sandbox=params.sandbox` (was `sandbox=params.permission_tier`)

### CLI: `src/meridian/cli/spawn.py`

- **Update** `--sandbox` help text (~lines 177-186): change to `"Sandbox mode passed to harness (e.g., read-only, workspace-write). Overrides agent profile."`

### Import-only updates:

- `src/meridian/lib/launch/plan.py` — change `permission_config.tier` to `permission_config.sandbox` where accessed (~lines 302-307)
- `src/meridian/lib/launch/env.py` — verify no `.tier` field access (type annotation only, likely no change needed)
- `src/meridian/lib/launch/command.py` — verify no `.tier` field access (type annotation only, likely no change needed)

## Dependencies

- **Requires**: Nothing — this is the foundation phase
- **Independent of**: Test updates (Phase 2)

## Interface Contract (post-change)

```python
class PermissionConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    sandbox: str | None = None
    approval: str = "default"
    opencode_permission_override: str | None = None

def build_permission_config(sandbox: str | None, *, approval: str = "default") -> PermissionConfig:
    """Normalize and package. No tier parsing."""

def permission_flags_for_harness(harness_id: HarnessId, config: PermissionConfig) -> list[str]:
    """Sandbox string passes through to --sandbox flag for Codex. Other harnesses: []."""
```

## Patterns to Follow

The `model` and `harness` fields in `RuntimeOverrides` are the pattern — free-form `str | None` with no validator, validated by downstream consumers. Sandbox should look identical.

## Constraints

- **Do NOT rename** `TieredPermissionResolver` (decision D6)
- **Do NOT touch** approval mode logic in `permission_flags_for_harness()`
- **Do NOT modify** `.agents/` profile YAML files
- **Do NOT touch** `allowed_tools`/`disallowed_tools` resolver system
- **Do NOT modify** harness adapter files (`claude.py`, `codex.py`, `opencode.py`)

## Verification Criteria

- [ ] `uv run pyright` passes with 0 errors
- [ ] `uv run ruff check .` passes
- [ ] `grep -r "PermissionTier" src/` returns no results
- [ ] `grep -r "KNOWN_SANDBOX_VALUES" src/` returns no results
- [ ] `grep -r "permission_tier_from_profile" src/` returns no results
- [ ] `grep -r "parse_permission_tier" src/` returns no results
- [ ] `grep -r "\.tier" src/meridian/lib/safety/permissions.py` returns no results (no `.tier` field access)
