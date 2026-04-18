# Refactors: mars add Bootstrap

## Required Refactors

None. The change is additive.

## Optional Cleanup (deferred)

### Extract `bootstrap_project` helper

Currently, `init.rs` has `ensure_consumer_config` which creates `mars.toml`. The bootstrap logic in `find_agents_root` could share this.

**Recommendation**: Extract to a shared `bootstrap::bootstrap_project()` function.

**Reason for deferral**: The duplication is minimal (3-4 lines). Can be done during implementation if the code feels cleaner, but not a blocker.

### Remove or simplify `default_project_root`

`default_project_root` exists to find the git root for `mars init` when no `--root` is specified. With git no longer being a boundary for bootstrap, this function's role is reduced.

**Recommendation**: Keep for `mars init` backward compatibility. `mars init` without `--root` still defaults to git root (when available) or cwd. This is unchanged.

**Note**: The new bootstrap logic in `find_agents_root` does NOT call `default_project_root`. It bootstraps at cwd directly. The two code paths are now independent.
