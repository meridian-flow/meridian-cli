# Refactors: mars add Bootstrap

## Required Refactors

None. The change is additive.

## Optional Cleanup (deferred)

### Extract `bootstrap_project` helper

Currently, `init.rs` has `ensure_consumer_config` which creates `mars.toml`. The bootstrap logic in `find_agents_root` could share this.

**Recommendation**: Extract to a shared `bootstrap::bootstrap_project()` function.

**Reason for deferral**: The duplication is minimal (3-4 lines). Can be done during implementation if the code feels cleaner, but not a blocker.

### Consolidate root-finding variants

`find_agents_root` and `default_project_root` have overlapping logic. Could be unified.

**Recommendation**: Not in scope. The current separation (one finds config, one finds git root) is clear.
