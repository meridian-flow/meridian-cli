# Architecture: mars add Bootstrap

## Target Repository

`mars-agents` — all changes land in the mars CLI. No meridian changes required unless doc updates reference the new behavior.

## Design Decision: Centralized Auto-Bootstrap

### Rejected: Per-command bootstrap

Each command that requires context (`add`, `sync`, `upgrade`, etc.) could independently check for missing config and bootstrap. This leads to duplication and inconsistent behavior across commands.

### Chosen: Bootstrap flag in `find_agents_root`

The `find_agents_root` function (in `src/cli/mod.rs`) is the single entry point for context-requiring commands. Add an `auto_bootstrap: bool` parameter. Only `add` sets it to `true`.

**Tradeoff**: This couples bootstrap to root discovery. If a command wants to require explicit init (e.g., a hypothetical `mars check-config`), it would need a different code path. Acceptable for now; extract if needed.

## Root Selection Algorithm

### Current behavior (walk-up to git boundary)

1. If `--root` provided, validate `mars.toml` exists there → error if missing
2. Else walk up from cwd, stop at `.git` boundary, looking for `mars.toml`
3. Error if not found

### New behavior (cwd-first, git-agnostic)

1. If `--root` provided:
   - If `mars.toml` exists, use it
   - Else if `auto_bootstrap`, bootstrap at `--root` (create `mars.toml` + `.agents/`)
   - Else error
2. Else walk up from cwd to filesystem root (no git boundary):
   - If `mars.toml` found, use it
   - Else if `auto_bootstrap`, bootstrap at cwd
   - Else error
3. Return `MarsContext` with `bootstrapped: bool` field (for messaging)

### Key change: No git boundary

The walk-up no longer stops at `.git`. It continues to filesystem root. This means:
- A project can span multiple git repos
- Non-git directories work identically
- Nested git repos don't affect root discovery

The walk-up still prefers the nearest `mars.toml`, so existing projects work unchanged.

## Implementation Shape

### Modified: `find_agents_root` signature

```rust
pub fn find_agents_root(
    explicit: Option<&Path>,
    auto_bootstrap: bool,
) -> Result<MarsContext, MarsError>
```

### Modified: `find_agents_root_from`

```rust
fn find_agents_root_from(
    _explicit: Option<&Path>,
    start: &Path,
    auto_bootstrap: bool,
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
    if auto_bootstrap {
        bootstrap_project(&cwd_canon)?;
        let ctx = MarsContext::new(cwd_canon)?;
        return Ok(MarsContext {
            bootstrapped: true,
            ..ctx
        });
    }

    Err(MarsError::Config(ConfigError::Invalid {
        message: format!(
            "no mars.toml found from {} to filesystem root. Run `mars init` first.",
            start.display()
        ),
    }))
}
```

### Modified: `--root` handling

```rust
if let Some(root) = explicit {
    // ... existing validation for managed-dir-looking paths ...
    
    let config_path = root.join("mars.toml");
    if !config_path.exists() {
        if auto_bootstrap {
            bootstrap_project(root)?;
            let ctx = MarsContext::new(root.to_path_buf())?;
            return Ok(MarsContext {
                bootstrapped: true,
                ..ctx
            });
        }
        return Err(MarsError::Config(ConfigError::Invalid {
            message: format!(
                "{} does not contain mars.toml. Run `mars init` first.",
                root.display()
            ),
        }));
    }
    return MarsContext::new(root.to_path_buf());
}
```

### New: `bootstrap_project` helper

```rust
fn bootstrap_project(project_root: &Path) -> Result<(), MarsError> {
    let config_path = project_root.join("mars.toml");
    crate::fs::atomic_write(&config_path, b"[dependencies]\n")?;
    let managed_root = project_root.join(".agents");
    std::fs::create_dir_all(&managed_root)?;
    std::fs::create_dir_all(project_root.join(".mars"))?;
    Ok(())
}
```

This is factored out from `init.rs:ensure_consumer_config` to share logic.

### Modified: MarsContext struct

```rust
pub struct MarsContext {
    pub project_root: PathBuf,
    pub managed_root: PathBuf,
    pub bootstrapped: bool,  // NEW
}
```

### Modified: Command dispatch

```rust
fn dispatch_result(cli: Cli) -> Result<i32, MarsError> {
    match &cli.command {
        // Root-free commands
        Command::Init(args) => init::run(args, cli.root.as_deref(), cli.json),
        Command::Check(args) => check::run(args, cli.json),
        Command::Cache(args) => cache::run(args, cli.json),
        // Add gets auto_bootstrap=true
        Command::Add(args) => {
            let ctx = find_agents_root(cli.root.as_deref(), true)?;
            add::run(args, &ctx, cli.json)
        }
        // All other commands get auto_bootstrap=false
        cmd => {
            let ctx = find_agents_root(cli.root.as_deref(), false)?;
            dispatch_with_root(cmd, &ctx, cli.json)
        }
    }
}
```

### Modified: add.rs output

