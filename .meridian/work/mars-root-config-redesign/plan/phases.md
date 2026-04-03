# Implementation Plan

## Execution Order

```
Round 1: Phase 1 (foundation — everything depends on it)
Round 2: Phase 2 (API cleanup — must land before Phase 3 touches same files)
Round 3: Phase 3 (local package symlinks — builds on Phase 2's &MarsContext API)
Round 4: Phase 4, Phase 5 (independent — integration tests + walk-up tests)
```

Phases 2 and 3 both modify `src/sync/mod.rs` — Phase 2 changes the `execute()` signature and all internal references, Phase 3 adds local item discovery into the same function body. They MUST run sequentially in the same worktree, with Phase 3 building on Phase 2's changes.

---

## Phase 1: Config Model & Init Cleanup

**Scope:** Kill init marker, protect package manifests, add `managed_root` to settings, fix canonicalization, gitignore `mars.local.toml`, default project root to git root.

**Files to modify:**
- `src/cli/mod.rs` — delete `INIT_MARKER`, simplify `is_consumer_config` (just check `[sources]` key, no comment scanning), change `detect_managed_root` to return `Result<PathBuf>` and read `settings.managed_root` from config (distinguish `NotFound` from parse errors), fix `from_roots` to canonicalize both paths, add `default_project_root()` helper (walk up to `.git`), add `--root` footgun rejection (basename in WELL_KNOWN ∪ TOOL_DIRS)
- `src/cli/init.rs` — rewrite `ensure_consumer_config` (no marker; if no file create `[sources]\n`; if file has `[sources]` return Ok(true); if file has `[package]` only return error), add `ensure_local_gitignored(project_root)` (append `mars.local.toml` to project root .gitignore), call `default_project_root()` instead of `current_dir()` as fallback, persist `settings.managed_root` for non-default targets, handle re-init with different target (update managed_root + warn)
- `src/config/mod.rs` — add `managed_root: Option<String>` to `Settings` struct (with serde skip_serializing_if None), validate `_self` is reserved source name in `merge()` / `merge_with_root()`

**Existing test changes:**
- `ensure_consumer_config_creates_root_mars_toml` — remove `INIT_MARKER` assertion, verify `[sources]` exists
- **`ensure_consumer_config_upgrades_package_only_file`** — **INVERT**: must now assert `Err(...)` instead of `Ok(false)`. This test asserts the exact opposite of the new behavior — failing to update it will cause `cargo test` failure.

**New tests:**
- `ensure_consumer_config_refuses_package_only` — `[package]` only → error with descriptive message
- `detect_managed_root_reads_settings` — config with `managed_root = ".claude"` → returns `.claude`
- `detect_managed_root_falls_through_on_missing_config` — no mars.toml → returns `.agents` default
- `detect_managed_root_surfaces_parse_errors` — malformed mars.toml → returns Err (not silent fallback)
- `default_project_root_finds_git_root` — temp dir with .git → returns that dir
- `init_rejects_root_that_looks_like_managed_dir` — `--root .agents` → error
- `self_source_name_rejected` — `[sources._self]` in config → error from merge()

**Verification criteria:**
- `cargo test` passes
- `cargo clippy` clean

**Agent:** `coder`

---

## Phase 2: API Cleanup — `&MarsContext` Threading

**Scope:** Replace two-path args with `&MarsContext` in sync/repair/link. Fix `mars link` lock dir creation.

**Files to modify:**
- `src/sync/mod.rs` — change `execute(project_root: &Path, managed_root: &Path, request)` → `execute(ctx: &MarsContext, request)`. Replace all `project_root` → `ctx.project_root`, `managed_root` → `ctx.managed_root` within the function body.
- `src/cli/sync.rs` — update call: `crate::sync::execute(&ctx.project_root, &ctx.managed_root, &request)` → `crate::sync::execute(ctx, &request)`
- `src/cli/add.rs` — same call site pattern
- `src/cli/remove.rs` — same
- `src/cli/upgrade.rs` — same
- `src/cli/override_cmd.rs` — same
- `src/cli/rename.rs` — same (if it calls sync::execute)
- `src/cli/link.rs` — add `std::fs::create_dir_all(ctx.managed_root.join(".mars"))` before lock acquisition. Update any two-path APIs.
- `src/cli/repair.rs` — update `execute_repair_with_collision_cleanup` if it takes two paths
- `src/sync/mod.rs` tests — add `MarsContext::for_test()` helper, update test functions

**Files NOT to modify:**
- `src/cli/resolve_cmd.rs` — operates on lock file directly, no two-path API calls

**Test helper to add:**
```rust
#[cfg(test)]
impl MarsContext {
    pub fn for_test(project_root: PathBuf, managed_root: PathBuf) -> Self {
        MarsContext { project_root, managed_root }
    }
}
```

**Dependencies:** Phase 1 (detect_managed_root now returns Result)

**Verification criteria:**
- `cargo test` passes
- `cargo clippy` clean
- `grep -rn "fn execute(project_root: &Path, managed_root: &Path" src/` returns nothing

**Agent:** `coder`

---

## Phase 3: Local Package Symlinks

**Scope:** Detect `[package]`, discover local items, symlink into managed dir during sync.

**Files to modify:**
- `src/sync/mod.rs` — add `discover_local_items()`, inject symlink actions into plan after step 13 (see design/local-package-sync.md §Pipeline Integration), add `_self` entries to lock file after step 17 (persist lock), add `relative_symlink_path()` helper
- `src/sync/plan.rs` — add `PlannedAction::Symlink { source_abs: PathBuf, dest_rel: DestPath, kind: ItemKind, name: ItemName }`
- `src/sync/apply.rs` — add `Symlink` arm in `execute_action` (create parent dirs, remove existing, create relative symlink) and `dry_run_action` (report `ActionTaken::Symlinked`). Add `ActionTaken::Symlinked` variant.
- `src/lock/mod.rs` — in `build()`, after building sources from graph nodes, if any outcome has `source_name == "_self"`, insert synthetic `LockedSource { path: Some(PathBuf::from(".")), version: None, commit: None, .. }` and corresponding `LockedItem` entries
- `Cargo.toml` — add `pathdiff = "0.2"` dependency

