# Phase 7: B3 — .mars/ Canonical Store + Managed Targets

**Round:** 3 (parallel with Phase 6)
**Depends on:** Phase 1 (A1 — pipeline phases), Phase 4 (A4 — reconciliation), Phase 5 (A5 — diagnostics)
**Risk:** High — architectural pivot, changes the fundamental write path
**Estimated delta:** ~+500 LOC (target sync, config, migration), ~-50 LOC (simplified apply path)
**Codebase:** `/home/jimyao/gitrepos/mars-agents/`

## Scope

Make `.mars/` the canonical content store. All target directories (`.agents/`, `.claude/`, `.cursor/`) become managed outputs materialized via copy from `.mars/`. The pipeline's `apply_plan()` writes to `.mars/`, and a new `sync_managed_targets()` phase copies to all configured targets.

## Why This Matters

This is the architectural pivot that enables per-target content control. Currently `.agents/` is both source of truth and what harnesses read. With `.mars/` as canonical store, each target can get different content (variants in B2, per-harness rules in B1). Even without variants shipping in this refactor, the plumbing must be right.

## Files to Create

| File | Contents |
|------|----------|
| `src/target_sync/mod.rs` | `ManagedTarget` struct, `AdapterKind` enum, `sync_managed_targets()` phase function, `sync_target_content()` per-target logic, orphan cleanup. |

## Files to Modify

| File | Changes |
|------|---------|
| `src/lib.rs` | Add `pub mod target_sync;` |
| `src/config/mod.rs` | Add `targets: Option<Vec<String>>` to `Settings`. Add `links` → `targets` migration/equivalence. Add `managed_targets()` method that returns the effective target list (defaults to `[".agents"]` when unset). |
| `src/sync/mod.rs` | Add `SyncedState` struct. Insert `sync_managed_targets()` call between `apply_plan()` and `finalize()`. Update `finalize()` to accept `SyncedState`. Add `target_outcomes: Vec<TargetSyncOutcome>` to `SyncReport`. |
| `src/sync/apply.rs` | Change write destination from managed_root (`.agents/`) to `.mars/` content directory. The apply logic is otherwise unchanged — items are written to `.mars/agents/`, `.mars/skills/` instead of `.agents/agents/`, `.agents/skills/`. |
| `src/lock/mod.rs` | Lock is written after apply regardless of target sync outcome (D21). No lock format changes. |
| `src/types.rs` | Add `MarsContext.mars_dir` field (path to `.mars/`). Or derive from `project_root`. |
| `src/cli/sync.rs` | Display per-target sync outcomes in human and JSON output. |
| `src/cli/doctor.rs` (or equivalent) | Add `.mars/` gitignore check — warn if `.mars/` is not in `.gitignore` (D29). |
| `src/link.rs` | Update link behavior: linking a directory now means adding it as a managed target. The existing `mars link .claude` becomes equivalent to adding `.claude` to `settings.targets`. |

## Interface Contract — ManagedTarget

```rust
/// A directory that mars manages — materialized from .mars/.
pub struct ManagedTarget {
    /// Target directory path relative to project root (e.g. ".claude", ".agents").
    pub path: String,
    /// Harness identifier for future variant resolution (e.g. "claude", "agents").
    pub harness_id: String,
    /// Which adapter handles this target (for future capability cross-compilation).
    pub adapter: AdapterKind,
}

pub enum AdapterKind {
    Claude,
    Cursor,
    Codex,
    Generic,
}

impl AdapterKind {
    pub fn from_target(path: &str) -> Self {
        match path.trim_start_matches('.') {
            "claude" => Self::Claude,
            "cursor" => Self::Cursor,
            "codex" => Self::Codex,
            _ => Self::Generic,
        }
    }
}
```

## Interface Contract — Target Sync Phase

```rust
/// Phase 6 (new): All managed targets synced from .mars/.
pub struct SyncedState {
    pub applied: AppliedState,
    pub target_outcomes: Vec<TargetSyncOutcome>,
}

pub struct TargetSyncOutcome {
    pub target: String,           // e.g. ".claude"
    pub items_synced: usize,
    pub items_removed: usize,
    pub errors: Vec<String>,
}

/// Sync all managed targets from .mars/ canonical store.
pub fn sync_managed_targets(
    ctx: &MarsContext,
    applied: AppliedState,
    request: &SyncRequest,
    diag: &mut DiagnosticCollector,
) -> Result<SyncedState, MarsError>;
```

## Target Sync Algorithm

For each managed target:

1. **Enumerate items** from `.mars/` that should exist in this target (for now, all items — kind filtering comes with B1).
2. **For each item**: use `reconcile::reconcile_one()` to copy from `.mars/` to target, following symlinks (local package items are symlinks in `.mars/`).
3. **Orphan cleanup**: scan target for files/dirs not in the expected set, remove them.
4. **Record outcome** per target.