```rust
pub fn run(args: &AddArgs, ctx: &super::MarsContext, json: bool) -> Result<i32, MarsError> {
    // Print bootstrap message first if applicable
    if ctx.bootstrapped && !json {
        output::print_success(&format!(
            "initialized {} with mars.toml",
            ctx.project_root.display()
        ));
    }
    
    // ... rest of existing add logic ...
}
```

## File Changes

| File | Change |
|------|--------|
| `src/cli/mod.rs` | Add `auto_bootstrap` param to `find_agents_root`, remove git boundary from walk-up, add `bootstrap_project` helper |
| `src/cli/add.rs` | Check `ctx.bootstrapped` and print init message if true |
| `src/types.rs` | Add `bootstrapped: bool` to `MarsContext` struct |

## Edge Cases

### Nested mars projects

If `/project/mars.toml` exists and user runs from `/project/subdir`, walk-up finds the existing config. No bootstrap. This is correct.

If user wants a nested project, they use `mars add --root .` to force cwd.

### Permission errors

If `mars.toml` cannot be written (permissions, read-only filesystem), the error surfaces naturally from `atomic_write`. No special handling needed.

### Race with concurrent `mars add`

Two `mars add` commands running simultaneously in the same uninitialized directory:
- Both detect missing `mars.toml`
- Both attempt `atomic_write`
- First one wins (atomic rename)
- Second one reads the just-created file on next attempt

This is correct. `atomic_write` uses tmp+rename, and the add logic is idempotent.

### Existing `.agents/` directory without `mars.toml`

If `.agents/` exists but `mars.toml` does not, bootstrap creates `mars.toml` and leaves `.agents/` as-is. This covers repos that have manually created `.agents/` or migrated from legacy systems.

### Symlinked directories

Walk-up uses canonicalized paths. If cwd is a symlink, we canonicalize before walking. The bootstrap location is the canonical path.

## Testing Strategy

### Unit tests (src/cli/mod.rs)

1. `bootstrap_at_cwd_when_no_config` — no `mars.toml` anywhere, `auto_bootstrap=true`, bootstrap at cwd
2. `no_bootstrap_when_flag_false` — no `mars.toml`, `auto_bootstrap=false`, error returned
3. `bootstrap_at_explicit_root` — `--root /path` with no `mars.toml`, `auto_bootstrap=true`, bootstrap at path
4. `existing_config_not_overwritten` — `mars.toml` exists, `bootstrapped` is false, content unchanged
5. `walk_up_finds_ancestor_config` — `mars.toml` in parent, no bootstrap even with `auto_bootstrap=true`
6. `walk_up_reaches_filesystem_root` — deep directory with no `mars.toml` anywhere, bootstrap at cwd

### Removed tests

- `walk_up_stops_at_git_boundary` — git is no longer a boundary
- `submodule_isolation` — git submodules are no longer special
- `no_bootstrap_outside_git` — non-git directories now bootstrap normally

### Smoke tests

1. Fresh directory (no git) → `mars add owner/repo` → creates `mars.toml` at cwd, adds dependency, syncs
2. Fresh directory → `mars add owner/repo --root .` → same behavior
3. Existing project → `mars add another/dep` → no init message, dependency added
4. Subdirectory of project → `mars add pkg` → finds existing `mars.toml`, no bootstrap
5. Subdirectory of project → `mars add pkg --root .` → creates nested project

## Migration / Compatibility

### Behavioral change

Previously: `mars add` in uninitialized non-git directory → error
Now: `mars add` in uninitialized directory → auto-init at cwd + add

This is additive, not breaking. No existing workflows depend on the error.

### Git users unaffected (mostly)

Git users who run `mars add` from within their repo will now bootstrap at cwd, not git root. This is a behavior change, but:
- Existing projects (with `mars.toml`) are unaffected
- New projects created at git root work the same
- New projects created from subdirectory will create `mars.toml` at cwd

If this causes issues, users can `mars add --root $(git rev-parse --show-toplevel)` to force git root. We could add a `MARS_PROJECT_ROOT` env var later if demand exists.

### Documentation updates

| Doc | Change |
|-----|--------|
| `mars-agents/docs/troubleshooting.md` | Update "no mars.toml found" section to note auto-bootstrap |
| `meridian-cli/docs/getting-started.md` | Simplify first-use flow — `mars add` works directly |
| `meridian-cli/docs/commands.md` | Note that `mars add` bootstraps if needed |

## Alternatives Considered

### Keep git root as bootstrap target when available

**Rejected**. The user feedback explicitly stated git must not be a requirement. A hybrid design (git root when available, cwd otherwise) would:
- Add complexity
- Create surprising behavior differences between git and non-git
- Contradict the stated requirement

### Require `--init` flag for bootstrap

**Rejected**. Adds explicit control but defeats the purpose of reducing friction. If the user wanted explicit init, they would run `mars init`.

### Prompt before bootstrap

**Rejected**. Adds ceremony that slows down scripts and spawns. The bootstrap location is deterministic (cwd) and logged, so mistakes are surfaced immediately.

### Scan for project markers (pyproject.toml, package.json, etc.)

**Rejected**. Adds complexity and heuristics. Different projects use different markers. cwd is a simple, universal signal that the user controls directly.
