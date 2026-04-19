# Architecture: Walk-Up Add, Explicit Init

## Target Repository

`mars-agents` — all changes land in the mars CLI. No meridian changes required unless doc updates reference the new behavior.

## Design Decision: Unified Walk-Up for Context Commands

### Key Insight

All context-requiring commands (add, sync, list, etc.) share the same project discovery algorithm: walk up from cwd to filesystem root, find nearest `mars.toml`, error if not found.

Only `init` is different: it creates a project at an explicit target (cwd or `--root`) without walking up.

### Rejected: Dual-path with cwd-first for add

Using cwd-first for `add` (auto-init if no config at cwd) was rejected because:
- Diverges from `uv add`, `cargo add`, npm semantics
- Creates nested projects implicitly — confusing when user meant to add to parent
- Requires ancestor-warning machinery that adds complexity without benefit

### Chosen: Single walk-up algorithm for all context commands

The dispatch layer uses one algorithm for context commands:
- **Context commands** (`add`, `sync`, `list`, etc.): walk up from cwd (or `--root`) to filesystem root, error if not found
- **Create command** (`init`): target is cwd (or `--root`) exactly, no walk-up

## Implementation Shape

### Existing: `find_root_for_context` function

For all context commands, walk up to find existing config:

```rust
/// Find project root for context/read commands.
/// Walks from target (cwd or --root) to filesystem root.
fn find_root_for_context(
    explicit: Option<&Path>,
) -> Result<MarsContext, MarsError> {
    let start = match explicit {
        Some(p) => p.to_path_buf(),
        None => std::env::current_dir()?,
    };
    let start_canon = start.canonicalize().unwrap_or_else(|_| start.clone());
    let mut dir = start_canon.as_path();

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
    Err(MarsError::Config(ConfigError::Invalid {
        message: format!(
            "no mars.toml found from {} to filesystem root. Run `mars init` first.",
            start.display()
        ),
    }))
}
```

### Init: target-based, no walk-up

Init uses cwd (or `--root`) directly without walk-up:

```rust
/// Run `mars init` (CLI entry point).
pub fn run(args: &InitArgs, explicit_root: Option<&Path>, json: bool) -> Result<i32, MarsError> {
    // 1. Determine project root — cwd or explicit --root, no walk-up
    let project_root = explicit_root.map(Path::to_path_buf).unwrap_or_else(|| {
        std::env::current_dir().unwrap()
    });
    let project_root_canon = project_root.canonicalize()
        .unwrap_or_else(|_| project_root.clone());

    // 2. Check if already initialized
    let config_path = project_root_canon.join("mars.toml");
    if config_path.exists() {
        if !json {
            output::print_info(&format!(
                "already initialized at {}",
                project_root_canon.display()
            ));
        }
        return Ok(0);
    }

    // 3. Bootstrap
    crate::fs::atomic_write(&config_path, b"[dependencies]\n")?;
    std::fs::create_dir_all(project_root_canon.join(".agents"))?;
    std::fs::create_dir_all(project_root_canon.join(".mars"))?;

    if !json {
        output::print_success(&format!(
            "initialized {} with mars.toml",
            project_root_canon.display()
        ));
    }

    // 4. Handle additional init args (--link, etc.)
    // ...
    Ok(0)
}
```

### Command dispatch

```rust
fn dispatch_result(cli: Cli) -> Result<i32, MarsError> {
    match &cli.command {
        // Root-free commands (no context needed)
        Command::Init(args) => init::run(args, cli.root.as_deref(), cli.json),
        Command::Check(args) => check::run(args, cli.json),
        Command::Cache(args) => cache::run(args, cli.json),
        
        // All context commands use walk-up (including add)
        cmd => {
            let ctx = find_root_for_context(cli.root.as_deref())?;
            dispatch_with_context(cmd, &ctx, cli.json)
        }
    }
}

fn dispatch_with_context(cmd: &Command, ctx: &MarsContext, json: bool) -> Result<i32, MarsError> {
    match cmd {
        Command::Add(args) => add::run(args, ctx, json),
        Command::Sync(args) => sync::run(args, ctx, json),
        Command::List(args) => list::run(args, ctx, json),
        // ... other context commands
        _ => unreachable!("root-free commands handled separately"),
    }
}
```

### add.rs: no auto-init, no ancestor handling

```rust
pub fn run(
    args: &AddArgs, 
    ctx: &MarsContext,
    json: bool,
) -> Result<i32, MarsError> {
    // Context was resolved by dispatcher — project exists
    // No bootstrap logic, no ancestor warnings
    
    // ... existing add logic: resolve package, update mars.toml, sync ...
}
```

## File Changes Summary

| File | Change |
|------|--------|
| `src/cli/mod.rs` | Remove dual-path root selection, use single `find_root_for_context` for all context commands including `add` |
| `src/cli/init.rs` | Confirm cwd-only target, no walk-up |
| `src/cli/add.rs` | Remove bootstrap/auto-init logic, remove ancestor parameter |

## Walk-up Changes

### Current behavior (git boundary)