```rust
fn sync_one_target(
    mars_dir: &Path,
    target: &ManagedTarget,
    items: &[ActionOutcome],  // from apply phase
    project_root: &Path,
    diag: &mut DiagnosticCollector,
) -> Result<TargetSyncOutcome, MarsError> {
    let target_root = project_root.join(&target.path);
    let content_root = mars_dir; // .mars/agents/, .mars/skills/
    
    for outcome in items {
        if outcome.action == ActionTaken::Removed {
            // Remove from target too
            reconcile::fs_ops::safe_remove(&target_root.join(&outcome.dest_path))?;
        } else {
            // Copy from .mars/ to target (follows symlinks)
            let source = content_root.join(&outcome.dest_path);
            let dest = target_root.join(&outcome.dest_path);
            reconcile::reconcile_one(&dest, DesiredState::CopyFile { source, ... }, false)?;
        }
    }
    
    // Orphan cleanup
    // ...
}
```

## Configuration

```toml
[settings]
# New field — managed targets
targets = [".claude", ".codex"]

# Backwards compat — old links syntax is equivalent
# links = [".claude"]  →  targets = [".agents", ".claude"]
```

When `targets` is omitted: `.agents/` is the sole target (D30 — backwards compatibility).
When `targets` is specified: only listed targets. To include `.agents/`, list it explicitly.

## .mars/ Directory Layout

```
.mars/
  agents/         # resolved agent profiles
  skills/         # resolved skills
  cache/
    bases/        # merge base cache (existing, moved from .mars/cache/bases)
  models-cache.json  # from Phase 6 (B4)
```

Note: content lives directly under `.mars/` (`.mars/agents/`, `.mars/skills/`), NOT under `.mars/content/`. The design doc mentions `.mars/content/` in some places — for this implementation, flatten to `.mars/agents/` and `.mars/skills/` directly. Simpler paths, less nesting.

## Migration Path

1. **First run after upgrade:** `apply_plan()` now writes to `.mars/` instead of `.agents/`. The `sync_managed_targets()` phase copies to `.agents/` (default target). Net result: `.agents/` has the same content as before, plus `.mars/` exists.
2. **Existing `.agents/` content:** On first run, `.agents/` may have content from the old pipeline. Target sync overwrites it with copies from `.mars/`. This is safe because the content is identical.
3. **Existing `links`:** Recognized as equivalent to `targets`. `links = [".claude"]` → targets `.agents/` and `.claude/`.

## Failure Semantics

- **Target sync is non-fatal by default** (D9). Content in `.mars/` is correct. Lock is written regardless (D21).
- **Each item copy is atomic** (tmp+rename via reconcile layer). A crash mid-target-sync leaves `.mars/` correct and targets partially updated.
- **Re-running `mars sync` converges:** content diffs as unchanged (lock matches `.mars/`), targets get re-synced.

## Constraints

- **D25:** `.mars/` is canonical. All targets are derived.
- **D26:** Copy, not symlink for target materialization. Always follow symlinks when reading from `.mars/`.
- **D29:** Mars does NOT auto-edit `.gitignore`. `mars doctor` warns.
- **D30:** `.agents/` is default target when `targets` unset.
- **D21:** Lock written regardless of target sync outcome.
- **Use reconciliation layer** (Phase 4) for all filesystem operations.
- **Use structured diagnostics** (Phase 5) for target sync warnings.

## Verification Criteria

- [ ] `cargo build` compiles cleanly
- [ ] `cargo test` — all existing tests pass
- [ ] `cargo clippy` — no new warnings
- [ ] After `mars sync`: `.mars/agents/` and `.mars/skills/` contain resolved content
- [ ] After `mars sync`: `.agents/` contains copies of `.mars/` content (default target)
- [ ] With `targets = [".claude"]`: `.claude/` is populated, `.agents/` is NOT (unless listed)
- [ ] With no `targets` config: `.agents/` is populated (backwards compat)
- [ ] `links = [".claude"]` works same as `targets = [".agents", ".claude"]`
- [ ] Lock is written even if target sync for one target fails
- [ ] Local package items (symlinks in `.mars/`) are followed — targets get file copies, not symlinks
- [ ] `mars doctor` warns if `.mars/` is not gitignored

## Agent Staffing

- **Coder:** 1x gpt-5.3-codex
- **Reviewers:** 3x — correctness (migration path, orphan cleanup, lock write timing), design alignment (verify D21/D25/D26/D29/D30), security (ensure target sync doesn't write outside target directories)
- **Tester:** 1x smoke-tester — test migration from old layout, multi-target sync, backwards compat with no targets config
