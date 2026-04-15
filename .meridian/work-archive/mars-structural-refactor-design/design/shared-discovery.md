# F19: Extract Shared Installed-Item Discovery

## Problem

`src/cli/check.rs:58-139` and `src/cli/doctor.rs:88-181` both independently:
1. Walk `agents/*.md` and `skills/*/SKILL.md` directories
2. Parse YAML frontmatter from each file
3. Extract skill references from agents
4. Validate skill dependencies against available skills

They differ subtly: check.rs does manual validation, doctor.rs delegates to `validate::check_deps()`. Both will drift when discovery conventions change.

## Design

### New Function: `discover::discover_installed()`

Add to `src/discover/mod.rs`. Unlike `discover_source()` which scans a raw source tree, `discover_installed()` scans the installed managed root and returns parsed frontmatter.

```rust
/// An installed item with parsed frontmatter metadata.
#[derive(Debug, Clone)]
pub struct InstalledItem {
    pub id: ItemId,
    /// Disk path (absolute) to the installed file/dir.
    pub path: PathBuf,
    /// Parsed frontmatter name (may differ from filename).
    pub frontmatter_name: Option<String>,
    /// Parsed frontmatter description.
    pub description: Option<String>,
    /// Skills referenced in frontmatter (agents only).
    pub skill_refs: Vec<String>,
    /// Whether this is a symlink (skipped from validation).
    pub is_symlink: bool,
}

/// Result of scanning an installed managed root.
#[derive(Debug, Clone)]
pub struct InstalledState {
    pub agents: Vec<InstalledItem>,
    pub skills: Vec<InstalledItem>,
}

/// Discover all installed agents and skills in a managed root.
///
/// Scans `agents/*.md` and `skills/*/SKILL.md`, parses frontmatter,
/// and collects metadata. Includes symlinks (marked as such) so
/// callers can decide whether to skip or warn.
pub fn discover_installed(root: &Path) -> Result<InstalledState, MarsError> { ... }
```

### Key Differences from `discover_source()`

| Aspect | `discover_source()` | `discover_installed()` |
|---|---|---|
| Input | Raw source tree path | Managed root (`.agents/`) |
| Frontmatter | Not parsed | Parsed — returns name, description, skill refs |
| Symlinks | Not encountered (sources are fetched) | Detected and flagged |
| Output | `Vec<DiscoveredItem>` (id + source_path) | `InstalledState` (id + path + frontmatter) |
| Used by | `target.rs` build phase | `check.rs`, `doctor.rs` validation |

### Consumer Changes

**doctor.rs** becomes:
```rust
let installed = discover::discover_installed(&ctx.managed_root)?;
// Skill dep check
let available_skills: HashSet<String> = installed.skills.iter()
    .filter(|s| !s.is_symlink)
    .map(|s| s.id.name.to_string())
    .collect();
let agents_for_check: Vec<(String, PathBuf)> = installed.agents.iter()
    .filter(|a| !a.is_symlink)
    .map(|a| (a.id.name.to_string(), a.path.clone()))
    .collect();
let warnings = validate::check_deps(&agents_for_check, &available_skills)?;
```

The lock-based agent enumeration in doctor.rs (lines 94-128) is replaced — `discover_installed()` already finds both lock-managed and user-created agents.

**check.rs** is NOT changed to use `discover_installed()`. Check validates raw *source packages* (pre-install), not installed managed roots. It operates on a different path with different validation rules (name/filename match, description presence). Its discovery logic stays in check.rs.

### Decision: Don't merge check.rs and doctor.rs discovery

Despite the superficial similarity, check.rs and doctor.rs scan fundamentally different things:
- **check.rs** scans a source package for *publishing* validation — no lock, no managed root, stricter rules.
- **doctor.rs** scans an installed managed root for *health* validation — uses lock, includes unmanaged files, runs skill-dep checks.

Forcing them into the same code path would require branching on context ("am I a source check or installed check?"), which is worse than two focused functions. Extract only the installed-root scanning that doctor.rs needs.