```rust
// Never cross the current git root (or submodule root).
if dir.join(".git").exists() {
    break;
}
```

### New behavior

The `.git` check is removed. Walk-up continues until `Path::parent()` returns `None`.

### Key implications

- Walk-up finds nearest ancestor `mars.toml`
- Git is not a boundary or requirement for any operation
- `add` from a subdirectory uses the ancestor project (not auto-init at cwd)
- Nested mars projects require explicit `mars init`

## Default Project Root

The previous `default_project_root()` function walked up to git root. This is replaced:

**For init**: cwd directly (or `--root`), no helper needed
**For context commands**: walk-up via `find_root_for_context`

```rust
// Removed: default_project_root() that walked to git root
// Replaced by: direct cwd usage for init, walk-up for context commands
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

1. `add_walks_up_to_ancestor` — ancestor `mars.toml` exists, cwd does not, `add` uses ancestor
2. `add_fails_when_no_project` — no config anywhere, `add` errors with "Run `mars init` first"
3. `add_does_not_auto_init` — no config anywhere, `add` does NOT create config
4. `context_walk_up_finds_ancestor` — for `sync`, walk-up finds ancestor config
5. `explicit_root_starts_walk_from_path` — `--root /path` walks up from that path

### Unit tests to remove

- `walk_up_stops_at_git_boundary` — git is no longer a boundary
- `submodule_isolation` — git submodules are no longer special
- `auto_init_at_cwd_not_ancestor` — auto-init removed
- `auto_init_warns_on_ancestor` — ancestor warning removed

### Windows-specific tests

These tests run only on Windows (`#[cfg(target_os = "windows")]`):

1. `walk_up_terminates_at_drive_root` — deep path on `C:\`, walk-up terminates at `C:\`
2. `add_finds_ancestor_across_drive_path` — `mars add` from `C:\project\subdir` finds `C:\project\mars.toml`
3. `root_flag_accepts_forward_slashes` — `--root C:/project` works
4. `root_flag_accepts_backslashes` — `--root C:\project` works
5. `unc_path_walk_up` — `\\server\share\project\subdir` walks up correctly

### Smoke tests

1. Fresh directory (no project) → `mars add owner/repo` → error "Run `mars init` first"
2. Fresh directory → `mars init` then `mars add` → works
3. Existing project → `mars add another/dep` → works
4. Subdirectory of project → `mars add pkg` → uses parent project (walk-up)
5. Subdirectory of project → `mars sync` → finds parent project via walk-up
6. Fresh directory → `mars sync` → error with "Run `mars init` first"
7. Nested projects → `mars list` in nested → uses nested config, not ancestor

### CI matrix

- `ubuntu-latest`
- `macos-latest`
- `windows-latest`

## Edge Cases

### Nested mars projects

If `/project/mars.toml` and `/project/subdir/mars.toml` both exist:
- Run `mars add foo` from `/project/subdir` → uses `/project/subdir/mars.toml` (nearest)
- Run `mars add foo` from `/project/subdir/deeper` → uses `/project/subdir/mars.toml` (nearest)

Nested projects require explicit `mars init` to create. Walk-up finds the nearest config.

### Permission errors

If `mars.toml` cannot be read, the error surfaces naturally from the filesystem.

### Race with concurrent init

Two `mars init` commands in the same directory:
- Both attempt to create `mars.toml`
- First atomic_write wins (tmp+rename)
- Second one sees existing file on next check
- Init reports "already initialized" for the second
- Both succeed

### Existing `.agents/` without `mars.toml`

`mars add` fails — no `mars.toml` means no project, even if `.agents/` exists. User must run `mars init`.

### --root for add

If user runs `mars add foo/bar --root /path`:
- Walk-up starts from `/path`, not cwd
- Find nearest `mars.toml` at or above `/path`
- If not found, error with "Run `mars init` first"

## Migration / Compatibility

### Behavioral change: add requires existing project

Previously: `mars add` auto-inited if no config found
Now: `mars add` errors, requires `mars init` first

This is intentional. Users who expected auto-init now get a clear error directing them to `mars init`.

### Behavioral change: add in subdirectory uses ancestor

Previously: `mars add` from subdirectory auto-inited nested project with warning
Now: `mars add` from subdirectory uses ancestor project

This matches `uv add`, `cargo add`, npm semantics.

### Behavioral change: init

Previously: `mars init` defaults to git root if inside a git repo
Now: `mars init` defaults to cwd

Users who expected git-root initialization can use `--root $(git rev-parse --show-toplevel)`.

### Documentation updates

| Doc | Change |
|-----|--------|
| `mars-agents/docs/quickstart.md` | Document two-step flow: `mars init` then `mars add` |
| `mars-agents/docs/commands/init.md` | Note that init defaults to cwd, not git root |
| `mars-agents/docs/commands/add.md` | Document walk-up behavior, remove auto-init |
| `mars-agents/docs/troubleshooting.md` | Update "no mars.toml found" section |
| `meridian-cli/docs/getting-started.md` | Document `mars init` step |
