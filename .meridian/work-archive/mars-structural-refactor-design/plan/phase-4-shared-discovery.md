# Phase 4: Extract Shared Discovery (F19)

## Scope
Add `discover_installed()` to `src/discover/mod.rs`. Simplify doctor.rs to use it.

## Files to Modify
- `src/discover/mod.rs` — add `InstalledItem`, `InstalledState`, `discover_installed()` function
- `src/cli/doctor.rs` — replace inline agent/skill scanning (lines 88-181) with `discover_installed()` call

## Dependencies
- Cleaner after Phase 3 (dead code removed)
- Independent of Phases 1, 2

## Interface Contract

```rust
/// An installed item with parsed frontmatter metadata.
#[derive(Debug, Clone)]
pub struct InstalledItem {
    pub id: ItemId,
    pub path: PathBuf,
    pub frontmatter_name: Option<String>,
    pub description: Option<String>,
    pub skill_refs: Vec<String>,
    pub is_symlink: bool,
}

#[derive(Debug, Clone)]
pub struct InstalledState {
    pub agents: Vec<InstalledItem>,
    pub skills: Vec<InstalledItem>,
}

pub fn discover_installed(root: &Path) -> Result<InstalledState, MarsError>
```

## Implementation Notes

### `discover_installed()`
1. Scan `root/agents/*.md`:
   - Check each entry for symlink status
   - Parse frontmatter to extract name, description, skills
   - If frontmatter parse fails, still include item with `frontmatter_name: None`
2. Scan `root/skills/*/SKILL.md`:
   - Same symlink check
   - Parse frontmatter for name, description
   - `skill_refs` always empty for skills
3. Sort both lists by `id` for deterministic order

### doctor.rs changes
Replace the manual agent/skill scanning block (lines 88-181) with:
```rust
let installed = crate::discover::discover_installed(&ctx.managed_root)?;

// Build available skills set
let available_skills: HashSet<String> = installed.skills.iter()
    .filter(|s| !s.is_symlink)
    .map(|s| s.id.name.to_string())
    .collect();

// Build agents list for validation
let agents_for_check: Vec<(String, PathBuf)> = installed.agents.iter()
    .filter(|a| !a.is_symlink)
    .map(|a| (a.id.name.to_string(), a.path.clone()))
    .collect();

// Keep symlink warnings
for item in installed.agents.iter().chain(installed.skills.iter()) {
    if item.is_symlink {
        let kind = if item.id.kind == ItemKind::Agent { "agent" } else { "skill" };
        issues.push(format!(
            "skipping symlinked {kind} `{}` — individual symlinks in managed dirs are not validated",
            item.id.name
        ));
    }
}

if let Ok(warnings) = crate::validate::check_deps(&agents_for_check, &available_skills) {
    // ... existing warning formatting ...
}
```

### Tests
Add tests in `src/discover/mod.rs`:
- `discover_installed_finds_agents_and_skills` — creates managed root with agents/*.md and skills/*/SKILL.md, verifies discovery
- `discover_installed_parses_frontmatter` — verifies name, description, skill_refs extracted
- `discover_installed_handles_symlinks` — creates symlinked agent/skill, verifies `is_symlink: true`
- `discover_installed_handles_missing_frontmatter` — agent without frontmatter still discovered

## Verification Criteria
- [ ] `cargo test` passes
- [ ] `cargo clippy --all-targets --all-features` clean
- [ ] doctor.rs no longer contains `read_dir(&agents_dir)` or `read_dir(&skills_dir)` inline
- [ ] New `discover_installed()` tests pass
- [ ] doctor output unchanged (same warning messages)