**Key design details (from design/local-package-sync.md):**

1. **Discovery**: `discover_local_items(project_root) -> Result<Vec<LocalItem>>` returns `LocalItem` structs. Agents are file-level (`agents/*.md`), skills are directory-level (`skills/*/` containing SKILL.md).

2. **Bypass diff engine**: `_self` items don't go through diff/plan pipeline. They're injected as `PlannedAction::Symlink` directly after the normal plan is built.

3. **Collision handling**: Check AFTER `build_with_collisions` returns. If a `_self` item's dest_rel matches an external item in target_state, warn and remove the external item (local wins). `build_with_collisions` signature doesn't change.

4. **Symlink check**: Before creating a symlink action, check if an existing symlink already points to the right relative path — skip if so (idempotent).

5. **Source paths**: `discover_local_items` stores **absolute paths** in `LocalItem.source_path`. `apply::execute_action` uses this directly to compute the relative symlink — no project_root parameter needed in apply.

6. **Lock file**: Use actual content hashes (agent file hash / skill SKILL.md hash), not empty strings.

7. **Frozen/dry-run**: `PlannedAction::Symlink` counts as a change for `--frozen`. `--dry-run` reports without touching disk.

**Dependencies:** Phase 2 (sync::execute takes &MarsContext, so ctx.project_root is available)

**Verification criteria:**
- `cargo test` passes
- `cargo clippy` clean
- New test: `discover_local_items_finds_agents_and_skills` — verify agents are files, skills are directories
- New test: `sync_creates_symlinks_for_local_package` — full sync with `[package]` + `[sources]`, verify symlinks exist and are relative
- New test: `sync_skill_symlink_is_directory_level` — skill symlink points to dir, not just SKILL.md
- New test: `local_item_shadows_external_with_warning` — local agent same name as source agent → local wins
- New test: `removing_package_section_prunes_self_symlinks` — remove `[package]`, sync → symlinks removed
- New test: `sync_idempotent_for_existing_symlinks` — second sync doesn't recreate correct symlinks

**Agent:** `coder`

---

## Phase 4: Integration — Full Pipeline

**Scope:** End-to-end test combining all features.

**Files to modify:**
- `tests/integration/mod.rs` — add integration test

**Test scenario:**
1. Create project with `mars init .claude` (custom target)
2. Add `[package]` section to mars.toml, create `agents/local-agent.md` and `skills/local-skill/SKILL.md`
3. Add external source
4. Run `mars sync`
5. Verify: `.claude/agents/local-agent.md` is relative symlink to `../../agents/local-agent.md`
6. Verify: `.claude/skills/local-skill/` is relative symlink to `../../skills/local-skill/`
7. Verify: `.claude/agents/external-agent.md` is a regular file (copied)
8. Verify: lock file has `_self` entries
9. Verify: `settings.managed_root = ".claude"` persisted
10. Re-run `mars sync` — verify no changes (idempotent)

**Dependencies:** Phase 2 + Phase 3

**Verification criteria:**
- `cargo test` passes

**Agent:** `coder`

---

## Phase 5: Walk-Up Discovery Tests (R4)

**Scope:** Test coverage for git boundary behavior in root discovery.

**Files to modify:**
- `src/cli/mod.rs` — refactor `find_agents_root` to accept `start: Option<&Path>` parameter (defaults to `current_dir()` when None). This avoids `std::env::set_current_dir` which is process-global and races with parallel test execution.

**Tests to add (all use explicit start paths via the new parameter, no cwd mutation):**
1. `walk_up_stops_at_git_boundary` — outer dir has consumer `mars.toml` + `.git`, inner dir has `.git` but no config → error from inner start path
2. `walk_up_finds_config_at_git_root` — dir with `.git` AND consumer `mars.toml`, start from subdir → found
3. `walk_up_skips_package_only_toml` — child dir has `mars.toml` with only `[package]`, parent has consumer config + `.git` → finds parent consumer config
4. `walk_up_from_deep_subdirectory` — consumer config at root, start is `src/foo/bar/` → found
5. `submodule_isolation` — outer repo has `.git` + consumer config, inner dir has `.git` file (submodule marker, create as file not dir) → start from inner → error (must not see outer config)

**Dependencies:** Phase 1 (is_consumer_config without marker)

**Verification criteria:**
- `cargo test` passes
- All 5 tests pass
- No `set_current_dir` calls in tests

**Agent:** `coder` (refactoring find_agents_root signature + writing tests is one coherent unit)

---

## Phase Staffing Summary

| Phase | Agent | Model | Notes |
|-------|-------|-------|-------|
| 1 | coder | gpt-5.3-codex | Foundation — most files touched |
| 2 | coder | gpt-5.3-codex | Mechanical refactor, many call sites |
| 3 | coder | gpt-5.3-codex | New feature, most design complexity |
| 4 | coder | sonnet | Integration test — straightforward |
| 5 | coder | sonnet | Refactor + tests — straightforward |

**Review after Phase 3:** Two reviewers — one on correctness (symlink edge cases, lock file tracking, path handling) on a strong model, one on design alignment (does implementation match design docs) on a different strong model.

**Final verification after all phases:** verifier agent to run `cargo test && cargo clippy && cargo fmt --check`.
