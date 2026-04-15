# Phase 4: Skill Conflict Overwrite Policy

## Task

In /home/jimyao/gitrepos/mars-agents/, modify the sync planner to handle skill conflicts differently from agent conflicts.

### 1. Planner change in src/sync/plan.rs

In the `DiffEntry::Conflict` match arm, branch on `ItemKind::Skill`:

```rust
DiffEntry::Conflict { target, locked, local_hash: _ } => {
    if options.force || target.id.kind == ItemKind::Skill {
        // --force or skill conflict: source wins (overwrite)
        actions.push(PlannedAction::Overwrite { target: target.clone() });
        
        // If skill conflict (not --force), emit warning via diagnostics
        if target.id.kind == ItemKind::Skill && !options.force {
            // Warning needs to go through DiagnosticCollector
        }
    } else {
        // Agent conflict: three-way merge (existing logic)
        // ... existing merge path ...
    }
}
```

### 2. Warning emission via DiagnosticCollector

Thread `&mut DiagnosticCollector` into `plan::create()`. The function signature needs to accept `diag`. The planner emits:

```
diag.warn("skill-conflict-overwrite", format!(
    "skill `{}` has local modifications — overwriting with upstream (directory contents will be replaced)",
    target.id.name
));
```

In `sync/mod.rs`, the `create_plan` phase function already receives `diag: &mut DiagnosticCollector` — thread it through to `plan::create()`.

### 3. Keep existing behavior unchanged for

- Agent conflicts still merge (unless --force)
- LocalModified keeps local for both kinds (unless --force)
- --force overrides everything to overwrite (existing behavior)

## Files to Touch

- /home/jimyao/gitrepos/mars-agents/src/sync/plan.rs
- /home/jimyao/gitrepos/mars-agents/src/sync/mod.rs (thread diag into plan::create)

## Verification

Run from /home/jimyao/gitrepos/mars-agents/:
```bash
cargo build && cargo test && cargo clippy && cargo fmt --check
```

## EARS Claims: SKILL-01, SKILL-02, SKILL-03, SKILL-04

## Key Constraint

Do NOT modify sync/apply.rs — that's Phase 5 territory for checksum changes.
