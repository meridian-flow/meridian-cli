# Architecture: Skill Directory Conflict Handling (R4)

## Problem

`sync/plan.rs` plans `PlannedAction::Merge` for all copy-materialized conflicts without checking `ItemKind`. For agents (single `.md` files), three-way merge works. For skills (directories), `apply.rs` reads `SKILL.md` as the merge target, but the merge result is written as a single file to the dest path — this overwrites the directory with a file, losing `resources/` and any other skill files.

## Solution

Branch on `ItemKind` in the conflict arm of `sync/plan.rs::create()`. Skills get `PlannedAction::Overwrite` (source wins); agents keep existing merge logic.

### Change in `sync/plan.rs`

```rust
// In DiffEntry::Conflict match, after R3 removes symlink branches:
DiffEntry::Conflict { target, locked, local_hash: _ } => {
    if options.force || target.id.kind == ItemKind::Skill {
        // --force or skill conflict: source wins
        actions.push(PlannedAction::Overwrite {
            target: target.clone(),
        });
    } else {
        // Agent conflict: three-way merge
        let base_path = cache_bases_dir.join(locked.installed_checksum.as_ref());
        let base_content = std::fs::read(&base_path).unwrap_or_default();
        let local_path = locked.dest_path.as_path().to_path_buf();
        actions.push(PlannedAction::Merge {
            target: target.clone(),
            base_content,
            local_path,
        });
    }
}
```

### Warning Emission

The overwrite-on-skill-conflict should produce a user-visible warning. Two options:

**Option A:** Add a `reason` or `warning` field to `PlannedAction::Overwrite` — rejected, clutters the enum for a single case.

**Option B (chosen):** Add a diagnostic in `sync/apply.rs::execute_action` for the Overwrite case when the target is a skill and there was a conflict. This requires threading a `DiagnosticCollector` through `execute_action`, or using a simpler approach: log the warning via `eprintln!` in the apply phase. Given that the sync pipeline already uses `DiagnosticCollector`, the cleaner path is to collect diagnostics in apply and return them alongside `ApplyResult`.

**Simplest approach:** Since `ApplyResult` already has `ActionOutcome` entries, and the planner chose Overwrite for skills, the CLI output layer can detect "Overwrite for a Skill that was previously a Conflict" by comparing the diff with the plan. But this is complex. Instead, just emit to stderr in the planner — the planner already has the diff context to know this was a conflict that became an overwrite.

**Final decision (revised per review):** Pass `&mut DiagnosticCollector` into `plan::create()`. The planner emits the warning directly via `diag.warn()` when a skill conflict is resolved by overwrite. This uses the existing diagnostic infrastructure without adding a second warning channel to `SyncPlan`. The `create_plan` phase function in `sync/mod.rs` already receives `diag: &mut DiagnosticCollector` — just thread it through to `plan::create()`.

The warning message should be explicit about data loss: "skill `{name}` has local modifications — overwriting with upstream (directory contents will be replaced)".

### LocalModified Branch

The `DiffEntry::LocalModified` arm has the same issue — if `--force` is set, it overwrites (fine for both kinds). If not forced, it keeps local (`PlannedAction::KeepLocal`). This is correct for skills too — if only the local skill changed and source didn't, keeping local is right. No change needed here.

## Files Changed

| File | Change |
|---|---|
| `src/sync/plan.rs` | Branch on `ItemKind::Skill` in Conflict arm, add warnings to `SyncPlan` |
| `src/sync/mod.rs` | Drain plan warnings into `DiagnosticCollector` |
