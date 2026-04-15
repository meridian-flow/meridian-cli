# Phase 1: Frontmatter Module

**Fixes:** #3 (substring corruption), #4 (temp file collisions)
**Design doc:** [frontmatter.md](../design/frontmatter.md)
**Risk:** Low — new module, additive changes, no existing API removed until callers migrated

## Scope and Intent

Extract a single `frontmatter` module that handles all YAML frontmatter parsing, typed access, skill rewriting, and serialization. Both `validate/mod.rs` and `sync/target.rs` migrate to it, eliminating the substring-replace corruption bug and the global temp file collision.

## Files to Modify

- **`src/frontmatter/mod.rs`** (NEW) — `Frontmatter` struct, `parse()`, `render()`, `skills()`, `set_skills()`, `rewrite_skills()`, `rewrite_content_skills()`. ~150 lines + tests.
- **`src/lib.rs`** — Add `pub mod frontmatter;`
- **`src/validate/mod.rs`** — Replace internal frontmatter parser with `crate::frontmatter::Frontmatter::parse()`. Keep `parse_agent_skills()` convenience function with error→warning policy.
- **`src/sync/target.rs`** — Replace string-replace `rewrite_skill_refs` with `crate::frontmatter::rewrite_content_skills()`. Add `rewritten_content: Option<String>` to `TargetItem`. Remove `/tmp/mars-rewrite/` temp file logic.
- **`src/sync/apply.rs`** — Check `TargetItem.rewritten_content` before reading from `source_path` via `content_to_install()` helper.

## Dependencies

- **Requires:** Nothing — first phase, no prior changes needed.
- **Produces:** `frontmatter` module that phases 4-8 depend on for frontmatter handling.
- **Independent of:** All other phases.

## Interface Contract

```rust
// src/frontmatter/mod.rs

pub struct Frontmatter {
    yaml: serde_yaml::Mapping,
    body: String,
}

pub enum FrontmatterError {
    MalformedYaml(serde_yaml::Error),
    NotAMapping,
}

impl Frontmatter {
    pub fn parse(content: &str) -> Result<Self, FrontmatterError>;
    pub fn skills(&self) -> Vec<String>;
    pub fn set_skills(&mut self, skills: Vec<String>);
    pub fn name(&self) -> Option<&str>;
    pub fn get(&self, key: &str) -> Option<&serde_yaml::Value>;
    pub fn body(&self) -> &str;
    pub fn has_frontmatter(&self) -> bool;
    pub fn render(&self) -> String;
}

pub fn rewrite_skills(fm: &mut Frontmatter, renames: &IndexMap<String, String>) -> IndexSet<String>;
pub fn rewrite_content_skills(content: &str, renames: &IndexMap<String, String>) -> Result<Option<String>, FrontmatterError>;
```

## Patterns to Follow

- Look at `src/validate/mod.rs` for the existing frontmatter parsing pattern (lines ~100-200)
- Error handling: use `thiserror` like all other modules in the crate
- Test structure: in-module `#[cfg(test)]` block, same pattern as other modules

## Constraints and Boundaries

- **Out of scope:** Changing the `skills` field format or adding new frontmatter fields
- **Out of scope:** Changing `RenameAction` types (that's phase 7)
- **Preserve:** All 281 existing tests must pass. The `validate/` tests exercise `parse_agent_skills` — they should pass with the new backend.
- **Preserve:** The `rewritten_content` field is `Option<String>` — `None` means use source file, `Some` means use this content.

## Verification Criteria

- [ ] `cargo test` — all 281 existing tests pass
- [ ] `cargo test frontmatter` — new module tests pass, including:
  - Round-trip: parse → render produces reparseable output
  - Corruption regression: renaming "plan" does NOT corrupt "planner" or "planning-extended"
  - Edge cases: no frontmatter, empty frontmatter, malformed YAML, flow-style lists
- [ ] `cargo clippy -- -D warnings` — clean
- [ ] `uv run pyright` (if applicable) — N/A for Rust
- [ ] No `/tmp/mars-rewrite/` references remain in the codebase

## Design Conformance

- [ ] `validate/mod.rs` calls `Frontmatter::parse()`, not its own parser
- [ ] `sync/target.rs` calls `rewrite_content_skills()`, not string replacement
- [ ] `TargetItem` has `rewritten_content: Option<String>` field
- [ ] `sync/apply.rs` checks `rewritten_content` before reading source file

## Agent Staffing

- **Implementer:** `coder` (standard backend work, clear spec)
- **Reviewer:** 1 reviewer focused on correctness (frontmatter edge cases are the main risk)
- **Tester:** `verifier` for build health
