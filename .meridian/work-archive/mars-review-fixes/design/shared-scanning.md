# F19 + F20: Shared Scanning and link.rs Decomposition (Tier 3)

These are structural improvements that don't fix bugs. Tracked here for backlog; implementation deferred.

## F19: Shared Frontmatter Scanning

`check.rs` and `doctor.rs` both independently scan `agents/` and `skills/` directories, parse frontmatter, extract names, and check for duplicates. The scanning logic is nearly identical — iterate entries, filter by extension/structure, read content, parse frontmatter, validate fields.

### Recommended Approach

Extract a shared scanning module at `src/discover/scan.rs` (or extend existing `src/discover/mod.rs`):

```rust
pub struct ScannedAgent {
    pub name: String,
    pub path: PathBuf,
    pub skills: Vec<String>,
    pub warnings: Vec<String>,
    pub errors: Vec<String>,
}

pub struct ScannedSkill {
    pub name: String,
    pub path: PathBuf,
    pub warnings: Vec<String>,
    pub errors: Vec<String>,
}

pub struct ScanResult {
    pub agents: Vec<ScannedAgent>,
    pub skills: Vec<ScannedSkill>,
}

/// Scan agents/ and skills/ directories, parse frontmatter, validate structure.
pub fn scan_package(base: &Path) -> Result<ScanResult, MarsError> { ... }
```

Both `check.rs` and `doctor.rs` call `scan_package()` and add their command-specific checks on top.

### Why Defer

- No correctness impact — both implementations produce correct results
- The duplication is ~80 lines per file, not growing
- Extracting shared infrastructure before the F3 symlink-awareness changes would mean doing the work twice

### When to Do It

After F3 (symlink containment) is implemented, since the symlink checks need to go in the scanning loops. Refactoring the loops into shared code at that point kills two birds.

## F20: link.rs Decomposition

`link.rs` is 753 lines with four distinct concerns: scan, act, config persist, and unlink. Each concern is already separated by section comments but lives in one file.

### Recommended Split

```
src/cli/link/
  mod.rs      — public API (run, unlink), LinkArgs, types
  scan.rs     — ScanResult, scan_link_target, scan_dir_recursive, hash_file
  act.rs      — merge_and_link, create_symlink, remove_dir_contents_and_tree
  tests.rs    — all tests
```

### Why Defer

- The file is well-organized internally (section comments, clear separation)
- No other module imports link internals — the public surface is just `run()`
- Splitting doesn't improve correctness or enable parallel development
- The file will change during F1/F3/F4 fixes — split afterward to avoid merge conflicts

## F21: dispatch_result Boilerplate

15 identical match arms in `dispatch_result()` that call `find_agents_root` then dispatch. A macro or helper would reduce this to 1-2 lines per command.

### Recommended Approach

```rust
macro_rules! with_root {
    ($cli:expr, $args:expr, $handler:path) => {{
        let ctx = find_agents_root($cli.root.as_deref())?;
        $handler($args, &ctx, $cli.json)
    }};
}
```

Deferred — mechanical cleanup, no correctness impact.
