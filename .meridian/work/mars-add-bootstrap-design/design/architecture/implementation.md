# Architecture: Init-Centric Bootstrap

## Target Repository

`mars-agents` — all changes land in the mars CLI. No meridian changes required unless doc updates reference the new behavior.

## Design Decision: Init as the Bootstrap Primitive

### Rejected: Per-command bootstrap logic

Each command that requires context (`add`, `sync`, etc.) could independently check for missing config and bootstrap. This leads to duplication, inconsistent behavior, and hidden special cases.

### Chosen: Shared init semantics via allowlist

The dispatch layer checks whether a command is in the auto-init allowlist. Auto-init commands invoke init logic when config is missing; init-required commands fail fast. The init logic is shared, not duplicated.

## Implementation Shape

### Modified: `find_agents_root` signature

```rust
pub fn find_agents_root(
    explicit: Option<&Path>,
    auto_init: AutoInit,
) -> Result<MarsContext, MarsError>

/// Whether this command may auto-initialize a project.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AutoInit {
    /// Auto-initialize if config is missing.
    Allowed,
    /// Fail if config is missing.
    Required,
}
```

### Modified: `find_agents_root_from`

```rust
fn find_agents_root_from(
    _explicit: Option<&Path>,
    start: &Path,
    auto_init: AutoInit,
) -> Result<MarsContext, MarsError> {
    let cwd_canon = start.canonicalize().unwrap_or_else(|_| start.to_path_buf());
    let mut dir = cwd_canon.as_path();

    loop {
        let config_path = dir.join("mars.toml");
        if config_path.exists() {
            return MarsContext::new(dir.to_path_buf());
        }

        // No git boundary check — walk to filesystem root
        match dir.parent() {
            Some(parent) => dir = parent,
            None => break,
        }
    }

    // No config found anywhere
    if auto_init == AutoInit::Allowed {
        return invoke_init_at(&cwd_canon);
    }

    Err(MarsError::Config(ConfigError::Invalid {
        message: format!(
            "no mars.toml found from {} to filesystem root. Run `mars init` first.",
            start.display()
        ),
    }))
}
```

### New: `invoke_init_at` helper

This helper reuses the init logic from `init.rs`:

```rust
/// Invoke init semantics at a directory, returning context with bootstrapped=true.
fn invoke_init_at(project_root: &Path) -> Result<MarsContext, MarsError> {
    // Reuse the core init logic
    init::bootstrap_at(project_root)?;
    
    let mut ctx = MarsContext::new(project_root.to_path_buf())?;
    ctx.bootstrapped = true;
    Ok(ctx)
}
```

### Modified: `init.rs` — extract bootstrap_at

Factor out the core bootstrap logic from `init::run` so it can be called by auto-init:

```rust
/// Core bootstrap: create mars.toml and managed directory.
/// Returns (project_root, managed_root, already_initialized).
pub fn bootstrap_at(project_root: &Path) -> Result<(PathBuf, PathBuf, bool), MarsError> {
    let config_path = project_root.join("mars.toml");
    let already_initialized = config_path.exists();
    
    if !already_initialized {
        crate::fs::atomic_write(&config_path, b"[dependencies]\n")?;
    }
    
    let managed_root = project_root.join(".agents");
    std::fs::create_dir_all(&managed_root)?;
    std::fs::create_dir_all(project_root.join(".mars"))?;
    
    Ok((project_root.to_path_buf(), managed_root, already_initialized))
}

/// Run `mars init` (CLI entry point).
pub fn run(args: &InitArgs, explicit_root: Option<&Path>, json: bool) -> Result<i32, MarsError> {
    // 1. Determine project root
    let project_root = explicit_root.map(Path::to_path_buf).unwrap_or_else(|| {
        std::env::current_dir().unwrap()
    });

    // 2. Determine target from args or existing config
    let target = determine_target(args, &project_root);
    validate_target(&target)?;
    
    // 3. Bootstrap
    let (_, managed_root, already_initialized) = bootstrap_at(&project_root)?;
    
    // 4. Persist settings.managed_root if non-default
    if target != ".agents" {
        persist_managed_root(&project_root, &target)?;
    }
    
    // ... rest of init logic (messaging, --link, etc.)
}
```

### Modified: MarsContext struct

