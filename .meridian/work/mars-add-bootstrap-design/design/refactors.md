# Refactors: Walk-Up Add, Explicit Init

## Required Refactors

### REF-1: Remove git boundary from walk-up

**Scope**: `src/cli/mod.rs`, function `find_agents_root_from`

**Current state**:
```rust
// Never cross the current git root (or submodule root).
if dir.join(".git").exists() {
    break;
}
```

**Target state**: Delete this check. Walk continues until `Path::parent()` returns `None`.

**Rationale**: Git is not a requirement. Walk-up should reach filesystem root.

**Lines affected**: 3 lines deleted.

### REF-2: Change `default_project_root` to return cwd

**Scope**: `src/cli/mod.rs`, function `default_project_root`

**Current state**: Walks up to git root or falls back to cwd.

**Target state**: Returns `std::env::current_dir()` directly.

**Rationale**: Init should default to cwd, not git root.

**Lines affected**: ~10 lines replaced with 1 line.

### REF-3: Remove auto-init from add

**Scope**: `src/cli/add.rs` and `src/cli/mod.rs`

**Current state**: `add` has auto-init logic that creates `mars.toml` if not found.

**Target state**: `add` uses standard context discovery. No auto-init. Error if no project found.

**Rationale**: `add` operates on existing projects only. Creation is `init`'s job.

**Lines affected**: ~20-30 lines removed from add.rs and dispatch logic.

### REF-4: Remove ancestor warning machinery

**Scope**: `src/cli/add.rs` and `src/cli/mod.rs`

**Current state**: `find_root_for_write` returns optional ancestor path, `add` emits warning.

**Target state**: No ancestor detection needed. Walk-up naturally uses ancestor when present.

**Rationale**: With walk-up semantics, using the ancestor is correct behavior, not a warning condition.

**Lines affected**: ~15 lines deleted (find_ancestor_config helper, warning emission).

### REF-5: Remove `bootstrapped` field from MarsContext

**Scope**: `src/types.rs` or `src/cli/mod.rs` (wherever MarsContext is defined)

**Current state**: `MarsContext { project_root, managed_root, bootstrapped: bool }`

**Target state**: `MarsContext { project_root, managed_root }`

**Rationale**: No auto-init means no need to track whether this invocation created the project.

**Lines affected**: ~5 lines removed.

### REF-6: Unify root selection to single path

**Scope**: `src/cli/mod.rs`

**Current state**: Dual-path with `find_root_for_write` and `find_root_for_context`.

**Target state**: Single `find_root_for_context` for all context commands. Init uses cwd directly.

**Rationale**: With auto-init removed from add, all context commands use the same algorithm.

**Lines affected**: ~30 lines removed (find_root_for_write, RootSelection enum).

## Test Refactors

### REF-T1: Remove git-boundary tests

**Tests to remove**:
- `walk_up_stops_at_git_boundary`
- `submodule_isolation`

**Rationale**: Git is no longer a boundary. These tests assert removed behavior.

### REF-T2: Remove auto-init tests

**Tests to remove**:
- `auto_init_at_cwd_not_ancestor`
- `auto_init_warns_on_ancestor`
- `no_walk_up_for_add`

**Rationale**: Auto-init behavior removed. These tests no longer apply.

### REF-T3: Add walk-up add tests

**Tests to add**:
- `add_walks_up_to_ancestor` — ancestor `mars.toml` exists, cwd does not, `add` uses ancestor
- `add_fails_when_no_project` — no config anywhere, `add` errors
- `add_does_not_create_config` — verify no `mars.toml` created on add failure

**Rationale**: Cover the walk-up behavior for add.

### REF-T4: Add Windows-specific tests

**Tests to add** (gated with `#[cfg(target_os = "windows")]`):
- `walk_up_terminates_at_drive_root`
- `root_flag_accepts_forward_slashes`
- `root_flag_accepts_backslashes`
- `unc_path_walk_up`

**Rationale**: Validate Windows path handling explicitly.

## Follow-On Refactors (Separate Tracks)

These are out of scope for this feature but named for future work:

### FO-1: Audit git assumptions repo-wide

After this feature ships, audit the codebase for other git-coupled behaviors:
- Source resolution that assumes git repos
- Cache paths that use git hashes
- Any other `.git` checks

This is a separate design track.

### FO-2: Windows compatibility audit

After this feature ships, audit the full command surface for Windows compatibility:
- Path handling in source resolution
- File operations in the install pipeline
- Shell invocations and process spawning
- Extended-length path support

This is a separate design track.
