# Refactors: Init-Centric Bootstrap

## Required Refactors

### REF-1: Extract `bootstrap_at` from init.rs

**Scope**: `src/cli/init.rs`

**Current state**: `ensure_consumer_config` creates `mars.toml`. Directory creation is inline in `run()`.

**Target state**: Extract `bootstrap_at(project_root) -> Result<(PathBuf, PathBuf, bool)>` that:
1. Creates `mars.toml` if missing (via atomic_write)
2. Creates managed directory (`.agents/`)
3. Creates `.mars/` marker
4. Returns `(project_root, managed_root, already_initialized)`

**Rationale**: Auto-init from `add` needs to invoke init logic. Extracting it avoids duplication.

**Lines affected**: ~15 lines extracted, ~5 lines in run() replaced with call.

### REF-2: Remove git boundary from walk-up

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

### REF-3: Change `default_project_root` to return cwd

**Scope**: `src/cli/mod.rs`, function `default_project_root`

**Current state**: Walks up to git root or falls back to cwd.

**Target state**: Returns `std::env::current_dir()` directly.

**Rationale**: Consistency with auto-init. `mars init` should default to cwd, same as auto-init from `add`.

**Lines affected**: ~10 lines replaced with 1 line.

### REF-4: Add `AutoInit` enum and modify `find_agents_root`

**Scope**: `src/cli/mod.rs`

**Current state**: `find_agents_root(explicit: Option<&Path>) -> Result<MarsContext, MarsError>`

**Target state**: 
```rust
pub enum AutoInit { Allowed, Required }
pub fn find_agents_root(explicit: Option<&Path>, auto_init: AutoInit) -> Result<MarsContext, MarsError>
```

**Rationale**: Per-command control over auto-init behavior.

**Lines affected**: ~15 lines added/modified.

### REF-5: Add `bootstrapped` field to MarsContext

**Scope**: `src/types.rs` or `src/cli/mod.rs` (wherever MarsContext is defined)

**Current state**: `MarsContext { project_root, managed_root }`

**Target state**: `MarsContext { project_root, managed_root, bootstrapped: bool }`

**Rationale**: Commands need to know if this invocation created the project (for messaging).

**Lines affected**: ~3 lines added.

## Test Refactors

### REF-T1: Remove git-boundary tests

**Tests to remove**:
- `walk_up_stops_at_git_boundary`
- `submodule_isolation`

**Rationale**: Git is no longer a boundary. These tests assert removed behavior.

### REF-T2: Add auto-init tests

**Tests to add**:
- `auto_init_at_cwd_when_no_config`
- `no_init_when_required`
- `walk_up_reaches_filesystem_root`
- `auto_init_respects_explicit_root`

**Rationale**: Cover the new auto-init behavior.

### REF-T3: Add Windows-specific tests

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
