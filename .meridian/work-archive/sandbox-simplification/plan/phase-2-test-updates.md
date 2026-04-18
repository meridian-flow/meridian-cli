# Phase 2: Test Updates — Rewrite Permission Test Assertions

## Scope

Update `tests/exec/test_permissions.py` to remove all `PermissionTier` enum references. Change enum comparison assertions to string comparisons. Verify the 5 other test files that import `TieredPermissionResolver` need no changes (since the class name is preserved per D6).

## Files to Modify

### Primary: `tests/exec/test_permissions.py`

- **Remove** `PermissionTier` from imports (lines 11-20)
- **Rewrite assertions**: `config.tier is PermissionTier.WORKSPACE_WRITE` becomes `config.sandbox == "workspace-write"`
- **Rewrite assertions**: `config.tier is PermissionTier.FULL_ACCESS` becomes `config.sandbox == "full-access"`
- **Rewrite assertions**: `config.tier is PermissionTier.DANGER_FULL_ACCESS` becomes `config.sandbox == "danger-full-access"`
- **Rewrite assertions**: `config.tier is PermissionTier.UNRESTRICTED` becomes `config.sandbox == "unrestricted"`
- **Update** any `config.tier is None` checks to `config.sandbox is None`
- **Update** test that checks `BackgroundWorkerParams` field name if present (was `permission_tier`, now `sandbox`)
- **Rename** test functions if they reference "tier" in the name (e.g., `test_codex_uses_exact_sandbox_tier_from_profile` -> keep as-is or update, coder's judgment)

### Verify only (expect no changes): 5 test files

These import `TieredPermissionResolver` and `PermissionConfig` — since both names are preserved, no changes needed. Verify they still compile:

- `tests/test_launch_process.py`
- `tests/exec/test_signals.py`
- `tests/exec/test_claude_cwd_isolation.py`
- `tests/exec/test_pipe_drain.py`
- `tests/exec/test_lifecycle.py`

If any of these access `.tier` on a `PermissionConfig` instance (not just construct with defaults), update to `.sandbox`.

## Dependencies

- **Requires**: Phase 1 (new `PermissionConfig.sandbox` field must exist)
- Could run in parallel if coder codes against the target interface contract from Phase 1

## Interface Contract (from Phase 1)

```python
class PermissionConfig(BaseModel):
    sandbox: str | None = None    # was: tier: PermissionTier | None
    approval: str = "default"
    opencode_permission_override: str | None = None
```

## Verification Criteria

- [ ] `uv run pytest-llm` — all tests pass
- [ ] `uv run pyright` passes with 0 errors
- [ ] `grep -r "PermissionTier" tests/` returns no results
- [ ] `grep -r "\.tier" tests/exec/test_permissions.py` returns no results
