# Init and Root Discovery

## `mars init` Behavior

### Project Root Default

**Decision: `mars init` defaults `project_root` to the nearest git root, not cwd.**

Rationale: `mars.toml` is a repo-root config file (like `Cargo.toml`). Creating it in a subdirectory causes walk-up discovery to fail from sibling subdirectories. Users running `mars init` from `src/` expect it to initialize the project, not create a stranded config.

Implementation:
1. Walk up from cwd looking for `.git/` or `.git` (file, for submodules)
2. If found, use that directory as `project_root`
3. If no `.git` found (not a git repo), fall back to cwd
4. `--root` flag overrides everything

```rust
fn default_project_root() -> Result<PathBuf, MarsError> {
    let cwd = std::env::current_dir()?;
    let mut dir = cwd.as_path();
    loop {
        if dir.join(".git").exists() {
            return Ok(dir.to_path_buf());
        }
        match dir.parent() {
            Some(parent) => dir = parent,
            None => return Ok(cwd),  // not a git repo, use cwd
        }
    }
}
```

### `--root` Footgun Prevention

**Decision: Reject `--root` values that look like managed output directories.**

If `--root .agents` is passed (old mental model where `--root` meant managed dir), the result is a nested `.agents/.agents` structure. Detect and reject:

```
error: `--root .agents` looks like a managed output directory.
  --root takes the project root (containing mars.toml), not the output directory.
  Try: mars init  (auto-detects project root)
  Or:  mars init .agents  (specify output directory name)
```

Check: if the basename of `--root` is in `WELL_KNOWN ∪ TOOL_DIRS`, reject with this message.

### Init Flow (Revised)

```
mars init [TARGET] [--root DIR] [--link DIR...]
```

1. Determine `project_root`: `--root` flag → `default_project_root()` (git root or cwd)
2. Determine `target`: argument → `settings.managed_root` from existing config → `.agents`
3. Validate target is a simple directory name
4. Check existing `mars.toml`:
   - None: create with `[dependencies]\n`
   - Has `[dependencies]`: already initialized (idempotent)
   - Has `[package]` only: **error** — refuse to mutate
5. If target ≠ `.agents`, write `[settings]\nmanaged_root = "<target>"`
6. Create managed dir + `.mars/` inside it
7. Gitignore `.mars/` in managed dir's `.gitignore`
8. **Gitignore `mars.local.toml` in project root's `.gitignore`**
9. Process `--link` flags

### Gitignore for `mars.local.toml`

New function `ensure_local_gitignored(project_root)` — appends `mars.local.toml` to `<project_root>/.gitignore` (creates if needed, idempotent like existing `add_to_gitignore`). Called during `mars init`.

## Root Discovery (`find_agents_root`)

### Walk-Up Algorithm

No changes to the core algorithm — it's correct:
1. Start at canonicalized cwd
2. Check `dir/mars.toml` — if `is_consumer_config()` returns true, use it
3. If `dir/.git` exists, stop (never cross git boundary)
4. Go to parent, repeat
5. If exhausted, error

### `is_consumer_config` Simplification

Old: scan for `INIT_MARKER` comment OR check for `[dependencies]` key.
New: parse TOML, check `table.contains_key("dependencies")`. One path, no comment scanning.

### Canonicalization Fix

**Both `project_root` and `managed_root` must be canonicalized in `MarsContext::from_roots()`.**

Currently only `managed_root` is canonicalized, so `starts_with()` fails when `project_root` is a relative path or contains symlinks. Fix: canonicalize `project_root` the same way `MarsContext::new()` does.

```rust
pub fn from_roots(project_root: PathBuf, managed_root: PathBuf) -> Result<Self, MarsError> {
    let project_canon = if project_root.exists() {
        project_root.canonicalize().unwrap_or(project_root.clone())
    } else {
        project_root.clone()
    };
    let managed_canon = if managed_root.exists() {
        managed_root.canonicalize().unwrap_or(managed_root.clone())
    } else {
        managed_root.clone()
    };
    // ... starts_with check using both canonicalized paths
}
```

### `detect_managed_root` — Settings-Aware

When `settings.managed_root` is set in `mars.toml`, it's authoritative. The function now returns `Result<PathBuf>` to properly propagate config parse errors (vs silently falling back):

```rust
fn detect_managed_root(project_root: &Path) -> Result<PathBuf, MarsError> {
    // 1. Check settings in mars.toml
    match crate::config::load(project_root) {
        Ok(config) => {
            if let Some(name) = &config.settings.managed_root {
                return Ok(project_root.join(name));
            }
        }
        // Config doesn't exist yet (before mars init) — expected, fall through
        Err(MarsError::Config(ConfigError::NotFound { .. })) => {}
        // Config exists but has parse errors — surface the real error
        Err(e) => return Err(e),
    }

    // 2. Default: .agents
    let default_root = project_root.join(WELL_KNOWN[0]);
    if default_root.exists() || is_symlink(&default_root) {
        return Ok(default_root);
    }

    // 3. Fallback: scan for .mars/ marker (legacy compat)
    // ... existing scan logic ...

    Ok(default_root)
}
```

This means `MarsContext::new()` does a config load to read settings before constructing the context. The load is cheap (one file read) and happens once per command. Importantly, it distinguishes "config not found" (expected before init, falls through) from "config has parse errors" (surfaced to user).

### Re-init with Different Target

When `mars init <target>` is run on an already-initialized project with a different `settings.managed_root`:
- Update `settings.managed_root` in `mars.toml` to the new target
- Create the new managed dir
- Warn: `managed root changed from .agents to .claude — run mars sync to populate`
- Do NOT move files from old managed dir (user may want to delete it manually)