```rust
pub struct MarsContext {
    pub project_root: PathBuf,
    pub managed_root: PathBuf,
    pub bootstrapped: bool,  // NEW: true if this invocation created the project
}

impl MarsContext {
    pub fn new(project_root: PathBuf) -> Result<Self, MarsError> {
        // ... existing logic ...
        Ok(MarsContext {
            project_root: project_canon,
            managed_root,
            bootstrapped: false,  // default
        })
    }
}
```

### Modified: Command dispatch

```rust
fn dispatch_result(cli: Cli) -> Result<i32, MarsError> {
    match &cli.command {
        // Root-free commands (no context needed)
        Command::Init(args) => init::run(args, cli.root.as_deref(), cli.json),
        Command::Check(args) => check::run(args, cli.json),
        Command::Cache(args) => cache::run(args, cli.json),
        
        // Auto-init allowed
        Command::Add(args) => {
            let ctx = find_agents_root(cli.root.as_deref(), AutoInit::Allowed)?;
            add::run(args, &ctx, cli.json)
        }
        
        // Init-required (all other commands)
        cmd => {
            let ctx = find_agents_root(cli.root.as_deref(), AutoInit::Required)?;
            dispatch_with_root(cmd, &ctx, cli.json)
        }
    }
}
```

### Modified: add.rs output

```rust
pub fn run(args: &AddArgs, ctx: &super::MarsContext, json: bool) -> Result<i32, MarsError> {
    // Print bootstrap message first if auto-init occurred
    if ctx.bootstrapped && !json {
        output::print_success(&format!(
            "initialized {} with mars.toml",
            ctx.project_root.display()
        ));
    }
    
    // ... rest of existing add logic ...
}
```

## File Changes Summary

| File | Change |
|------|--------|
| `src/cli/mod.rs` | Add `AutoInit` enum, modify `find_agents_root` to accept it, remove git boundary from walk-up, add `invoke_init_at` helper, modify dispatch to pass `AutoInit::Allowed` for `add` |
| `src/cli/init.rs` | Extract `bootstrap_at()` as reusable core logic |
| `src/cli/add.rs` | Check `ctx.bootstrapped` and print init message if true |
| `src/types.rs` | Add `bootstrapped: bool` to `MarsContext` struct |

## Walk-up Changes

### Current behavior (git boundary)

```rust
// Never cross the current git root (or submodule root).
if dir.join(".git").exists() {
    break;
}
```

### New behavior (filesystem root only)

The `.git` check is removed. Walk-up continues until `Path::parent()` returns `None` (filesystem root).

### Key implications

- A project can span multiple git repos
- Non-git directories work identically to git directories
- Nested git repos don't affect root discovery
- Walk-up still prefers the nearest `mars.toml`, so existing projects work unchanged

## Default Project Root

The current `default_project_root()` function walks up to git root. For `mars init` in the new model:

**Option A**: Remove git-root behavior, use cwd directly.  
**Option B**: Keep git-root for init, but use cwd for auto-init from add.

**Chosen**: Option A — consistency. `mars init` uses cwd as the project root unless `--root` is specified. This matches the auto-init behavior and removes the git dependency from init as well.

```rust
// Before: walk up to git root
pub fn default_project_root() -> Result<PathBuf, MarsError> {
    let cwd = std::env::current_dir()?;
    let mut dir = cwd.as_path();
    loop {
        if dir.join(".git").exists() {
            return Ok(dir.to_path_buf());
        }
        match dir.parent() {
            Some(parent) => dir = parent,
            None => return Ok(cwd),
        }
    }
}

// After: just use cwd
pub fn default_project_root() -> Result<PathBuf, MarsError> {
    std::env::current_dir().map_err(Into::into)
}
```

## Windows Path Semantics

### Walk-up termination

The `Path::parent()` method correctly handles platform differences:

| Platform | Path | `parent()` |
|----------|------|------------|
| Unix | `/` | `None` |
| Windows | `C:\` | `None` |
| Windows | `D:\project` | `D:\` |
| Windows | `\\server\share` | `\\server` or `None` (implementation-dependent) |

The walk-up loop uses `match dir.parent() { None => break, ... }`, which terminates correctly on both platforms.

### canonicalize() behavior

Windows `canonicalize()` returns extended-length paths (`\\?\...`). The implementation:
1. Uses canonicalized paths for filesystem operations (correctness)
2. Uses `display()` for user output (readability)
3. Falls back to original path if canonicalize fails (non-existent paths)

### Path separator handling

Rust's `PathBuf` accepts both `/` and `\` as separators on Windows. No normalization needed.

### Case sensitivity

Windows paths are case-insensitive. `canonicalize()` normalizes case, so path comparisons work correctly after canonicalization.

## Testing Strategy

### Unit tests to add

1. `auto_init_at_cwd_when_no_config` — no `mars.toml` anywhere, `AutoInit::Allowed`, invoke_init_at at cwd
2. `no_init_when_required` — no `mars.toml`, `AutoInit::Required`, error returned
3. `existing_config_not_overwritten` — `mars.toml` exists, `bootstrapped` is false, content unchanged
4. `walk_up_finds_ancestor_config` — `mars.toml` in parent, no init even with `AutoInit::Allowed`
5. `walk_up_reaches_filesystem_root` — deep directory with no `mars.toml` anywhere, init at cwd

### Unit tests to remove

- `walk_up_stops_at_git_boundary` — git is no longer a boundary
- `submodule_isolation` — git submodules are no longer special

### Windows-specific tests

These tests run only on Windows (`#[cfg(target_os = "windows")]`):

1. `walk_up_terminates_at_drive_root` — deep path on `C:\`, walk-up terminates at `C:\`
2. `auto_init_at_cwd_not_drive_root` — `mars add` from `C:\temp\test`, init at cwd not `C:\`
3. `root_flag_accepts_forward_slashes` — `--root C:/project` works
4. `root_flag_accepts_backslashes` — `--root C:\project` works
5. `unc_path_walk_up` — `\\server\share\project\subdir` walks up correctly

### Smoke tests

1. Fresh directory (no git) → `mars add owner/repo` → prints init message, adds dependency
2. Fresh directory → `mars init` then `mars add` → no init message second time
3. Existing project → `mars add another/dep` → no init message
4. Subdirectory of project → `mars add pkg` → finds existing `mars.toml`, no init
5. Subdirectory of project → `mars add pkg --root .` → creates nested project
6. Fresh directory → `mars sync` → error with "Run `mars init` first"
7. Fresh directory → `mars list` → error with "Run `mars init` first"

### CI matrix

- `ubuntu-latest`
- `macos-latest`
- `windows-latest`

## Edge Cases

### Nested mars projects

If `/project/mars.toml` exists and user runs from `/project/subdir`, walk-up finds the existing config. No init. If user wants a nested project, they use `mars add --root .` to force cwd.

### Permission errors

If `mars.toml` cannot be written, the error surfaces naturally from `atomic_write`.

### Race with concurrent `mars add`

Two `mars add` commands in the same uninitialized directory:
- Both detect missing `mars.toml`
- Both attempt `invoke_init_at`
- First atomic_write wins (tmp+rename)
- Second one sees existing file on next check
- `bootstrap_at` returns `already_initialized=true` for the second
- Both proceed to add their dependency

This is correct. Atomic writes and idempotent init handle the race.

### Existing `.agents/` without `mars.toml`

`bootstrap_at` creates `mars.toml` and leaves `.agents/` as-is. This covers repos with manually created `.agents/`.

## Migration / Compatibility

### Behavioral change: add

Previously: `mars add` in uninitialized directory → error
Now: `mars add` in uninitialized directory → auto-init at cwd + add

This is additive. No existing workflows depend on the error.

### Behavioral change: init

Previously: `mars init` defaults to git root if inside a git repo
Now: `mars init` defaults to cwd

This could affect users who expect `mars init` from a subdirectory to create config at git root. Mitigation: the init message shows exactly where config was created. Users can retry with `--root $(git rev-parse --show-toplevel)` if needed.

### Documentation updates

| Doc | Change |
|-----|--------|
| `mars-agents/docs/quickstart.md` | Simplify — `mars add` works directly, no init step |
| `mars-agents/docs/commands/init.md` | Note that init defaults to cwd, not git root |
| `mars-agents/docs/troubleshooting.md` | Update "no mars.toml found" section |
| `meridian-cli/docs/getting-started.md` | Simplify first-use flow |
