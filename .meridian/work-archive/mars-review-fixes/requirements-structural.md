# Mars Structural Refactor — Requirements

## Context

Refactor-reviewer (opus, p721) did a deep structural review of the full mars-agents codebase. Found correctness bugs (F15, F17), duplication (F19), dead code, and architectural debt. This is the entropy-reduction pass.

Codebase: `/home/jimyao/gitrepos/mars-agents` (Rust CLI)
Current state: 352 tests pass (326 unit + 26 integration)

## Findings to Fix (ordered by impact)

### 1. F17: Typed error for unmanaged collisions
- `src/sync/target.rs:372-378` formats a string into `MarsError::Source`
- `src/cli/repair.rs:99-107` parses that string back with `strip_prefix`
- Add `MarsError::UnmanagedCollision { source_name, path }` variant
- Match typed variant in repair.rs instead of parsing strings
- Exit code stays 3

### 2. F15: Fix collision rename for cross-package deps
- `src/sync/target.rs:319-327` `rewrite_skill_refs()` uses `.or_else(|| entries.first())` fallback
- The `_graph` parameter is already passed but unused
- Use dependency graph to find which renamed skill belongs to a declared dependency
- Agent from source A depending on skill from source B should get source B's renamed version

### 3. F19: Extract shared discovery
- `src/cli/check.rs:58-139` and `src/cli/doctor.rs:88-181` both scan agents/skills and parse frontmatter
- Extract `discover::discover_installed(root)` returning agents + skills with parsed frontmatter
- Both check.rs and doctor.rs become thin consumers
- check.rs adds package-specific validations on top
- doctor.rs feeds into validate::check_deps

### 4. F21: Simplify dispatch
- `src/cli/mod.rs:152-209` has 13 identical stanzas
- Split: root-free commands (init, check) vs root-required (everything else)
- Makes the root requirement explicit in code structure

### 5. Delete dead code
- `src/sync/target.rs:117-157` `check_collisions()` — entirely dead, superseded by `build_with_collisions()`
- `src/sync/target.rs:51-111` `build()` — only used in tests, production uses `build_with_collisions()`
- Update tests to use the production code path

### 6. F20: Split link.rs
- Extract `scan_link_target()` and `scan_dir_recursive()` into library module
- Keep CLI concerns (output, args, config persist) in cli/link.rs
- Scan module becomes independently testable

### 7. F16: Remove dead DepSpec.items schema
- `src/manifest/mod.rs:36` DepSpec.items exists but resolver ignores it
- Remove field and associated test until ready to implement
- Don't ship dead schema that creates false expectations

### 8. Fix silent error swallowing in rewrite_skill_refs
- `src/sync/target.rs:340` `Err(_) => {}` silently swallows frontmatter rewrite errors
- At minimum warn, better propagate as ValidationWarning

## Constraints

- 352 tests must stay green (update tests that exercise dead code paths)
- Follow AGENTS.md core principles
- Commit after each logical unit
- Reduce entropy: fewer code paths, fewer concepts, fewer places to update
