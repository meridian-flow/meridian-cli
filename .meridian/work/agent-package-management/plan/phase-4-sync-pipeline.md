# Phase 4: Sync Pipeline (target → diff → plan → apply)

## Scope

Implement the `sync/` module — the heart of mars. This integrates all prior modules into the complete sync pipeline: build target state from resolved graph, detect collisions, diff against current disk + lock, create an action plan, apply changes atomically, and write the updated lock. This is the largest and highest-risk phase.

## Why This Order

The sync pipeline is the integration point. It consumes:
- `config::EffectiveConfig` (Phase 1b)
- `lock::LockFile` (Phase 1b)
- `resolve::ResolvedGraph` (Phase 3)
- `discover::discover_source()` (Phase 2a)
- `validate::check_deps()` (Phase 2a)
- `merge::merge_content()` (Phase 3)
- `hash::compute_hash()` (Phase 1a)
- `fs::atomic_write()`, `fs::FileLock` (Phase 1a)

Every module feeds into this phase. It cannot start until Rounds 2-3 complete.

## Files to Modify

### `src/sync/mod.rs` — Pipeline Orchestrator

```rust
pub mod target;
pub mod diff;
pub mod plan;
pub mod apply;

pub struct SyncContext {
    pub root: PathBuf,              // .agents/ directory
    pub cache_dir: PathBuf,         // .agents/.mars/cache/
    pub options: SyncOptions,
}

pub struct SyncOptions {
    pub force: bool,       // --force: overwrite local modifications
    pub dry_run: bool,     // --diff: compute plan but don't apply
    pub frozen: bool,      // --frozen: install exactly from lock, error if stale
}

pub struct SyncReport {
    pub outcomes: Vec<ActionOutcome>,
    pub warnings: Vec<ValidationWarning>,
    pub has_conflicts: bool,
}

/// The complete sync pipeline.
///
/// 1. Acquire sync lock (flock on .agents/.mars/sync.lock)
/// 2. Load config (agents.toml + agents.local.toml merge)
/// 3. Load existing lock file
/// 4. Fetch sources + resolve dependency graph — abort on any fetch failure
/// 5. Discover items in each source, apply filtering
/// 6. Build target state, detect collisions, rewrite frontmatter
/// 7. Diff current state against rendered target (using dual checksums from lock)
/// 8. Plan actions from diff
/// 9. Apply plan (or dry-run)
/// 10. Write new lock file (atomic)
/// 11. Validate agent→skill references (warnings)
/// 12. Release sync lock
/// 13. Return report
pub fn sync(ctx: &SyncContext) -> Result<SyncReport>;
```

**Key invariant**: The sync lock is held from start to end (step 1 → step 12). This prevents TOCTOU races where two concurrent syncs compute diffs from the same stale lock. The diff logic relies on lock checksums — if the lock changes between diff and apply, the plan is invalid.

**Abort semantics**: If ANY source fetch fails in step 3, abort before modifying `.agents/` or the lock. Partially updated caches are fine (non-authoritative). The lock file is only written after all apply actions succeed.

### `src/sync/target.rs` — Desired Target State

```rust
/// What .agents/ should look like after sync
pub struct TargetState {
    pub items: IndexMap<String, TargetItem>,  // keyed by dest_path (not ItemId — two renamed items with same identity need distinct keys)
}

pub struct TargetItem {
    pub id: ItemId,
    pub source_name: String,
    pub source_path: PathBuf,      // path to content in fetched source tree
    pub dest_path: PathBuf,        // relative path under .agents/ (e.g., "agents/coder.md")
    pub source_hash: String,       // sha256 of source content
    pub content: Option<Vec<u8>>,  // pre-read content for merge base caching
}

/// Build target state from resolved graph + config filtering.
///
/// For each source in topological order:
/// 1. discover_source(tree_path) → list of items
/// 2. Apply filter mode from EffectiveConfig:
///    - agents/skills (intent-based): install named items + transitive skill deps
///    - exclude: install everything except listed items
///    - all (default): install everything from the source
/// 3. Apply rename mappings
/// 4. For Include mode with agents: parse agent frontmatter to discover
///    transitive skill deps, add those skills to the include set
/// 5. Compute source_hash for each item
/// 6. Add to TargetState
pub fn build(
    graph: &ResolvedGraph,
    config: &EffectiveConfig,
) -> Result<TargetState>;

/// Check for collisions — two sources producing the same dest_path.
///
/// When detected:
/// - Auto-rename BOTH using {name}__{owner}_{repo} format
/// - Rewrite frontmatter skill refs in affected agents (for transitive dep collisions)
/// - Return warnings about the renames
///
/// Errors only if a managed item collides with a user-authored file
/// (exists on disk, not in lock).
pub fn check_collisions(
    target: &mut TargetState,
    graph: &ResolvedGraph,     // needed for source URLs → {owner}_{repo} extraction
    config: &EffectiveConfig,  // needed for explicit rename precedence
    lock: &LockFile,
    root: &Path,
) -> Result<Vec<CollisionWarning>>;
```

