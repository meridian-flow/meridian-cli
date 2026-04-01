# Phase 5: CLI Commands + Integration Tests

## Scope

Implement all v1 CLI commands using clap derive API, wire them to the library functions, add output formatting, and write end-to-end integration tests that exercise the binary. This is the user-facing shell — it calls into the library and formats results.

## Why Last

The CLI is a thin layer over the library. Every command calls library functions implemented in Phases 1-4. Building the CLI last means all the business logic is tested and stable — the CLI just wires args to function calls and formats output.

## Files to Modify

### `src/main.rs` — Binary Entry Point

```rust
use clap::Parser;

fn main() {
    let cli = mars_agents::cli::Cli::parse();
    let result = mars_agents::cli::dispatch(cli);
    match result {
        Ok(code) => std::process::exit(code),
        Err(e) => {
            eprintln!("error: {e}");
            std::process::exit(3);
        }
    }
}
```

### `src/cli/mod.rs` — Top-Level CLI Definition

```rust
use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(name = "mars", about = "Package manager for .agents/")]
pub struct Cli {
    #[command(subcommand)]
    pub command: Command,

    /// Path to .agents/ directory (default: auto-detect by walking up from cwd)
    #[arg(long, global = true)]
    pub root: Option<PathBuf>,

    /// Output as JSON
    #[arg(long, global = true)]
    pub json: bool,
}

#[derive(Subcommand)]
pub enum Command {
    /// Initialize .agents/ with agents.toml
    Init(init::InitArgs),
    /// Add a source
    Add(add::AddArgs),
    /// Sync sources to .agents/
    Sync(sync::SyncArgs),
    /// Remove a source
    Remove(remove::RemoveArgs),
    /// Mark conflicts as resolved
    Resolve(resolve_cmd::ResolveArgs),
    /// Rename a managed item
    Rename(rename::RenameArgs),
    /// List managed items
    List(list::ListArgs),
    /// Upgrade sources to newest compatible versions
    Upgrade(upgrade::UpgradeArgs),
    /// Explain why an item is installed
    Why(why::WhyArgs),
    /// Set a dev override for a source
    Override(override_cmd::OverrideArgs),
}

pub fn dispatch(cli: Cli) -> Result<i32>;

/// Find .agents/ root by walking up from cwd, or use --root flag
pub fn find_agents_root(explicit: Option<&Path>) -> Result<PathBuf>;
```

### `src/cli/init.rs` — `mars init`

```rust
pub struct InitArgs {
    /// Path to initialize (default: current directory)
    pub path: Option<PathBuf>,
}
```

- Create `.agents/agents.toml` with empty `[sources]` section.
- Create `.agents/.mars/` directory.
- Add `.agents/.mars/` to `.gitignore` if not already there.
- If `.agents/agents.toml` already exists, error (suggest `mars sync` instead).
- If `.agents/` exists with content but no `agents.toml`, offer to create config alongside existing content.

### `src/cli/add.rs` — `mars add <source>`

```rust
pub struct AddArgs {
    /// Source specifier: owner/repo, URL, or local path
    pub source: String,

    /// Version constraint (e.g., @v0.5.0, @latest)
    #[arg(long)]
    pub version: Option<String>,

    /// Only install these agents (intent-based filtering)
    #[arg(long, value_delimiter = ',')]
    pub agents: Option<Vec<String>>,

    /// Only install these skills (intent-based filtering)
    #[arg(long, value_delimiter = ',')]
    pub skills: Option<Vec<String>>,

    /// Exclude these items
    #[arg(long, value_delimiter = ',')]
    pub exclude: Option<Vec<String>>,
}
```

Pipeline:
1. Parse source specifier: detect git URL vs local path vs GitHub shorthand (`owner/repo`).
2. Auto-init if `.agents/` doesn't exist.
3. Load existing config, add or update source entry (**upsert** — if source already exists, update its version constraint and filters rather than erroring).
4. Save config (atomic write).
5. Run full sync.
6. Report what was installed.

