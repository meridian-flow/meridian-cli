# Phase 2a: Filesystem Discovery + Dependency Validation

## Scope

Implement two modules: `discover/` (scan source trees for installable agents and skills by filesystem convention) and `validate/` (check that agent frontmatter skill references resolve after sync). These are paired because validation depends on discovery output and both deal with the filesystem structure of `.agents/`.

## Why This Order

Discovery is used by `sync/target.rs` to determine what each source provides. Validation is used at the end of the sync pipeline to warn about broken references. Both depend on the data types from Phase 1b (`ItemId`, `ItemKind`) and filesystem primitives from Phase 1a. Neither depends on source fetching or resolution — they operate on already-fetched source trees.

## Files to Modify

### `src/discover/mod.rs` — Source Tree Discovery

```rust
/// An item discovered in a source tree
#[derive(Debug, Clone)]
pub struct DiscoveredItem {
    pub id: ItemId,
    pub source_path: PathBuf,   // absolute path to content in fetched source tree
    pub relative_path: String,  // e.g., "agents/coder.md" or "skills/__meridian-spawn"
}

/// Discover all installable items in a source tree by filesystem convention.
///
/// Convention:
///   agents/*.md → ItemKind::Agent (filename without .md = name)
///   skills/*/SKILL.md → ItemKind::Skill (directory name = name)
///
/// Everything else is ignored. No manifest needed.
pub fn discover_source(tree_path: &Path) -> Result<Vec<DiscoveredItem>>;
```

Implementation:
1. Check for `agents/` subdirectory. If present, walk it (non-recursive) looking for `*.md` files. Each becomes an `Agent` item. Name = filename stem (e.g., `coder.md` → name `coder`).
2. Check for `skills/` subdirectory. If present, walk it (non-recursive) looking for directories that contain a `SKILL.md` file. Each becomes a `Skill` item. Name = directory name (e.g., `__meridian-spawn/SKILL.md` → name `__meridian-spawn`).
3. Sort results by `(kind, name)` for deterministic ordering.
4. Skip hidden files/directories (starting with `.`).
5. Log (don't error) if `agents/` or `skills/` don't exist — a source might only provide one type.

### `src/validate/mod.rs` — Agent→Skill Dependency Validation

```rust
#[derive(Debug, Clone)]
pub enum ValidationWarning {
    /// Agent references a skill that doesn't exist in the target state
    MissingSkill {
        agent_name: String,
        agent_path: String,
        skill_name: String,
        suggestion: Option<String>,  // fuzzy match: "did you mean X?"
    },
    /// Skill is installed but no agent references it
    OrphanedSkill {
        skill_name: String,
    },
}

/// Check agent→skill references. Warnings, not errors.
///
/// Reads YAML frontmatter from agent .md files to extract `skills: [...]`.
/// Checks each referenced skill name exists in the provided skill set.
pub fn check_deps(
    agents: &[(String, PathBuf)],    // (name, path to .md file)
    available_skills: &HashSet<String>,
) -> Result<Vec<ValidationWarning>>;

/// Parse YAML frontmatter from an agent .md file.
/// Returns the `skills` list, or empty vec if no frontmatter or no skills field.
pub fn parse_agent_skills(agent_path: &Path) -> Result<Vec<String>>;
```

**Frontmatter parsing**:
- Read the file, look for `---` delimiters at the start.
- Extract the YAML block between the first two `---` lines.
- Parse with `serde_yaml` into a minimal struct: `struct AgentFrontmatter { skills: Option<Vec<String>> }`.
- Only read the frontmatter block, not the full markdown body.
- If no frontmatter or no `skills` field, return empty vec (not an error).

**Fuzzy matching for suggestions**:
- When a skill name is missing, check if any available skill name has a small edit distance. Simple approach: check if any available name contains the missing name as a substring or vice versa. Don't add a Levenshtein dependency for v1 — substring matching is good enough.

## Dependencies

- Requires: Phase 0 (module stubs), Phase 1a (`ItemKind` from lock, error types), Phase 1b (`ItemId` struct)
- Produces: `discover_source()` consumed by `sync/target.rs` (Phase 4), `check_deps()` consumed by `sync/` pipeline end (Phase 4)
- Independent of: Phase 2b (source fetching), Phase 3 (resolve + merge)

## Interface Contract

Downstream consumers:
- `sync/target.rs` calls `discover::discover_source(tree_path)` on each resolved source to enumerate items
- `sync/` pipeline calls `validate::check_deps(agents, skills)` after building target state
- `validate::parse_agent_skills()` is also used by `sync/target.rs` for intent-based filtering (when `agents` filter is set, need to read agent frontmatter to discover skill dependencies)

## Patterns to Follow

- Return `Vec<DiscoveredItem>` sorted by `(kind, name)` — deterministic ordering.
- Validation produces warnings, not errors. A missing skill doesn't prevent sync.
- Frontmatter parsing is defensive: malformed YAML → warning + empty skills list, not a hard error.

## Verification Criteria

- [ ] `cargo build` succeeds
- [ ] Discovery tests:
  - Source tree with `agents/coder.md`, `agents/reviewer.md` → discovers 2 agents
  - Source tree with `skills/planning/SKILL.md` → discovers 1 skill
  - Source tree with both agents and skills → discovers all
  - Source tree with no `agents/` dir → empty list (no error)
  - Source tree with `agents/` containing non-.md files → those are skipped
  - Skills directory without `SKILL.md` → skipped
  - Hidden files (`.hidden.md`) → skipped
  - Deterministic ordering: same tree → same order
- [ ] Validation tests:
  - Agent with `skills: [planning, review]` + both skills present → no warnings
  - Agent with `skills: [missing-skill]` → `MissingSkill` warning
  - Skill installed but not referenced by any agent → `OrphanedSkill` warning
  - Agent with no frontmatter → no warnings (empty skills list)
  - Agent with malformed YAML frontmatter → warning, not crash
- [ ] Frontmatter parsing tests:
  - Valid frontmatter with `skills: [a, b]` → `vec!["a", "b"]`
  - No frontmatter → empty vec
  - Frontmatter without `skills` field → empty vec
  - Frontmatter with `skills: []` → empty vec
- [ ] `cargo clippy -- -D warnings` passes

## Constraints

- Discovery is filesystem-only. Do NOT read `mars.toml` — that's the manifest module's job.
- Validation is warnings-only. Do NOT return errors for missing skills.
- Frontmatter parsing MUST handle: no frontmatter, empty frontmatter, malformed YAML, missing skills field. All gracefully.
- Do not add fuzzy matching libraries. Substring matching is sufficient for suggestions in v1.