**Intent-based filtering** (when `agents`/`skills` filter is set):
1. Start with the explicitly requested agents and skills.
2. For each requested agent, parse its frontmatter `skills: [...]`.
3. Add those skills to the include set (they're transitive deps).
4. This is re-resolved on every sync — if an agent adds a new skill dep, it comes in automatically.

**Auto-rename on collision**:
- Format: `{name}__{owner}_{repo}` where owner/repo are extracted from the source URL.
- For path sources: use the source name from config.
- Both colliding items get renamed (no implicit precedence).
- After renaming, scan affected agents' frontmatter for skill references that need updating. If agent A from source X references `skills: [code-review]` and `code-review` was renamed to `code-review__haowjy_meridian-base`, rewrite the frontmatter reference.

### `src/sync/diff.rs` — State Diffing

```rust
pub struct SyncDiff {
    pub entries: Vec<DiffEntry>,
}

pub enum DiffEntry {
    /// New item — not in lock, not on disk (or not in lock but exists as user file → error earlier)
    Add { target: TargetItem },
    /// Source changed, local unchanged → overwrite
    Update { target: TargetItem, locked: LockedItem },
    /// Nothing changed → skip
    Unchanged { target: TargetItem, locked: LockedItem },
    /// Source changed AND local changed → needs merge
    Conflict { target: TargetItem, locked: LockedItem, local_hash: String },
    /// In old lock but not in new target → orphan, should be removed
    Orphan { locked: LockedItem },
    /// Local modified, source unchanged → keep local
    LocalModified { target: TargetItem, locked: LockedItem, local_hash: String },
}

/// Compute diff between current state and target state.
///
/// Uses dual checksums from lock:
/// - Source changed? Compare target.source_hash against locked.source_checksum
/// - Local changed? Compare disk hash against locked.installed_checksum
///
/// The four-case matrix:
/// | Source changed? | Local changed? | Result |
/// |---|---|---|
/// | No  | No  | Unchanged → skip |
/// | Yes | No  | Update → overwrite |
/// | No  | Yes | LocalModified → keep local |
/// | Yes | Yes | Conflict → three-way merge |
pub fn compute(
    root: &Path,
    lock: &LockFile,
    target: &TargetState,
) -> Result<SyncDiff>;
```

**Dual checksum logic**:
- `source_checksum` in lock = what upstream provided last time (pre-rewrite).
- `installed_checksum` in lock = what mars wrote to disk (post-rewrite, if any rename rewrites happened).
- Source changed? `target.source_hash != locked.source_checksum`
- Local changed? `hash(disk_content) != locked.installed_checksum`
- When no collision/rewrite, both checksums are identical.

### `src/sync/plan.rs` — Action Planning

```rust
pub struct SyncPlan {
    pub actions: Vec<PlannedAction>,
}

pub enum PlannedAction {
    /// New item → copy source to dest
    Install { target: TargetItem },
    /// Clean update → overwrite dest with source
    Overwrite { target: TargetItem },
    /// No changes → do nothing
    Skip { item_id: ItemId, reason: &'static str },
    /// Both changed → three-way merge
    Merge {
        target: TargetItem,
        locked: LockedItem,
        local_path: PathBuf,
    },
    /// Orphan → remove from disk
    Remove { locked: LockedItem },
    /// Local modified, source unchanged → keep
    KeepLocal { item_id: ItemId },
}

/// Create execution plan from diff.
///
/// --force: all Conflict entries become Overwrite (source wins)
/// --diff: plan is created but not executed (dry run)
pub fn create(diff: &SyncDiff, options: &SyncOptions) -> Result<SyncPlan>;
```

### `src/sync/apply.rs` — Plan Execution

```rust
pub struct ApplyResult {
    pub outcomes: Vec<ActionOutcome>,
}

pub struct ActionOutcome {
    pub item_id: ItemId,
    pub action: ActionTaken,
    pub dest_path: PathBuf,
    pub source_checksum: Option<String>,
    pub installed_checksum: Option<String>,
}

#[derive(Debug, Clone)]
pub enum ActionTaken {
    Installed,
    Updated,
    Merged,           // clean auto-merge
    Conflicted,       // merge with conflict markers written
    Removed,
    Skipped,
    KeptLocal,
}

/// Execute the sync plan, applying changes to .agents/.
///
/// For each action:
/// - Install: atomic_write (file) or atomic_install_dir (skill dir)
/// - Overwrite: atomic_write/atomic_install_dir
/// - Merge: read base from lock cache, read local from disk, read theirs from source
///          → merge_content() → atomic_write result
/// - Remove: fs::remove_item()
/// - Skip/KeepLocal: no-op
///
/// Returns outcomes with both source_checksum and installed_checksum
/// (they differ when frontmatter rewriting occurred).
pub fn execute(
    root: &Path,
    plan: &SyncPlan,
    options: &SyncOptions,
) -> Result<ApplyResult>;
```

**Merge execution detail**:
1. Read base content: the content mars installed last time. Where does this come from? The lock stores the `installed_checksum` but not the content. **Decision**: Store base content in `.agents/.mars/cache/bases/{item_hash}` after each install. This is the merge base for next sync. If base cache is missing, fall back to two-way diff (treat as all-new content, likely produces conflict markers).
2. Read local content: `std::fs::read(dest_path)`.
3. Read theirs content: `std::fs::read(target.source_path)`.
4. Call `merge::merge_content(base, local, theirs, labels)`.
5. Write result via `atomic_write`.
6. If merge has conflicts, mark as `ActionTaken::Conflicted`.

**Base content caching**:
```
.agents/.mars/cache/bases/
  sha256_abc123...    # content of a file as installed by mars
```
Content-addressed by installed checksum. Written after every install/overwrite. Read before every merge. If missing (first sync, cache corruption), warn and treat as empty base (produces more conflict markers but doesn't fail).

## Dependencies

- Requires: ALL prior phases (0, 1a, 1b, 2a, 2b, 3)
- Produces: `sync()` function — the core library entry point consumed by CLI (Phase 5)
- This is the integration phase — it proves all modules work together.

## Interface Contract

- `cli/sync.rs` calls `sync::sync(ctx)` → gets `SyncReport`
- `cli/add.rs` calls config manipulation then `sync::sync(ctx)`
- `cli/remove.rs` calls config manipulation then `sync::sync(ctx)`

## Verification Criteria

### Target state tests:
- [ ] Single source, no filter → all discovered items in target
- [ ] Source with `agents: ["coder"]` → only coder agent + its skill deps
- [ ] Source with `exclude: ["agents/deprecated"]` → everything except excluded
- [ ] Rename mapping applied → dest_path reflects rename
- [ ] Two sources with same item → auto-rename with `{name}__{owner}_{repo}`
- [ ] Collision with user-authored file → error (not warning)

### Diff tests:
- [ ] New item (in target, not in lock) → Add
- [ ] Unchanged item (same hashes) → Unchanged
- [ ] Source changed, local unchanged → Update
- [ ] Local changed, source unchanged → LocalModified
- [ ] Both changed → Conflict
- [ ] Orphan (in lock, not in target) → Orphan

### Plan tests:
- [ ] Add → Install action
- [ ] Update → Overwrite action
- [ ] Conflict → Merge action
- [ ] Conflict + --force → Overwrite action (not Merge)
- [ ] Orphan → Remove action
- [ ] Unchanged → Skip action

### Apply tests (integration, needs temp dirs):
- [ ] Install: new file appears at dest_path with correct content
- [ ] Install: skill directory (not just file) installed correctly
- [ ] Overwrite: existing file replaced with new content
- [ ] Merge (clean): auto-merged content written, no conflict markers
- [ ] Merge (conflict): content with conflict markers written
- [ ] Remove: file/dir deleted from disk
- [ ] Base content cached after install for future merges
- [ ] Lock file written atomically after all actions succeed
- [ ] Dry run (--diff): plan computed, no files changed

### Integration test (full pipeline):
- [ ] Fresh sync: empty .agents/ + config with two sources → all items installed, lock written
- [ ] Re-sync with no changes → no files modified, same lock
- [ ] Source update (new version) → changed items updated, others untouched
- [ ] Local modification + source unchanged → local kept
- [ ] Local modification + source changed → merge attempted
- [ ] Source removed from config → orphaned items pruned
- [ ] --force → local modifications overwritten

- [ ] `cargo clippy -- -D warnings` passes

## Constraints

- If any apply action fails, abort and do NOT write the lock. Partial state is acceptable (atomic writes mean individual files are consistent), but the lock must reflect what actually happened.
- Base content cache (`.mars/cache/bases/`) is best-effort. Missing cache = degrade to two-way diff, not crash.
- Dry run must produce the exact same plan as a real run — same diff, same actions, just not executed.
- Auto-rename format: `{name}__{owner}_{repo}` — name first for autocomplete grouping.
- Frontmatter rewriting for transitive dep collisions: only modify the `skills:` line in YAML frontmatter. Do not touch any other content.

## Risk

This is the highest-risk phase:
1. **Integration complexity**: first time all modules interact. Expect interface mismatches.
2. **Base content caching**: new requirement not fully specified in design docs. Decision documented here: content-addressed cache in `.mars/cache/bases/`.
3. **Frontmatter rewriting**: parsing YAML, modifying one field, serializing back. Edge cases: multi-line skills lists, comments in frontmatter, single vs double quotes.

Mitigations:
- Build each sub-module (`target.rs`, `diff.rs`, `plan.rs`, `apply.rs`) incrementally with unit tests before wiring up `sync()`.
- Test the full pipeline with a fixture that covers all 4 merge cases.
- Frontmatter rewriting: use regex to find and replace the `skills:` line rather than full YAML parse+serialize (which loses comments and formatting).