**GitHub shorthand**: `owner/repo` → `github.com/owner/repo`. Detect by: no `/` prefix (not a local path), no `.` in first segment (not a domain), contains exactly one `/`.

**Version from source string**: `owner/repo@v0.5.0` → split on `@`, version = `v0.5.0`. If no `@`, default to `@latest`.

### `src/cli/sync.rs` — `mars sync`

```rust
pub struct SyncArgs {
    /// Overwrite local modifications for managed files
    #[arg(long)]
    pub force: bool,

    /// Dry run — show what would change
    #[arg(long)]
    pub diff: bool,

    /// Install exactly from lock file, error if stale
    #[arg(long)]
    pub frozen: bool,
}
```

Calls `sync::sync(ctx)` with options, formats and prints the `SyncReport`.

### `src/cli/remove.rs` — `mars remove <source>`

```rust
pub struct RemoveArgs {
    /// Source name to remove
    pub source: String,
}
```

1. Load config, remove source entry.
2. Save config.
3. Run sync (orphans from removed source get pruned).

### `src/cli/resolve_cmd.rs` — `mars resolve`

```rust
pub struct ResolveArgs {
    /// Specific file to resolve (default: all conflicted)
    pub file: Option<PathBuf>,
}
```

1. Scan `.agents/` for files with conflict markers.
2. If `--file` specified, check only that file.
3. For files without conflict markers: update lock with current disk hash (marks as resolved).
4. Report resolved files.

### `src/cli/rename.rs` — `mars rename`

```rust
pub struct RenameArgs {
    /// Current item path (e.g., agents/coder__haowjy_meridian-base.md)
    pub from: String,
    /// New item path (e.g., agents/coder.md)
    pub to: String,
}
```

1. Validate `from` is a managed item (in lock).
2. Add rename entry to config.
3. Run sync (rename applied, lock updated).

### `src/cli/list.rs` — `mars list`

```rust
pub struct ListArgs {
    /// Filter by source name
    #[arg(long)]
    pub source: Option<String>,

    /// Filter by item kind (agents, skills)
    #[arg(long)]
    pub kind: Option<String>,
}
```

Read lock file, format as table. Compare disk hashes against lock to detect local modifications. Show status: `ok`, `modified`, `conflicted`.

### `src/cli/why.rs` — `mars why <name>`

```rust
pub struct WhyArgs {
    /// Item name to explain
    pub name: String,
}
```

Look up item in lock → show source, version, commit. Parse agents to find which ones reference this skill in their frontmatter.

### `src/cli/override_cmd.rs` — `mars override`

```rust
pub struct OverrideArgs {
    /// Source name to override
    pub source: String,

    /// Local path
    #[arg(long)]
    pub path: PathBuf,
}
```

Write override to `agents.local.toml`. Run sync.

### `src/cli/upgrade.rs` — `mars upgrade`

```rust
pub struct UpgradeArgs {
    /// Sources to upgrade (default: all)
    pub sources: Vec<String>,
}
```

1. If sources specified, upgrade only those. Otherwise, upgrade all.
2. Use resolver in maximize-versions mode to find newest compatible versions across all targets simultaneously.
3. Update version constraints in config.
4. Run full sync.
5. Report version changes.

### `src/cli/output.rs` — Shared Formatting

```rust
/// Print sync report as human-readable table
pub fn print_sync_report(report: &SyncReport, json: bool);

/// Print item list as table
pub fn print_list(items: &[ListEntry], json: bool);

/// Colored output respecting NO_COLOR env var
pub fn use_color() -> bool;
```

Use `termcolor` for colored output. Respect `NO_COLOR` environment variable. `--json` flag outputs machine-readable JSON instead of tables.

