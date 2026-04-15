# Decision Log — Phase 3: A2 First-Class LocalPackage

## D1: Symlink items must be source-authoritative in diff/plan

**What:** For items with `Materialization::Symlink`, the diff/plan pipeline must never generate Merge, Overwrite, or KeepLocal. These actions would destroy the symlink by writing a regular file.

**Why:** Symlinked items point to the local source file — "source changed" and "local changed" refer to the same file. The standard diff logic sees both as changed → Conflict, but this is a false conflict. The source IS the local file.

**Fix approach:** In `plan.rs`, when processing Conflict/LocalModified/Unchanged for symlink items:
- Conflict/LocalModified → generate `PlannedAction::Symlink` (re-point the symlink)
- Unchanged → check if current lock entry has a different source than `_self`. If so, generate Symlink (ownership changed). If same, Skip.
- Also handle `--force` for these: always Symlink.

**Alternatives rejected:** Modifying diff.rs to produce different DiffEntry variants for symlink items. This would be more invasive and push symlink knowledge into the diff layer. Better to keep diff generic and handle materialization in plan creation.

## D2: atomic_symlink must handle existing directories

**What:** `reconcile::fs_ops::atomic_symlink` uses `rename(2)` which can't replace a directory. When a local package skill shadows a dependency skill, the existing skill directory must be removed first.

**Fix:** Remove existing directory before the atomic rename.

## D3: Reverse ownership handoff (dep→local→dep) deferred

**What:** When `[package]` is removed and a dependency provides the same content at the same dest, the diff sees Unchanged → old `_self` lock entry preserved. The lock has wrong provenance.

**Why deferred:** This is a very rare edge case (remove package declaration AND dependency provides identical content). Behavioral impact is minimal — the item works correctly, just has wrong source in the lock. The next content change fixes it automatically. Fixing it properly requires making the diff or plan aware of ownership changes for Copy-materialized items, which is invasive for minimal gain.

## D4: Non-atomic directory replacement in atomic_symlink is acceptable

**What:** Reviewer noted that removing a directory before rename creates a non-atomic window. If rename fails after dir removal, the destination is lost.

**Why accepted:** Mars follows crash-only design — "Recovery IS startup." If the operation fails mid-way, the next `mars sync` detects the missing item and recreates it. The alternative (rename-to-.old pattern from atomic_copy_dir) adds complexity for a very rare error case in a crash-recoverable system.
