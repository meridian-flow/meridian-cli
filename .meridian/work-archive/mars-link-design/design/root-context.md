# Root Detection & MarsContext

## Problem

The concept of "project root" vs "managed root" is critical but has no explicit representation. Every module that needs the project root re-derives it with `root.parent().unwrap_or(root)` — duplicated in `link.rs:27` and `sync/mod.rs:128`. The `WELL_KNOWN` constant is defined inside `find_agents_root`'s function body, invisible to init and link.

## MarsContext

Replace the raw `root: &Path` parameter with a struct that provides both paths:

```rust
/// Resolved context for a mars command — both the managed root
/// and its parent project root.
pub struct MarsContext {
    /// The directory containing agents.toml (e.g. /project/.agents)
    pub managed_root: PathBuf,
    /// The project directory (managed_root's parent, e.g. /project)
    pub project_root: PathBuf,
}
```

`MarsContext` is constructed by `find_agents_root` (auto-detection) or from `--root` (explicit). All commands receive `&MarsContext` instead of `&Path`. The `managed_root` field replaces the current `root` parameter everywhere.

### Construction

```rust
impl MarsContext {
    /// Build from a managed root path. Enforces the invariant that
    /// managed_root must have a parent (i.e., is always a subdirectory).
    pub fn new(managed_root: PathBuf) -> Result<Self, MarsError> {
        // Canonicalize to resolve relative paths and symlinks
        let canonical = if managed_root.exists() {
            managed_root.canonicalize().unwrap_or(managed_root.clone())
        } else {
            managed_root.clone()
        };
        let project_root = canonical.parent()
            .ok_or_else(|| MarsError::Config(ConfigError::Invalid {
                message: format!(
                    "managed root {} has no parent directory — the managed root must be \
                     a subdirectory (e.g., /project/.agents, not /project)",
                    managed_root.display()
                ),
            }))?
            .to_path_buf();
        Ok(MarsContext { managed_root: canonical, project_root })
    }
}
```

### Migration

Every command signature changes from `run(args, root: &Path, json)` to `run(args, ctx: &MarsContext, json)`. Inside each command, replace:
- `root` → `ctx.managed_root` (most uses)
- `root.parent().unwrap_or(root)` → `ctx.project_root`

This is a mechanical change — no logic changes, just replacing the parameter type and adjusting field access.

## Directory Constants

Two module-level constants in `cli/mod.rs`:

```rust
/// Directories where mars manages agents.toml as the primary root.
/// These are the default target for `mars init`.
pub const WELL_KNOWN: &[&str] = &[".agents"];

/// Tool-specific directories that commonly need linking.
/// Root detection searches these in addition to WELL_KNOWN.
/// `mars link` warns if the target isn't in TOOL_DIRS or WELL_KNOWN.
pub const TOOL_DIRS: &[&str] = &[".claude", ".cursor"];
```

**Why separate**: `.agents` is the conventional managed root — it's what `mars init` creates by default. `.claude` and `.cursor` are tool directories that users link to. The distinction matters:
- Root detection searches both (any can contain `agents.toml`)
- Init defaults to `.agents` (from WELL_KNOWN)
- Link warns on non-TOOL_DIRS targets (unusual but allowed)

## find_agents_root Redesign

```rust
pub fn find_agents_root(explicit: Option<&Path>) -> Result<MarsContext, MarsError> {
    if let Some(root) = explicit {
        return MarsContext::new(root.to_path_buf());
    }

    let cwd = std::env::current_dir()?;
    let mut dir = cwd.as_path();

    loop {
        // Check all known subdirectories (WELL_KNOWN + TOOL_DIRS)
        for subdir in WELL_KNOWN.iter().chain(TOOL_DIRS.iter()) {
            let candidate = dir.join(subdir);
            if candidate.join("agents.toml").exists() {
                return MarsContext::new(candidate);
            }
        }

        // Check if we're already inside a mars-managed directory
        if dir.join("agents.toml").exists() {
            return MarsContext::new(dir.to_path_buf());
        }

        match dir.parent() {
            Some(parent) => dir = parent,
            None => break,
        }
    }

    Err(MarsError::Config(ConfigError::Invalid {
        message: format!(
            "no agents.toml found from {} to /. Run `mars init` first.",
            cwd.display()
        ),
    }))
}
```

### Multiple Roots at Same Level

If both `.agents/agents.toml` and `.claude/agents.toml` exist at the same directory level, the first match wins (WELL_KNOWN searched before TOOL_DIRS, so `.agents` wins). This is intentional — `.agents` is the conventional primary root. Users who want a different root use `--root`.

Future enhancement: warn when multiple roots exist at the same level. Not in scope for v1.

### "Already inside" Detection

The check `if dir.join("agents.toml").exists()` handles the case where `cwd` is inside the managed root itself (e.g., user cd'd into `.agents/`). In this case, `dir` is the managed root and its parent is the project root — the invariant holds.