**Human output format** (from architecture doc):
```
$ mars sync
  ✓ meridian-base@0.5.2 (3 agents, 8 skills)
  ✓ meridian-dev-workflow@2.1.0 (8 agents, 5 skills)

  installed   2 new items
  updated     3 items
  removed     1 orphan
  conflicts   1 file (run `mars resolve` after fixing)
```

### Exit Codes

- `0` — success, no conflicts
- `1` — sync completed with unresolved conflicts
- `2` — resolution/validation error (bad config, dep conflict)
- `3` — I/O or git error (network, permissions)

Map `MarsError` variants to exit codes in `dispatch()`.

### `tests/integration/` — End-to-End Tests

Use `assert_cmd` to run the `mars` binary and `assert_fs` for temp directories.

**Test scenarios**:
1. **Fresh init + add + sync**: `mars init` → `mars add` with a local path source → verify files installed
2. **Add with GitHub shorthand**: `mars add owner/repo` → verify config entry
3. **Sync with no changes**: Run sync twice → second run changes nothing
4. **Add + remove**: Add source, verify installed, remove source, verify pruned
5. **List**: Add source, `mars list` → verify table output
6. **Why**: Install items, `mars why <skill>` → shows which agent depends on it
7. **Dry run**: `mars sync --diff` → shows changes but doesn't apply them
8. **Force sync**: Modify a managed file, `mars sync --force` → local changes overwritten
9. **Conflict flow**: Modify a managed file, update source, `mars sync` → conflict markers, `mars resolve` → resolved
10. **Include filtering**: `mars add` with `--agents coder` → only coder + its skill deps installed
11. **Root discovery**: Run mars from a subdirectory → finds `.agents/` by walking up

**Test fixture strategy**: Create local path sources (directories with `agents/*.md` and `skills/*/SKILL.md`) in temp dirs. For git tests, create real git repos with `git2` in temp dirs and tag them. This gives full end-to-end coverage without network access.

## Dependencies

- Requires: Phase 4 (sync pipeline — the core library entry point)
- Produces: The `mars` binary — the deliverable
- Independent of: nothing (this is the final phase)

## Interface Contract

The CLI is the consumer of all library modules. It calls:
- `config::load()`, `config::save()`
- `lock::load()`
- `sync::sync()`
- `validate::parse_agent_skills()` (for `mars why`)
- `hash::compute_hash()` (for `mars list` status)

## Patterns to Follow

- Each command handler: parse args → find root → load context → call library → format output → return exit code
- No business logic in CLI layer. All logic is in the library.
- `clap::Parser` derive for all arg structs.
- `--json` flag on all commands that produce output.

## Verification Criteria

- [ ] `cargo build` succeeds
- [ ] `mars --help` shows all commands
- [ ] `mars <command> --help` shows command-specific options for all commands
- [ ] All 11 integration test scenarios pass
- [ ] `mars init` creates valid `.agents/agents.toml`
- [ ] `mars add <local-path>` installs items and writes lock
- [ ] `mars sync` is idempotent (second run produces no changes)
- [ ] `mars remove` prunes items
- [ ] `mars list` shows installed items with correct status
- [ ] `mars why` traces dependency chain
- [ ] `mars sync --diff` doesn't modify files
- [ ] `mars sync --force` overwrites local modifications
- [ ] Exit codes match spec (0, 1, 2, 3)
- [ ] `--json` produces valid JSON on all commands
- [ ] `NO_COLOR=1` disables colored output
- [ ] Root discovery works from subdirectories
- [ ] `cargo clippy -- -D warnings` passes
- [ ] `cargo test` — all unit + integration tests pass

## Constraints

- No business logic in CLI handlers. If you're tempted to add conditional logic, it belongs in the library.
- `assert_cmd` tests run the compiled binary — they're slow. Keep the count reasonable (~15 tests).
- Integration tests that create git repos: use `git2` to init/commit/tag, not subprocess `git`.
- GitHub shorthand parsing must handle edge cases: `owner/repo@version`, `github.com/owner/repo`, `https://github.com/owner/repo.git`.
